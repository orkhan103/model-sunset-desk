#!/usr/bin/env python3
"""Swap & Verify regression harness for Otter Blocks' OpenAI prompt-template features.

Produced 2026-10-09 (AI-assisted, human-reviewed) (Model Sunset Desk sample; AI-assisted, human-reviewed).

What it does
  For each case in cases.jsonl it builds the exact Chat Completions request Otter 3.2.7 sends on its
  OpenAI-key path (template + {ACTION}/{INSERT_TASK} substitution + the "regenerate" temperature),
  then runs it against:
    * the OLD arm: the request as sent today (template pins gpt-3.5-turbo, legacy functions/function_call);
    * one NEW arm per --candidate: the same request after the patch.diff server-side transform
      (model swap, reasoning_effort, sampling-parameter handling, functions -> tools).
  It records HTTP status, output format validity, refusals, length, latency, token usage and a cost
  estimate from pricing.json, then writes results.jsonl, requests.jsonl and comparison.md.

Modes
  --dry-run   No network, no key. Replays mock responses from mocks/*.jsonl (synthetic fixtures).
  --live      Calls https://api.openai.com/v1/chat/completions with YOUR key from the OPENAI_API_KEY
              environment variable. Guarded by --max-cost-usd and an explicit confirmation (--yes).
  The harness never ships, prints or writes an API key.

Python 3.8+ standard library only. Example:
  python3 -I run_harness.py --dry-run --out out/dry-run
  OPENAI_API_KEY=sk-... python3 -I run_harness.py --live --templates otter-prompts.json --max-cost-usd 0.50 --yes
"""

import argparse
import copy
import datetime
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

HARNESS_VERSION = "1.0.0"
AUTHORED_BY = "AI agent"
AUTHORED_ON = "2026-10-09"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
HERE = os.path.dirname(os.path.abspath(__file__))
ABSENT = object()

# Mirror of patch.diff RETIRING_MODEL_REPLACEMENTS (source: developers.openai.com/api/docs/deprecations,
# shutdown 2026-10-23, read 2026-10-09).
RETIRING_MODEL_REPLACEMENTS = {
    "gpt-3.5-turbo": "gpt-5.6-terra", "gpt-3.5-turbo-0125": "gpt-5.6-terra",
    "o4-mini": "gpt-5.6-terra", "o4-mini-2025-04-16": "gpt-5.6-terra",
    "gpt-4": "gpt-5.6-sol", "gpt-4-0613": "gpt-5.6-sol", "gpt-4-turbo": "gpt-5.6-sol",
    "gpt-4-turbo-2024-04-09": "gpt-5.6-sol", "gpt-4-1106-preview": "gpt-5.6-sol",
    "gpt-4o-2024-05-13": "gpt-5.6-sol", "o1": "gpt-5.6-sol", "o1-2024-12-17": "gpt-5.6-sol",
    "o3-mini": "gpt-5.6-sol", "o3-mini-2025-01-31": "gpt-5.6-sol",
    "gpt-4.1-nano": "gpt-5.6-luna", "gpt-4.1-nano-2025-04-14": "gpt-5.6-luna",
}

# Otter 3.2.7 block-editor JS: form field type -> block. Unknown types are silently dropped by the editor.
FORM_TYPE_TO_BLOCK = {
    "text": "form-input", "email": "form-input", "password": "form-input", "number": "form-input",
    "tel": "form-input", "url": "form-input", "date": "form-input", "time": "form-input",
    "select": "form-multiple-choice", "checkbox": "form-multiple-choice", "radio": "form-multiple-choice",
    "file": "form-file", "textarea": "form-textarea",
}
HTML_ALLOWED = {"p", "h1", "h2", "h3", "h4", "ul", "li", "table", "tr", "td", "th", "strong", "em", "b", "i", "u", "a", "img"}
HTML_TOLERATED = {"ol", "thead", "tbody", "br", "h5", "h6", "span", "blockquote"}
HTML_FORBIDDEN = {"html", "head", "body", "footer", "script", "style", "iframe", "header"}
REFUSAL_RE = re.compile(
    r"^\s*(<[^>]+>\s*)*(i[’']?m sorry|i am sorry|sorry, but|i can[’']?t|i cannot|i won[’']?t|i[’']?m unable|i am unable|"
    r"i[’']?m not able|je suis désolé|je ne peux pas|lo siento|no puedo)",
    re.IGNORECASE,
)
STOPWORDS = {
    "en": {"the", "and", "your", "for", "with", "you", "our", "of", "to", "is"},
    "fr": {"le", "la", "les", "des", "et", "pour", "votre", "vous", "nos", "du", "une"},
    "es": {"el", "los", "las", "para", "su", "por", "y", "tu", "nuestro", "del", "una"},
}


# ---------------------------------------------------------------------------- loading

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError as exc:
                    sys.exit("%s:%d invalid JSON: %s" % (path, n, exc))
    return rows


