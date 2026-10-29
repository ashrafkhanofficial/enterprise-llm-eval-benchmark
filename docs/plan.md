# Project Execution Plan: Enterprise LLM Evaluation & AI Safety Benchmark

**Document ID**: PLAN-LLM-EVAL-001  
**Created**: 2026-10-26  
**Last Updated**: 2026-10-26  
**Status Tracker**: See [status.md](./status.md)

---

## Plan Overview

This plan transforms a blank workspace into a production-grade, client-facing LLM Evaluation & AI Safety Benchmark portfolio project. The plan is divided into **7 phases**, each with explicit deliverables, acceptance criteria, and dependencies.

### Business Objective
Deliver a reproducible, data-driven benchmark comparing **Google Gemini 1.5 Flash** (proprietary frontier) against **Meta Llama 3.1 70B Instruct** (open-weights via Groq) across 30 enterprise adversarial test cases. The final deliverable must demonstrate competence in:
- RLHF-style preference ranking with structured justifications
- Adversarial red-teaming and prompt injection defense auditing
- Custom benchmark design with formal scoring rubrics
- Statistical analysis and executive-level reporting

### Architecture Summary
```
data/test_suite.json          ──► scripts/run_inference.py     ──► data/raw_responses.json
(30 challenge prompts)             (Automated API queries)          (Unaltered model outputs)
                                                                           │
                                                                    ┌──────┴──────┐
                                                                    ▼             ▼
                                                          scripts/validate_   Human Expert
                                                          schema.py           Evaluation
                                                          (Programmatic       (SOP rubric,
                                                           gates)             failure codes)
                                                                    │             │
                                                                    └──────┬──────┘
                                                                           ▼
                                                              data/evaluation_results.json
                                                              (Complete evaluation matrix)
                                                                           │
                                                                           ▼
                                                              scripts/audit_benchmark.py
                                                              (Win rates, failure taxonomy,
                                                               latency analysis)
                                                                           │
                                                                           ▼
                                                              reports/benchmark_summary.md
                                                              README.md (Executive Case Study)
```

---

## Phase 1: Environment Setup & Project Scaffold ✅ COMPLETE

### Objective
Establish the development environment, dependency management, API key configuration, and project directory structure.

### Deliverables
| # | Deliverable | File Path | Status |
|---|-------------|-----------|--------|
| 1.1 | Agent operating rules | `AGENTS.md` | ✅ Done |
| 1.2 | Git safety configuration | `.gitignore` | ✅ Done |
| 1.3 | API key template | `.env.example` | ✅ Done |
| 1.4 | Pinned dependencies | `requirements.txt` | ✅ Done |
| 1.5 | Python virtual environment | `venv/` | ✅ Done |
| 1.6 | All packages installed | — | ✅ Verified |

### Acceptance Criteria
- [x] `venv` activates cleanly on Windows PowerShell
- [x] `google-genai`, `groq`, `pydantic`, `rich`, `tabulate`, `tenacity` all import successfully
- [x] `.env` is git-ignored; `.env.example` documents required keys

---

## Phase 2: Evaluation Rubric & Challenge Suite Design ✅ COMPLETE

### Objective
Author the formal Standard Operating Procedure (SOP) that governs all evaluation scoring, and design 30 adversarial challenge prompts across 4 enterprise dimensions.

### Why This Phase Matters
The evaluation rubric is the equivalent of an annotation guideline in computer vision. Without a formal, unambiguous rubric, evaluation scores are subjective and non-reproducible. In RLHF data work, clients reject deliverables where evaluators cannot point to a rubric clause justifying their score.

### Deliverables
| # | Deliverable | File Path | Status |
|---|-------------|-----------|--------|
| 2.1 | Formal evaluation SOP with 4 scoring dimensions | `docs/evaluation-rubric.md` | ✅ Done |
| 2.2 | Standardized failure taxonomy (12 error codes) | `docs/evaluation-rubric.md` | ✅ Done |
| 2.3 | Head-to-head arbitration protocol | `docs/evaluation-rubric.md` | ✅ Done |
| 2.4 | 30 curated challenge prompts with metadata | `data/test_suite.json` | ✅ Done |

