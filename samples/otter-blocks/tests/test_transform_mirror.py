"""Checks that harness/run_harness.py mirrors patch.diff adapt_payload() (same scenarios as test_adapt_payload.php).
Produced 2026-10-09 (AI-assisted, human-reviewed). Usage: python3 -I tests/test_transform_mirror.py"""
import importlib.util, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rh", os.path.join(HERE, "..", "harness", "run_harness.py"))
rh = importlib.util.module_from_spec(spec); spec.loader.exec_module(rh)
M = rh.RETIRING_MODEL_REPLACEMENTS
form = {"model": "gpt-3.5-turbo", "messages": [], "functions": [{"name": "generateForm", "parameters": {"type": "object"}}], "function_call": {"name": "generateForm"}}
checks = []
o = rh.patched_server_transform(form, M)
checks += [("1 swap+effort+tools", o["model"] == "gpt-5.6-terra" and o["reasoning_effort"] == "none" and o["tools"][0]["function"]["name"] == "generateForm" and o["tool_choice"]["function"]["name"] == "generateForm" and "functions" not in o and "function_call" not in o)]
o = rh.patched_server_transform({"model": "gpt-3.5-turbo", "messages": [], "temperature": 1.3, "stream": False}, M)
checks += [("2 temperature dropped", "temperature" not in o and o["stream"] is False)]
o = rh.patched_server_transform({"model": "gpt-5-mini", "messages": [], "max_tokens": 8192}, M)
checks += [("3 gpt-5-mini untouched, max_tokens renamed", o["model"] == "gpt-5-mini" and "reasoning_effort" not in o and o["max_completion_tokens"] == 8192)]
o = rh.patched_server_transform({"model": "o4-mini", "messages": []}, M)
checks += [("4 o-series source keeps model default effort", o["model"] == "gpt-5.6-terra" and "reasoning_effort" not in o)]
o = rh.patched_server_transform(dict(form, temperature=1.3), {})
checks += [("5 swap disabled", o["model"] == "gpt-3.5-turbo" and o["temperature"] == 1.3 and "reasoning_effort" not in o and "tools" in o)]
o = rh.patched_server_transform({"model": "gpt-3.5-turbo", "messages": [], "temperature": 1.3}, M, keep_sampling=True)
checks += [("6 keep sampling", o["temperature"] == 1.3)]
o = rh.patched_server_transform(form, M, swap_effort="")
checks += [("7 effort omitted", "reasoning_effort" not in o)]
o = rh.patched_server_transform(dict(form, reasoning_effort="low"), M)
checks += [("8 explicit effort kept", o["reasoning_effort"] == "low")]
checks += [("9 supports none", rh.supports_reasoning_effort_none("gpt-5.6-terra") and not rh.supports_reasoning_effort_none("gpt-5-mini"))]
o = rh.patched_server_transform(dict(form, tools=[{"type": "function", "function": {"name": "x"}}]), M)
checks += [("10 existing tools left alone", o["tools"][0]["function"]["name"] == "x" and "functions" in o)]
fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("PASS " if ok else "FAIL ") + n)
print("%d checks, %d failed" % (len(checks), len(fail)))
sys.exit(1 if fail else 0)
