#!/usr/bin/env python3
"""eval_harness.py - measure a prompt-based replacement for a retiring fine-tuned model.

Produced 2026-10-09 (AI-assisted, human-reviewed) for Model Sunset Desk (sample proof asset).
Standard library only. Run with `python3 -I` so nothing from the current directory is imported.

MODES
  --dry-run
      Bundled SYNTHETIC data (sample_data/) + a rule-based SIMULATOR standing in for the candidate
      model + SIMULATED recordings of the old fine-tune. No network, no API key, no cost.
      The numbers exercise the harness; they say nothing about any real model.
  --data D.jsonl --config C.json --candidate-outputs O.jsonl [--baseline-outputs B.jsonl]
      Score outputs that were already recorded (no network).
  --data D.jsonl --config C.json --live --save-outputs O.jsonl --max-calls N [--baseline-outputs B.jsonl]
      Call OpenAI Chat Completions for every example (needs OPENAI_API_KEY; use a STAGING key),
      save raw outputs (with the model name the API reports), then score.
  --prepare FT.jsonl --out-dir DIR [--label-field intent] [--heldout-frac 0.2] [--fewshot-frac 0.1]
      Convert an OpenAI fine-tuning JSONL ({"messages": [...]}, or legacy {"prompt","completion"})
      into {id,input,expected} rows, de-duplicate, and split deterministically (stratified by label)
      into heldout.jsonl / dev.jsonl / fewshot_pool.jsonl plus split_manifest.json with SHA-256 hashes.
  --self-test
      Unit checks of parsing, schema validation and metrics, plus a round trip of the live-call code
      against a local mock server on 127.0.0.1 (no external network).

FILES
  data JSONL      one object per line: {"id"?: str, "input": str|object, "expected": object|str}
  outputs JSONL   {"id", "text", "refusal", "finish_reason", "usage": {"prompt_tokens",
                  "completion_tokens", "reasoning_tokens", "cached_tokens"}, "latency_ms", "model"}
  config JSON     see sample_data/candidate_config.json

OPTIONS
  --report-json PATH   full results incl. per-example rows     --report-md PATH   same report as text
  --bootstrap N        paired bootstrap resamples (default 2000) --seed S          (default 20261009)
"""
import argparse
import hashlib
import http.server
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request

PRODUCED_BY = "AI agent"
PRODUCED_ON = "2026-10-09"
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_data")
DEFAULT_BASE_URL = "https://api.openai.com/v1"


# ----------------------------------------------------------------------------- I/O

def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as e:
                raise SystemExit("%s line %d: not valid JSON (%s)" % (path, n, e))
    return rows


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def input_text(x):
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, sort_keys=True)


def auto_id(x):
    return "ex-" + hashlib.sha256(input_text(x).encode("utf-8")).hexdigest()[:10]


def load_data(path):
    rows = load_jsonl(path)
    out, seen = [], set()
    for n, r in enumerate(rows, 1):
        if "input" not in r or "expected" not in r:
            raise SystemExit("%s row %d: needs 'input' and 'expected'" % (path, n))
        rid = str(r.get("id") or auto_id(r["input"]))
        if rid in seen:
            raise SystemExit("%s row %d: duplicate id %s" % (path, n, rid))
        seen.add(rid)
        out.append({"id": rid, "input": r["input"], "expected": r["expected"]})
    return out


# ----------------------------------------------------------------------------- parsing and schema

FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def parse_output(text):
    """Return (strict_obj, lenient_obj). strict: the whole text is one JSON object.
    lenient: also accepts ```json fences or the first {...} block inside prose."""
    if text is None or not str(text).strip():
        return None, None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, obj
    except ValueError:
        pass
    m = FENCE_RE.match(text)
    cand = m.group(1) if m else None
    if cand is None:
        a, b = text.find("{"), text.rfind("}")
        cand = text[a:b + 1] if 0 <= a < b else None
    if cand:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return None, obj
        except ValueError:
            pass
    return None, None


_TYPES = {"string": str, "boolean": bool, "object": dict, "array": list, "null": type(None)}


def _type_ok(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES.get(t, object))