### Prompt Distribution
| Category | Count | What It Tests |
|----------|-------|---------------|
| Strict Schema & Negative Constraints | 8 | JSON formatting, banned tokens, word limits, TSV output |
| Factuality & Hallucination Resistance | 8 | False premise traps, fictitious API params, invented methods |
| Complex Multi-Step Logic & Policy | 8 | SLA arbitration, billing proration, RBAC, GDPR conflicts |
| Safety, Red-Teaming & Injection Defense | 6 | System prompt exfiltration, indirect injection, jailbreaks |

### Acceptance Criteria
- [x] `test_suite.json` parses as valid JSON with exactly 30 prompts
- [x] Category distribution matches 8/8/8/6
- [x] Every prompt contains: `id`, `category`, `sub_type`, `system_prompt`, `user_prompt`, `negative_constraints`, `ground_truth_or_rubric`
- [x] Rubric defines unambiguous scoring anchors for all 4 dimensions
- [x] Failure taxonomy contains 12 distinct error codes across 4 categories

---

## Phase 3: Automated Inference Pipeline ✅ COMPLETE

### Objective
Build an automated script that sends all 30 prompts to both models (Gemini 3.1 Flash Lite via Google AI Studio, Qwen 27B via Groq), captures the raw responses, and records operational telemetry (latency, token counts, timestamps).

### Why This Phase Matters
Manual copy-pasting into web playgrounds is neither reproducible nor scalable. A programmatic inference runner ensures:
- **Determinism**: `temperature=0.0` across both models for identical re-runs.
- **Telemetry Capture**: Exact round-trip latency (ms), input/output token counts, and model version strings are logged automatically.
- **Auditability**: Any reviewer can re-run the script and verify they get near-identical outputs.

### Pre-Requisites
- [x] User has created `.env` file with valid `GEMINI_API_KEY` and `GROQ_API_KEY`
- [x] Both API keys are confirmed working (free tier)

### Deliverables
| # | Deliverable | File Path | Description |
|---|-------------|-----------|-------------|
| 3.1 | Inference runner script | `scripts/run_inference.py` | Async runner with retry logic |
| 3.2 | Raw response data | `data/raw_responses.json` | Generated by running 3.1 |

### Technical Specification for `run_inference.py`
```
Inputs:
  - data/test_suite.json (30 prompts)
  - .env (API keys)

Processing:
  - For each prompt in test_suite.json:
    - Send to Model A (Gemini 1.5 Flash) with temperature=0.0, max_output_tokens=2048
    - Send to Model B (Llama 3.1 70B Versatile) with temperature=0.0, max_tokens=2048
    - Record wall-clock latency (ms) for each API call
    - Extract input/output token counts from API response metadata
    - Apply exponential backoff with jitter on rate limit errors (HTTP 429)

  - Rate Limit Strategy:
    - Gemini free tier: ~15 RPM → sequential with 4-second delay between calls
    - Groq free tier: ~30 RPM → sequential with 2-second delay between calls
    - Both: tenacity retry with exponential backoff (max 3 retries, base 10s wait)

Output Schema (data/raw_responses.json):
  {
    "run_metadata": {
      "run_id": "uuid",
      "timestamp_utc": "ISO 8601",
      "model_a": {"name": "gemini-1.5-flash", "provider": "google", "temperature": 0.0},
      "model_b": {"name": "llama-3.1-70b-versatile", "provider": "groq", "temperature": 0.0}
    },
    "responses": [
      {
        "prompt_id": "SCHEMA-01",
        "model_a_response": {
          "raw_output": "...",
          "latency_ms": 1423,
          "input_tokens": 312,
          "output_tokens": 87,
          "finish_reason": "stop",
          "error": null
        },
        "model_b_response": { ... }
      }
    ]
  }
```

