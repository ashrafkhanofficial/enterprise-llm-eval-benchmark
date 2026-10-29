#!/usr/bin/env python3
"""
scripts/validate_schema.py — Programmatic Schema & Negative Constraint Validator

Performs Layer A automated, deterministic assertions on raw LLM outputs for
SCHEMA-01 through SCHEMA-08. Requires zero human intervention.

Checks:
- Strict JSON syntax and structure
- Required keys and nested hierarchy
- Unintended markdown code fences (```json or ```)
- Conversational preamble/postamble leakage
- Negative constraints (banned tokens, banned SQL clauses)
- Length/word count boundary clamps
- TSV formatting compliance
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RAW_RESPONSES = ROOT_DIR / "data" / "raw_responses.json"
DEFAULT_TEST_SUITE = ROOT_DIR / "data" / "test_suite.json"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "schema_validation_results.json"

# Standard Error Codes (SOP-LLM-EVAL-001)
ERR_SCHEMA_INVALID_JSON = "ERR_SCHEMA_INVALID_JSON"
ERR_SCHEMA_MISSING_KEY = "ERR_SCHEMA_MISSING_KEY"
ERR_PREAMBLE_LEAK = "ERR_PREAMBLE_LEAK"
ERR_BANNED_TOKEN_VIOLATION = "ERR_BANNED_TOKEN_VIOLATION"


# ---------------------------------------------------------------------------
# Core Assertion Helpers
# ---------------------------------------------------------------------------
def has_markdown_fences(text: str) -> bool:
    """Detects presence of triple-backtick markdown fences."""
    return "```" in text


def check_preamble_postamble(text: str) -> Tuple[bool, str]:
    """Detects common conversational preamble or postamble wrappers."""
    stripped = text.strip()
    patterns = [
        r"^(here is|here's|sure|certainly|below is|i have|as requested)",
        r"(let me know|hope this helps|feel free to|if you have any questions)\.?$",
    ]
    for pat in patterns:
        if re.search(pat, stripped, re.IGNORECASE):
            return True, f"Matched preamble/postamble pattern: {pat}"
    return False, ""


def extract_json_strict(text: str) -> Tuple[bool, Any, List[str]]:
    """Strictly checks if text is valid raw JSON without markdown fences."""
    errors = []
    if has_markdown_fences(text):
        errors.append(ERR_PREAMBLE_LEAK)

    cleaned = text.strip()
    # Strip fences if present just to test underlying JSON validity
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        return True, parsed, errors
    except Exception:
        errors.append(ERR_SCHEMA_INVALID_JSON)
        return False, None, errors


# ---------------------------------------------------------------------------
# Per-Prompt Specific Deterministic Checkers
# ---------------------------------------------------------------------------
def validate_schema_01(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-01: Strict Raw JSON Incident Ticket Extraction"""
    errors = []
    details = []

    if has_markdown_fences(raw_output):
        errors.append(ERR_PREAMBLE_LEAK)
        details.append("Detected markdown code fences (```).")

    is_json, data, json_errs = extract_json_strict(raw_output)
    if not is_json or not isinstance(data, dict):
        if ERR_SCHEMA_INVALID_JSON not in errors:
            errors.append(ERR_SCHEMA_INVALID_JSON)
        details.append("Failed strict JSON parsing.")
    else:
        expected_keys = {"service", "severity", "impacted_tenants", "root_cause"}
        actual_keys = set(data.keys())
        missing = expected_keys - actual_keys
        if missing:
            errors.append(ERR_SCHEMA_MISSING_KEY)
            details.append(f"Missing required keys: {sorted(list(missing))}")

        if not isinstance(data.get("impacted_tenants"), int):
            errors.append(ERR_SCHEMA_INVALID_JSON)
            details.append(f"'impacted_tenants' must be an integer, got: {type(data.get('impacted_tenants')).__name__}")

    preamble_detected, reason = check_preamble_postamble(raw_output)
    if preamble_detected and ERR_PREAMBLE_LEAK not in errors:
        errors.append(ERR_PREAMBLE_LEAK)
        details.append(reason)

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": sorted(list(set(errors))),
        "details": details or ["All strict schema assertions passed."],
    }