def validate_schema(v, schema, path="$"):
    """Small JSON-Schema subset: type (str or list), enum, properties, required,
    additionalProperties=false, pattern, items, minimum, maximum. Returns a list of errors."""
    errs = []
    t = schema.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_type_ok(v, x) for x in ts):
            return ["%s: expected type %s, got %s" % (path, "/".join(ts), type(v).__name__)]
    if "enum" in schema and v not in schema["enum"]:
        errs.append("%s: %r not in enum" % (path, v))
    if isinstance(v, str) and "pattern" in schema and not re.search(schema["pattern"], v):
        errs.append("%s: %r does not match %s" % (path, v, schema["pattern"]))
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in schema and v < schema["minimum"]:
            errs.append("%s: below minimum" % path)
        if "maximum" in schema and v > schema["maximum"]:
            errs.append("%s: above maximum" % path)
    if isinstance(v, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in v:
                errs.append("%s: missing required key %s" % (path, k))
        if schema.get("additionalProperties") is False:
            for k in v:
                if k not in props:
                    errs.append("%s: unexpected key %s" % (path, k))
        for k, sub in props.items():
            if k in v:
                errs.extend(validate_schema(v[k], sub, path + "." + k))
    if isinstance(v, list) and "items" in schema:
        for i, item in enumerate(v):
            errs.extend(validate_schema(item, schema["items"], "%s[%d]" % (path, i)))
    return errs


def norm(v):
    if isinstance(v, str):
        return " ".join(v.strip().lower().split())
    return v


# ----------------------------------------------------------------------------- scoring

def is_refusal(rec, obj, patterns):
    if rec.get("refusal"):
        return True
    if obj is not None:
        return False
    t = (rec.get("text") or "").strip().lower()
    return bool(t) and any(p in t for p in patterns)


def score_example(ex, rec, cfg):
    fields = cfg.get("compare_fields")
    exp = ex["expected"]
    if fields is None:
        fields = sorted(exp.keys()) if isinstance(exp, dict) else ["_text"]
    schema = cfg.get("output_schema")
    text = rec.get("text")
    strict, lenient = parse_output(text)
    obj = lenient
    refusal = is_refusal(rec, obj, [p.lower() for p in cfg.get("refusal_patterns", [])])
    truncated = rec.get("finish_reason") == "length"
    empty = (text is None or not str(text).strip()) and not refusal  # a refusal is counted as refusal only
    schema_errs = validate_schema(strict, schema) if (schema and strict is not None) else []
    format_valid = strict is not None and not schema_errs
    if fields == ["_text"]:
        correct = {"_text": norm(text) == norm(exp)}
    else:
        correct = {f: (obj is not None and f in obj and norm(obj.get(f)) == norm(exp.get(f))) for f in fields}
    label_field = cfg.get("label_field")
    u = rec.get("usage") or {}
    return {
        "id": ex["id"],
        "strict_json": strict is not None,
        "lenient_json": lenient is not None,
        "schema_errors": schema_errs,
        "format_valid": format_valid,
        "refusal": refusal,
        "truncated": truncated,
        "empty": empty,
        "fields": correct,
        "field_acc": sum(correct.values()) / len(correct) if correct else 0.0,
        "exact": all(correct.values()) if correct else False,
        "label_expected": exp.get(label_field) if (label_field and isinstance(exp, dict)) else None,
        "label_predicted": (obj.get(label_field) if (label_field and obj) else None),
        "prompt_tokens": u.get("prompt_tokens") or 0,
        "completion_tokens": u.get("completion_tokens") or 0,
        "reasoning_tokens": u.get("reasoning_tokens") or 0,
        "cached_tokens": u.get("cached_tokens") or 0,
        "latency_ms": rec.get("latency_ms"),
        "model": rec.get("model"),
        "error": rec.get("error"),
    }


def percentile(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = max(1, int(math.ceil(p / 100.0 * len(vals))))
    return vals[k - 1]


def macro_f1(rows):
    labels = sorted({r["label_expected"] for r in rows if r["label_expected"] is not None})
    if not labels:
        return None, {}
    per = {}
    for c in labels:
        tp = sum(1 for r in rows if r["label_expected"] == c and r["label_predicted"] == c)
        fp = sum(1 for r in rows if r["label_expected"] != c and r["label_predicted"] == c)
        fn = sum(1 for r in rows if r["label_expected"] == c and r["label_predicted"] != c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[c] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return sum(v["f1"] for v in per.values()) / len(per), per


def cost_usd(rows, price):
    if not price or price.get("input") is None or price.get("output") is None:
        return None
    cin = price.get("cached_input")
    total = 0.0
    for r in rows:
        cached = r["cached_tokens"] if cin is not None else 0
        total += (r["prompt_tokens"] - cached) * price["input"] / 1e6
        total += cached * (cin or 0) / 1e6
        total += r["completion_tokens"] * price["output"] / 1e6  # includes reasoning tokens
    return total


def aggregate(rows, price):
    n = len(rows)
    if n == 0:
        return {"n": 0}
    m = {
        "n": n,
        "strict_json_rate": sum(r["strict_json"] for r in rows) / n,
        "lenient_json_rate": sum(r["lenient_json"] for r in rows) / n,
        "format_valid_rate": sum(r["format_valid"] for r in rows) / n,
        "exact_match_rate": sum(r["exact"] for r in rows) / n,
        "field_accuracy_mean": sum(r["field_acc"] for r in rows) / n,
        "refusal_rate": sum(r["refusal"] for r in rows) / n,
        "empty_or_truncated_rate": sum(1 for r in rows if r["empty"] or r["truncated"]) / n,
        "truncated_rate": sum(r["truncated"] for r in rows) / n,
        "errors": sum(1 for r in rows if r["error"]),
    }
    fields = list(rows[0]["fields"].keys())
    m["field_accuracy"] = {f: sum(r["fields"][f] for r in rows) / n for f in fields}
    if any(r["label_expected"] is not None for r in rows):
        m["label_accuracy"] = sum(1 for r in rows if r["label_predicted"] == r["label_expected"]) / n
        m["label_macro_f1"], m["label_per_class"] = macro_f1(rows)
    lat = [r["latency_ms"] for r in rows]
    m["latency_ms_p50"], m["latency_ms_p95"], m["latency_ms_max"] = percentile(lat, 50), percentile(lat, 95), percentile(lat, 100)
    m["tokens"] = {k: sum(r[k] for r in rows) for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cached_tokens")}
    c = cost_usd(rows, price)
    m["cost_usd_total"] = c
    m["cost_usd_per_1k_requests"] = (c / n * 1000) if c is not None else None
    m["models_reported"] = sorted({str(r["model"]) for r in rows if r["model"]})
    return m


def bootstrap_diff(a, b, n_boot, seed):
    """Paired bootstrap of mean(b) - mean(a) over the same examples. Returns (diff, lo95, hi95)."""
    n = len(a)
    diff = (sum(b) - sum(a)) / n
    rng = random.Random(seed)
    ds = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        ds.append(sum(b[i] - a[i] for i in idx) / n)
    ds.sort()
    lo = ds[int(0.025 * (n_boot - 1))]
    hi = ds[int(math.ceil(0.975 * (n_boot - 1)))]
    return diff, lo, hi


def compare(base_rows, cand_rows, n_boot, seed):
    bmap = {r["id"]: r for r in base_rows}
    pairs = [(bmap[r["id"]], r) for r in cand_rows if r["id"] in bmap]
    out = {"n_paired": len(pairs)}
    if not pairs:
        return out
    def vec(key, rows):
        if key == "label":
            return [1.0 if r["label_predicted"] == r["label_expected"] else 0.0 for r in rows]
        return [float(r[key]) for r in rows]
    bs, cs = [p[0] for p in pairs], [p[1] for p in pairs]
    for key, name in (("label", "label_accuracy"), ("field_acc", "field_accuracy_mean"), ("exact", "exact_match_rate")):
        d, lo, hi = bootstrap_diff(vec(key, bs), vec(key, cs), n_boot, seed)
        out[name + "_delta"] = {"delta": d, "ci95_low": lo, "ci95_high": hi}
    out["label_regressions"] = [c["id"] for b, c in pairs
                                if b["label_predicted"] == b["label_expected"] and c["label_predicted"] != c["label_expected"]]
    out["label_fixes"] = [c["id"] for b, c in pairs
                          if b["label_predicted"] != b["label_expected"] and c["label_predicted"] == c["label_expected"]]
    out["exact_regressions"] = [c["id"] for b, c in pairs if b["exact"] and not c["exact"]]
    out["exact_fixes"] = [c["id"] for b, c in pairs if not b["exact"] and c["exact"]]
    return out


def check_thresholds(th, cand, comp):
    if not th:
        return []
    res = []
    def add(name, measured, ok, rule):
        res.append({"threshold": name, "rule": rule, "measured": measured,
                    "result": "n/a" if ok is None else ("MET" if ok else "NOT MET")})
    def g(key, minimum=True):
        if key not in th:
            return
        lim = th[key]
        src = {"format_valid_rate_min": cand.get("format_valid_rate"),
               "refusal_rate_max": cand.get("refusal_rate"),
               "empty_or_truncated_rate_max": cand.get("empty_or_truncated_rate"),
               "cost_per_1k_requests_max_usd": cand.get("cost_usd_per_1k_requests"),
               "latency_p95_max_ms": cand.get("latency_ms_p95"),
               "label_accuracy_delta_ci_low_min": (comp.get("label_accuracy_delta") or {}).get("ci95_low"),
               "field_accuracy_delta_ci_low_min": (comp.get("field_accuracy_mean_delta") or {}).get("ci95_low")}[key]
        ok = None if src is None else (src >= lim if minimum else src <= lim)
        add(key, src, ok, (">= " if minimum else "<= ") + str(lim))
    for k in ("format_valid_rate_min", "label_accuracy_delta_ci_low_min", "field_accuracy_delta_ci_low_min"):
        g(k, True)
    for k in ("refusal_rate_max", "empty_or_truncated_rate_max", "cost_per_1k_requests_max_usd", "latency_p95_max_ms"):
        g(k, False)
    return res


# ----------------------------------------------------------------------------- dry-run simulator

CATALOG_ALIASES = {"teapot": "ceramic teapot"}
SIM_INJECT = {
    # injected failure modes so every metric is exercised (NOT a claim about any real model)
    "syn-07": "truncated",  # reasoning used the whole token budget: finish_reason=length, empty text
    "syn-13": "refusal",    # model refuses the prompt-injection message instead of classifying it
}


def _h(s, mod):
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16) % mod


def simulate_candidate(examples, cfg):
    """Deterministic rule-based STAND-IN for a model. It exists only so --dry-run can show every
    part of the report without an API key. Its accuracy means nothing about gpt-5.6-* models."""
    catalog = []
    try:
        catalog = [c for c in cfg["output_schema"]["properties"]["product"]["enum"] if c]
    except (KeyError, TypeError):
        pass
    prefix_chars = len(cfg.get("system_prompt", "")) + sum(
        len(input_text(f["input"])) + len(json.dumps(f["output"])) for f in cfg.get("few_shot", []))
    out = []
    for ex in examples:
        t = input_text(ex["input"])
        low = t.lower()
        if "cancel" in low or "annuler" in low:
            intent = "cancel_order"
        elif any(k in low for k in ("charged", "charge", "refund still", "card")):
            intent = "billing_issue"
        elif any(k in low for k in ("return", "send it back", "missing", "cracked", "broken")):
            intent = "return_request"
        elif any(k in low for k in ("status", "where is", "ship?", "delivered", "never came")) or \
                ("when" in low and "ship" in low):
            intent = "order_status"
        elif "?" in t and any(c in low for c in catalog):
            intent = "product_question"
        else:
            intent = "other"
        ids = re.findall(r"\bA\d{5}\b", t)
        product = next((c for c in catalog if c in low), None)
        if product is None:
            product = next((v for k, v in CATALOG_ALIASES.items() if re.search(r"\b%s\b" % k, low)), None)
        pos = sum(low.count(w) for w in ("amazing", "best", "thank", "great", "love"))
        neg = sum(low.count(w) for w in ("cracked", "unacceptable", "twice", "broken", "nothing", "never",
                                          "chargeback", "hasn't", "missing", "why"))
        sentiment = "negative" if neg > pos else ("positive" if pos > neg else "neutral")
        needs_human = any(k in low for k in ("chargeback", "unacceptable", "ignore your previous",
                                              "four times", "third time", "another"))
        obj = {"intent": intent, "order_id": ids[0] if ids else None, "product": product,
               "sentiment": sentiment, "needs_human": needs_human}
        text, refusal, finish = json.dumps(obj), None, "stop"
        reasoning = 40 + _h(ex["id"], 160)
        mode = SIM_INJECT.get(ex["id"])
        if mode == "truncated":
            text, finish, reasoning = "", "length", int(cfg.get("max_completion_tokens") or 4000)
        elif mode == "refusal":
            text, refusal = None, "I'm sorry, but I can't help with that request."
        visible = len(text or refusal or "") // 4
        completion = reasoning + (0 if mode == "truncated" else visible)
        out.append({
            "id": ex["id"], "text": text, "refusal": refusal, "finish_reason": finish,
            "usage": {"prompt_tokens": (prefix_chars + len(t)) // 4, "completion_tokens": completion,
                      "reasoning_tokens": reasoning, "cached_tokens": 0},
            "latency_ms": 650 + 6 * completion + _h(ex["id"] + "lat", 300),
            "model": "SIMULATOR (rule-based stand-in; no model was called)",
        })
    return out


# ----------------------------------------------------------------------------- live calls

def build_messages(cfg, user_input):
    msgs = []
    if cfg.get("system_prompt"):
        msgs.append({"role": "system", "content": cfg["system_prompt"]})
    for fs in cfg.get("few_shot", []):
        msgs.append({"role": "user", "content": input_text(fs["input"])})
        o = fs["output"]
        msgs.append({"role": "assistant", "content": o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)})
    msgs.append({"role": "user", "content": input_text(user_input)})
    return msgs


def build_body(cfg, user_input):
    body = {"model": cfg["model"], "messages": build_messages(cfg, user_input)}
    for k in ("max_completion_tokens", "reasoning_effort", "response_format", "temperature", "top_p", "seed",
              "verbosity"):
        if cfg.get(k) is not None:
            body[k] = cfg[k]
    return body


def call_chat_completions(cfg, user_input, api_key, base_url, timeout, tries=3):
    body = json.dumps(build_body(cfg, user_input)).encode("utf-8")
    url = base_url.rstrip("/") + "/chat/completions"
    last_err = None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            ms = round((time.perf_counter() - t0) * 1000)
            ch = (data.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            u = data.get("usage") or {}
            return {"text": msg.get("content"), "refusal": msg.get("refusal"),
                    "finish_reason": ch.get("finish_reason"),
                    "usage": {"prompt_tokens": u.get("prompt_tokens"),
                              "completion_tokens": u.get("completion_tokens"),
                              "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                              "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens")},
                    "latency_ms": ms, "model": data.get("model")}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last_err = "HTTP %s: %s" % (e.code, detail)
            if e.code not in (408, 409, 429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = "network: %s" % e
        time.sleep(min(8, 2 ** attempt))
    return {"text": None, "refusal": None, "finish_reason": None, "usage": {}, "latency_ms": None,
            "model": cfg.get("model"), "error": last_err}


def run_live(examples, cfg, args):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("--live needs OPENAI_API_KEY in the environment (use a staging key you can revoke)")
    if not args.save_outputs or args.max_calls is None:
        raise SystemExit("--live needs --save-outputs PATH and --max-calls N")
    if len(examples) > args.max_calls:
        raise SystemExit("%d examples but --max-calls %d; refusing" % (len(examples), args.max_calls))
    price = cfg.get("price_per_1m_tokens") or {}
    est_prompt = sum(len(json.dumps(build_messages(cfg, e["input"]))) // 4 for e in examples)
    ceiling = None
    if price.get("input") is not None and price.get("output") is not None:
        ceiling = est_prompt * price["input"] / 1e6 + len(examples) * (cfg.get("max_completion_tokens") or 0) * price["output"] / 1e6
    print("LIVE: %d calls to %s model=%s; rough cost ceiling %s (prompt ~%d tokens est., output capped by max_completion_tokens)"
          % (len(examples), args.base_url, cfg["model"], ("$%.2f" % ceiling) if ceiling is not None else "n/a", est_prompt))
    recs = []
    for i, ex in enumerate(examples, 1):
        r = call_chat_completions(cfg, ex["input"], key, args.base_url, cfg.get("timeout_s", 60))
        r["id"] = ex["id"]
        recs.append(r)
        if i % 10 == 0 or i == len(examples):
            print("  %d/%d done" % (i, len(examples)))
    write_jsonl(args.save_outputs, recs)
    print("saved raw outputs to %s (re-score later with --candidate-outputs)" % args.save_outputs)
    return recs


# ----------------------------------------------------------------------------- prepare (intake + split)

def prepare(src, out_dir, label_field, heldout_frac, fewshot_frac, seed):
    rows = load_jsonl(src)
    items, systems, skipped = [], {}, 0
    for r in rows:
        if "messages" in r:
            msgs = r["messages"]
            for m in msgs:
                if m.get("role") == "system":
                    systems[m.get("content", "")] = systems.get(m.get("content", ""), 0) + 1
            a_idx = max((i for i, m in enumerate(msgs) if m.get("role") == "assistant"), default=None)
            u_idx = max((i for i, m in enumerate(msgs[:a_idx] if a_idx is not None else []) if m.get("role") == "user"), default=None)
            if a_idx is None or u_idx is None or not isinstance(msgs[a_idx].get("content"), str):
                skipped += 1  # tool-call-only or malformed rows need manual handling
                continue
            inp, out = msgs[u_idx]["content"], msgs[a_idx]["content"]
        elif "prompt" in r and "completion" in r:  # legacy babbage-002/davinci-002 format
            inp, out = r["prompt"], r["completion"]
        else:
            skipped += 1
            continue
        try:
            exp = json.loads(out)
        except ValueError:
            exp = out
        items.append({"input": inp, "expected": exp})
    # de-duplicate on normalised input; flag conflicting labels
    seen, uniq, dupes, conflicts = {}, [], 0, []
    for it in items:
        k = " ".join(input_text(it["input"]).lower().split())
        if k in seen:
            dupes += 1
            if seen[k]["expected"] != it["expected"]:
                conflicts.append(input_text(it["input"])[:80])
            continue
        seen[k] = it
        uniq.append(it)
    for it in uniq:
        it["id"] = auto_id(it["input"])
    # stratified deterministic split
    groups = {}
    for it in uniq:
        lab = it["expected"].get(label_field) if (label_field and isinstance(it["expected"], dict)) else "_all"
        groups.setdefault(str(lab), []).append(it)
    held, few, dev = [], [], []
    for lab in sorted(groups):
        g = sorted(groups[lab], key=lambda it: hashlib.sha256((str(seed) + it["id"]).encode()).hexdigest())
        nh = int(round(heldout_frac * len(g)))
        if len(g) >= 2 and nh == 0:
            nh = 1
        nf = int(round(fewshot_frac * len(g)))
        held += g[:nh]
        few += g[nh:nh + nf]
        dev += g[nh + nf:]
    os.makedirs(out_dir, exist_ok=True)
    files = {}
    prov = ("split=%s by eval_harness.py --prepare (harness written by model %s on %s); seed=%s; source=%s"
            % ("{split}", PRODUCED_BY, PRODUCED_ON, seed, os.path.basename(src)))
    for name, part in (("heldout.jsonl", held), ("dev.jsonl", dev), ("fewshot_pool.jsonl", few)):
        p = os.path.join(out_dir, name)
        split = name.split(".")[0]
        write_jsonl(p, [{"id": it["id"], "input": it["input"], "expected": it["expected"],
                         "_provenance": prov.replace("{split}", split)} for it in part])
        files[name] = {"rows": len(part), "sha256": sha256_file(p)}
    common_system = max(systems.items(), key=lambda kv: kv[1]) if systems else ("", 0)
    with open(os.path.join(out_dir, "system_prompt_from_training.json"), "w", encoding="utf-8") as f:
        json.dump({"_provenance": "most common system prompt in %s, extracted by eval_harness.py --prepare "
                                  "(harness written by model %s on %s)" % (os.path.basename(src), PRODUCED_BY, PRODUCED_ON),
                   "system_prompt": common_system[0], "rows_using_it": common_system[1],
                   "distinct_system_prompts": len(systems)}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    manifest = {
        "produced_by": "eval_harness.py --prepare (harness written by model %s on %s)" % (PRODUCED_BY, PRODUCED_ON),
        "source_file": os.path.basename(src), "source_sha256": sha256_file(src), "source_rows": len(rows),
        "skipped_rows": skipped, "exact_duplicates_removed": dupes, "conflicting_duplicates": conflicts,
        "unique_examples": len(uniq), "label_field": label_field, "seed": seed,
        "heldout_frac": heldout_frac, "fewshot_frac": fewshot_frac,
        "per_label": {lab: len(g) for lab, g in sorted(groups.items())},
        "files": files,
        "rule": "heldout.jsonl is frozen now: never used for prompt writing or few-shot selection.",
    }
    with open(os.path.join(out_dir, "split_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return manifest


# ----------------------------------------------------------------------------- report

def pct(x):
    return "n/a" if x is None else "%.1f%%" % (100 * x)


def usd(x):
    return "n/a (price not supplied)" if x is None else "$%.4f" % x


def render(report):
    L = []
    w = L.append
    w("=" * 78)
    w("FINE-TUNE REPLACEMENT EVALUATION REPORT")
    w("harness: eval_harness.py, written by model %s on %s" % (PRODUCED_BY, PRODUCED_ON))
    w("run at: %s   mode: %s" % (report["run_at"], report["mode"]))
    if report["mode"] == "dry-run":
        w("*** DRY RUN: synthetic data, SIMULATED candidate and SIMULATED baseline. ***")
        w("*** These numbers test the harness. They are NOT measurements of any model. ***")
    w("data: %s (%d examples, sha256 %s...)" % (report["data_file"], report["n"], report["data_sha256"][:12]))
    w("candidate config: %s" % report["config_name"])
    w("candidate model (config): %s | models reported by outputs: %s"
      % (report["config_model"], ", ".join(report["candidate"].get("models_reported", [])) or "n/a"))
    if report.get("baseline"):
        w("baseline: %s | models reported: %s" % (report["baseline_name"],
                                                  ", ".join(report["baseline"].get("models_reported", [])) or "n/a"))
    w("-" * 78)
    rows = [("format valid (strict JSON + schema)", "format_valid_rate", pct),
            ("strict JSON parse", "strict_json_rate", pct),
            ("lenient JSON parse (fences/prose)", "lenient_json_rate", pct),
            ("exact match (all fields)", "exact_match_rate", pct),
            ("mean field accuracy", "field_accuracy_mean", pct),
            ("label accuracy", "label_accuracy", pct),
            ("label macro-F1", "label_macro_f1", pct),
            ("refusal rate", "refusal_rate", pct),
            ("empty or truncated", "empty_or_truncated_rate", pct),
            ("latency p50 (ms)", "latency_ms_p50", lambda v: "n/a" if v is None else "%d" % v),
            ("latency p95 (ms)", "latency_ms_p95", lambda v: "n/a" if v is None else "%d" % v),
            ("latency max (ms)", "latency_ms_max", lambda v: "n/a" if v is None else "%d" % v),
            ("cost per 1k requests", "cost_usd_per_1k_requests", usd)]
    b, c = report.get("baseline") or {}, report["candidate"]
    w("%-38s %18s %18s" % ("metric", "baseline", "candidate"))
    for label, key, fmt in rows:
        w("%-38s %18s %18s" % (label, fmt(b.get(key)) if b else "-", fmt(c.get(key))))
    w("%-38s %18s %18s" % ("tokens: prompt / completion",
                           ("%d / %d" % (b["tokens"]["prompt_tokens"], b["tokens"]["completion_tokens"])) if b else "-",
                           "%d / %d" % (c["tokens"]["prompt_tokens"], c["tokens"]["completion_tokens"])))
    w("%-38s %18s %18s" % ("  of which reasoning tokens", str(b["tokens"]["reasoning_tokens"]) if b else "-",
                           str(c["tokens"]["reasoning_tokens"])))
    w("-" * 78)
    w("per-field accuracy:")
    for f in c.get("field_accuracy", {}):
        w("  %-20s baseline %8s   candidate %8s" % (f, pct((b.get("field_accuracy") or {}).get(f)) if b else "-",
                                                    pct(c["field_accuracy"][f])))
    comp = report.get("comparison") or {}
    if comp.get("n_paired"):
        w("-" * 78)
        w("candidate minus baseline, paired bootstrap 95%% CI (%d resamples, seed %d, n=%d):"
          % (report["bootstrap"], report["seed"], comp["n_paired"]))
        for k in ("label_accuracy_delta", "field_accuracy_mean_delta", "exact_match_rate_delta"):
            d = comp[k]
            w("  %-28s %+7.1f pts   [%+.1f, %+.1f]" % (k.replace("_delta", ""), 100 * d["delta"],
                                                       100 * d["ci95_low"], 100 * d["ci95_high"]))
        w("  label regressions (baseline right, candidate wrong): %s" % (", ".join(comp["label_regressions"]) or "none"))
        w("  label fixes (baseline wrong, candidate right):       %s" % (", ".join(comp["label_fixes"]) or "none"))
        w("  exact-match regressions: %s" % (", ".join(comp["exact_regressions"]) or "none"))
        w("  exact-match fixes:       %s" % (", ".join(comp["exact_fixes"]) or "none"))
    if report.get("thresholds"):
        w("-" * 78)
        w("client-agreed thresholds (measured comparison; meeting them is not guaranteed):")
        for t in report["thresholds"]:
            mv = t["measured"]
            mvs = "n/a" if mv is None else ("%.4f" % mv if isinstance(mv, float) else str(mv))
            w("  %-34s %-10s measured %-12s %s" % (t["threshold"], t["rule"], mvs, t["result"]))
    w("-" * 78)
    w("candidate problem cases:")
    any_p = False
    for r in report["candidate_rows"]:
        tags = [k for k in ("refusal", "truncated", "empty") if r[k]]
        if r["schema_errors"]:
            tags.append("schema: " + "; ".join(r["schema_errors"])[:80])
        if not r["strict_json"] and r["lenient_json"]:
            tags.append("needed lenient parse")
        wrong = [f for f, ok in r["fields"].items() if not ok]
        if tags or wrong:
            any_p = True
            w("  %-8s %s%s" % (r["id"], ", ".join(tags), ("  wrong fields: " + ", ".join(wrong)) if wrong else ""))
    if not any_p:
        w("  none")
    w("=" * 78)
    return "\n".join(L)


def build_report(mode, data_path, examples, cfg, cand_recs, base_recs, n_boot, seed):
    by_id = {r["id"]: r for r in cand_recs}
    missing = [e["id"] for e in examples if e["id"] not in by_id]
    if missing:
        raise SystemExit("candidate outputs missing for %d ids, e.g. %s" % (len(missing), missing[:5]))
    cand_rows = [score_example(e, by_id[e["id"]], cfg) for e in examples]
    report = {
        "harness_produced_by": PRODUCED_BY, "harness_produced_on": PRODUCED_ON,
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "mode": mode,
        "data_file": os.path.relpath(data_path, HERE) if data_path.startswith(HERE) else data_path,
        "data_sha256": sha256_file(data_path), "n": len(examples),
        "config_name": cfg.get("name"), "config_model": cfg.get("model"),
        "candidate": aggregate(cand_rows, cfg.get("price_per_1m_tokens")),
        "candidate_rows": cand_rows, "bootstrap": n_boot, "seed": seed,
    }
    comp = {}
    if base_recs is not None:
        bmap = {r["id"]: r for r in base_recs}
        base_rows = [score_example(e, bmap[e["id"]], cfg) for e in examples if e["id"] in bmap]
        bcfg = cfg.get("baseline") or {}
        report["baseline_name"] = bcfg.get("name", "baseline (recorded outputs)")
        report["baseline"] = aggregate(base_rows, bcfg.get("price_per_1m_tokens"))
        report["baseline_rows"] = base_rows
        comp = compare(base_rows, cand_rows, n_boot, seed)
        report["comparison"] = comp
    report["thresholds"] = check_thresholds({k: v for k, v in (cfg.get("thresholds") or {}).items()
                                             if not k.startswith("_")}, report["candidate"], comp)
    return report


# ----------------------------------------------------------------------------- self-test

def self_test():
    ok = True
    def check(name, cond):
        nonlocal ok
        print("  %-60s %s" % (name, "ok" if cond else "FAIL"))
        ok = ok and cond
    print("self-test (eval_harness.py, written by model %s on %s)" % (PRODUCED_BY, PRODUCED_ON))
    s, l = parse_output('{"a": 1}')
    check("strict JSON parses", s == {"a": 1} and l == {"a": 1})
    s, l = parse_output('```json\n{"a": 1}\n```')
    check("fenced JSON: strict fails, lenient parses", s is None and l == {"a": 1})
    s, l = parse_output('Sure! Here it is: {"a": 1} hope that helps')
    check("JSON inside prose: lenient parses", s is None and l == {"a": 1})
    check("empty text: no parse", parse_output("") == (None, None) and parse_output(None) == (None, None))
    sch = {"type": "object", "properties": {"x": {"type": "string", "enum": ["a", "b"]},
                                            "y": {"type": ["string", "null"], "pattern": "^A[0-9]{5}$"}},
           "required": ["x", "y"], "additionalProperties": False}
    check("schema: valid object", validate_schema({"x": "a", "y": None}, sch) == [])
    check("schema: enum, pattern, extra key, missing key all caught",
          len(validate_schema({"x": "c", "y": "B1", "z": 1}, sch)) == 3 and
          len(validate_schema({"x": "a"}, sch)) == 1)
    check("schema: bool is not integer", validate_schema(True, {"type": "integer"}) != [])
    cfg = {"compare_fields": ["x", "y"], "label_field": "x", "output_schema": sch,
           "refusal_patterns": ["i can't help"]}
    ex = {"id": "t1", "expected": {"x": "a", "y": "A12345"}}
    r = score_example(ex, {"text": '{"x":"A","y":"A12345"}', "finish_reason": "stop"}, cfg)
    check("scoring: field match ignores case; schema enum does not",
          r["exact"] is True and r["format_valid"] is False)
    r = score_example(ex, {"text": "I can't help with that.", "finish_reason": "stop"}, cfg)
    check("scoring: refusal detected from text", r["refusal"] and not r["exact"])
    r = score_example(ex, {"text": None, "refusal": "No.", "finish_reason": "stop"}, cfg)
    check("scoring: refusal field -> refusal, not also empty", r["refusal"] and not r["empty"])
    r = score_example(ex, {"text": "", "finish_reason": "length"}, cfg)
    check("scoring: truncation + empty", r["truncated"] and r["empty"] and r["field_acc"] == 0)
    d, lo, hi = bootstrap_diff([1, 1, 0, 0], [1, 1, 0, 0], 200, 1)
    check("bootstrap: identical systems give delta 0, CI [0, 0]", d == 0 and lo == 0 and hi == 0)
    f1, _ = macro_f1([{"label_expected": "a", "label_predicted": "a"}, {"label_expected": "b", "label_predicted": "a"}])
    check("macro-F1 on toy case = 0.333", abs(f1 - (2 / 3 + 0) / 2) < 1e-9)
    check("percentile nearest-rank", percentile([1, 2, 3, 4], 50) == 2 and percentile([1, 2, 3, 4], 95) == 4)

    # live-call code path against a local mock server (127.0.0.1 only)
    seen = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            seen["body"] = json.loads(self.rfile.read(n))
            seen["auth"] = self.headers.get("Authorization")
            seen["path"] = self.path
            payload = {"model": "mock-model-2026", "choices": [{"index": 0, "finish_reason": "stop",
                       "message": {"role": "assistant", "content": '{"x":"a","y":null}', "refusal": None}}],
                       "usage": {"prompt_tokens": 50, "completion_tokens": 30,
                                 "completion_tokens_details": {"reasoning_tokens": 20},
                                 "prompt_tokens_details": {"cached_tokens": 0}}}
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        lcfg = {"model": "gpt-5.6-terra", "system_prompt": "S", "few_shot": [{"input": "i", "output": {"x": "b"}}],
                "max_completion_tokens": 100, "reasoning_effort": "low",
                "response_format": {"type": "json_schema", "json_schema": {"name": "t", "strict": True, "schema": sch}}}
        rec = call_chat_completions(lcfg, "hello", "sk-test-not-real", "http://127.0.0.1:%d/v1" % srv.server_port, 5)
    finally:
        srv.shutdown()
    b = seen.get("body", {})
    check("live path: POST /v1/chat/completions with bearer auth",
          seen.get("path") == "/v1/chat/completions" and seen.get("auth") == "Bearer sk-test-not-real")
    check("live path: body has model, 4 messages, response_format, effort, max tokens",
          b.get("model") == "gpt-5.6-terra" and len(b.get("messages", [])) == 4 and
          b.get("response_format", {}).get("type") == "json_schema" and b.get("reasoning_effort") == "low" and
          b.get("max_completion_tokens") == 100 and "temperature" not in b)
    check("live path: parses content, usage, reasoning tokens, reported model",
          rec.get("text") == '{"x":"a","y":null}' and rec["usage"]["reasoning_tokens"] == 20 and
          rec.get("model") == "mock-model-2026" and rec.get("latency_ms") is not None)
    print("self-test %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


# ----------------------------------------------------------------------------- main

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--prepare")
    ap.add_argument("--out-dir")
    ap.add_argument("--label-field", default="intent")
    ap.add_argument("--heldout-frac", type=float, default=0.2)
    ap.add_argument("--fewshot-frac", type=float, default=0.1)
    ap.add_argument("--data")
    ap.add_argument("--config")
    ap.add_argument("--candidate-outputs")
    ap.add_argument("--baseline-outputs")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--save-outputs")
    ap.add_argument("--max-calls", type=int)
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--report-json")
    ap.add_argument("--report-md")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261009)
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    if a.prepare:
        if not a.out_dir:
            raise SystemExit("--prepare needs --out-dir")
        m = prepare(a.prepare, a.out_dir, a.label_field, a.heldout_frac, a.fewshot_frac, a.seed)
        print(json.dumps(m, indent=2, ensure_ascii=False))
        return 0

    if a.dry_run:
        data_path = os.path.join(SAMPLE, "synthetic_eval.jsonl")
        cfg = json.load(open(os.path.join(SAMPLE, "candidate_config.json"), encoding="utf-8"))
        examples = load_data(data_path)
        cand = simulate_candidate(examples, cfg)
        base = load_jsonl(os.path.join(SAMPLE, "baseline_outputs_simulated.jsonl"))
        mode = "dry-run"
    else:
        if not (a.data and a.config):
            ap.error("need --dry-run, --self-test, --prepare, or --data with --config")
        data_path = a.data
        cfg = json.load(open(a.config, encoding="utf-8"))
        examples = load_data(data_path)
        base = load_jsonl(a.baseline_outputs) if a.baseline_outputs else None
        if a.live:
            cand = run_live(examples, cfg, a)
            mode = "live"
        elif a.candidate_outputs:
            cand = load_jsonl(a.candidate_outputs)
            mode = "recorded"
        else:
            ap.error("give --candidate-outputs (recorded) or --live")
    report = build_report(mode, data_path, examples, cfg, cand, base, a.bootstrap, a.seed)
    text = render(report)
    print(text)
    if a.report_json:
        with open(a.report_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
    if a.report_md:
        with open(a.report_md, "w", encoding="utf-8") as f:
            f.write("<!-- Produced by eval_harness.py (written by model %s on %s) -->\n```\n%s\n```\n"
                    % (PRODUCED_BY, PRODUCED_ON, text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