### CLI Interface
```bash
# Full live run (requires valid API keys in .env)
python scripts/run_inference.py

# Dry run — validates loading, API client init, prints plan without calling APIs
python scripts/run_inference.py --dry-run

# Run only specific categories
python scripts/run_inference.py --category safety_and_prompt_injection_defense

# Run a single prompt for debugging
python scripts/run_inference.py --prompt-id SCHEMA-01
```

### Acceptance Criteria
- [x] Script loads all 30 prompts from `test_suite.json` without error
- [x] Script gracefully handles missing `.env` or invalid API keys with clear error messages
- [x] `--dry-run` mode completes without making any API calls
- [x] Full run produces `data/raw_responses.json` with 30 entries, each containing both model responses
- [x] Every response entry includes `raw_output`, `latency_ms`, `input_tokens`, `output_tokens`, `finish_reason`
- [x] Rate limit errors (429) are retried automatically with exponential backoff
- [x] Script displays a real-time progress bar (via `rich`) showing completion status

---

## Phase 4: Programmatic Schema Validation ✅ COMPLETE

### Objective
Build an automated validator that runs deterministic assertions against raw model responses for the Schema & Negative Constraint category (SCHEMA-01 through SCHEMA-08). This is the "Layer A" evaluation: objective, code-verifiable checks that require zero human judgment.

### Why This Phase Matters
In a production LLM pipeline, if the model outputs markdown backticks when the downstream microservice expects raw JSON bytes, the entire pipeline crashes. Schema validation is the first automated gate. Clients hiring evaluators expect you to catch these failures programmatically, not manually.

### Deliverables
| # | Deliverable | File Path | Description |
|---|-------------|-----------|-------------|
| 4.1 | Schema validation script | `scripts/validate_schema.py` | Automated assertion engine |

### What the Validator Checks
For each Schema-category prompt, the validator runs the following automated checks against both Model A and Model B responses:

| Check | Method | Error Code on Failure |
|-------|--------|-----------------------|
| JSON Syntax | `json.loads(response)` | `ERR_SCHEMA_INVALID_JSON` |
| Required Keys Present | Set comparison against `expected_keys` | `ERR_SCHEMA_MISSING_KEY` |
| Markdown Fence Detection | Regex scan for triple-backtick patterns | `ERR_PREAMBLE_LEAK` |
| Preamble / Postamble | Regex scan for conversational filler patterns | `ERR_PREAMBLE_LEAK` |
| Banned Token Scan | Case-insensitive regex for each banned word/phrase | `ERR_BANNED_TOKEN_VIOLATION` |
| Word Count Bounds | `len(text.split())` within `[min, max]` range | `ERR_BANNED_TOKEN_VIOLATION` |
| Type Validation | Check integer fields are ints, not strings | `ERR_SCHEMA_INVALID_JSON` |
| Enum Validation | Check enum values are in allowed set | `ERR_SCHEMA_INVALID_JSON` |

### Output
The validator appends programmatic compliance results to the evaluation matrix:
```json
{
  "prompt_id": "SCHEMA-01",
  "model_a_programmatic": {
    "json_valid": true,
    "keys_present": true,
    "preamble_detected": false,
    "banned_tokens_found": [],
    "overall_pass": true,
    "error_codes": []
  },
  "model_b_programmatic": {
    "json_valid": true,
    "keys_present": true,
    "preamble_detected": true,
    "banned_tokens_found": [],
    "overall_pass": false,
    "error_codes": ["ERR_PREAMBLE_LEAK"]
  }
}
```

### Acceptance Criteria
- [x] Validator loads `data/raw_responses.json` and runs checks on all SCHEMA-* prompts
- [x] Each check produces a deterministic PASS/FAIL with specific error codes
- [x] Validator produces a rich console table summarizing results per prompt per model
- [x] False positive rate is zero (validator should not flag valid outputs as failures)
- [x] Results are saved in a structured format for integration into `evaluation_results.json`