def load_templates(path):
    """Accepts the site's raw otter_prompts array or the sample file's {"templates": [...]} object."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    templates = doc["templates"] if isinstance(doc, dict) else doc
    by_name = {t.get("otter_name"): t for t in templates if isinstance(t, dict)}
    slugs = {"free": [], "pro": []}
    pp = by_name.get("patternsPicker")
    if pp:
        sys_text = " ".join(m.get("content", "") for m in pp.get("messages", []) if m.get("role") == "system")
        slugs["free"] = re.findall(r"- `([a-z0-9-]+)`", sys_text)
        pro_text = " ".join(m.get("content", "") for m in pp.get("otter_pro_addon", []) if isinstance(m, dict))
        slugs["pro"] = re.findall(r"- `([a-z0-9-]+)`", pro_text)
    return by_name, slugs


def load_pricing(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------- request building

def build_client_payload(template, case):
    """Mirror of Otter 3.2.7 build/blocks/blocks.js prompt-template path (module 3907, functions _, mT, rM).

    textTransformation: {ACTION} <- template.otter_action_prompt (the AI Block always uses this action).
    patternsPicker + Pro: each otter_pro_addon message is inserted before the last user message.
    {INSERT_TASK} <- the user's text. otter_* keys are removed (server strips them too).
    Regenerate uses the temperature 1.3 variant; both variants add stream:false.
    """
    t = copy.deepcopy(template)
    if case["feature"] == "textTransformation":
        action = t.get("otter_action_prompt", "")
        t["messages"] = [
            {"role": m["role"], "content": m["content"].replace("{ACTION}", action)}
            if m.get("role") == "user" and "{ACTION}" in m.get("content", "") else m
            for m in t["messages"]
        ]
    if case["feature"] == "patternsPicker" and case.get("pro"):
        for addon in t.get("otter_pro_addon", []) or []:
            roles = [m.get("role") for m in t["messages"]]
            last_user = len(roles) - 1 - roles[::-1].index("user") if "user" in roles else -1
            if last_user >= 0:
                t["messages"] = t["messages"][:last_user] + [addon] + t["messages"][last_user:]
    t["messages"] = [
        {"role": m["role"], "content": m["content"].replace("{INSERT_TASK}", case["input"])}
        if m.get("role") == "user" and "{INSERT_TASK}" in m.get("content", "") else m
        for m in t["messages"]
    ]
    payload = {k: v for k, v in t.items() if not k.startswith("otter_")}
    payload.update({"temperature": 1.3, "stream": False} if case.get("regenerate") else {"stream": False})
    return payload


def supports_reasoning_effort_none(model):
    return re.match(r"^gpt-5\.6(-(sol|terra|luna))?$", model or "") is not None


def patched_server_transform(payload, replacements, swap_effort="none", keep_sampling=False):
    """Python mirror of patch.diff Otter_OpenAI_Backend::adapt_payload() + the existing max_tokens rename."""
    p = copy.deepcopy(payload)
    requested = p.get("model") if isinstance(p.get("model"), str) else ""
    model = replacements.get(requested, requested) if requested else ""
    if model and model != requested:
        p["model"] = model
        if "reasoning_effort" not in p and not re.match(r"^o[1-9]", requested) and supports_reasoning_effort_none(model):
            if swap_effort:
                p["reasoning_effort"] = swap_effort
    if re.match(r"^(gpt-5|o[1-9])", model or "") and not keep_sampling:
        for k in ("temperature", "top_p", "logprobs", "top_logprobs"):
            p.pop(k, None)
    if isinstance(p.get("functions"), list) and "tools" not in p:
        tools = [{"type": "function", "function": f} for f in p["functions"] if isinstance(f, dict) and f.get("name")]
        if tools:
            fc = p.get("function_call")
            if isinstance(fc, dict) and fc.get("name"):
                p["tool_choice"] = {"type": "function", "function": {"name": str(fc["name"])}}
            elif fc in ("none", "auto"):
                p["tool_choice"] = fc
            p["tools"] = tools
            p.pop("functions", None)
            p.pop("function_call", None)
    if "max_tokens" in p:  # existing 3.2.7 behaviour, unchanged by the patch
        p["max_completion_tokens"] = p.pop("max_tokens")
    return p


# ---------------------------------------------------------------------------- transport

def post_chat(payload, api_key, timeout, retries=2):
    body = json.dumps(payload).encode("utf-8")
    attempt = 0
    while True:
        req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
            "Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            status = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raw = json.dumps({"error": {"code": "network_error", "message": str(exc)[:300]}})
            status = 0
        latency_ms = int((time.monotonic() - t0) * 1000)
        if status in (0, 429, 500, 502, 503, 504) and attempt < retries:
            attempt += 1
            time.sleep(1.5 * (2 ** (attempt - 1)))
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {"error": {"code": "non_json_response", "message": raw[:300]}}
        return status, parsed, latency_ms, attempt


# ---------------------------------------------------------------------------- response parsing & checks

def parse_response(body):
    """Mirror of the PATCHED Otter_OpenAI_Backend::generate() parsing (tool_calls, then function_call, then content)."""
    out = {"content": "", "format": "text", "refusal": None, "finish_reason": None, "response_model": None,
           "usage": {}, "error_code": None, "error_message": None, "shape": None}
    if not isinstance(body, dict):
        out["error_code"] = "invalid_body"
        return out
    if isinstance(body.get("error"), dict):
        out["error_code"] = str(body["error"].get("code") or body["error"].get("type") or "openai_error")
        out["error_message"] = str(body["error"].get("message", ""))[:300]
        return out
    out["response_model"] = body.get("model")
    out["usage"] = body.get("usage") or {}
    choice = (body.get("choices") or [{}])[0] or {}
    out["finish_reason"] = choice.get("finish_reason")
    msg = choice.get("message") or {}
    tc = msg.get("tool_calls") or []
    if tc and isinstance(tc[0], dict) and isinstance((tc[0].get("function") or {}).get("arguments"), str):
        out["content"], out["format"], out["shape"] = tc[0]["function"]["arguments"], "json", "tool_calls"
    elif isinstance(msg.get("function_call"), dict) and "arguments" in msg["function_call"]:
        out["content"], out["format"], out["shape"] = str(msg["function_call"]["arguments"]), "json", "function_call"
    elif msg.get("content") is not None:
        out["content"], out["shape"] = str(msg["content"]), "content"
    if isinstance(msg.get("refusal"), str) and msg["refusal"]:
        out["refusal"] = msg["refusal"]
    return out


def strip_tags(html):
    return re.sub(r"<[^>]+>", " ", html or "")


def word_count(text):
    return len(re.findall(r"\w+", text or "", re.UNICODE))


def guess_language(text):
    words = re.findall(r"\w+", (text or "").lower(), re.UNICODE)
    scores = {lang: sum(1 for w in words if w in sw) for lang, sw in STOPWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def alt_match(spec, values):
    return any(opt in values for opt in spec.split("|"))


def evaluate(case, parsed, slugs):
    feature, expect = case["feature"], case.get("expect", {})
    content = parsed["content"]
    r = {"format_valid": False, "format_problems": [], "expect_met": None, "expect_failures": [],
         "refusal": False, "refusal_signal": None, "output_chars": len(content), "output_words": 0, "units": None}

    if parsed["refusal"]:
        r["refusal"], r["refusal_signal"] = True, "message.refusal"
    elif parsed["finish_reason"] == "content_filter":
        r["refusal"], r["refusal_signal"] = True, "finish_reason=content_filter"
    elif feature in ("form", "patternsPicker") and parsed["format"] != "json" and content:
        r["refusal"], r["refusal_signal"] = True, "no function/tool call; text reply"
    elif REFUSAL_RE.search(content or ""):
        r["refusal"], r["refusal_signal"] = True, "refusal phrasing"
    if parsed["finish_reason"] == "length":
        r["format_problems"].append("finish_reason=length (output truncated)")

    fails = r["expect_failures"]
    if feature == "textTransformation":
        tags = {t.lower() for t in re.findall(r"</?\s*([a-zA-Z0-9]+)", content)}
        r["output_words"] = word_count(strip_tags(content))
        if not content.strip():
            r["format_problems"].append("empty")
        if "```" in content:
            r["format_problems"].append("markdown code fence")
        if tags & HTML_FORBIDDEN:
            r["format_problems"].append("forbidden tags: " + ",".join(sorted(tags & HTML_FORBIDDEN)))
        if content.strip() and not tags:
            r["format_problems"].append("no HTML tags (plain text)")
        extra = tags - HTML_ALLOWED - HTML_TOLERATED - HTML_FORBIDDEN
        if extra:
            r["format_problems"].append("tags outside allowlist: " + ",".join(sorted(extra)))
        hard = [p for p in r["format_problems"] if not p.startswith("tags outside")]
        r["format_valid"] = not hard and not r["refusal"]
        r["units"] = r["output_words"]
        if "min_words" in expect and r["output_words"] < expect["min_words"]:
            fails.append("words %d < min %d" % (r["output_words"], expect["min_words"]))
        if "max_words" in expect and r["output_words"] > expect["max_words"]:
            fails.append("words %d > max %d" % (r["output_words"], expect["max_words"]))
        for spec in expect.get("tags_include", []):
            if not alt_match(spec, tags):
                fails.append("missing tag " + spec)
        for s in expect.get("preserve", []):
            if s not in content:
                fails.append("did not preserve " + s)
        if "language" in expect and guess_language(strip_tags(content)) != expect["language"]:
            fails.append("language != %s (heuristic)" % expect["language"])

    elif feature == "form":
        try:
            args = json.loads(content) if content else None
        except ValueError:
            args = None
            r["format_problems"].append("arguments are not valid JSON (editor shows an empty form)")
        fields = args.get("fields") if isinstance(args, dict) else None
        if args is not None and not isinstance(fields, list):
            r["format_problems"].append("no 'fields' array")
        fields = fields if isinstance(fields, list) else []
        mapped = [f for f in fields if isinstance(f, dict) and f.get("type") in FORM_TYPE_TO_BLOCK]
        dropped = [f.get("type") if isinstance(f, dict) else f for f in fields if f not in mapped]
        if dropped:
            r["format_problems"].append("fields silently dropped by editor (unknown type): %s" % dropped)
        r["output_words"] = word_count(" ".join(str(f.get("label", "")) for f in mapped))
        r["units"] = len(mapped)
        r["format_valid"] = bool(mapped) and not r["refusal"] and "arguments are not valid JSON (editor shows an empty form)" not in r["format_problems"]
        types = {f.get("type") for f in mapped}
        if len(mapped) < expect.get("min_fields", 1):
            fails.append("fields %d < min %d" % (len(mapped), expect.get("min_fields", 1)))
        for spec in expect.get("types_include", []):
            if not alt_match(spec, types):
                fails.append("missing field type " + spec)
        if expect.get("file_mime"):
            for f in mapped:
                if f.get("type") == "file":
                    ft = f.get("allowedFileTypes") or []
                    if not ft or not all(isinstance(x, str) and "/" in x for x in ft):
                        fails.append("file field without MIME allowedFileTypes")
        if "language" in expect and mapped:
            text = " ".join(str(f.get("label", "")) + " " + str(f.get("helpText", "")) for f in mapped)
            if guess_language(text) not in (expect["language"], None):
                fails.append("language != %s (heuristic)" % expect["language"])

    elif feature == "patternsPicker":
        try:
            args = json.loads(content) if content else None
        except ValueError:
            args = None
            r["format_problems"].append("arguments are not valid JSON")
        picked = args.get("slugs") if isinstance(args, dict) else None
        picked = picked if isinstance(picked, list) else []
        known = set(slugs.get("free", [])) | (set(slugs.get("pro", [])) if case.get("pro") else set())
        valid = [s for s in picked if s in known]
        unknown = [s for s in picked if s not in known]
        if unknown:
            r["format_problems"].append("unknown pattern slugs: %s" % unknown)
        r["units"] = len(valid)
        r["output_words"] = len(picked)
        r["format_valid"] = bool(valid) and not r["refusal"]
        if len(valid) < expect.get("min_slugs", 1):
            fails.append("valid slugs %d < min %d" % (len(valid), expect.get("min_slugs", 1)))
        if expect.get("slugs_include_any") and not set(expect["slugs_include_any"]) & set(valid):
            fails.append("none of expected slugs %s" % expect["slugs_include_any"])

    if expect.get("policy_edge"):
        r["expect_met"] = None  # record-only case
    elif parsed["error_code"]:
        r["expect_met"] = False
    else:
        r["expect_met"] = r["format_valid"] and not fails
    return r


# ---------------------------------------------------------------------------- cost

def estimate_cost(usage, model, pricing):
    """USD from usage and pricing.json. Returns (cost or None, note)."""
    models = pricing.get("models", {})
    price = models.get(model)
    if price is None:
        base = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model or "")
        price = models.get(base)
    if price is None:
        return None, "no price for %s in pricing file" % model
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    ptd = usage.get("prompt_tokens_details") or {}
    cached = int(ptd.get("cached_tokens") or 0)
    writes = int(ptd.get("cache_write_tokens") or 0)
    note = ""
    if pt > 272000 and model.startswith("gpt-5.6"):
        note = "prompt >272K tokens: long-context pricing not applied"
    cached_price = price.get("cached_input") if price.get("cached_input") is not None else price["input"]
    write_price = price.get("cache_write") if price.get("cache_write") is not None else price["input"]
    uncached = max(0, pt - cached - writes)
    cost = (uncached * price["input"] + cached * cached_price + writes * write_price + ct * price["output"]) / 1e6
    return cost, note


def rough_preflight_cost(payload, model, pricing, est_output_tokens):
    approx_prompt = len(json.dumps(payload.get("messages", [])) + json.dumps(payload.get("tools", payload.get("functions", [])))) // 4
    cost, _ = estimate_cost({"prompt_tokens": approx_prompt, "completion_tokens": est_output_tokens}, model, pricing)
    return cost


# ---------------------------------------------------------------------------- run

def summarize(rows):
    def pct(n, d):
        return "%d/%d (%.0f%%)" % (n, d, 100.0 * n / d) if d else "0/0"
    ok = [r for r in rows if r["http_status"] == 200 and not r["error_code"]]
    lat = sorted(r["latency_ms"] for r in ok)
    costs = [r["cost_usd"] for r in ok if r["cost_usd"] is not None]
    scored = [r for r in rows if r["expect_met"] is not None]
    p90 = lat[min(len(lat) - 1, int(math.ceil(0.9 * len(lat))) - 1)] if lat else None
    u = lambda key: sum(int((r["usage"] or {}).get(key) or 0) for r in ok)
    rt = sum(int(((r["usage"] or {}).get("completion_tokens_details") or {}).get("reasoning_tokens") or 0) for r in ok)
    return {
        "requests": len(rows), "http_ok": pct(len(ok), len(rows)),
        "format_valid": pct(sum(1 for r in rows if r["format_valid"]), len(rows)),
        "expectations_met": pct(sum(1 for r in scored if r["expect_met"]), len(scored)),
        "refusals": sum(1 for r in rows if r["refusal"]),
        "errors": sum(1 for r in rows if r["error_code"]),
        "latency_median_ms": int(statistics.median(lat)) if lat else None, "latency_p90_ms": p90,
        "mean_text_words": (round(statistics.mean([r["output_words"] for r in ok if r["feature"] == "textTransformation"]), 1)
                            if any(r["feature"] == "textTransformation" for r in ok) else None),
        "mean_output_chars": round(statistics.mean([r["output_chars"] for r in ok]), 1) if ok else None,
        "prompt_tokens": u("prompt_tokens"), "completion_tokens": u("completion_tokens"), "reasoning_tokens": rt,
        "cost_usd": round(sum(costs), 6) if costs else None,
        "cost_per_1000_requests_usd": round(1000 * statistics.mean(costs), 4) if costs else None,
        "response_models": sorted({r["response_model"] for r in ok if r["response_model"]}),
    }


def compare_flags(old, new):
    flags = []
    if new["error_code"]:
        flags.append("NEW-ERROR:" + new["error_code"])
    if old is None or old["error_code"]:
        return flags + (["NO-BASELINE"] if old is None or old["error_code"] else [])
    if old["format_valid"] and not new["format_valid"]:
        flags.append("FORMAT-REGRESSION")
    if not old["format_valid"] and new["format_valid"]:
        flags.append("FORMAT-FIXED")
    if old["refusal"] != new["refusal"]:
        flags.append("REFUSAL-CHANGE")
    if old["expect_met"] is True and new["expect_met"] is False:
        flags.append("EXPECTATION-REGRESSION")
    if old["expect_met"] is False and new["expect_met"] is True:
        flags.append("EXPECTATION-FIXED")
    if old["feature"] == "textTransformation" and old["output_words"] and new["output_words"] is not None:
        delta = (new["output_words"] - old["output_words"]) / float(old["output_words"])
        if abs(delta) > 0.5:
            flags.append("LENGTH-SHIFT %+.0f%%" % (100 * delta))
    elif old["units"] is not None and new["units"] is not None and abs(new["units"] - old["units"]) >= 2:
        flags.append("COUNT-SHIFT %d->%d" % (old["units"], new["units"]))
    return flags


def mock_lookup(mocks, case_id, arm):
    for key in ((case_id, arm["label"]), (case_id, arm["kind"])):
        if key in mocks:
            return mocks[key]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="replay mock responses; no network, no key, no cost")
    mode.add_argument("--live", action="store_true", help="call OpenAI with OPENAI_API_KEY (your key, your cost)")
    ap.add_argument("--cases", default=os.path.join(HERE, "cases.jsonl"))
    ap.add_argument("--templates", default=os.path.join(HERE, "templates.sample.json"),
                    help="site's real otter_prompts JSON (recommended for live runs); default: paraphrased sample")
    ap.add_argument("--pricing", default=os.path.join(HERE, "pricing.json"))
    ap.add_argument("--mocks", default=os.path.join(HERE, "mocks", "mock_responses.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "run"))
    ap.add_argument("--candidate", action="append", default=None,
                    help="replacement model for the NEW arm (repeatable). Default: gpt-5.6-terra (OpenAI's recommendation)")
    ap.add_argument("--old-model", default=None, help="override the OLD arm model (default: the template's pin)")
    ap.add_argument("--skip-old", action="store_true", help="do not call the old model")
    ap.add_argument("--baseline", default=None, help="results.jsonl from an earlier run to use as the OLD arm")
    ap.add_argument("--swap-effort", default="none", help="reasoning_effort after a swap ('' = model default). Patch default: none")
    ap.add_argument("--keep-sampling", action="store_true", help="keep temperature/top_p on GPT-5.x (tests the opt-in filter)")
    ap.add_argument("--only", default=None, help="comma-separated features or case ids to run")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=300, help="seconds; Otter's default request timeout is 300")
    ap.add_argument("--max-cost-usd", type=float, default=0.50, help="live mode hard cap on estimated spend")
    ap.add_argument("--est-output-tokens", type=int, default=700, help="pre-flight output estimate per request")
    ap.add_argument("--yes", action="store_true", help="confirm live spend non-interactively")
    args = ap.parse_args(argv)

    cases = load_jsonl(args.cases)
    if args.only:
        sel = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in sel or c["feature"] in sel]
    if args.limit:
        cases = cases[: args.limit]
    templates, slugs = load_templates(args.templates)
    pricing = load_pricing(args.pricing)
    candidates = args.candidate or ["gpt-5.6-terra"]
    sample_templates = os.path.basename(args.templates) == "templates.sample.json"

    arms = []
    if not args.skip_old:
        arms.append({"label": "old", "kind": "old", "model": args.old_model})
    for cand in candidates:
        arms.append({"label": "new:" + cand, "kind": "new", "model": cand})

    mocks = {}
    api_key = None
    if args.dry_run:
        for m in load_jsonl(args.mocks):
            mocks[(m["case_id"], m["arm"])] = m
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            sys.exit("--live needs OPENAI_API_KEY in the environment (use a staging/project key you can revoke).")

    # Build every request first so live mode can price the whole run before spending anything.
    plan = []
    for case in cases:
        tpl = templates.get(case["feature"])
        if tpl is None:
            sys.exit("template '%s' not found in %s" % (case["feature"], args.templates))
        client = build_client_payload(tpl, case)
        for arm in arms:
            if arm["kind"] == "old":
                payload = copy.deepcopy(client)  # 3.2.7 server forwards the template payload unchanged
                if arm["model"]:
                    payload["model"] = arm["model"]
            else:
                repl = dict(RETIRING_MODEL_REPLACEMENTS)
                repl[client.get("model", "")] = arm["model"]
                payload = patched_server_transform(client, repl, args.swap_effort, args.keep_sampling)
            plan.append((case, arm, payload))

    if args.live:
        est = sum(rough_preflight_cost(p, p.get("model", ""), pricing, args.est_output_tokens) or 0 for _, _, p in plan)
        unpriced = sorted({p.get("model") for _, _, p in plan if estimate_cost({}, p.get("model", ""), pricing)[0] is None})
        print("Live plan: %d requests, models %s, rough pre-flight estimate $%.4f (cap $%.4f)." % (
            len(plan), sorted({p.get('model') for _, _, p in plan}), est, args.max_cost_usd))
        if unpriced:
            sys.exit("No price in %s for %s; add it before a live run." % (args.pricing, unpriced))
        if est > args.max_cost_usd:
            sys.exit("Estimated cost exceeds --max-cost-usd; raise the cap or use --limit/--only.")
        if sample_templates:
            print("WARNING: using the paraphrased SAMPLE templates. Pass --templates with the site's real otter_prompts JSON for a client verdict.")
        if not args.yes:
            if input("Type 'spend' to call the OpenAI API with your key: ").strip() != "spend":
                sys.exit("Aborted; nothing was sent.")

    os.makedirs(args.out, exist_ok=True)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    results, spent, old_unavailable = [], 0.0, None
    baseline = {}
    if args.baseline:
        for row in load_jsonl(args.baseline):
            if row.get("arm_kind") == "old":
                baseline[row["case_id"]] = row

    with open(os.path.join(args.out, "requests.jsonl"), "w", encoding="utf-8") as reqf:
        for case, arm, payload in plan:
            reqf.write(json.dumps({"case_id": case["id"], "arm": arm["label"], "request": payload}, ensure_ascii=False) + "\n")
            if arm["kind"] == "old" and case["id"] in baseline:
                results.append(baseline[case["id"]])
                continue
            if arm["kind"] == "old" and old_unavailable:
                status, body, latency, retries = None, {"error": {"code": "skipped_old_model_unavailable", "message": old_unavailable}}, 0, 0
            elif args.dry_run:
                m = mock_lookup(mocks, case["id"], arm)
                if m is None:
                    status, body, latency, retries = None, {"error": {"code": "no_mock", "message": "no mock for this case/arm"}}, 0, 0
                else:
                    status, body, latency, retries = m["http_status"], m["body"], m["latency_ms"], 0
            else:
                if spent >= args.max_cost_usd:
                    status, body, latency, retries = None, {"error": {"code": "skipped_cost_cap", "message": "cost cap reached"}}, 0, 0
                else:
                    status, body, latency, retries = post_chat(payload, api_key, args.timeout)
            parsed = parse_response(body)
            ev = evaluate(case, parsed, slugs)
            cost, cost_note = (estimate_cost(parsed["usage"], parsed["response_model"] or payload.get("model", ""), pricing)
                               if parsed["usage"] else (None, ""))
            if cost:
                spent += cost
            if arm["kind"] == "old" and parsed["error_code"] in ("model_not_found",) or (
                    arm["kind"] == "old" and status == 404):
                old_unavailable = "old model %s unavailable: %s" % (payload.get("model"), parsed["error_message"])
            row = {
                "case_id": case["id"], "feature": case["feature"], "regenerate": bool(case.get("regenerate")),
                "arm": arm["label"], "arm_kind": arm["kind"], "requested_model": payload.get("model"),
                "response_model": parsed["response_model"], "reasoning_effort": payload.get("reasoning_effort"),
                "sent_temperature": payload.get("temperature"), "http_status": status, "retries": retries,
                "latency_ms": latency, "error_code": parsed["error_code"], "error_message": parsed["error_message"],
                "finish_reason": parsed["finish_reason"], "response_shape": parsed["shape"], "usage": parsed["usage"],
                "cost_usd": round(cost, 8) if cost is not None else None, "cost_note": cost_note,
                "content": parsed["content"], "refusal_text": parsed["refusal"],
                "mode": "dry-run (synthetic mock)" if args.dry_run else "live",
                "mock_note": (mock_lookup(mocks, case["id"], arm) or {}).get("_note") if args.dry_run else None,
            }
            row.update(ev)
            results.append(row)
            if args.live:
                print("%-4s %-22s HTTP %-4s %5d ms  valid=%-5s refusal=%-5s $%.5f" % (
                    case["id"], arm["label"], status, latency, row["format_valid"], row["refusal"], cost or 0))

    with open(os.path.join(args.out, "results.jsonl"), "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta = {
        "harness_version": HARNESS_VERSION, "harness_authored_by": AUTHORED_BY, "harness_authored_on": AUTHORED_ON,
        "run_started_utc": started, "mode": "dry-run" if args.dry_run else "live",
        "cases": len(cases), "arms": [a["label"] for a in arms], "templates": os.path.relpath(args.templates, HERE),
        "sample_templates": sample_templates, "pricing_file": os.path.relpath(args.pricing, HERE),
        "swap_effort": args.swap_effort, "keep_sampling": args.keep_sampling,
        "mocks": os.path.relpath(args.mocks, HERE) if args.dry_run else None,
        "old_arm_unavailable": old_unavailable, "estimated_spend_usd": round(spent, 6) if args.live else 0.0,
    }
    with open(os.path.join(args.out, "run_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    md = write_report(results, cases, arms, pricing, meta, plan)
    with open(os.path.join(args.out, "comparison.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print("Wrote %s (results.jsonl, requests.jsonl, run_meta.json, comparison.md)" % args.out)
    return 0


# ---------------------------------------------------------------------------- report

def write_report(results, cases, arms, pricing, meta, plan):
    dry = meta["mode"] == "dry-run"
    L = []
    L.append("# Otter Blocks Swap & Verify: before/after comparison\n")
    L.append("Harness v%s authored by model %s on %s. This report was generated by run_harness.py at %s UTC (mode: **%s**).\n" % (
        HARNESS_VERSION, AUTHORED_BY, AUTHORED_ON, meta["run_started_utc"], meta["mode"]))
    if dry:
        L.append("> **DRY RUN. Every response below is a SYNTHETIC MOCK from `%s`, written by hand to exercise the harness. "
                 "No model was called and no money was spent. Latency, token and cost figures are illustrative only and say "
                 "nothing about how gpt-3.5-turbo or gpt-5.6-terra behave. Live numbers require running with `--live` on the "
                 "client's own OpenAI key.**\n" % meta["mocks"])
    if meta["sample_templates"]:
        L.append("> Templates: paraphrased SAMPLE templates (structure mirrors Otter's served templates). For a client verdict, rerun with `--templates` pointing at the site's real `otter_prompts` JSON.\n")
    if meta["old_arm_unavailable"]:
        L.append("> Old arm: %s. Remaining old-arm requests were skipped; use `--baseline` with a pre-shutdown run to compare.\n" % meta["old_arm_unavailable"].rstrip("."))
    L.append("Settings: swap reasoning_effort = `%s`; keep sampling params on GPT-5.x = `%s`; pricing = `%s`.\n" % (
        meta["swap_effort"] or "(model default)", meta["keep_sampling"], meta["pricing_file"]))

    by_arm = {a["label"]: [r for r in results if r["arm"] == a["label"]] for a in arms}
    L.append("## 1. Summary by arm\n")
    keys = [("requests", "Requests"), ("http_ok", "HTTP 200"), ("format_valid", "Format valid"),
            ("expectations_met", "Expectations met (excl. policy-edge)"), ("refusals", "Refusals"), ("errors", "Errors"),
            ("latency_median_ms", "Latency median (ms)"), ("latency_p90_ms", "Latency p90 (ms)"),
            ("mean_text_words", "Mean words, AI Block outputs"), ("mean_output_chars", "Mean output chars, all"),
            ("prompt_tokens", "Prompt tokens"),
            ("completion_tokens", "Completion tokens (incl. reasoning)"), ("reasoning_tokens", "Reasoning tokens"),
            ("cost_usd", "Est. cost, this run (USD)"), ("cost_per_1000_requests_usd", "Est. cost per 1,000 requests (USD)"),
            ("response_models", "Model reported by API")]
    sums = {k: summarize(v) for k, v in by_arm.items()}
    L.append("| Metric | " + " | ".join(by_arm) + " |")
    L.append("|---|" + "---|" * len(by_arm))
    for k, label in keys:
        L.append("| %s | %s |" % (label, " | ".join(
            (", ".join(sums[a][k]) or "-") if isinstance(sums[a][k], list) else ("-" if sums[a][k] is None else str(sums[a][k]))
            for a in by_arm)))
    L.append("\nCost = usage x `%s` (USD per 1M tokens; edit the file to match your pricing). Reasoning tokens are billed as output.\n" % meta["pricing_file"])

    L.append("## 2. By feature (format valid / expectations met)\n")
    feats = sorted({c["feature"] for c in cases})
    L.append("| Feature | " + " | ".join(by_arm) + " |")
    L.append("|---|" + "---|" * len(by_arm))
    for f in feats:
        cells = []
        for a, rows in by_arm.items():
            fr = [r for r in rows if r["feature"] == f]
            sc = [r for r in fr if r["expect_met"] is not None]
            cells.append("%d/%d valid, %d/%d met" % (sum(r["format_valid"] for r in fr), len(fr), sum(1 for r in sc if r["expect_met"]), len(sc)))
        L.append("| %s | %s |" % (f, " | ".join(cells)))

    L.append("\n## 3. Per case\n")
    old_rows = {r["case_id"]: r for r in by_arm.get("old", [])}
    new_arms = [a["label"] for a in arms if a["kind"] == "new"]
    L.append("| Case | Feature | Regen | Old: valid / words / ms | " + " | ".join("%s: valid / words / ms" % n for n in new_arms) + " | Flags |")
    L.append("|---|---|---|---|" + "---|" * len(new_arms) + "---|")
    review = []
    for c in cases:
        o = old_rows.get(c["id"])
        cell = lambda r: "-" if r is None else ("ERR %s" % r["error_code"] if r["error_code"] else "%s / %s / %s" % (
            "yes" if r["format_valid"] else "NO", r["units"] if r["units"] is not None else "-", r["latency_ms"]))
        flags = []
        new_cells = []
        for n in new_arms:
            nr = next((r for r in by_arm[n] if r["case_id"] == c["id"]), None)
            new_cells.append(cell(nr))
            if nr is not None:
                f = compare_flags(o, nr)
                if c.get("expect", {}).get("policy_edge"):
                    f.append("POLICY-EDGE")
                if f:
                    flags.append(("%s: " % n.split(":", 1)[1] if len(new_arms) > 1 else "") + ", ".join(f))
                    if any(x for x in f if x not in ("FORMAT-FIXED", "EXPECTATION-FIXED", "NO-BASELINE")):
                        review.append((c["id"], n, f, o, nr))
        L.append("| %s | %s | %s | %s | %s | %s |" % (c["id"], c["feature"], "yes" if c.get("regenerate") else "",
                                                     cell(o), " | ".join(new_cells), "; ".join(flags) or ""))
    L.append("\nUnits: words for HTML outputs, mapped form fields for `form`, valid pattern slugs for `patternsPicker`.\n")

    L.append("## 4. Needs human review\n")
    if not review:
        L.append("Nothing flagged.\n")
    for cid, n, f, o, nr in review:
        L.append("### %s (%s): %s\n" % (cid, n, ", ".join(f)))
        for label, r in (("old", o), (n, nr)):
            if r is None:
                continue
            probs = "; ".join(r["format_problems"] + r["expect_failures"]) or "none"
            txt = (r["refusal_text"] or r["content"] or r["error_message"] or "")[:400].replace("\n", " ")
            L.append("- **%s** (%s, finish=%s, refusal=%s): problems: %s  \n  output: `%s`" % (
                label, r["requested_model"], r["finish_reason"], r["refusal_signal"] or "no", probs, txt.replace("`", "'")))
            if r.get("mock_note"):
                L.append("  \n  mock note: %s" % r["mock_note"])
        L.append("")

    L.append("## 5. What changed on the wire (first case per feature)\n")
    examples, feats_seen = [], set()
    for c in cases:
        if c["feature"] not in feats_seen and not c.get("regenerate"):
            feats_seen.add(c["feature"])
            examples.append(c)
    examples += [c for c in cases if c.get("regenerate")][:1]
    for case in examples:
        olds = [p for c2, a2, p in plan if c2["id"] == case["id"] and a2["kind"] == "old"]
        news = [p for c2, a2, p in plan if c2["id"] == case["id"] and a2["kind"] == "new"]
        if not olds or not news:
            continue
        payload = olds[0]
        o_keys, n = set(payload), news[0]
        changes = []
        for k in sorted(o_keys | set(n)):
            if k == "messages":
                continue
            ov, nv = payload.get(k, ABSENT), n.get(k, ABSENT)
            if ov != nv:
                fmt = lambda v: "(absent)" if v is ABSENT else json.dumps(v)[:90] + ("..." if len(json.dumps(v)) > 90 else "")
                changes.append("| `%s` | `%s` | `%s` |" % (k, fmt(ov), fmt(nv)))
        L.append("**%s (%s%s)**\n" % (case["id"], case["feature"], ", regenerate" if case.get("regenerate") else ""))
        L.append("| Key | Old request | New request |\n|---|---|---|")
        L.extend(changes or ["| (no differences outside messages) | | |"])
        L.append("")

    L.append("## 6. How to read this\n")
    L.append("- **Format valid** mirrors what the Otter editor can use: HTML without code fences or page-level tags for the AI Block; "
             "parseable `generateForm` arguments with at least one field type the editor maps (unknown types are dropped silently); "
             "parseable `pickPatterns` arguments with known slugs.")
    L.append("- **Expectations** are per-case soft checks from cases.jsonl (length bounds, required tags/field types, preserved markup, "
             "language heuristic). Policy-edge cases are record-only.")
    L.append("- **Refusal** = `message.refusal`, `finish_reason=content_filter`, a text reply where a function call was forced, or refusal phrasing.")
    L.append("- Thirty cases show direction, not statistical significance. A regenerate case is one sample at the sent temperature.")
    L.append("- Files: `results.jsonl` (one row per case x arm, including the model the API reported), `requests.jsonl` (exact request bodies, no key), `run_meta.json`.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
