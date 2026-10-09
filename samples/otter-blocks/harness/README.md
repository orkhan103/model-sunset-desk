# Regression harness: Otter Blocks, gpt-3.5-turbo vs gpt-5.6-terra

Produced 2026-10-09 (AI-assisted, human-reviewed) (Model Sunset Desk sample; AI-assisted, human-reviewed).
Python 3.8+ standard library only. No dependencies, no key in any file.

**Status of the numbers in this folder:** the only runs included are **dry runs on synthetic mock responses** (`out/`).
No live API call was made (budget $0). Live before/after numbers come from running this harness on the
client's own OpenAI key, as described below.

## What it tests

Otter 3.2.7's OpenAI-key path sends Chat Completions requests built from prompt templates that Otter downloads
from Themeisle and caches for a week. On 2026-10-09 all four served templates pinned `gpt-3.5-turbo`, which
OpenAI shuts down on 2026-10-23. For each case in `cases.jsonl` the harness builds the exact request the editor
sends (template, `{ACTION}`/`{INSERT_TASK}` substitution, Pro pattern add-on, and the `temperature: 1.3`
"Regenerate" variant), then runs:

| Arm | Request | Purpose |
|---|---|---|
| `old` | Unchanged 3.2.7 request (`gpt-3.5-turbo`, legacy `functions`/`function_call`) | Baseline, while the model still exists |
| `new:<model>` | The same request after the `patch.diff` transform (model swap, `reasoning_effort`, sampling params, `functions` -> `tools`) | Candidate; repeat `--candidate` to compare several |

Per request it records: HTTP status and error code, response shape (`tool_calls` / `function_call` / `content`),
**format validity** as the Otter editor would see it, per-case **expectations**, **refusals**, output length,
**latency**, **token usage** (prompt, completion, reasoning, cached, cache writes), **cost estimate**, and the
**model name the API reported**.

| Feature (template) | Cases | Format-valid means |
|---|---|---|
| AI Block (`textTransformation`, action `otter_action_prompt`) | 16 (B01-B16) | Non-empty HTML, no code fences, no page-level tags (`html`, `head`, `body`, `footer`, `script`, `style`) |
| AI Form generator (`form`, forced `generateForm`) | 10 (F01-F10) | Arguments parse as JSON and contain at least one field type the editor maps; unknown types are counted because the editor drops them silently |
| Patterns picker (`patternsPicker`, forced `pickPatterns`, legacy blocks) | 4 (P01-P04) | Arguments parse and contain known pattern slugs |

Four cases are "Regenerate" requests (B04, B13, F07, P04). Two are policy-edge cases (B16 health claim, F10 SSN
and card collection), which are recorded for review and not scored.

## Files

| File | What it is |
|---|---|
| `run_harness.py` | The harness |
| `cases.jsonl` | 30 cases (edit or replace with the client's own inputs) |
| `templates.sample.json` | Paraphrased SAMPLE templates that mirror the structure of the served ones. **Use the site's real templates for client work.** |
| `pricing.json` | Cost table, an **input you can edit**. Values are OpenAI list prices read on 2026-10-09 from the linked model pages |
| `mocks/build_mocks.py`, `mocks/*.jsonl` | Synthetic mock responses for `--dry-run` (hand-written; labelled anomalies exercise the detectors) |
| `out/dry-run/` | Dry-run demo output: `comparison.md`, `results.jsonl`, `requests.jsonl`, `run_meta.json` |
| `out/dry-run-post-shutdown/` | Dry-run demo of the old model failing (synthetic `model_not_found`) |
| `out/console.txt`, `out/live-guards.console.txt` | Console transcripts of the demo runs and of the live-mode safety guards |

## Quick start (no key, no cost)

```bash
python3 -I run_harness.py --dry-run --out out/dry-run
python3 -I run_harness.py --dry-run --mocks mocks/mock_responses_post_shutdown.jsonl --only B01,F01,P01 --out out/dry-run-post-shutdown
```

## Live run on the client's key

1. Create a **separate OpenAI project key** for this test, ideally in a staging project with a small budget, and
   revoke it afterwards. The harness reads it from the `OPENAI_API_KEY` environment variable only; it never
   prints it or writes it to disk.
2. Export the site's **real** cached templates (exactly what that site sends today):
   ```bash
   wp transient get otter_prompts --format=json > otter-prompts.json
   ```
   If the transient has expired, open an Otter AI Block in the editor once and re-run the command.
3. Optionally replace `cases.jsonl` with the client's own typical prompts (same fields).
4. Before 2026-10-23, run both arms and keep the output as the baseline:
   ```bash
   export OPENAI_API_KEY=...   # staging key
   python3 -I run_harness.py --live --templates otter-prompts.json --max-cost-usd 0.50 --out out/live-1
   ```
   The harness prints the request count, models and a rough pre-flight cost estimate (about $0.31 for all
   30 cases x 2 arms at list prices, assuming 700 output tokens per request). It refuses to run if the estimate
   exceeds `--max-cost-usd`, and it asks you to type `spend` unless you pass `--yes`.
5. After 2026-10-23 the old model is gone. The harness detects the first `model_not_found`/404, skips the rest of
   the old arm, and lets you compare against the earlier run with `--baseline out/live-1/results.jsonl`.

Useful variants:

| Flag | Use |
|---|---|
| `--candidate gpt-5.6-luna` (repeatable) | Add an arm for another target model. Luna is cheaper per token, but OpenAI recommends **terra** as the gpt-3.5-turbo replacement |
| `--swap-effort low` | Test `reasoning_effort: low` instead of the patch default `none` |
| `--keep-sampling` | Send `temperature`/`top_p` to GPT-5.x, testing whether `temperature: 1.3` on Regenerate is accepted (the docs do not say) |
| `--only form,F01` / `--limit 5` | Run a subset |
| `--timeout 300` | Per-request timeout; matches Otter's default |

## Reading the output

`comparison.md` contains a summary per arm, a per-feature table, a per-case table with flags, a "needs human review" list
with both outputs side by side, and the request keys that changed on the wire. The flags are:

| Flag | Meaning |
|---|---|
| `FORMAT-REGRESSION` / `FORMAT-FIXED` | The editor-usable format broke / was repaired |
| `EXPECTATION-REGRESSION` / `EXPECTATION-FIXED` | The case's soft checks failed / now pass |
| `REFUSAL-CHANGE` | Refusal status differs between the arms |
| `LENGTH-SHIFT ±N%` | Word count changed by more than 50% (AI Block) |
| `COUNT-SHIFT a->b` | Field or slug count changed by 2 or more |
| `NEW-ERROR:<code>` | The candidate request failed (for example an unsupported parameter) |
| `POLICY-EDGE` | Always reviewed by a human |

## Limitations (read before quoting any number)

- Thirty cases show direction, not statistical significance. Each Regenerate case is a single sample.
- Latency depends on the network, the account's usage tier and OpenAI load. GPT-5.6 safeguards can pause
  generation mid-stream (OpenAI GPT-5.6 guide).
- The language check is a stop-word heuristic, and refusal detection is heuristic beyond `message.refusal`.
- Results on `templates.sample.json` are not evidence about Themeisle's production prompts.
- Out of scope: Otter's page/section generation pipeline (defaults to `gpt-5-mini`, which is not on the
  2026-10-23 list) and the WordPress AI Client backend (Otter drops the model pin there).
- Data handling: `requests.jsonl` and `results.jsonl` contain the client's prompts and outputs. Treat them as
  client data and delete them within 7 days of delivery, as the engagement terms require.