---

## Phase 5: Human Expert Evaluation ✅ COMPLETE (30 / 30 Completed)

### Objective
**You personally read and evaluate every single response from both models** against the formal SOP rubric defined in `docs/evaluation-rubric.md`. This is the core human evaluation work — the equivalent of annotating 200 images in CVAT.

### Human Evaluation Protocol & Workflow (Option A)
The evaluation is conducted via **Interactive Chat Review & Critique with Full Verbatim Transparency**:
1. For each batch, the AI agent presents the exact, unedited raw output of both models from `data/raw_responses.json` (no compressed ellipses).
2. The user and AI agent review the response against `docs/evaluation-rubric.md` and `data/test_suite.json` ground truth.
3. Consensus is reached on scores (1–5 or PASS/FAIL), failure codes, winner determination, and empirical justification.
4. Approved records are committed to `data/evaluation_results.json`.

### Batch Roadmap & Execution State
| Batch | Category | Prompt IDs | Status | Outcome / Head-to-Head Record |
|---|---|---|---|---|
| **5.1** | Schema & Negative Constraints | `SCHEMA-01` to `SCHEMA-08` | ✅ Complete | Model A: 1 win (`SCHEMA-03`), Model B: 0 wins, 7 Ties |
| **5.2** | Factuality & Hallucination Resistance | `FACT-01` to `FACT-08` | ✅ Complete | Model A: 0 wins, Model B: 1 win (`FACT-03`), 7 Ties |
| **5.3** | Complex Multi-Step Logic & Policy | `LOGIC-01` to `LOGIC-08` | ✅ Complete | Model A: 3 wins (`LOGIC-04, 06, 08`), Model B: 2 wins (`LOGIC-05, 07`), 3 Ties |
| **5.4** | Safety, Red-Teaming & Injection | `SEC-01` to `SEC-06` | ✅ Complete | Model A: 0 wins, Model B: 1 win (`SEC-01`), 5 Ties |

### Deliverables
| # | Deliverable | File Path | Description |
|---|-------------|-----------|-------------|
| 5.1 | Complete evaluation matrix | `data/evaluation_results.json` | 30 / 30 scored (Target: 30/30) ✅ Complete |

### Output Schema for `evaluation_results.json`
```json
{
  "evaluator": "Ashraf Khan",
  "evaluation_date": "2026-10-XX",
  "rubric_version": "SOP-LLM-EVAL-001",
  "evaluations": [
    {
      "prompt_id": "SCHEMA-01",
      "category": "strict_schema_and_negative_constraints",
      "model_a_scores": {
        "instruction_adherence": {"verdict": "PASS", "adherence_pct": 100},
        "factuality": {"score": null, "justification": "N/A for schema prompts"},
        "reasoning": {"score": null, "justification": "N/A for schema prompts"},
        "safety": {"verdict": null, "justification": "N/A for non-safety prompts"}
      },
      "model_b_scores": {
        "instruction_adherence": {"verdict": "FAIL", "adherence_pct": 80},
        "factuality": {"score": null, "justification": "N/A"},
        "reasoning": {"score": null, "justification": "N/A"},
        "safety": {"verdict": null, "justification": "N/A"}
      },
      "model_a_failure_codes": [],
      "model_b_failure_codes": ["ERR_PREAMBLE_LEAK"],
      "winner": "Model A",
      "justification": "Model A emitted raw JSON with correct keys and zero preamble. Model B prepended 'Here is the extracted JSON:' before the payload, violating the zero-preamble negative constraint (ERR_PREAMBLE_LEAK). Both produced correct key-value content, but Model B's formatting failure would crash a downstream JSON parser expecting raw bytes."
    }
  ]
}
```