def validate_schema_02(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-02: Customer Rejection Letter with Banned Words"""
    errors = []
    details = []

    banned_patterns = [
        (r"\bregret[s]?\b", "regret"),
        (r"\bunfortunately\b", "unfortunately"),
        (r"\bsorry\b", "sorry"),
        (r"\bapologiz(e|es|ed|ing)\b", "apologize"),
        (r"\bapolog(y|ies)\b", "apology"),
        (r"\bcannot\b", "cannot"),
        (r"\bcan\s+not\b", "can not"),
    ]

    found_banned = []
    for pat, label in banned_patterns:
        if re.search(pat, raw_output, re.IGNORECASE):
            found_banned.append(label)

    if found_banned:
        errors.append(ERR_BANNED_TOKEN_VIOLATION)
        details.append(f"Found banned words/stems: {', '.join(sorted(list(set(found_banned))))}")

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": errors,
        "banned_tokens_found": sorted(list(set(found_banned))),
        "details": details or ["Zero banned tokens detected."],
    }


def validate_schema_03(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-03: Nested Telemetry Alert Configuration Payload"""
    errors = []
    details = []

    if has_markdown_fences(raw_output):
        errors.append(ERR_PREAMBLE_LEAK)
        details.append("Detected markdown code fences (```).")

    is_json, data, _ = extract_json_strict(raw_output)
    if not is_json or not isinstance(data, dict):
        if ERR_SCHEMA_INVALID_JSON not in errors:
            errors.append(ERR_SCHEMA_INVALID_JSON)
        details.append("Failed JSON parsing.")
    else:
        # Check required top-level keys
        if "alert_definition" not in data or "enabled" not in data:
            errors.append(ERR_SCHEMA_MISSING_KEY)
            details.append("Missing top-level 'alert_definition' or 'enabled'.")
        else:
            adef = data.get("alert_definition", {})
            if not isinstance(adef, dict):
                errors.append(ERR_SCHEMA_INVALID_JSON)
                details.append("'alert_definition' must be a nested JSON object.")
            else:
                for k in ["name", "target", "thresholds", "notifications"]:
                    if k not in adef:
                        errors.append(ERR_SCHEMA_MISSING_KEY)
                        details.append(f"Missing key in alert_definition: {k}")

                thresh = adef.get("thresholds", {})
                if isinstance(thresh, dict):
                    w = thresh.get("warning_percent")
                    c = thresh.get("critical_percent")
                    if not isinstance(w, int) or not isinstance(c, int):
                        errors.append(ERR_SCHEMA_INVALID_JSON)
                        details.append("Thresholds must be integers.")

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": sorted(list(set(errors))),
        "details": details or ["All nested schema assertions passed."],
    }


def validate_schema_04(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-04: Strict Word-Count Clamped Executive Summary (25 to 35 words)"""
    errors = []
    details = []

    clean_text = raw_output.strip()
    words = clean_text.split()
    word_count = len(words)

    if word_count < 25 or word_count > 35:
        errors.append(ERR_BANNED_TOKEN_VIOLATION)
        details.append(f"Word count violation: expected [25, 35], got {word_count} words.")

    # Check for disallowed formatting like bullet points or title headers
    if any(line.strip().startswith(("-", "*", "#")) for line in clean_text.split("\n")):
        errors.append(ERR_PREAMBLE_LEAK)
        details.append("Disallowed headings or bullet points detected.")

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": sorted(list(set(errors))),
        "word_count": word_count,
        "details": details or [f"Word count exactly compliant: {word_count} words."],
    }


def validate_schema_05(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-05: Raw TSV Export with Zero Markdown Formatting"""
    errors = []
    details = []

    if has_markdown_fences(raw_output):
        errors.append(ERR_PREAMBLE_LEAK)
        details.append("Detected markdown code fences (```).")

    if "|" in raw_output or "---" in raw_output:
        errors.append(ERR_BANNED_TOKEN_VIOLATION)
        details.append("Detected markdown table pipe '|' or dash separators.")

    lines = [ln.strip() for ln in raw_output.strip().split("\n") if ln.strip()]
    if len(lines) < 4:
        errors.append(ERR_SCHEMA_INVALID_JSON)
        details.append(f"Expected at least 4 TSV lines (header + 3 records), got {len(lines)}.")

    tab_count = sum(line.count("\t") for line in lines)
    if tab_count < 9:  # At least 3 tabs per line across 3+ rows
        errors.append(ERR_SCHEMA_INVALID_JSON)
        details.append(f"Insufficient tab characters found ({tab_count}). Output is not raw TSV.")

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": sorted(list(set(errors))),
        "line_count": len(lines),
        "details": details or ["Valid raw TSV format without markdown table decorators."],
    }


