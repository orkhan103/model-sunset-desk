#!/usr/bin/env python3
"""validate.py - find OpenAI model IDs that are being shut down inside workflow exports.

Produced 2026-10-09 (AI-assisted, human-reviewed) for Model Sunset Desk (sample proof asset).

Standard library only. It reads JSON as data and never executes or imports anything
from the files it checks. Run it with `python3 -I` so nothing from the current directory
is imported.

Usage
  python3 -I validate.py                     sample mode: checks before.json and after.json
                                             next to this script
  python3 -I validate.py export1.json ...    check any n8n export, Make blueprint or other JSON
  python3 -I validate.py --json [files...]   machine-readable output

Exit codes
  sample mode     0 if both files parse AND before.json pins >= 1 model shutting down on
                  2026-10-23 AND after.json pins none; otherwise 1
  explicit files  0 if no file pins a model shutting down on 2026-10-23; 1 if any does;
                  2 if any file fails to parse (parse errors take priority)

"Pins" means the ID sits in a model setting: a key such as model / modelId / chatModel, an n8n
resource-locator value under such a key, or text like '"model": "gpt-4"' inside a string (for
example an HTTP Request JSON body). Other occurrences (prose, code comments, display labels)
are listed as "mention" for a human to review but do not fail the check.

Sources for the tables below (read live 2026-10-09):
  OpenAI deprecations page https://developers.openai.com/api/docs/deprecations
    - entry 2026-04-22 "Legacy GPT model snapshots" (shutdown 2026-10-23)
    - entry 2026-06-02 "GPT Image model deprecations" (shutdown 2026-12-01)
    - entry 2026-06-11 "GPT-5 and o3 model deprecations" (shutdown 2026-12-11)
  Anthropic claude-sonnet-4-5-20250929 retirement 2026-11-30: reported in OFFER_SPEC.md
    (https://platform.claude.com/docs/en/about-claude/model-deprecations), not re-read here.
  n8n node schemas: github.com/n8n-io/n8n at commit 5bc602147761788693427000bbd998279c09c689
"""
import json
import os
import re
import sys

SHUTDOWN_DATE = "2026-10-23"

# Exact model IDs shut down on 2026-10-23 -> OpenAI's recommended replacement.
SHUTDOWN_2026_10_23 = {
    "gpt-3.5-turbo": "gpt-5.6-terra",
    "gpt-3.5-turbo-0125": "gpt-5.6-terra",
    "gpt-3.5-turbo-completions": "gpt-5.6-terra",
    "gpt-4": "gpt-5.6-sol",
    "gpt-4-0613": "gpt-5.6-sol",
    "gpt-4-completions": "gpt-5.6-sol",
    "gpt-4-0613-completions": "gpt-5.6-sol",
    "gpt-4-1106-preview": "gpt-5.6-sol",
    "gpt-4-turbo": "gpt-5.6-sol",
    "gpt-4-turbo-2024-04-09": "gpt-5.6-sol",
    "gpt-4-turbo-completions": "gpt-5.6-sol",
    "gpt-4.1-nano": "gpt-5.6-luna",
    "gpt-4.1-nano-2025-04-14": "gpt-5.6-luna",
    "gpt-4o-2024-05-13": "gpt-5.6-sol",
    "gpt-image-1": "gpt-image-2.5-sunburst or gpt-image-2.5-flare",
    "o1": "gpt-5.6-sol",
    "o1-2024-12-17": "gpt-5.6-sol",
    "o1-pro": "gpt-5.6-sol (reasoning.mode: pro)",
    "o1-pro-2025-03-19": "gpt-5.6-sol (reasoning.mode: pro)",
    "o3-mini": "gpt-5.6-sol",
    "o3-mini-2025-01-31": "gpt-5.6-sol",
    "o4-mini": "gpt-5.6-terra",
    "o4-mini-2025-04-16": "gpt-5.6-terra",
    # The deprecations page names fine-tune families like this (hyphen form):
    "ft-gpt-3.5-turbo": "gpt-5.6-terra (base model; rebuild behaviour, see fine-tune method)",
    "ft-gpt-4": "gpt-5.6-sol (base model; rebuild behaviour, see fine-tune method)",
    "ft-gpt-4.1-nano-2025-04-14": "gpt-5.6-luna (base model; rebuild behaviour, see fine-tune method)",
    "ft-o4-mini-2025-04-16": "gpt-5.6-terra (base model; rebuild behaviour, see fine-tune method)",
    "ft-babbage-002": "gpt-5.6-terra (base model; rebuild behaviour, see fine-tune method)",
    "ft-davinci-002": "gpt-5.6-terra (base model; rebuild behaviour, see fine-tune method)",
}