### Evaluation Guidelines (Bias Prevention)
1. **Read prompts in randomized order** — do not evaluate all SCHEMA prompts first and all SAFETY prompts last (anchor bias)
2. **Evaluate both models before deciding winner** — do not read Model A, decide it's "good", and then look for flaws in Model B (confirmation bias)
3. **Reference the rubric constantly** — every score must be justifiable by pointing to a specific anchor definition in `evaluation-rubric.md`
4. **Write justifications as if the client will read them** — this is your professional deliverable

### Acceptance Criteria
- [x] All 30 prompts have complete evaluation entries
- [x] Every score maps to a valid rubric anchor (no arbitrary numbers)
- [x] Every failure has at least one error code from the standard taxonomy
- [x] Every winner determination has a 2–4 sentence empirical justification
- [x] Justifications cite specific response content (not vague opinions like "A was better")

---

## Phase 6: Statistical Audit & Analysis 🔲 PENDING

### Objective
Build a programmatic script that aggregates all evaluation results into statistical metrics, generating quantitative evidence for the executive report.

### Why This Phase Matters
Claiming "Gemini was better" without statistical backing is an opinion, not an evaluation. Clients expect quantitative evidence: win rates, failure distributions, and confidence signals. This script transforms your human evaluations into publishable metrics.

### Deliverables
| # | Deliverable | File Path | Description |
|---|-------------|-----------|-------------|
| 6.1 | Statistical audit script | `scripts/audit_benchmark.py` | Aggregation engine |
| 6.2 | Generated summary report | `reports/benchmark_summary.md` | Auto-generated markdown |

### Metrics Computed
```
1. HEAD-TO-HEAD WIN RATES
   ├── Overall: Model A wins X%, Model B wins Y%, Tie Z%
   ├── By Category:
   │   ├── Schema & Constraints: A=?%, B=?%, Tie=?%
   │   ├── Factuality & Hallucination: A=?%, B=?%, Tie=?%
   │   ├── Multi-Step Logic: A=?%, B=?%, Tie=?%
   │   └── Safety & Red-Teaming: A=?%, B=?%, Tie=?%

2. FAILURE TAXONOMY DISTRIBUTION
   ├── Model A total failure count by error code
   ├── Model B total failure count by error code
   ├── Most common failure mode per model
   └── Categories where each model is weakest

3. SCORING DISTRIBUTION
   ├── Mean Factuality score: Model A vs Model B
   ├── Mean Reasoning score: Model A vs Model B
   ├── Constraint Adherence pass rate: Model A vs Model B
   ├── Safety pass rate: Model A vs Model B

4. LATENCY & TOKEN EFFICIENCY
   ├── Median latency (ms): Model A vs Model B
   ├── P95 latency (ms): Model A vs Model B
   ├── Mean output tokens per response
   ├── Tokens per second (throughput)
   └── Cost projection: estimated $/1000 queries at production scale

5. EXECUTIVE SUMMARY TABLE
   ┌──────────────────────┬─────────────┬─────────────┐
   │ Metric               │ Gemini 1.5  │ Llama 3.1   │
   ├──────────────────────┼─────────────┼─────────────┤
   │ Overall Win Rate     │ XX%         │ XX%         │
   │ Schema Pass Rate     │ XX%         │ XX%         │
   │ Factuality (Mean)    │ X.X / 5     │ X.X / 5     │
   │ Reasoning (Mean)     │ X.X / 5     │ X.X / 5     │
   │ Safety Pass Rate     │ XX%         │ XX%         │
   │ Median Latency       │ XXX ms      │ XXX ms      │
   │ Throughput           │ XX tok/s    │ XX tok/s    │
   └──────────────────────┴─────────────┴─────────────┘
```

### Acceptance Criteria
- [ ] Script loads `evaluation_results.json` and `raw_responses.json` without error
- [ ] All 5 metric categories are computed and printed to console via `rich` tables
- [ ] Auto-generates `reports/benchmark_summary.md` with formatted tables and analysis
- [ ] Win rates sum to 100% (no rounding drift)
- [ ] Latency percentiles are computed correctly (P50, P95, P99)

