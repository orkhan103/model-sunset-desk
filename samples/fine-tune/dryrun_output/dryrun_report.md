<!-- Produced by eval_harness.py (written 2026-10-09 (AI-assisted, human-reviewed)) -->
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