# Later shutdowns, reported as LATER (do not fail the 23 Oct check).
LATER = {
    "gpt-image-1-mini": ("2026-12-01", "gpt-image-2.5-sunburst or gpt-image-2.5-flare"),
    "gpt-image-1.5": ("2026-12-01", "gpt-image-2.5-sunburst or gpt-image-2.5-flare"),
    "chatgpt-image-latest": ("2026-12-01", "gpt-image-2.5-sunburst or gpt-image-2.5-flare"),
    "gpt-5-2025-08-07": ("2026-12-11", "gpt-5.6-sol"),
    "gpt-5-mini-2025-08-07": ("2026-12-11", "gpt-5.6-terra"),
    "gpt-5-nano-2025-08-07": ("2026-12-11", "gpt-5.6-luna"),
    "gpt-5-pro-2025-10-06": ("2026-12-11", "gpt-5.6-sol (reasoning.mode: pro)"),
    "o3-2025-04-16": ("2026-12-11", "gpt-5.6-sol"),
    "o3-pro-2025-06-10": ("2026-12-11", "gpt-5.6-sol (reasoning.mode: pro)"),
    "claude-sonnet-4-5-20250929": ("2026-11-30", "see Anthropic model-deprecations page"),
}

FT_NOTE = "base model; rebuild behaviour, see fine-tune method"

# Keys that hold a model choice in n8n / Make / generic configs.
MODEL_KEYS = {"model", "modelid", "chatmodel", "model_id", "modelname", "deployment"}

OPENAI_NODE_TYPES = {
    "@n8n/n8n-nodes-langchain.openAi": "modelId",
    "@n8n/n8n-nodes-langchain.lmChatOpenAi": "model",
    "n8n-nodes-base.openAi": None,  # legacy node, handled specially
}

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]*")
# A model ID written inside a string, e.g. a JSON body '{"model": "gpt-4"}' or 'model=gpt-4'
EMBEDDED_MODEL_RE = re.compile(r"""model(?:_?id|name)?["']?\s*[:=]\s*["']?$""", re.IGNORECASE)


def ft_base(token):
    """Return (replacement) if token is an OpenAI fine-tuned model ID on a retiring base."""
    if not token.startswith("ft:"):
        return None
    base = token[3:].split(":", 1)[0]
    if base.startswith("gpt-3.5-turbo"):
        return "gpt-5.6-terra (" + FT_NOTE + ")"
    if base == "gpt-4" or base.startswith("gpt-4-0"):
        return "gpt-5.6-sol (" + FT_NOTE + ")"
    if base == "gpt-4.1-nano-2025-04-14":
        return "gpt-5.6-luna (" + FT_NOTE + ")"
    if base == "o4-mini-2025-04-16":
        return "gpt-5.6-terra (" + FT_NOTE + ")"
    if base in ("babbage-002", "davinci-002"):
        return "gpt-5.6-terra (" + FT_NOTE + ")"
    return None


def classify_token(token):
    """Return (status, detail) for one token, or None if it is not interesting."""
    t = token.rstrip(".:-")
    low = t.lower()
    if low in SHUTDOWN_2026_10_23:
        return ("SHUTDOWN", low, SHUTDOWN_2026_10_23[low], SHUTDOWN_DATE)
    rep = ft_base(low)
    if rep:
        return ("SHUTDOWN", low, rep, SHUTDOWN_DATE)
    if low in LATER:
        date, rep = LATER[low]
        return ("LATER", low, rep, date)
    if low.startswith(("gpt-3.5", "text-davinci", "text-curie", "text-babbage", "text-ada", "code-davinci")):
        return ("LEGACY", low, "not on the 2026-10-23 list; may already be shut down. Check the deprecations page", "?")
    return None


