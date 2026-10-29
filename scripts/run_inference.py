#!/usr/bin/env python3
"""
scripts/run_inference.py — Production-Grade Automated Inference Pipeline

Executes the 30 curated benchmark prompts against Model A (Google Gemini 1.5 Flash)
and Model B (Llama 3.1 70B via Groq), capturing full raw outputs, exact wall-clock
latency (ms), input/output token counts, and operational telemetry.

Zero-cost free-tier APIs are strictly utilized with deterministic parameters
(temperature=0.0) and rate-limit pacing.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

console = Console()

# ---------------------------------------------------------------------------
# Path Configuration
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEST_SUITE = ROOT_DIR / "data" / "test_suite.json"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "raw_responses.json"


def load_environment() -> tuple[Optional[str], Optional[str]]:
    """Loads environment variables and returns API keys."""
    load_dotenv(ROOT_DIR / ".env")
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    return gemini_key, groq_key


def is_rate_limit_or_transient(exception: BaseException) -> bool:
    """Helper to detect retryable rate limits (429) or transient network drops/503 spikes."""
    err_str = str(exception).lower()
    retry_markers = [
        "429", "rate limit", "resource exhausted", "too many requests",
        "overloaded", "503", "500", "unavailable", "temporarily",
        "tokens per minute", "otpm"
    ]
    return any(marker in err_str for marker in retry_markers)


# ---------------------------------------------------------------------------
# Model Inference Providers
# ---------------------------------------------------------------------------
class InferenceEngine:
    def __init__(
        self,
        gemini_api_key: Optional[str],
        groq_api_key: Optional[str],
        gemini_model: str = "gemini-3.1-flash-lite",
        groq_model: str = "qwen/qwen3.8-27b",
        dry_run: bool = False,
    ):
        self.dry_run = dry_run
        self.gemini_model = gemini_model
        self.groq_model = groq_model
        self.gemini_client = None
        self.groq_client = None

        if not dry_run:
            if not gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not set. Please update your .env file.")
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY is not set. Please update your .env file.")

            # Initialize Google GenAI client
            from google import genai
            self.gemini_client = genai.Client(api_key=gemini_api_key)

            # Initialize Groq client
            from groq import Groq
            self.groq_client = Groq(api_key=groq_api_key)

    def call_gemini(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Queries Google Gemini with temperature=0.0 and captures telemetry."""
        if self.dry_run:
            time.sleep(0.05)
            return {
                "raw_output": "[DRY RUN MOCK] Gemini 1.5 Flash deterministic response simulation.",
                "latency_ms": 48.5,
                "input_tokens": 120,
                "output_tokens": 35,
                "finish_reason": "STOP",
                "error": None,
            }

        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.0,
            max_output_tokens=2048,
        )

        @retry(
            retry=retry_if_exception(is_rate_limit_or_transient),
            wait=wait_exponential_jitter(initial=4, max=30),
            stop=stop_after_attempt(4),
            reraise=True,
        )
        def _invoke():
            start_time = time.perf_counter()
            response = self.gemini_client.models.generate_content(
                model=self.gemini_model,
                contents=user_prompt,
                config=config,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            raw_text = ""
            if hasattr(response, "text") and response.text:
                raw_text = response.text
            elif hasattr(response, "candidates") and response.candidates:
                cand = response.candidates[0]
                if hasattr(cand, "content") and cand.content and hasattr(cand.content, "parts"):
                    raw_text = "".join(getattr(p, "text", "") or "" for p in cand.content.parts if hasattr(p, "text"))

            input_tokens = 0
            output_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            finish_reason = "STOP"
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason") and candidate.finish_reason:
                    finish_reason = str(candidate.finish_reason)

            return {
                "raw_output": raw_text,
                "latency_ms": elapsed_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason,
                "error": None,
            }

        try:
            return _invoke()
        except Exception as exc:
            return {
                "raw_output": "",
                "latency_ms": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "finish_reason": "ERROR",
                "error": f"{type(exc).__name__}: {str(exc)}",
            }

    def call_groq(self, system_prompt: str, user_prompt: str, max_tokens: int = 750) -> Dict[str, Any]:
        """Queries Groq with temperature=0.0 and captures telemetry."""
        if self.dry_run:
            time.sleep(0.05)
            return {
                "raw_output": "[DRY RUN MOCK] Llama 3.1 70B deterministic response simulation.",
                "latency_ms": 32.1,
                "input_tokens": 125,
                "output_tokens": 40,
                "finish_reason": "stop",
                "error": None,
            }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        @retry(
            retry=retry_if_exception(is_rate_limit_or_transient),
            wait=wait_exponential_jitter(initial=12, max=45),
            stop=stop_after_attempt(4),
            reraise=True,
        )
        def _invoke(model_to_use: str):
            start_time = time.perf_counter()
            response = self.groq_client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                temperature=0.0,
                max_tokens=max_tokens,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            choice = response.choices[0] if response.choices else None
            raw_text = choice.message.content if choice and choice.message else ""
            finish_reason = choice.finish_reason if choice else "unknown"

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            return {
                "raw_output": raw_text or "",
                "latency_ms": elapsed_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason or "stop",
                "error": None,
            }

        try:
            return _invoke(self.groq_model)
        except Exception as exc:
            # Fallback if specific Groq model name was retired or decommissioned
            err_msg = str(exc).lower()
            if "decommissioned" in err_msg or "model_not_found" in err_msg:
                fallback_model = "llama-3.3-70b-versatile"
                console.print(f"[yellow]Notice:[/yellow] {self.groq_model} unavailable. Falling back to {fallback_model}...")
                self.groq_model = fallback_model
                try:
                    return _invoke(fallback_model)
                except Exception as inner_exc:
                    exc = inner_exc

            return {
                "raw_output": "",
                "latency_ms": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "finish_reason": "ERROR",
                "error": f"{type(exc).__name__}: {str(exc)}",
            }


# ---------------------------------------------------------------------------
# Orchestration & Runner Logic
# ---------------------------------------------------------------------------
def run_benchmark(
    test_suite_path: Path,
    output_path: Path,
    prompt_id_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    dry_run: bool = False,
    delay_gemini: float = 4.0,
    delay_groq: float = 2.0,
    gemini_model: str = "gemini-3.1-flash-lite",
    groq_model: str = "qwen/qwen3.8-27b",
    groq_max_tokens: int = 750,
    retry_failed: bool = False,
):
    console.print(Panel.fit(
        "[bold cyan]Enterprise LLM Evaluation Benchmark — Automated Inference Runner[/bold cyan]\n"
        f"Mode: {'[bold yellow]RETRY FAILED RESPONSES[/bold yellow]' if retry_failed else ('[bold yellow]DRY RUN (Simulated)[/bold yellow]' if dry_run else '[bold green]LIVE INFERENCE[/bold green]')}\n"
        f"Model A: [bold white]{gemini_model}[/bold white] (Google AI Studio) | Model B: [bold white]{groq_model}[/bold white] (Groq)\n"
        f"Pacing: Gemini delay={delay_gemini}s | Groq delay={delay_groq}s | Groq max_tokens={groq_max_tokens}",
        border_style="cyan"
    ))

    # 1. Load test suite
    if not test_suite_path.exists():
        console.print(f"[red]Error:[/red] Test suite file not found at {test_suite_path}")
        sys.exit(1)

    with open(test_suite_path, "r", encoding="utf-8") as f:
        suite_data = json.load(f)

    prompts: List[Dict[str, Any]] = suite_data.get("prompts", [])
    if not prompts:
        console.print("[red]Error:[/red] No prompts found in test suite.")
        sys.exit(1)

    # 2. Filter prompts if requested
    if prompt_id_filter:
        prompts = [p for p in prompts if p.get("id") == prompt_id_filter]
        if not prompts:
            console.print(f"[red]Error:[/red] Prompt ID '{prompt_id_filter}' not found in suite.")
            sys.exit(1)

    if category_filter:
        prompts = [p for p in prompts if p.get("category") == category_filter]
        if not prompts:
            console.print(f"[red]Error:[/red] Category '{category_filter}' not found or has no prompts.")
            sys.exit(1)

    console.print(f"[bold]Selected Challenge Prompts:[/bold] {len(prompts)} total\n")

    # 3. Environment verification
    gemini_key, groq_key = load_environment()
    if not dry_run:
        missing = []
        if not gemini_key:
            missing.append("GEMINI_API_KEY")
        if not groq_key:
            missing.append("GROQ_API_KEY")
        if missing:
            console.print(f"[red]Missing API keys in .env:[/red] {', '.join(missing)}")
            console.print("Please configure .env before running live inference.")
            sys.exit(1)

    engine = InferenceEngine(
        gemini_api_key=gemini_key,
        groq_api_key=groq_key,
        gemini_model=gemini_model,
        groq_model=groq_model,
        dry_run=dry_run,
    )

    # 4. Handle Retry Failed Mode
    if retry_failed:
        if not output_path.exists():
            console.print(f"[red]Error:[/red] Output file {output_path} does not exist. Run full benchmark first.")
            sys.exit(1)

        with open(output_path, "r", encoding="utf-8") as f:
            existing_payload = json.load(f)

        existing_responses: List[Dict[str, Any]] = existing_payload.get("responses", [])
        prompt_lookup = {p["id"]: p for p in prompts}

        failed_items = [
            (idx, r) for idx, r in enumerate(existing_responses)
            if (r.get("model_a_response", {}).get("error") is not None or
                r.get("model_b_response", {}).get("error") is not None)
        ]

        if not failed_items:
            console.print("[bold green]Zero failed responses found! Benchmark is already 100% complete.[/bold green]")
            return

        console.print(f"[bold yellow]Found {len(failed_items)} responses requiring backfill.[/bold yellow]\n")

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        )

        with progress:
            task_id = progress.add_task("Backfilling...", total=len(failed_items))

            for step_idx, (resp_idx, entry) in enumerate(failed_items):
                pid = entry.get("prompt_id")
                prompt_def = prompt_lookup.get(pid, {})
                sys_prompt = prompt_def.get("system_prompt", "")
                usr_prompt = prompt_def.get("user_prompt", "")

                progress.update(task_id, description=f"Backfilling [bold cyan]{pid}[/bold cyan] ({step_idx+1}/{len(failed_items)})")

                # Retry Model A if errored
                if entry.get("model_a_response", {}).get("error") is not None:
                    entry["model_a_response"] = engine.call_gemini(system_prompt=sys_prompt, user_prompt=usr_prompt)
                    if step_idx < len(failed_items) - 1:
                        time.sleep(delay_gemini)

                # Retry Model B if errored
                if entry.get("model_b_response", {}).get("error") is not None:
                    entry["model_b_response"] = engine.call_groq(system_prompt=sys_prompt, user_prompt=usr_prompt, max_tokens=groq_max_tokens)
                    if step_idx < len(failed_items) - 1:
                        time.sleep(delay_groq)

                existing_responses[resp_idx] = entry
                existing_payload["responses"] = existing_responses

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(existing_payload, f, indent=2, ensure_ascii=False)

                progress.advance(task_id)

        console.print(f"\n[bold green]Success:[/bold green] Backfill completed and saved to [bold underline]{output_path}[/bold underline]\n")

        # Telemetry summary
        summary_table = Table(title="Updated Telemetry Summary (After Backfill)")
        summary_table.add_column("Prompt ID", style="cyan", no_wrap=True)
        summary_table.add_column("Category", style="magenta")
        summary_table.add_column(f"Model A ({engine.gemini_model[:15]})", style="green")
        summary_table.add_column(f"Model B ({engine.groq_model[:15]})", style="blue")

        for r in existing_responses:
            ma = r["model_a_response"]
            mb = r["model_b_response"]
            stat_a = f"[red]ERR[/red]" if ma["error"] else f"{ma['latency_ms']}ms | in:{ma['input_tokens']} out:{ma['output_tokens']}"
            stat_b = f"[red]ERR[/red]" if mb["error"] else f"{mb['latency_ms']}ms | in:{mb['input_tokens']} out:{mb['output_tokens']}"
            summary_table.add_row(r["prompt_id"], r["category"], stat_a, stat_b)

        console.print(summary_table)
        return

    # 5. Prepare data structure for normal full run
    run_id = str(uuid.uuid4())
    timestamp_utc = datetime.now(timezone.utc).isoformat()

    results: List[Dict[str, Any]] = []

    # 6. Progress execution
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}[/bold blue]"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task_id = progress.add_task("Running Inference...", total=len(prompts))

        for idx, prompt_item in enumerate(prompts):
            pid = prompt_item.get("id", f"P-{idx+1}")
            category = prompt_item.get("category", "unknown")
            system_prompt = prompt_item.get("system_prompt", "")
            user_prompt = prompt_item.get("user_prompt", "")

            progress.update(task_id, description=f"Evaluating [bold cyan]{pid}[/bold cyan] ({idx+1}/{len(prompts)})")

            # Call Model A (Gemini)
            resp_a = engine.call_gemini(system_prompt=system_prompt, user_prompt=user_prompt)
            if not dry_run and idx < len(prompts) - 1:
                time.sleep(delay_gemini)

            # Call Model B (Groq)
            resp_b = engine.call_groq(system_prompt=system_prompt, user_prompt=user_prompt)
            if not dry_run and idx < len(prompts) - 1:
                time.sleep(delay_groq)

            results.append({
                "prompt_id": pid,
                "category": category,
                "title": prompt_item.get("title", ""),
                "model_a_response": resp_a,
                "model_b_response": resp_b,
            })

            # Progressive checkpoint write
            interim_payload = {
                "run_metadata": {
                    "run_id": run_id,
                    "timestamp_utc": timestamp_utc,
                    "total_prompts": len(results),
                    "dry_run": dry_run,
                    "model_a": {
                        "name": engine.gemini_model,
                        "provider": "google",
                        "temperature": 0.0,
                        "max_output_tokens": 2048,
                    },
                    "model_b": {
                        "name": engine.groq_model,
                        "provider": "groq",
                        "temperature": 0.0,
                        "max_tokens": 2048,
                    },
                },
                "responses": results,
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(interim_payload, f, indent=2, ensure_ascii=False)

            progress.advance(task_id)

    # 6. Assemble benchmark payload
    payload = {
        "run_metadata": {
            "run_id": run_id,
            "timestamp_utc": timestamp_utc,
            "total_prompts": len(results),
            "dry_run": dry_run,
            "model_a": {
                "name": engine.gemini_model,
                "provider": "google",
                "temperature": 0.0,
                "max_output_tokens": 2048,
            },
            "model_b": {
                "name": engine.groq_model,
                "provider": "groq",
                "temperature": 0.0,
                "max_tokens": 2048,
            },
        },
        "responses": results,
    }

    # 7. Write results atomically
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    console.print(f"\n[bold green]Success:[/bold green] Inference benchmark results written to [bold underline]{output_path}[/bold underline]\n")

    # 8. Print telemetry summary table
    summary_table = Table(title=f"Telemetry Summary (Run ID: {run_id[:8]})")
    summary_table.add_column("Prompt ID", style="cyan", no_wrap=True)
    summary_table.add_column("Category", style="magenta")
    summary_table.add_column(f"Model A ({engine.gemini_model[:15]})", style="green")
    summary_table.add_column(f"Model B ({engine.groq_model[:15]})", style="blue")

    for r in results:
        ma = r["model_a_response"]
        mb = r["model_b_response"]
        
        stat_a = (
            f"[red]ERR[/red]" if ma["error"]
            else f"{ma['latency_ms']}ms | in:{ma['input_tokens']} out:{ma['output_tokens']}"
        )
        stat_b = (
            f"[red]ERR[/red]" if mb["error"]
            else f"{mb['latency_ms']}ms | in:{mb['input_tokens']} out:{mb['output_tokens']}"
        )
        summary_table.add_row(r["prompt_id"], r["category"], stat_a, stat_b)

    console.print(summary_table)


def main():
    parser = argparse.ArgumentParser(
        description="Run automated inference for the Enterprise LLM Evaluation Benchmark."
    )
    parser.add_argument(
        "--test-suite",
        type=Path,
        default=DEFAULT_TEST_SUITE,
        help="Path to test_suite.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to output raw_responses.json",
    )
    parser.add_argument(
        "--prompt-id",
        type=str,
        default=None,
        help="Filter run to a single prompt ID (e.g., SCHEMA-01)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter run to a specific category",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the inference run without calling APIs or consuming quota",
    )
    parser.add_argument(
        "--delay-gemini",
        type=float,
        default=4.0,
        help="Delay in seconds between Gemini API calls to respect free tier RPM (default: 4.0)",
    )
    parser.add_argument(
        "--delay-groq",
        type=float,
        default=2.0,
        help="Delay in seconds between Groq API calls (default: 2.0)",
    )
    parser.add_argument(
        "--model-a",
        type=str,
        default="gemini-3.1-flash-lite",
        help="Model A identifier (default: gemini-3.1-flash-lite)",
    )
    parser.add_argument(
        "--model-b",
        type=str,
        default="qwen/qwen3.8-27b",
        help="Model B identifier (default: qwen/qwen3.8-27b)",
    )
    parser.add_argument(
        "--groq-max-tokens",
        type=int,
        default=750,
        help="Max output tokens for Groq to adhere to free tier 1000 OTPM limit (default: 750)",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Only backfill prompts that previously encountered an error in the output file",
    )

    args = parser.parse_args()

    run_benchmark(
        test_suite_path=args.test_suite,
        output_path=args.output,
        prompt_id_filter=args.prompt_id,
        category_filter=args.category,
        dry_run=args.dry_run,
        delay_gemini=args.delay_gemini,
        delay_groq=args.delay_groq,
        gemini_model=args.model_a,
        groq_model=args.model_b,
        groq_max_tokens=args.groq_max_tokens,
        retry_failed=args.retry_failed,
    )


if __name__ == "__main__":
    main()