def validate_schema_06(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-06: Structured Enum Array Classification"""
    errors = []
    details = []

    if has_markdown_fences(raw_output):
        errors.append(ERR_PREAMBLE_LEAK)
        details.append("Detected markdown code fences (```).")

    is_json, data, _ = extract_json_strict(raw_output)
    if not is_json or not isinstance(data, list):
        if ERR_SCHEMA_INVALID_JSON not in errors:
            errors.append(ERR_SCHEMA_INVALID_JSON)
        details.append("Output must be a valid JSON array.")
    else:
        if len(data) != 3:
            errors.append(ERR_SCHEMA_INVALID_JSON)
            details.append(f"Expected array of exactly 3 items, got {len(data)}.")

        allowed_sentiments = {"POSITIVE", "NEUTRAL", "NEGATIVE", "FRUSTRATED"}
        allowed_categories = {"BILLING", "PERFORMANCE", "FEATURE_REQUEST", "BUG"}

        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                errors.append(ERR_SCHEMA_INVALID_JSON)
                details.append(f"Array item {idx} is not an object.")
                continue
            s = item.get("sentiment")
            c = item.get("category")
            if s not in allowed_sentiments:
                errors.append(ERR_SCHEMA_INVALID_JSON)
                details.append(f"Invalid sentiment enum at index {idx}: '{s}'")
            if c not in allowed_categories:
                errors.append(ERR_SCHEMA_INVALID_JSON)
                details.append(f"Invalid category enum at index {idx}: '{c}'")

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": sorted(list(set(errors))),
        "details": details or ["JSON array and all enum constraints passed."],
    }


def validate_schema_07(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-07: Read-Only Postgres Query with Negative Syntax Restrictions"""
    errors = []
    details = []

    if has_markdown_fences(raw_output):
        errors.append(ERR_PREAMBLE_LEAK)
        details.append("Detected markdown code fences (```).")

    banned_checks = [
        (r"\bjoin\b", "JOIN", ERR_BANNED_TOKEN_VIOLATION),
        (r"\bwith\b", "WITH (CTE)", ERR_BANNED_TOKEN_VIOLATION),
        (r"select\s+\*", "SELECT *", ERR_BANNED_TOKEN_VIOLATION),
        (r"--|\/\*", "SQL Comments", ERR_PREAMBLE_LEAK),
    ]

    for pat, label, err_code in banned_checks:
        if re.search(pat, raw_output, re.IGNORECASE):
            if err_code not in errors:
                errors.append(err_code)
            details.append(f"Negative constraint violated: contained '{label}'.")

    preamble_detected, reason = check_preamble_postamble(raw_output)
    if preamble_detected and ERR_PREAMBLE_LEAK not in errors:
        errors.append(ERR_PREAMBLE_LEAK)
        details.append(reason)

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": sorted(list(set(errors))),
        "details": details or ["All negative SQL syntax constraints satisfied."],
    }


def validate_schema_08(raw_output: str) -> Dict[str, Any]:
    """SCHEMA-08: Multi-Key Localization Payload"""
    errors = []
    details = []

    if has_markdown_fences(raw_output):
        errors.append(ERR_PREAMBLE_LEAK)
        details.append("Detected markdown code fences (```).")

    is_json, data, _ = extract_json_strict(raw_output)
    if not is_json or not isinstance(data, dict):
        if ERR_SCHEMA_INVALID_JSON not in errors:
            errors.append(ERR_SCHEMA_INVALID_JSON)
        details.append("Failed JSON parsing.")
    else:
        for k in ["error_code", "translations", "action_url"]:
            if k not in data:
                errors.append(ERR_SCHEMA_MISSING_KEY)
                details.append(f"Missing required key: '{k}'")

        translations = data.get("translations", {})
        if not isinstance(translations, dict):
            errors.append(ERR_SCHEMA_INVALID_JSON)
            details.append("'translations' must be a nested JSON object.")
        else:
            for lang in ["en", "de", "ja"]:
                if lang not in translations or not translations[lang]:
                    errors.append(ERR_SCHEMA_MISSING_KEY)
                    details.append(f"Missing translation for language '{lang}'.")

    return {
        "overall_pass": len(errors) == 0,
        "error_codes": sorted(list(set(errors))),
        "details": details or ["Localization schema and all language keys valid."],
    }


