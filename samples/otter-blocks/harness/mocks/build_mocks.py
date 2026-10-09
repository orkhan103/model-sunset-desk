#!/usr/bin/env python3
"""Build SYNTHETIC mock responses for run_harness.py --dry-run.

Produced 2026-10-09 (AI-assisted, human-reviewed).

Every response here is hand-written fixture data. None of it was produced by gpt-3.5-turbo or
gpt-5.6-terra, and none of it is evidence about either model. Design choices that keep the demo honest:
  * Old and new arms share the same base output per case, except seven labelled variations (old: 3, new: 4)
    injected only to show that the detectors fire.
  * Latency and token counts come from ONE deterministic formula used for both arms.
  * Response JSON follows the documented Chat Completions shapes: legacy `function_call` for the old
    request (which sends `functions`), `tool_calls` for the patched request (which sends `tools`).

Usage: python3 -I build_mocks.py   (writes mock_responses.jsonl and mock_responses_post_shutdown.jsonl)
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "..", "cases.jsonl")

TEXT = {
    "B01": "<h2>Our Story</h2><p>Since 1998 our family has baked sourdough in the heart of Halifax, starting with one wood-fired oven and a starter we still feed every morning. Three generations now share the early shifts, the flour-dusted aprons and the pride of a loaf done right.</p><p>We use local grain, long fermentation and no shortcuts. Stop by for a warm loaf, a cinnamon knot or simply a chat about bread; the kettle is always on and the door is always open.</p>",
    "B02": "<h2>Frequently Asked Questions</h2><h3>How much does a groom cost?</h3><p>Prices start at $45 for small breeds and depend on coat type and size; we confirm the price before we begin.</p><h3>How do I book?</h3><p>Book online or call us. Weekend slots fill quickly, so please book a week ahead.</p><h3>Which vaccinations are required?</h3><p>Rabies and DHPP must be current. Please bring proof on your first visit.</p><h3>What is the cancellation policy?</h3><p>Cancel or reschedule at least 24 hours ahead to avoid a $15 late-cancellation fee.</p><h3>Is there parking?</h3><p>Yes, free parking is available behind the salon, with a short-stay drop-off spot by the door.</p>",
    "B03": "<h2>Compare Hosting Plans</h2><table><tr><th>Plan</th><th>Storage</th><th>Bandwidth</th><th>Sites</th><th>Monthly price</th></tr><tr><td>Starter</td><td>10 GB</td><td>100 GB</td><td>1</td><td>$X</td></tr><tr><td>Business</td><td>50 GB</td><td>Unmetered</td><td>5</td><td>$X</td></tr><tr><td>Agency</td><td>200 GB</td><td>Unmetered</td><td>25</td><td>$X</td></tr></table>",
    "B04": "<p>As the days shorten and the first frost approaches, your garden needs a little care to come back strong in spring. A few hours of preparation now protects roots, soil and tools from the hardest months of the year.</p><p>In this guide we cover what to cut back and what to leave standing, how to mulch beds, when to plant bulbs and how to store hoses and pots. Follow these steps and you will start next season with healthier plants and fewer surprises.</p>",
    "B05": "<p>Start every morning with a mug made by hand. Each 350 ml piece is thrown on the wheel, glazed in small batches and fired for a finish that is a little different every time.</p><ul><li>Generous 350 ml capacity</li><li>Dishwasher and microwave safe</li><li>Lead-free, food-safe glaze</li><li>Comfortable, balanced handle</li></ul>",
    "B06": "<h1>Bookkeeping that keeps up with your freelance life</h1><p>Send us your receipts and invoices; we keep your books accurate and tax-ready. You focus on clients, we handle the numbers.</p><ul><li>Monthly reports in plain language</li><li>Quarterly tax estimates on time</li><li>One flat fee, no surprises</li></ul>",
    "B07": "<h2>Nos services</h2><ul><li>Physiothérapie orthopédique et sportive</li><li>Rééducation après une chirurgie</li><li>Traitement des douleurs au dos et au cou</li><li>Programmes d'exercices à domicile personnalisés</li></ul>",
    "B08": "<p>For over fifteen years we have provided <strong>high-quality landscaping</strong> to homes and businesses across the region, earning a reputation for reliability, care and friendly service.</p>",
    "B09": "<p>Unwind after work with our evening yoga classes every Tuesday and Thursday. Each session blends gentle flow, breath work and a calm final relaxation, so you leave lighter than you arrived.</p><p>Classes welcome every level, from first-timers to regular practitioners. Mats and props are provided, and our instructors offer options for every body. Arrive ten minutes early on your first visit to settle in.</p>",
    "B10": "<ul><li>Up to three remote days per week, agreed with your manager a week ahead; be reachable 10:00-15:00 ET.</li><li>Home-office equipment can be expensed up to $500 per year with receipts; VPN and screen-lock rules still apply.</li><li>The policy will be reviewed after six months using a team survey and productivity data.</li></ul>",
    "B11": "<p>Please note that our store will be closed on Monday in observance of the holiday. We will reopen at our regular hours on Tuesday and look forward to welcoming you.</p>",
    "B12": "<p>Changed your mind? No problem! Just send us your return request within 30 days of purchase and we will take care of the rest. Requests after 30 days unfortunately cannot be processed, so be sure to reach out in time.</p>",
    "B13": "<p>Friendly reminder: the office kitchen is not a science experiment. Please wash your mug, wipe the counter and rescue your leftovers before they develop opinions of their own. The dishes will not do themselves, no matter how long we all stare at them.</p>",
    "B14": "<p>Welcome to the community garden! We are glad you are here. The tool shed is open from 7 am to 8 pm; please return tools clean and to their hooks, and report anything broken on the shed whiteboard.</p><p>Watering runs on a shared schedule: even-numbered plots water Monday, Wednesday and Friday, odd-numbered plots Tuesday, Thursday and Saturday. Sunday is free for all. Happy growing!</p>",
    "B15": "<p>Our <strong>cabin</strong> rests at the water's edge, framed by tall pines and a private dock where mornings start with mist over the lake. Inside, a stone fireplace warms the open living space, and <a href=\"/booking\">two bedrooms</a> with soft linens look out over the water.</p>",
    "B16": "<h2>A Calming Herbal Tea Ritual</h2><p>Our herbal blend is a caffeine-free way to slow down after meals. It is not a medicine and does not treat or cure diabetes or any other condition; talk to your doctor about managing blood sugar.</p>",
}

FORMS = {
    "F01": [{"label": "Full name", "type": "text", "placeholder": "Jane Doe", "required": True},
            {"label": "Email", "type": "email", "placeholder": "jane@example.com", "required": True},
            {"label": "Phone", "type": "tel", "placeholder": "902-555-0100"},
            {"label": "Preferred appointment date", "type": "date", "required": True},
            {"label": "Message", "type": "textarea", "placeholder": "How can we help?"}],
    "F02": [{"label": "Full name", "type": "text", "placeholder": "Alex Martin", "required": True},
            {"label": "Email", "type": "email", "placeholder": "alex@example.com", "required": True},
            {"label": "CV", "type": "file", "allowedFileTypes": ["application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"], "required": True},
            {"label": "Cover letter", "type": "textarea", "placeholder": "Tell us about yourself"}],
    "F03": [{"label": "Guest name", "type": "text", "placeholder": "Sam Lee", "required": True},
            {"label": "Number of guests", "type": "number", "placeholder": "2", "required": True},
            {"label": "Meal choice", "type": "radio", "choices": ["Beef", "Fish", "Vegetarian"], "required": True},
            {"label": "Dietary restrictions", "type": "textarea", "placeholder": "Nut allergy"},
            {"label": "Do you need parking?", "type": "radio", "choices": ["Yes", "No"]}],
    "F04": [{"label": "Prénom", "type": "text", "placeholder": "Marie", "required": True},
            {"label": "Adresse e-mail", "type": "email", "placeholder": "marie@exemple.fr", "required": True},
            {"label": "Centres d'intérêt", "type": "checkbox", "choices": ["Pains", "Viennoiseries", "Pâtisseries", "Ateliers"]}],
    "F05": [{"label": "Summary", "type": "text", "placeholder": "Export button does nothing", "required": True},
            {"label": "Steps to reproduce", "type": "textarea", "placeholder": "1. Open... 2. Click...", "required": True},
            {"label": "Severity", "type": "select", "choices": ["Low", "Medium", "High", "Critical"], "required": True},
            {"label": "Browser", "type": "text", "placeholder": "Chrome 129"},
            {"label": "Screenshot", "type": "file", "allowedFileTypes": ["image/png", "image/jpeg"]}],
    "F06": [{"label": "Date", "type": "date", "required": True},
            {"label": "Time", "type": "time", "required": True},
            {"label": "Party size", "type": "number", "placeholder": "4", "required": True},
            {"label": "Seating preference", "type": "radio", "choices": ["Indoor", "Patio"]},
            {"label": "Special occasion", "type": "text", "placeholder": "Birthday"},
            {"label": "I agree to the cancellation policy", "type": "checkbox", "choices": ["I agree"], "required": True}],
    "F07": [{"label": "Nombre", "type": "text", "placeholder": "Lucía Gómez", "required": True},
            {"label": "Correo electrónico", "type": "email", "placeholder": "lucia@ejemplo.com", "required": True},
            {"label": "Teléfono", "type": "tel", "placeholder": "555-0100"},
            {"label": "Disponibilidad", "type": "checkbox", "choices": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"], "required": True},
            {"label": "Experiencia previa", "type": "textarea", "placeholder": "Cuéntanos tu experiencia"}],
    "F08": [{"label": "Moving date", "type": "date", "required": True},
            {"label": "Origin postal code", "type": "text", "placeholder": "B3H 1A1", "required": True},
            {"label": "Destination postal code", "type": "text", "placeholder": "M5V 2T6", "required": True},
            {"label": "Home size", "type": "select", "choices": ["Studio", "1 bedroom", "2 bedrooms", "3+ bedrooms"]},
            {"label": "Large items", "type": "textarea", "placeholder": "Piano, sofa"},
            {"label": "Do you need packing help?", "type": "radio", "choices": ["Yes", "No"]}],
    "F09": [{"label": "Attendee name", "type": "text", "placeholder": "Chris Park", "required": True},
            {"label": "Email", "type": "email", "placeholder": "chris@example.com", "required": True},
            {"label": "Company", "type": "text", "placeholder": "Acme Inc."},
            {"label": "Ticket type", "type": "radio", "choices": ["Early bird", "Regular", "Student"], "required": True},
            {"label": "T-shirt size", "type": "select", "choices": ["XS", "S", "M", "L", "XL"]},
            {"label": "Accessibility needs", "type": "textarea", "placeholder": "Wheelchair access"}],
    "F10": [{"label": "Full name", "type": "text", "required": True},
            {"label": "Email", "type": "email", "required": True},
            {"label": "Home address", "type": "textarea", "required": True},
            {"label": "Social Security number", "type": "text", "placeholder": "123-45-6789", "required": True},
            {"label": "Credit card number", "type": "text", "required": True},
            {"label": "CVV", "type": "text", "required": True}],
}

PATTERNS = {
    "P01": ["hero-area-with-button", "columns-with-icon-features", "team-members", "testimonial-columns", "contact-details-and-form"],
    "P02": ["hero-area-with-button", "border-icon-features", "content-with-features", "border-pricing-table", "call-to-action"],
    "P03": ["hero-area-with-button", "grid-portfolio-with-two-columns-and-a-description", "gallery", "testimonial-with-inline-image", "contact-details-and-form"],
    "P04": ["hero-area-with-button", "countdown-special-offer-row", "icons-and-text", "testimonial-columns", "call-to-action"],
}

# Injected variations (old: 3, new: 4), each labelled in the record's _note.
ANOMALIES = {
    ("B05", "new"): "INJECTED: HTML wrapped in a markdown code fence (shows FORMAT-REGRESSION detection).",
    ("B09", "new"): "INJECTED: one short paragraph instead of two (shows LENGTH-SHIFT and min_words failure).",
    ("B16", "new"): "INJECTED: refusal via message.refusal (shows REFUSAL-CHANGE; patched PHP returns HTTP 422 model_refusal).",
    ("F05", "old"): "INJECTED: unknown field type 'textbox' (shows the editor's silent field drop).",
    ("F09", "old"): "INJECTED: arguments truncated with finish_reason=length (shows invalid-JSON detection).",
    ("P02", "old"): "INJECTED: hallucinated slug 'pricing-table' (shows unknown-slug detection).",
    ("F10", "new"): "INJECTED: omits the SSN/card fields on a policy-edge case (shows COUNT-SHIFT + POLICY-EDGE review).",
}
PROMPT_BASE = {"textTransformation": 190, "form": 335, "patternsPicker": 560}


def output_for(case, arm):
    cid, feat = case["id"], case["feature"]
    if feat == "textTransformation":
        text = TEXT[cid]
        if (cid, arm) == ("B05", "new"):
            text = "```html\n" + text + "\n```"
        if (cid, arm) == ("B09", "new"):
            text = "<p>Unwind with evening yoga every Tuesday and Thursday: gentle flow, breath work and relaxation for every level.</p>"
        if (cid, arm) == ("B16", "new"):
            return {"refusal": "I can't help write marketing that claims a tea cures diabetes, because that health claim is false and could cause harm. I can help with a section about the tea's flavour and ingredients instead."}
        return {"content": text}
    if feat == "form":
        fields = [dict(f) for f in FORMS[cid]]
        if (cid, arm) == ("F05", "old"):
            fields[1]["type"] = "textbox"
        if (cid, arm) == ("F10", "new"):
            fields = fields[:3] + [{"label": "I agree to the giveaway rules", "type": "checkbox", "choices": ["I agree"], "required": True}]
        args = json.dumps({"fields": fields}, ensure_ascii=False)
        if (cid, arm) == ("F09", "old"):
            return {"args": args[: int(len(args) * 0.6)], "finish": "length", "name": "generateForm"}
        return {"args": args, "name": "generateForm"}
    slugs = list(PATTERNS[cid])
    if (cid, arm) == ("P02", "old"):
        slugs[3] = "pricing-table"
    return {"args": json.dumps({"slugs": slugs}), "name": "pickPatterns"}


def body_for(case, arm, out):
    cid = case["id"]
    model = "gpt-3.5-turbo-0125" if arm == "old" else "gpt-5.6-terra"
    msg = {"role": "assistant", "content": None, "refusal": None}
    finish = out.get("finish", "stop")
    text_len = len(out.get("content") or out.get("args") or out.get("refusal") or "")
    if "refusal" in out:
        msg["refusal"] = out["refusal"]
    elif "content" in out:
        msg["content"] = out["content"]
    elif arm == "old":
        msg["function_call"] = {"name": out["name"], "arguments": out["args"]}
    else:
        msg["tool_calls"] = [{"id": "call_mock_%s" % cid, "type": "function",
                              "function": {"name": out["name"], "arguments": out["args"]}}]
        finish = out.get("finish", "tool_calls")
    pt = PROMPT_BASE[case["feature"]] + len(case["input"]) // 4 + (380 if case.get("pro") else 0)
    ct = max(1, text_len // 4)
    usage = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct,
             "prompt_tokens_details": {"cached_tokens": 0}, "completion_tokens_details": {"reasoning_tokens": 0}}
    if arm == "new":
        usage["prompt_tokens_details"]["cache_write_tokens"] = 0
    return {"id": "chatcmpl-mock-%s-%s" % (cid, arm), "object": "chat.completion", "created": 1791561600,
            "model": model, "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": usage}, ct


def latency(case_id, arm, completion_tokens):
    # Same formula AND the same noise draw for both arms (seeded by case only): differences come only from
    # output length, so the mock latencies carry no information about either model.
    rng = random.Random("latency|%s" % case_id)
    return int((350 + 11 * completion_tokens) * rng.lognormvariate(0, 0.25))


def main():
    cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
    rows = []
    for case in cases:
        for arm in ("old", "new"):
            out = output_for(case, arm)
            body, ct = body_for(case, arm, out)
            rows.append({"case_id": case["id"], "arm": arm, "http_status": 200, "latency_ms": latency(case["id"], arm, ct),
                         "_synthetic": True, "_note": ANOMALIES.get((case["id"], arm), "synthetic fixture"), "body": body})
    with open(os.path.join(HERE, "mock_responses.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Post-shutdown scenario: the old model is gone. The error body is SYNTHETIC; OpenAI's exact
    # post-shutdown error text/code was not verified (the shutdown has not happened on 2026-10-09).
    post = []
    for r in rows:
        if r["case_id"] not in ("B01", "F01", "P01"):
            continue
        if r["arm"] == "old":
            r = {"case_id": r["case_id"], "arm": "old", "http_status": 404, "latency_ms": 140, "_synthetic": True,
                 "_note": "SYNTHETIC post-2026-10-23 error; real code/message unverified",
                 "body": {"error": {"message": "(synthetic) The model `gpt-3.5-turbo` does not exist or you do not have access to it.",
                                    "type": "invalid_request_error", "param": None, "code": "model_not_found"}}}
        post.append(r)
    with open(os.path.join(HERE, "mock_responses_post_shutdown.jsonl"), "w", encoding="utf-8") as fh:
        for r in post:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote %d + %d mock rows" % (len(rows), len(post)))


if __name__ == "__main__":
    main()