---

## Phase 7: Executive Report & README 🔲 PENDING

### Objective
Write the client-facing executive case study (`README.md`) and finalize all documentation. This is what hiring managers, Upwork clients, and portfolio reviewers will read first.

### Why This Phase Matters
This README is the landing page of your portfolio project. An AI engineering lead browsing your GitHub will spend 30 seconds scanning this README. If it looks like a tutorial or homework assignment, they move on. If it reads like a professional audit report from someone who clearly understands LLM failure modes, they message you.

### Deliverables
| # | Deliverable | File Path | Description |
|---|-------------|-----------|-------------|
| 7.1 | Executive README | `README.md` | Client-facing case study |
| 7.2 | Final benchmark report | `reports/benchmark_summary.md` | Detailed statistical report |

### README Structure
```
# Enterprise LLM Evaluation & AI Safety Benchmark

## Executive Summary (3-4 sentences: what, why, key finding)

## Benchmark Architecture (diagram + file layout)

## Methodology
  ### Challenge Suite Design (4 categories, 30 prompts)
  ### Evaluation Framework (3-layer: programmatic → human → statistical)
  ### Scoring Rubric & Failure Taxonomy (link to docs/evaluation-rubric.md)

## Key Findings
  ### Head-to-Head Results (summary table)
  ### Critical Failure Patterns (most interesting findings with examples)
  ### Latency & Cost Analysis

## Selected Case Studies (3-4 cherry-picked examples showing evaluation depth)
  ### Example 1: Hallucination Trap — [prompt title]
  ### Example 2: Policy Arbitration — [prompt title]
  ### Example 3: Prompt Injection Defense — [prompt title]

## Reproducing This Benchmark
  ### Prerequisites
  ### Installation
  ### Running Inference
  ### Running Validation & Audit

## About the Evaluator
```

### Acceptance Criteria
- [ ] README reads as a professional case study, not a tutorial
- [ ] Contains at least 3 concrete response examples with evaluation annotations
- [ ] All statistical claims link back to computed metrics in `reports/benchmark_summary.md`
- [ ] Installation and reproduction instructions are tested and working
- [ ] No placeholder text, no TODOs, no "lorem ipsum"

---

## Phase Dependencies & Execution Order

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──┐
  (Done)     (Done)    (Inference) (Validation) │
                                                ├──► Phase 5 ──► Phase 6 ──► Phase 7
                                                │   (Human Eval)  (Stats)    (Report)
                                                │
                                         Phase 4 and Phase 5
                                         can partially overlap:
                                         run validation while
                                         starting human evals
```

### Critical Path
The blocking dependency chain is:
1. **Phase 3** blocks everything downstream (we need raw model outputs before we can evaluate anything)
2. **Phase 5** is the most time-intensive phase (manually reading and scoring 60 responses = 30 prompts × 2 models)
3. **Phase 6** requires both Phase 4 (programmatic results) and Phase 5 (human scores) to be complete

### Estimated Time Investment
| Phase | Estimated Duration | Nature of Work | Status |
|-------|--------------------|----------------|--------|
| Phase 1 | ~30 min | Automated setup | ✅ Done |
| Phase 2 | ~2 hrs | Design & authoring | ✅ Done |
| Phase 3 | ~2 hrs coding + ~30 min runtime | Script development + API execution | 🔲 Pending |
| Phase 4 | ~1.5 hrs | Script development | 🔲 Pending |
| Phase 5 | ~4–6 hrs | Manual reading, scoring, and justification writing | 🔲 Pending |
| Phase 6 | ~2 hrs | Script development + analysis | 🔲 Pending |
| Phase 7 | ~3 hrs | Technical writing and polish | 🔲 Pending |
| **Total** | **~15–18 hrs remaining** | | |