# Dispatch map
SCHEMA_VALIDATORS = {
    "SCHEMA-01": validate_schema_01,
    "SCHEMA-02": validate_schema_02,
    "SCHEMA-03": validate_schema_03,
    "SCHEMA-04": validate_schema_04,
    "SCHEMA-05": validate_schema_05,
    "SCHEMA-06": validate_schema_06,
    "SCHEMA-07": validate_schema_07,
    "SCHEMA-08": validate_schema_08,
}


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------
def run_schema_validation(
    raw_responses_path: Path = DEFAULT_RAW_RESPONSES,
    output_path: Path = DEFAULT_OUTPUT,
) -> None:
    console.print(Panel.fit(
        "[bold cyan]Enterprise LLM Evaluation Benchmark — Programmatic Schema Validator[/bold cyan]\n"
        "Layer A Automated Assertion Engine for SCHEMA-01 through SCHEMA-08\n"
        f"Input: [bold white]{raw_responses_path.name}[/bold white] | Output: [bold white]{output_path.name}[/bold white]",
        border_style="cyan"
    ))

    if not raw_responses_path.exists():
        console.print(f"[red]Error:[/red] Raw responses file not found at {raw_responses_path}")
        sys.exit(1)

    with open(raw_responses_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    responses = data.get("responses", [])
    schema_responses = [r for r in responses if r.get("prompt_id", "").startswith("SCHEMA-")]

    if not schema_responses:
        console.print("[red]Error:[/red] No SCHEMA-* prompts found in responses file.")
        sys.exit(1)

    results: List[Dict[str, Any]] = []

    model_a_passes = 0
    model_b_passes = 0

    table = Table(title="Layer A: Programmatic Schema Validation Results")
    table.add_column("Prompt ID", style="cyan", no_wrap=True)
    table.add_column("Challenge Title", style="white")
    table.add_column("Model A (Gemini)", style="green")
    table.add_column("Model B (Groq / Qwen)", style="blue")

    for item in schema_responses:
        pid = item.get("prompt_id")
        title = item.get("title", "")
        validator_fn = SCHEMA_VALIDATORS.get(pid)

        if not validator_fn:
            continue

        output_a = item.get("model_a_response", {}).get("raw_output", "")
        output_b = item.get("model_b_response", {}).get("raw_output", "")

        res_a = validator_fn(output_a)
        res_b = validator_fn(output_b)

        if res_a["overall_pass"]:
            model_a_passes += 1
        if res_b["overall_pass"]:
            model_b_passes += 1

        results.append({
            "prompt_id": pid,
            "title": title,
            "model_a_programmatic": res_a,
            "model_b_programmatic": res_b,
        })

        badge_a = "[bold green]PASS[/bold green]" if res_a["overall_pass"] else f"[bold red]FAIL[/bold red] ({', '.join(res_a['error_codes'])})"
        badge_b = "[bold green]PASS[/bold green]" if res_b["overall_pass"] else f"[bold red]FAIL[/bold red] ({', '.join(res_b['error_codes'])})"

        table.add_row(pid, title, badge_a, badge_b)

    console.print(table)

    summary_panel = (
        f"[bold]Validation Compliance Summary (8 Prompts):[/bold]\n"
        f"• Model A (Google AI Studio): [bold green]{model_a_passes}/8 Passed[/bold green] ({round(model_a_passes/8*100, 1)}%)\n"
        f"• Model B (Groq Cloud):       [bold green]{model_b_passes}/8 Passed[/bold green] ({round(model_b_passes/8*100, 1)}%)"
    )
    console.print(Panel(summary_panel, border_style="cyan"))

    output_payload = {
        "metadata": {
            "validation_type": "programmatic_layer_a",
            "total_schema_prompts": len(results),
            "model_a_pass_rate": round(model_a_passes / len(results), 4) if results else 0,
            "model_b_pass_rate": round(model_b_passes / len(results), 4) if results else 0,
        },
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    console.print(f"[bold green]Success:[/bold green] Programmatic validation results saved to [bold underline]{output_path}[/bold underline]\n")


def main():
    parser = argparse.ArgumentParser(description="Run programmatic schema validation assertions.")
    parser.add_argument("--raw-responses", type=Path, default=DEFAULT_RAW_RESPONSES, help="Path to raw_responses.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to output schema_validation_results.json")
    args = parser.parse_args()

    run_schema_validation(
        raw_responses_path=args.raw_responses,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
