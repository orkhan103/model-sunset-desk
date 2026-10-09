#!/usr/bin/env python3
"""check_code_node.py - exercise the 'Validate AI output' Code node and the alert expression
from after.json in Node.js, outside n8n.

Produced 2026-10-09 (AI-assisted, human-reviewed) for Model Sunset Desk.
Standard library only; needs `node` on PATH. It writes a temporary .js file to the system temp
directory, runs it, prints the results and deletes the file. It does not run n8n's own
expression engine, so it checks JavaScript syntax and logic only.

Run: python3 -I check_code_node.py   (exit 0 = all 9 cases routed as expected)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

CASES = r"""
const cases = [
  ['valid object', 'pass', {finish_reason:'stop', message:{content:{category:'bug',urgency:'high',summary:'Login fails',reply_draft:'Sorry, we are on it.'}}}],
  ['valid JSON string', 'pass', {finish_reason:'stop', message:{content:'{"category":"billing","urgency":"low","summary":"x","reply_draft":"y"}'}}],
  ['cut off at token cap', 'error', {finish_reason:'length', message:{content:''}}],
  ['empty string', 'error', {finish_reason:'stop', message:{content:''}}],
  ['null content', 'error', {finish_reason:'stop', message:{content:null}}],
  ['refusal with text', 'error', {finish_reason:'stop', message:{content:'x', refusal:'I cannot help with that.'}}],
  ['refusal, null content', 'error', {finish_reason:'stop', message:{content:null, refusal:'No.'}}],
  ['prose instead of JSON', 'error', {finish_reason:'stop', message:{content:'Sure! Here is the JSON: {category: bug'}}],
  ['wrong keys/values', 'error', {finish_reason:'stop', message:{content:{Category:'Bug',urgency:'urgent',summary:'',reply:'hi'}}}],
];
let bad = 0;
for (const [name, want, c] of cases) {
  let got, msg;
  try { const r = run(c); got = 'pass'; msg = JSON.stringify(r.json); }
  catch (e) { got = 'error'; msg = e.message; }
  if (got !== want) bad++;
  console.log((got === want ? 'ok  ' : 'FAIL') + ' ' + name.padEnd(24) + ' -> ' + got.toUpperCase().padEnd(6) + ' ' + msg);
}
const $workflow = {name: 'Support ticket triage'}; const $execution = {id: '1234'};
const $ = (n) => ({ first: () => ({ json: { body: { subject: 'Cannot log in' } } }) });
for (const $json of [{error: {message: 'example API error'}}, {error: 'AI output is empty (no text returned).'}, {}]) {
  console.log('alert body: ' + ALERT_EXPR);
}
process.exit(bad === 0 ? 0 : 1);
"""


def main():
    node = shutil.which("node")
    if not node:
        print("node not found on PATH; cannot run this check")
        return 2
    wf = json.load(open(os.path.join(HERE, "after.json"), encoding="utf-8"))
    byname = {n["name"]: n for n in wf["nodes"]}
    js = byname["Validate AI output"]["parameters"]["jsCode"]
    expr = byname["Alert: AI step failed"]["parameters"]["jsonBody"]
    assert expr.startswith("={{") and expr.endswith("}}")
    src = "function run($json){\n" + js + "\n}\n" + CASES.replace("ALERT_EXPR", expr[3:-2])
    fd, path = tempfile.mkstemp(suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(src)
        ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        print("node %s; checking after.json Code node + alert expression" % ver, flush=True)
        return subprocess.run([node, path]).returncode
    finally:
        os.remove(path)


if __name__ == "__main__":
    sys.exit(main())
