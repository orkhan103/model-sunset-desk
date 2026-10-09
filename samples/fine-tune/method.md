# Method: replacing a retiring fine-tuned model

Produced 2026-10-09 (AI-assisted, human-reviewed) for **Model Sunset Desk** (offer: **Fine-tune Replacement, US$2,500**). AI-assisted, human-reviewed.

This document describes how we replace a fine-tuned model whose base OpenAI shuts down on 23 Oct 2026 (for example `ft:gpt-3.5-turbo-0125:your-org::abc123`). It also covers how we prove what the replacement does, using a measured comparison rather than a promise of identical behaviour.

The sample code (`eval_harness.py`) and the dry run in section 8 use **synthetic data and a simulated model**. No API calls were made (budget $0).

Source labels:
- **[V]**: read live on 2026-10-09 from the named primary page; copies are kept under `launch/_untrusted/openai-docs/`.
- **[Tested]**: executed here.
- **[Unverified]**: not confirmed.

---

## 1. What we verified about fine-tuning availability today

**1. These fine-tunes shut down on 23 Oct 2026.** [V: https://developers.openai.com/api/docs/deprecations, entry 2026-04-22]

The page's column is headed "Recommended replacement base model":

| Fine-tune family | Recommended replacement base model |
|---|---|
| `ft-gpt-3.5-turbo` | `gpt-5.6-terra` |
| `ft-gpt-4` | `gpt-5.6-sol` |
| `ft-gpt-4.1-nano-2025-04-14` | `gpt-5.6-luna` |
| `ft-babbage-002`, `ft-davinci-002` | `gpt-5.6-terra` |
| `ft-o4-mini-2025-04-16` | `gpt-5.6-terra` (listed in the same entry's main table) |

**2. The recommended replacements cannot be fine-tuned.** [V: model pages for gpt-5.6-terra, gpt-5.6-sol and gpt-5.6-luna]
- Each page's Features list says **"Fine-tuning: Not supported"**.
- On each page, `v1/fine-tuning` appears among the *unsupported* endpoints.
- `v1/chat/completions`, `v1/responses` and `v1/batch` are supported.

**3. OpenAI is winding down self-serve fine-tuning.** [V: https://developers.openai.com/api/docs/guides/supervised-fine-tuning and the pricing page]

Both pages carry this notice, verbatim:
> "OpenAI is winding down the fine-tuning platform. The platform is no longer accessible to new users, but existing users of the fine-tuning platform will be able to create training jobs for the coming months. All fine-tuned models will remain available for inference until their base models are deprecated."

The deprecations page section "Update to OpenAI's self-serve fine-tuning" gives the timeline [V]:

| Date | Update (verbatim) |
|---|---|
| May 7, 2026 | "Creating fine-tuning jobs or training is not available to organizations that have not previously run fine-tuning." |
| July 2, 2026 | "Creating fine-tuning jobs is no longer available to organizations that have not run inference on a fine-tuned model in the past 60 days." |
| Jan 6, 2027 | "Active existing customers will no longer be able to create new fine-tuning jobs on this date. Inference on fine-tuned models will be disabled only when the underlying base model is deprecated." |

**4. Which base models can still be fine-tuned, by eligible existing customers only.** [V: model-optimization guide, "Fine-tuning methods" table]

| Method | Base models listed |
|---|---|
| Supervised fine-tuning and DPO | `gpt-4.1-2025-04-14`, `gpt-4.1-mini-2025-04-14`, `gpt-4.1-nano-2025-04-14` |
| Vision fine-tuning | `gpt-4o-2024-08-06` |
| Reinforcement fine-tuning | `o4-mini-2025-04-16` |

- Two of these bases, `gpt-4.1-nano-2025-04-14` and `o4-mini-2025-04-16`, are **themselves shut down on 23 Oct**.
- We searched today's deprecations page text for `gpt-4.1-2025-04-14`, `gpt-4.1-mini-2025-04-14` and `gpt-4o-2024-08-06`. None appears, so we found no announced shutdown date for them as of 2026-10-09.

**5. Prices per 1M tokens.** [V: pricing page fine-tuning table, Standard tier, read from the page's embedded table data; model pages]

| Model | Input | Cached input | Output | Training |
|---|---|---|---|---|
| Fine-tuned gpt-3.5-turbo (Legacy) | $3.00 | n/a | $6.00 | $8.00 |
| Fine-tuned gpt-4.1-mini-2025-04-14 | $0.80 | $0.20 | $3.20 | $5.00 |
| gpt-5.6-terra (base) | $2.00 | $0.20 | $12.00 | not fine-tunable |

On reasoning models, reasoning tokens "are billed as output tokens" [V: reasoning guide].

**6. OpenAI's own Evals platform is going away.** It becomes read-only on 31 Oct 2026 and shuts down on 30 Nov 2026 [V: deprecations page, entry 2026-06-03]. Our evaluation therefore runs locally with `eval_harness.py` and does not depend on OpenAI Evals.

**What this means for an owner of a retiring fine-tune.** Phrased with care:

- You **may not be able to simply retrain** on the recommended replacement. The gpt-5.6 models do not support fine-tuning, and new fine-tuning jobs end for everyone on 6 Jan 2027 (earlier for organizations that have not used a fine-tuned model in the last 60 days).
- An organization that is still eligible *could* retrain on `gpt-4.1-2025-04-14` or `gpt-4.1-mini-2025-04-14` as a bridge. That base is not OpenAI's listed replacement, and a future migration would still be needed.
- **Our default is to rebuild the behaviour on the recommended base**, using a written specification, structured outputs and few-shot examples, and to measure the result against the old model on held-out data.
- This agrees with, and is more specific than, the April 2026 OpenAI support answer recorded in our offer spec (GPT-5 family not listed for fine-tuning).

---

## 2. Overview

```
client training JSONL --prepare--> dedupe -> stratified split
                                      |-- heldout.jsonl  (frozen, SHA-256 recorded; never used for prompt work)
                                      |-- dev.jsonl      (all prompt iteration happens here)
                                      '-- fewshot_pool.jsonl
old fine-tune on heldout (BEFORE 23 Oct) --> baseline_outputs.jsonl   (recorded once, kept)
candidate configs (prompt + few-shot + schema + model + effort) --iterate on dev--> best 2-4 configs
best configs on heldout --> eval_harness.py --> comparison report (metrics, CIs, flips, cost, latency)
recommended config --> integration PR (+ fallback handling) --> client CI --> client go/no-go
```

---

## 3. Step 1: data intake and held-out split

**What we ask for.** Everything goes through a channel the client chooses; we need no production access and no passwords.
1. The training JSONL used for the fine-tune, plus the validation file if one was used.
   - Chat format is `{"messages": [...]}` [V: SFT guide].
   - The legacy `{"prompt","completion"}` format (babbage-002/davinci-002 era) is also supported by the tool. [Format from earlier OpenAI docs; not re-verified today]
2. The fine-tuned model ID and the code or config that calls it: system prompt, parameters, and how the output is parsed.
3. A **staging API key from the same OpenAI organization/project that owns the fine-tune**, so the old model can be called for the baseline. The client revokes it after delivery.
4. Optionally, 50-200 recent production inputs, with personal data removed. These show where training data and real traffic differ.

**What `--prepare` does** [Tested on synthetic data; see 8.3]:
- Parses every row. It uses the last user message as `input` and the last assistant message as `expected`, parsing the latter as JSON when possible.
- Counts rows it cannot convert, such as tool-call-only rows; those go to manual review.
- Removes exact duplicates on normalised input, and lists duplicates whose labels conflict. Conflicts are label noise and must be resolved with the client before scoring.
- Splits deterministically and stratified by the label field into `heldout` (default 20%), `fewshot_pool` (default 10%) and `dev` (the rest). Each row records which split it went to, plus the seed, in a `_provenance` field; the harness ignores that field.
- Writes `split_manifest.json` with SHA-256 hashes of the source file and each split file. The held-out set is **frozen** at this point.
- Extracts the most common system prompt into `system_prompt_from_training.json` as a starting point.

**How big the held-out set should be.**
- Aim for **at least 100 held-out examples, and at least 20-30 per important class**, where the data allows.
- The dry run in section 8 has n=20, and its 95% interval for the change in label accuracy spans 40 points. That interval is far too wide to decide anything, and shows why size matters.

**Recording the baseline must happen before 23 Oct.**
- We run the **old fine-tune** on the held-out set once and save its raw outputs, with the model name the API reports, as `baseline_outputs.jsonl`.
- After the shutdown this is impossible. The comparison would then fall back to the training labels only, which says how well each system matches the labels, but not how the new one differs from what users saw before.

**Data handling.** Client data is used only for the engagement and deleted within 7 days of delivery.

---

## 4. Step 2: rebuilding the behaviour

1. **Write the output contract.**
   - Derive a JSON schema from the training outputs: every field, its type, enums for categorical fields, and when values are null.
   - Use it with **Structured Outputs** (`response_format: {"type": "json_schema", "strict": true}`). Verified constraints [V: structured-outputs guide]:
     - the root must be an object, not `anyOf`;
     - all fields must be listed in `required`;
     - `additionalProperties: false`;
     - optional fields are emulated with a union type with `null`;
     - `pattern` and `format` are supported for strings.
2. **Write the specification the fine-tune learned implicitly.**
   - Start from the training system prompt.
   - Add label definitions and decision rules for the pairs that are easy to confuse (we find them by sampling training rows per class and from dev-set errors), plus rules for edge cases: multiple IDs, other languages, sarcasm, instructions embedded in the input.
3. **Choose few-shot examples, only from `fewshot_pool.jsonl`.**
   - Start with one or two per class.
   - Add hard cases found on dev, but never anything from held-out.
   - Few-shot examples raise prompt tokens on every call. That is a real cost difference from a fine-tune, which needed only a short prompt; the dry-run token rows show the mechanism with simulated counts.
   - Keep the static part (system prompt + examples) first, so repeated prefixes can use cached-input pricing ($0.20 vs $2.00 per 1M on gpt-5.6-terra [V]).
4. **Choose the model and reasoning effort.**
   - Start on OpenAI's listed replacement base: terra for `ft-gpt-3.5-turbo`, `ft-babbage-002`, `ft-davinci-002` and `ft-o4-mini`; sol for `ft-gpt-4`; luna for `ft-gpt-4.1-nano`.
   - Sweep `reasoning_effort` on dev. gpt-5.6-terra supports none, low, medium (default), high, xhigh and max [V].
   - Set `max_completion_tokens` with headroom. Reasoning tokens count toward it, and a low cap can produce an empty answer that still costs money [V: reasoning guide].
   - Do not send `temperature`/`top_p` unless tested. OpenAI documents that GPT-6 rejects them when reasoning effort is not none; for GPT-5.6 this is [Unverified].
5. **Iterate on dev only.**
   - Each candidate gets a named config file, so the report can say exactly what was tried.
   - Two to four finalists go to held-out once.
6. **Optional bridge arm.** Only for clients still eligible to fine-tune, and only if they ask: retrain on `gpt-4.1-mini-2025-04-14` and score it on the same held-out set. Training is billed to the client's OpenAI account.

---

## 5. Step 3: evaluation design (what `eval_harness.py` computes)

All metrics are computed over **all** held-out examples. Failures count against the system; nothing is quietly dropped.

| Metric | Definition (as implemented) |
|---|---|
| Format validity | The output is one JSON object (strict parse) **and** passes the output schema (types, enums, pattern, required keys, no extra keys). |
| Strict / lenient JSON | Strict: the whole text is a JSON object. Lenient: also accepts JSON inside code fences or prose. A gap between the two means the integration needs cleanup code. |
| Exact match | Every compared field equals the expected value. Strings are compared trimmed, lower-cased and with whitespace collapsed. |
| Field accuracy | Per field, and the per-example mean across fields. |
| Label accuracy, macro-F1 | For the main categorical field. Macro-F1 averages per-class F1, so rare classes count. Per-class precision and recall are in the JSON report. |
| Refusal rate | The API `refusal` field is set, or a non-JSON answer matches the configured refusal phrases. |
| Empty or truncated | `finish_reason == "length"`, or no text and no refusal. |
| Cost | `(prompt - cached) x input price + cached x cached price + completion x output price`, from the token usage the API reports. Completion tokens include reasoning tokens. Reported per 1,000 requests. |
| Latency | Wall-clock per call: p50, p95 (nearest rank) and max. |
| Candidate minus baseline | Paired bootstrap (default 2,000 resamples, fixed seed) of the difference in label accuracy, mean field accuracy and exact match, with 95% intervals. |
| Flips | Example IDs the baseline got right and the candidate got wrong ("regressions"), and the reverse ("fixes"). We read every regression by hand. |
| Provenance | Every output row stores the model name the API reported. The report prints it next to the configured model, so a silent model change is visible. |

We run the finalists twice to show run-to-run variation, and report both runs.

---

## 6. Acceptance criteria: a measured comparison, not parity

We do **not** promise the replacement will match the old fine-tune. Before work starts, the scope paragraph fixes:
1. the held-out set, with its SHA-256;
2. the metrics above;
3. the client's **own go/no-go thresholds**, for example:
   - "format validity at least 99%";
   - "lower 95% bound of label-accuracy change at least -2 points";
   - "refusal rate at most 1%";
   - "cost at most $X per 1k requests";
   - "p95 latency at most Y ms".

**The delivery is accepted when:**
1. the comparison report covers every agreed metric for the baseline and for each finalist on the frozen held-out set, and states for each client threshold whether it was **MET or NOT MET**, with the measured value;
2. the client can reproduce the numbers by running `eval_harness.py` with the delivered config, the held-out file and their key, within the run-to-run variation the report shows;
3. the integration PR implements the recommended config (schema validation, handling of empty, truncated and refused answers, and the model name logged per call) and passes the client's CI.

Whether the measured result is good enough to ship is the **client's decision**. If thresholds are not met, the report says so plainly and lists the remaining error types and what further work could address them.

**Price and terms.** Fine-tune Replacement costs **US$2,500**: $1,250 deposit to start (the Payment Link is emailed after the one-paragraph scope is agreed) and $1,250 on delivery of the comparison report (link sent with the report).
- The deposit is refunded in full if work has not started.
- If we miss the agreed delivery date, the client may cancel and get the deposit back.
- Liability is capped at the fee paid. No guarantee of parity, quality or uptime.

---

## 7. Timeline: 3-5 business days

| Day | Work | Client needs to provide |
|---|---|---|
| 0 | One-paragraph scope and acceptance test agreed; deposit paid | Training JSONL, fine-tuned model ID, call code, staging key |
| 1 | Intake, dedupe, split, held-out frozen; **baseline recorded on the old fine-tune** | Answers to label-conflict questions |
| 2 | Output contract and schema; specification; few-shot selection; first dev runs; effort sweep | - |
| 3 | Dev iteration; finalists run on held-out (twice); comparison report drafted | - |
| 4 | Integration PR with schema validation, fallback handling and model logging | CI run, review |
| 5 | Buffer, report delivered, walkthrough | Go/no-go decision |

The 3-day track merges days 2-3 and 4-5 for small, single-output tasks.

**Calendar facts** (not pressure):
- Mon 12 Oct 2026 is a bank holiday in Canada and the US. The next business day is Tue 13 Oct [V: as recorded in `launch/payment-setup.md`].
- Calls to the old fine-tune fail from 23 Oct. For the replacement to be in production first:
  - the 5-day track needs work to start by **Thu 15 Oct** (day 5 = Wed 21 Oct);
  - the 3-day track needs a start by **Mon 19 Oct** (day 3 = Wed 21 Oct).
  - Either way, the client deploys on Thu 22 Oct at the latest.
- The baseline recording on day 1 needs only hours, but it must happen by **Thu 22 Oct**.
- We take work with a 23 Oct deadline until our calendar is full, and will say so before anyone pays.

---

## 8. The dry run (synthetic data, simulated model)

**What is bundled** (`sample_data/`, rebuilt by `build_sample_data.py`, which is deterministic):
- `synthetic_eval.jsonl`: 20 invented customer e-mails to a fictional small tea shop, each with expected `{intent, order_id, product, sentiment, needs_human}`. Hard cases are included on purpose: a French message (syn-14), two order IDs (syn-15), sarcasm (syn-16) and a prompt-injection attempt (syn-13).
- `candidate_config.json`: a rebuilt system prompt, 6 few-shot examples that are **not** in the eval set, a strict JSON schema, `gpt-5.6-terra` with `reasoning_effort: low`, verified list prices, and **example** thresholds.
- `baseline_outputs_simulated.jsonl`: invented "recordings" of an old fine-tune, mostly right, with three planted mistakes (syn-14, syn-15, syn-16).
- `synthetic_finetune_train.jsonl`: the same examples in OpenAI chat fine-tuning format, plus one duplicate, for the `--prepare` demo.

**What is simulated.**
- The candidate is a **rule-based stand-in** (keyword rules), not a model. Two failure modes are injected so that every metric shows up: syn-07 hits the token cap with an empty answer, and syn-13 is a refusal.
- Token counts are estimated from text length, reasoning tokens are invented, and latency is derived from token counts.
- **None of these numbers say anything about gpt-5.6-terra or any other model.**
- What they do show: the report's structure, the metrics, the confidence intervals, the flip lists and the threshold checks all work end to end.

### 8.1 `python3 -I eval_harness.py --dry-run` [Tested 2026-10-09]

```
==============================================================================
FINE-TUNE REPLACEMENT EVALUATION REPORT
harness: eval_harness.py, written 2026-10-09 (AI-assisted, human-reviewed)
run at: 2026-10-09 12:56:54 EDT   mode: dry-run
*** DRY RUN: synthetic data, SIMULATED candidate and SIMULATED baseline. ***
*** These numbers test the harness. They are NOT measurements of any model. ***
data: sample_data/synthetic_eval.jsonl (20 examples, sha256 c9bc9db09818...)
candidate config: candidate-A: rebuilt system prompt + 6 few-shot + strict JSON schema
candidate model (config): gpt-5.6-terra | models reported by outputs: SIMULATOR (rule-based stand-in; no model was called)
baseline: old fine-tune ft:gpt-3.5-turbo-0125:example-org::SIMULATED (recorded outputs) | models reported: ft:gpt-3.5-turbo-0125:example-org::SIMULATED
------------------------------------------------------------------------------
metric                                           baseline          candidate
format valid (strict JSON + schema)                100.0%              90.0%
strict JSON parse                                  100.0%              90.0%
lenient JSON parse (fences/prose)                  100.0%              90.0%
exact match (all fields)                            85.0%              75.0%
mean field accuracy                                 95.0%              86.0%
label accuracy                                      95.0%              85.0%
label macro-F1                                      93.2%              91.9%
refusal rate                                         0.0%               5.0%
empty or truncated                                   0.0%               5.0%
latency p50 (ms)                                      531               1675
latency p95 (ms)                                      678               2172
latency max (ms)                                      679              24735
cost per 1k requests                              $0.3949            $5.3385
tokens: prompt / completion                    1517 / 558       11757 / 6938
  of which reasoning tokens                             0               6413
------------------------------------------------------------------------------
per-field accuracy:
  intent               baseline    95.0%   candidate    85.0%
  order_id             baseline    95.0%   candidate    85.0%
  product              baseline    95.0%   candidate    90.0%
  sentiment            baseline    95.0%   candidate    80.0%
  needs_human          baseline    95.0%   candidate    90.0%
------------------------------------------------------------------------------
candidate minus baseline, paired bootstrap 95% CI (2000 resamples, seed 20261009, n=20):
  label_accuracy                 -10.0 pts   [-30.0, +10.0]
  field_accuracy_mean             -9.0 pts   [-25.0, +2.0]
  exact_match_rate               -10.0 pts   [-30.0, +10.0]
  label regressions (baseline right, candidate wrong): syn-07, syn-13, syn-16
  label fixes (baseline wrong, candidate right):       syn-14
  exact-match regressions: syn-01, syn-07, syn-13
  exact-match fixes:       syn-14
------------------------------------------------------------------------------
client-agreed thresholds (measured comparison; meeting them is not guaranteed):
  format_valid_rate_min              >= 0.99    measured 0.9000       NOT MET
  label_accuracy_delta_ci_low_min    >= -0.05   measured -0.3000      NOT MET
  field_accuracy_delta_ci_low_min    >= -0.05   measured -0.2500      NOT MET
  refusal_rate_max                   <= 0.02    measured 0.0500       NOT MET
  empty_or_truncated_rate_max        <= 0.01    measured 0.0500       NOT MET
  cost_per_1k_requests_max_usd       <= 10.0    measured 5.3385       MET
  latency_p95_max_ms                 <= 4000    measured 2172         MET
------------------------------------------------------------------------------
candidate problem cases:
  syn-01     wrong fields: sentiment
  syn-07   truncated, empty  wrong fields: intent, order_id, product, sentiment, needs_human
  syn-13   refusal  wrong fields: intent, order_id, product, sentiment, needs_human
  syn-15     wrong fields: order_id
  syn-16     wrong fields: intent, sentiment
==============================================================================
```

**How to read it, as if these were real numbers.**
- The candidate's mean differences are negative, but with n=20 every 95% interval is very wide; label accuracy runs from -30 to +10 points. This size of set cannot separate the two systems, which is why we ask for at least 100 held-out examples.
- **Regressions to read by hand:**
  - syn-07: a truncated answer that used the whole 4,000-token budget. It produced the 24.7 s max latency and almost half of the candidate's cost.
  - syn-13: a refusal of the injection attempt, where the specification wanted `other` with `needs_human: true`.
  - syn-16: sarcasm read as a return request.
- **The fix:** syn-14 (the French message).
- **What we would do next on dev:**
  - raise `max_completion_tokens` or lower effort;
  - add an injection example to the few-shot set;
  - add a sarcasm rule;
  - re-run.
- **The thresholds marked NOT MET are the honest output.** The report never hides them.
- **Cost per 1k requests is higher for the candidate** because the prompt carries the specification and examples (about 588 vs 76 prompt tokens per call here), output costs $12 vs $6 per 1M, and reasoning tokens bill as output. The token counts are simulated; the prices are real list prices.

### 8.2 `python3 -I eval_harness.py --self-test` [Tested]

```
self-test (eval_harness.py, written 2026-10-09 (AI-assisted, human-reviewed))
  strict JSON parses                                           ok
  fenced JSON: strict fails, lenient parses                    ok
  JSON inside prose: lenient parses                            ok
  empty text: no parse                                         ok
  schema: valid object                                         ok
  schema: enum, pattern, extra key, missing key all caught     ok
  schema: bool is not integer                                  ok
  scoring: field match ignores case; schema enum does not      ok
  scoring: refusal detected from text                          ok
  scoring: refusal field -> refusal, not also empty            ok
  scoring: truncation + empty                                  ok
  bootstrap: identical systems give delta 0, CI [0, 0]         ok
  macro-F1 on toy case = 0.333                                 ok
  percentile nearest-rank                                      ok
  live path: POST /v1/chat/completions with bearer auth        ok
  live path: body has model, 4 messages, response_format, effort, max tokens ok
  live path: parses content, usage, reasoning tokens, reported model ok
self-test PASSED
```

The last three checks run the real live-call code against a local mock server on 127.0.0.1. They confirm the request body (model, messages, `response_format`, `reasoning_effort`, `max_completion_tokens`, no `temperature`) and the parsing of content, usage, reasoning tokens and the reported model name, without spending money. They do **not** prove compatibility with the real OpenAI API. [Unverified against the live API]

### 8.3 `--prepare` demo [Tested]

`python3 -I eval_harness.py --prepare sample_data/synthetic_finetune_train.jsonl --out-dir dryrun_output/prepare_demo`:

```
source_rows: 27 | exact duplicates removed: 1 | conflicting duplicates: 0 | unique: 26 | skipped: 0
per label: billing_issue=4, cancel_order=3, order_status=5, other=7, product_question=3, return_request=4
heldout.jsonl 6 rows (sha256 1ec25985324a4efc...) | dev.jsonl 19 rows | fewshot_pool.jsonl 1 rows
rule: heldout.jsonl is frozen now: never used for prompt writing or few-shot selection.
```

Re-running produced byte-identical split files, so the split is deterministic.

---

## 9. Running it on real data

```
# 1. intake and split (records hashes; heldout is frozen from here on)
python3 -I eval_harness.py --prepare client_train.jsonl --out-dir work/ --label-field <field>

# 2. BEFORE 23 Oct: record the old fine-tune on heldout (config with "model": "ft:...", no schema)
python3 -I eval_harness.py --data work/heldout.jsonl --config old_ft_config.json --live \
    --save-outputs work/baseline_outputs.jsonl --max-calls 500

# 3. iterate candidates on dev, then score finalists on heldout against the recorded baseline
python3 -I eval_harness.py --data work/heldout.jsonl --config candidate_A.json --live \
    --save-outputs work/candA_run1.jsonl --max-calls 500 \
    --baseline-outputs work/baseline_outputs.jsonl --report-json work/candA_run1_report.json

# 4. re-score saved outputs at any time without new API calls
python3 -I eval_harness.py --data work/heldout.jsonl --config candidate_A.json \
    --candidate-outputs work/candA_run1.jsonl --baseline-outputs work/baseline_outputs.jsonl
```

Live mode refuses to run without `OPENAI_API_KEY`, `--save-outputs` and a `--max-calls` cap at least as large as the data. It prints a rough cost ceiling before the first call [Tested: all three refusals].

---

## 10. Limits

- No live API call was made, so nothing here measures any real model. The live path was tested only against a local mock server.
- The tool's legacy prompt/completion format support is based on earlier OpenAI docs and was not re-verified today.
- Fine-tuned models are private to the owning organization, so baseline recording needs a key from that organization.
- Rows that are tool-call-only, or multi-turn with several assistant turns, are counted and set aside by `--prepare` for manual handling.
- Whether gpt-5.6 models accept `temperature`/`top_p` at non-`none` effort is not documented in the pages we read.
- The thresholds in `candidate_config.json` are examples; each client sets their own.

## 11. Sources (all read 2026-10-09)

- Deprecations (2026-04-22 entry; self-serve fine-tuning update; Evals; reusable prompts): https://developers.openai.com/api/docs/deprecations
- Model pages:
  - https://developers.openai.com/api/docs/models/gpt-5.6-terra
  - https://developers.openai.com/api/docs/models/gpt-5.6-sol
  - https://developers.openai.com/api/docs/models/gpt-5.6-luna
- Supervised fine-tuning guide: https://developers.openai.com/api/docs/guides/supervised-fine-tuning
- Model optimization guide (fine-tuning methods table): https://developers.openai.com/api/docs/guides/model-optimization
- Pricing (fine-tuning table): https://developers.openai.com/api/docs/pricing
- Reasoning guide: https://developers.openai.com/api/docs/guides/reasoning
- GPT-6 guide (unsupported-parameter rule): https://developers.openai.com/api/docs/guides/latest-model
- Structured outputs guide: https://developers.openai.com/api/docs/guides/structured-outputs
- Chat Completions API reference (`max_completion_tokens`, `finish_reason`, `refusal`, `completion_tokens_details.reasoning_tokens`): https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