def walk(obj, path="$"):
    """Yield (path, key, string_value) for every string in a JSON document."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = path + "." + str(k)
            if isinstance(v, str):
                yield p, str(k), v
            else:
                yield from walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = "%s[%d]" % (path, i)
            if isinstance(v, str):
                yield p, None, v
            else:
                yield from walk(v, p)


def path_kind(path, key):
    parts = [x.lower() for x in re.split(r"[.\[\]]", path) if x]
    if key and key.lower() == "cachedresultname":
        return "display label"
    if key and key.lower() in MODEL_KEYS:
        return "model setting"
    # n8n resource locator: ...modelId.value / ...model.value
    if key == "value" and len(parts) >= 2 and parts[-2] in MODEL_KEYS:
        return "model setting"
    return "text mention"


def node_label(doc, path):
    m = re.match(r"\$\.nodes\[(\d+)\]", path)
    if m and isinstance(doc, dict) and isinstance(doc.get("nodes"), list):
        i = int(m.group(1))
        if i < len(doc["nodes"]) and isinstance(doc["nodes"][i], dict):
            return doc["nodes"][i].get("name")
    return None


def rlc_value(v):
    if isinstance(v, dict):
        return v.get("value")
    return v


def n8n_checks(doc):
    """Structural and AI-node checks for an n8n workflow export.

    Returns (facts, warnings, implicit_findings)."""
    facts, warns, implicit = [], [], []
    nodes = doc.get("nodes")
    conns = doc.get("connections", {})
    if not isinstance(nodes, list):
        return facts, warns, implicit
    names = [n.get("name") for n in nodes if isinstance(n, dict)]
    dupes = sorted({x for x in names if names.count(x) > 1})
    if dupes:
        warns.append("duplicate node names: %s" % ", ".join(map(str, dupes)))
    nameset = set(names)
    bad = []
    for src, outs in (conns or {}).items():
        if src not in nameset:
            bad.append("source '%s' not a node" % src)
        for ctype, branches in (outs or {}).items():
            for bi, branch in enumerate(branches or []):
                for link in branch or []:
                    if link.get("node") not in nameset:
                        bad.append("'%s' %s[%d] -> missing node '%s'" % (src, ctype, bi, link.get("node")))
    if bad:
        warns.extend("broken connection: " + b for b in bad)
    else:
        facts.append("connections OK (%d source nodes, all targets exist)" % len(conns or {}))

    for idx, n in enumerate(nodes):
        if not isinstance(n, dict):
            continue
        ntype = n.get("type", "")
        if ntype not in OPENAI_NODE_TYPES:
            continue
        p = n.get("parameters", {}) or {}
        name = n.get("name")
        ver = n.get("typeVersion")
        if ntype == "n8n-nodes-base.openAi":
            resource = p.get("resource", "text")
            model = p.get("chatModel", p.get("model"))
            if resource == "chat" and model is None:
                model = "gpt-3.5-turbo (IMPLICIT: field absent; this legacy node's code default is gpt-3.5-turbo)"
                implicit.append({"status": "SHUTDOWN", "id": "gpt-3.5-turbo", "replacement": "gpt-5.6-terra",
                                 "date": SHUTDOWN_DATE, "path": "$.nodes[%d].parameters" % idx,
                                 "where": "model setting (implicit default)", "node": name})
                warns.append("'%s': legacy OpenAI node with no model field. Its default is gpt-3.5-turbo, "
                             "which shuts down %s. Replace it with the current OpenAI node." % (name, SHUTDOWN_DATE))
            facts.append("AI node '%s' (%s v%s, legacy, resource=%s): model=%s" % (name, ntype, ver, resource, model))
        else:
            key = OPENAI_NODE_TYPES[ntype]
            raw = p.get(key)
            model = rlc_value(raw)
            if raw is None:
                model = "(absent: node uses its code default, which can change between n8n versions)"
                warns.append("'%s': model field '%s' absent from export; open the node and set it explicitly"
                             % (name, key))
            opts = p.get("options", {}) or {}
            optstr = ", ".join("%s=%s" % (k, opts[k]) for k in sorted(opts)) or "none"
            on_err = n.get("onError", "stopWorkflow (default)")
            err_branch = False
            outs = (conns or {}).get(name, {}).get("main", [])
            if n.get("onError") == "continueErrorOutput" and len(outs) > 1 and outs[1]:
                err_branch = True
            facts.append("AI node '%s' (%s v%s): model=%s; options: %s; onError=%s; error branch wired: %s; retries: %s"
                         % (name, ntype, ver, model, optstr, on_err, "yes" if err_branch else "no",
                            ("%s tries" % n.get("maxTries", 3)) if n.get("retryOnFail") else "off"))
            m = str(model or "")
            if m.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")):
                risky = [k for k in ("temperature", "topP", "top_p", "frequency_penalty", "presence_penalty")
                         if k in opts]
                if risky:
                    warns.append("'%s': %s set on reasoning model %s. OpenAI documents that GPT-6 rejects "
                                 "temperature/top_p unless reasoning effort is none; not documented either way "
                                 "for GPT-5.6 in the pages we read. Remove or test." % (name, ", ".join(risky), m))
                mt = opts.get("maxTokens")
                if isinstance(mt, (int, float)) and mt < 4000:
                    warns.append("'%s': maxTokens=%s on reasoning model %s. Reasoning tokens count toward this "
                                 "cap; a low cap can return empty text (finish_reason=length)." % (name, mt, m))
            if not err_branch:
                warns.append("'%s': no error branch; a failed AI call stops the workflow without an alert" % name)
    return facts, warns, implicit


def check_file(path):
    res = {"file": path, "parse": None, "kind": None, "findings": [], "facts": [], "warnings": [],
           "stamp": False}
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        res["parse"] = "FAIL: %s" % e
        return res
    res["parse"] = "OK"
    if isinstance(doc, dict) and isinstance(doc.get("nodes"), list) and "connections" in doc:
        res["kind"] = "n8n workflow (%d nodes)" % len(doc["nodes"])
    elif isinstance(doc, dict) and isinstance(doc.get("flow"), list):
        res["kind"] = "Make blueprint (%d top-level modules)" % len(doc["flow"])
    else:
        res["kind"] = "generic JSON"
    for p, key, s in walk(doc):
        if "Produced by model" in s:
            res["stamp"] = True
        base_kind = path_kind(p, key)
        for m in TOKEN_RE.finditer(s):
            tok = m.group(0)
            # "model:gpt-4" style tokens: split on ':' unless it is an ft: fine-tune ID
            if tok.lower().startswith("ft:"):
                pieces = [(tok, m.start())]
            else:
                pieces, off = [], m.start()
                for piece in tok.split(":"):
                    pieces.append((piece, off))
                    off += len(piece) + 1
            for piece, start in pieces:
                if not piece:
                    continue
                c = classify_token(piece)
                if not c:
                    continue
                status, mid, rep, date = c
                where = base_kind
                if where == "text mention" and EMBEDDED_MODEL_RE.search(s[max(0, start - 24):start]):
                    where = "model setting (inside text)"
                res["findings"].append({
                    "status": status, "id": mid, "replacement": rep, "date": date, "path": p,
                    "where": where, "node": node_label(doc, p),
                })
    if isinstance(doc, dict) and "nodes" in doc:
        res["facts"], res["warnings"], implicit = n8n_checks(doc)
        res["findings"].extend(implicit)
    return res


def n_shutdown(res):
    """Occurrences that pin a retiring model (model settings, incl. ones embedded in text)."""
    return [f for f in res["findings"] if f["status"] == "SHUTDOWN" and f["where"].startswith("model setting")]


def n_mentions(res):
    """Occurrences that only mention a retiring ID (prose, comments, display labels): review by hand."""
    return [f for f in res["findings"] if f["status"] == "SHUTDOWN" and not f["where"].startswith("model setting")]


def print_report(res):
    print("== %s" % res["file"])
    print("   parse: %s%s" % (res["parse"], ("  [%s]" % res["kind"]) if res["kind"] else ""))
    if res["parse"] != "OK":
        return
    sd = n_shutdown(res)
    ids = sorted({f["id"] for f in sd})
    print("   PINNED to a model shutting down %s: %d setting(s)%s"
          % (SHUTDOWN_DATE, len(sd), (" -> " + ", ".join(ids)) if ids else ""))
    print("   mentions only (prose, comments, display labels; review, not counted): %d" % len(n_mentions(res)))
    for f in res["findings"]:
        tag = f["status"] if f["where"].startswith("model setting") or f["status"] != "SHUTDOWN" else "mention"
        where = f["where"] + ((" in node '%s'" % f["node"]) if f["node"] else "")
        print("     %-8s %-22s -> %-34s %s  (%s)" % (tag, f["id"], f["replacement"], f["path"], where))
    for x in res["facts"]:
        print("   info: " + x)
    for w in res["warnings"]:
        print("   WARN: " + w)
    print("   provenance stamp present: %s" % ("yes" if res["stamp"] else "no"))


def main(argv):
    as_json = "--json" in argv
    files = [a for a in argv if a != "--json"]
    sample_mode = not files
    here = os.path.dirname(os.path.abspath(__file__))
    if sample_mode:
        files = [os.path.join(here, "before.json"), os.path.join(here, "after.json")]
    results = [check_file(f) for f in files]

    if sample_mode:
        b, a = results
        ok = (b["parse"] == "OK" and a["parse"] == "OK" and len(n_shutdown(b)) > 0 and len(n_shutdown(a)) == 0)
        verdict = ("PASS: before.json pins a retiring model; after.json pins none" if ok
                   else "FAIL: expected a retiring model pinned in before.json and none in after.json")
        code = 0 if ok else 1
    else:
        if any(r["parse"] != "OK" for r in results):
            code, verdict = 2, "FAIL: at least one file did not parse"
        elif any(n_shutdown(r) for r in results):
            code, verdict = 1, "FAIL: retiring model pinned (shutdown %s)" % SHUTDOWN_DATE
        else:
            code, verdict = 0, "PASS: no model setting pins a model shutting down %s" % SHUTDOWN_DATE

    if as_json:
        print(json.dumps({"results": results, "verdict": verdict, "exit_code": code}, indent=2))
    else:
        for r in results:
            print_report(r)
        print(verdict)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
