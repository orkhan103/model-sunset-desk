# Sample fix: an n8n workflow pinned to gpt-3.5-turbo

Produced 2026-10-09 (AI-assisted, human-reviewed) for **Model Sunset Desk**. AI-assisted, human-reviewed before any client use.

**What this is.** A proof sample. The workflow is synthetic and was written for this demonstration; it is not a client's workflow, and no client data was used. **No OpenAI API calls were made** (budget $0), and the workflows were **not imported into a running n8n instance**. They were built against n8n's source code (pinned commit below) and checked with the scripts in this folder. Section 8 lists every limit.

Source labels used below:
- **[V-doc]**: read live on 2026-10-09 from the named primary page.
- **[V-src]**: read from n8n source at commit `5bc602147761788693427000bbd998279c09c689` (github.com/n8n-io/n8n, master on 2026-10-09).
- **[Tested]**: executed here; the output is shown.
- **[Unverified]**: our expectation, not confirmed.

## 1. Files

| File | What it is |
|---|---|
| `before.json` | n8n workflow export: Webhook -> OpenAI "Message a model" (pinned to `gpt-3.5-turbo`, JSON output, temperature 0.2, max 350 tokens) -> Respond to Webhook. |
| `after.json` | The fixed workflow: model `gpt-5.6-terra`, incompatible options removed or adapted, retries, an output validator and an error-alert branch with a graceful fallback response. |
| `validate.py` | Standard-library checker. Confirms both files parse and reports every retiring model ID, telling real model settings apart from mentions in text. It also works on other n8n exports and on Make blueprint JSON. |
| `check_code_node.py` | Runs the Code node's JavaScript and the alert expression from `after.json` in Node.js against 9 synthetic model replies (section 5.3). |
| `test_fixtures/` | Small JSON files used to test `validate.py` (legacy-node implicit default, model hidden in an HTTP body, Make-style mapper, fine-tune ID, near-miss IDs that must not match, broken JSON, naive swap). |

## 2. What breaks on 23 Oct 2026

- OpenAI's deprecations page, entry announced 2026-04-22, lists `gpt-3.5-turbo` (with `gpt-3.5-turbo-0125` and `gpt-3.5-turbo-completions`) for shutdown on **October 23, 2026**, with `gpt-5.6-terra` as the substitute. [V-doc: https://developers.openai.com/api/docs/deprecations]
- In `before.json`, node "Classify and draft reply" is the n8n OpenAI node (`@n8n/n8n-nodes-langchain.openAi`, typeVersion 1.8, resource `text`, operation `message`). It sends `model` plus the messages to `POST /chat/completions`. [V-src: `packages/@n8n/nodes-langchain/nodes/vendors/OpenAi/v1/actions/text/message.operation.ts`, lines 240-302]
- From 23 Oct, the API call fails because the model no longer exists. This is the loud failure. The exact error text and status code cannot be known before the shutdown. [Unverified]
- The node has no error handling (`onError` is unset, so it defaults to "Stop Workflow"). The execution therefore stops, the "Respond to Webhook" node never runs, and the support form that called the webhook gets an error instead of a triage result. Nobody is alerted unless a workflow-level Error Workflow is configured. [V-src: `OnError` type in `packages/workflow/src/interfaces.ts:1747`; error-workflow behaviour: V-doc https://docs.n8n.io/flow-logic/error-handling/]

## 3. Why changing only the model string is not enough

`test_fixtures/naive_swap_only.json` is `before.json` with only the model string changed to `gpt-5.6-terra`. It no longer pins a retiring model, but `validate.py` raises three warnings, each for a concrete reason:

1. **Hidden reasoning tokens can use up the token cap and return empty text.**
   - n8n maps the node's "Maximum Number of Tokens" option to `max_completion_tokens` [V-src: message.operation.ts:256-259]. OpenAI defines that as "an upper bound for the number of tokens that can be generated for a completion, including visible output tokens and reasoning tokens" [V-doc: Chat Completions API reference].
   - `gpt-5.6-terra` is a reasoning model. Its model page says "Reasoning.effort supports: none, low, medium (default), high, xhigh, and max" [V-doc: https://developers.openai.com/api/docs/models/gpt-5.6-terra].
   - OpenAI's reasoning guide warns that hitting the limit "might occur before any visible output tokens are produced, meaning you could incur costs for input and reasoning tokens without receiving a visible response". It also says "OpenAI recommends reserving at least 25,000 tokens for reasoning and outputs when you start experimenting with these models" [V-doc: https://developers.openai.com/api/docs/guides/reasoning].
   - Zapier's help article independently warns: "If you set the token limit too low, the model may return an empty output text." [V-doc: help.zapier.com article 14860148802829]
   - So a 350-token cap that was fine for gpt-3.5-turbo can now produce empty answers with `finish_reason: "length"`. That is a quiet failure: the workflow "succeeds" and returns nothing useful.
2. **Sampling settings.**
   - OpenAI's GPT-6 migration guidance says: "When reasoning effort is not none, remove temperature, top_p, and top_logprobs" [V-doc: https://developers.openai.com/api/docs/guides/latest-model]. GPT-5.6 also defaults to medium effort [V-doc: reasoning guide].
   - The pages we read do not say whether GPT-5.6 rejects `temperature`. [Unverified for 5.6] We remove it, so the request is valid either way.
3. **No error branch.** A naive swap keeps the "stop and say nothing" behaviour, so the next failure is just as invisible.

**Cost changes too.** Prices are per 1M tokens, list price, read from the model pages [V-doc]:

| Model | Input | Output |
|---|---|---|
| gpt-3.5-turbo | $0.50 | $1.50 |
| gpt-5.6-terra | $2.00 | $12.00 |

Reasoning tokens "are billed as output tokens" [V-doc: reasoning guide].

An illustration with assumed token counts, not measured:
- Assume a ticket uses 600 input and 250 visible output tokens. That costs about $0.000675 on gpt-3.5-turbo and $0.0042 on gpt-5.6-terra, before reasoning tokens.
- Each 500 reasoning tokens adds about $0.006.

The real numbers come from the regression run on the client's own tickets.

## 4. The fix (`after.json`)

| # | Change | Why | Basis |
|---|---|---|---|
| 1 | `modelId`: `gpt-3.5-turbo` (list mode) -> `gpt-5.6-terra` (ID mode) | OpenAI's listed substitute. ID mode sends the value as typed, without depending on the account's model list. | [V-doc] deprecations page; [V-src] `modelRLC` modes `list`/`id` in `v1/actions/descriptions.ts` |
| 2 | Removed `temperature: 0.2` | Avoids a rejected request while the model is reasoning; keep this as a test variable. | [V-doc] GPT-6 rule; [Unverified] for 5.6 |
| 3 | `maxTokens` 350 -> 25000 | This is a ceiling, not a target; reasoning tokens count toward it. After the test run, lower it to about 2x the largest observed `completion_tokens`. | [V-doc] reasoning guide, API reference |
| 4 | `reasoning_effort: low` added | Lower latency and cost for a short classification task. The test run compares `low` against `medium` (the default). n8n shows this option only for model IDs matching `^gpt-5.*` (and o-series). | [V-src] message.operation.ts:182-212 |
| 5 | OpenAI node: Retry On Fail, Max. Tries 3, Wait Between Tries 3000 ms | Rides out short rate-limit or server errors. | [V-src] `INode.retryOnFail/maxTries/waitBetweenTries`; UI labels from n8n `en.json` |
| 6 | OpenAI node: On Error = "Continue (using error output)" | API failures go to a second output instead of killing the run. | [V-src] `onError: 'continueErrorOutput'`; label from `en.json` line 2486 |
| 7 | New Code node "Validate AI output" (On Error = error output) | Turns quiet failures into errors: `finish_reason = length`, a refusal, empty text, non-JSON, or wrong keys/values. It passes through exactly `category`, `urgency`, `summary`, `reply_draft`. | [Tested] (see 5.3) |
| 8 | New HTTP Request node "Alert: AI step failed" | POSTs `{"text": ...}` to your alert webhook (Slack- or Google-Chat-style incoming webhook), with the workflow name, ticket subject, error and execution ID. Its own On Error is "Continue", so a broken alert never blocks the fallback. **Replace `https://replace-with-your-alert-webhook.invalid/`**; the `.invalid` domain can never resolve, so it fails safely until set. | [V-src] HttpRequest V3 params `method/url/sendBody/specifyBody/jsonBody` |
| 9 | New "Fallback: queued for human" Respond node, HTTP 202 `{"status":"queued_for_human_review"}` | The form caller always gets an answer. | [V-src] RespondToWebhook `respondWith: json`, `options.responseCode` |
| 10 | Success response unchanged in shape | "Return triage result" now returns the validated object, with the same four keys the old workflow returned. Downstream callers need no change. | [Tested] (validator logic) |

Unchanged: node type and version (`@n8n/n8n-nodes-langchain.openAi` v1.8, Chat Completions), prompts, JSON output mode, the webhook path, and the credential reference.

Not done in this sample (options to test with a client):
- moving to the node's v2 "Generate a Model Response" operation (Responses API, strict JSON-schema output) [V-src: `v2/actions/text/response.operation.ts`];
- `reasoning_effort: none`, which gpt-5.6-terra supports but n8n v1's dropdown does not offer.

## 5. Proof that the checks run

### 5.1 `python3 -I validate.py` (sample mode) [Tested, 2026-10-09]

```
== before.json
   parse: OK  [n8n workflow (4 nodes)]
   PINNED to a model shutting down 2026-10-23: 1 setting(s) -> gpt-3.5-turbo
   mentions only (prose, comments, display labels; review, not counted): 3
     mention  gpt-3.5-turbo          -> gpt-5.6-terra                      $.name  (text mention)
     mention  gpt-3.5-turbo          -> gpt-5.6-terra                      $.nodes[0].parameters.content  (text mention in node 'Sticky Note')
     SHUTDOWN gpt-3.5-turbo          -> gpt-5.6-terra                      $.nodes[2].parameters.modelId.value  (model setting in node 'Classify and draft reply')
     mention  gpt-3.5-turbo          -> gpt-5.6-terra                      $.nodes[2].parameters.modelId.cachedResultName  (display label in node 'Classify and draft reply')
   info: connections OK (2 source nodes, all targets exist)
   info: AI node 'Classify and draft reply' (@n8n/n8n-nodes-langchain.openAi v1.8): model=gpt-3.5-turbo; options: maxTokens=350, temperature=0.2; onError=stopWorkflow (default); error branch wired: no; retries: off
   WARN: 'Classify and draft reply': no error branch; a failed AI call stops the workflow without an alert
   provenance stamp present: yes
== after.json
   parse: OK  [n8n workflow (7 nodes)]
   PINNED to a model shutting down 2026-10-23: 0 setting(s)
   mentions only (prose, comments, display labels; review, not counted): 2
     mention  gpt-3.5-turbo          -> gpt-5.6-terra                      $.nodes[0].parameters.content  (text mention in node 'Sticky Note')
     mention  gpt-3.5-turbo          -> gpt-5.6-terra                      $.nodes[3].parameters.jsCode  (text mention in node 'Validate AI output')
   info: connections OK (4 source nodes, all targets exist)
   info: AI node 'Classify and draft reply' (@n8n/n8n-nodes-langchain.openAi v1.8): model=gpt-5.6-terra; options: maxTokens=25000, reasoning_effort=low; onError=continueErrorOutput; error branch wired: yes; retries: 3 tries
   provenance stamp present: yes
PASS: before.json pins a retiring model; after.json pins none
```

The "mention" rows in after.json are the sticky note and a code comment that describe the migration history. They are deliberately not counted. Only model settings fail the check.

### 5.2 Fixture runs [Tested]

| Fixture | Result | Exit |
|---|---|---|
| `legacy_node_implicit_default.json` | Legacy `n8n-nodes-base.openAi` node (chat) with **no model field**: flagged as implicit `gpt-3.5-turbo`, because that node's code default is `'gpt-3.5-turbo'` [V-src: `packages/nodes-base/nodes/OpenAi/ChatDescription.ts`, lines 94 and 156]. A plain text search would miss this. | 1 |
| `http_body_pin.json` | `"model": "gpt-4"` inside an HTTP Request JSON body: flagged as a model setting inside text | 1 |
| `make_style_mapper.json` | `gpt-4-turbo` and `ft:gpt-3.5-turbo-0125:acme::abc123` in a Make-shaped `flow[].mapper.model` (illustrative structure, not a verified Make schema) | 1 |
| `near_misses_should_pass.json` | `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-5.6-terra`, `o3`, `ft:gpt-4.1-2025-04-14:...`, `gpt-4o-2024-08-06`, `gpt-5-mini`: none flagged | 0 |
| `naive_swap_only.json` | Passes the pin check; warns about `temperature`, `maxTokens=350` and the missing error branch | 0 |
| `broken.json` | Parse failure reported | 2 |

### 5.3 Validator and alert logic [Tested in Node.js v22.22.3, outside n8n]

To reproduce, run `python3 -I check_code_node.py` (exit code 0 means all 9 cases were routed as expected). The Code node's JavaScript was wrapped in a function and run on 9 synthetic model replies:
- **Passed through:** a valid object, and a valid JSON string.
- **Sent to the error branch, each with its own message (7 cases):**
  - `finish_reason=length`
  - empty string
  - `null` content
  - a refusal with text content
  - a refusal with `null` content
  - prose instead of JSON
  - wrong keys or values

The alert `jsonBody` expression was evaluated as plain JavaScript with mock `$workflow`, `$execution` and `$()`. It produced, for example:
`{"text":"[n8n] Support ticket triage: AI triage failed; ticket \"Cannot log in\" needs a human. Error: AI output is empty (no text returned). | execution 1234"}`

n8n's own expression engine was not run. [Unverified inside n8n]

## 6. How a client applies it

**Before you start**
1. In the current workflow, open the canvas header's **Workflow** menu and choose **Download**. Keep that file: it is your rollback. [V-doc: https://docs.n8n.io/workflows/export-import/]
2. Use a **staging** OpenAI key, or a separate project key, for testing, and revoke it afterwards. Model Sunset Desk never needs production access or passwords.

**Import**
1. Create a new workflow, then choose **Workflow** menu -> **Import from File** and pick `after.json`. Pasting the JSON onto the canvas also works. [V-doc: same page]
2. Open "Classify and draft reply" and select your OpenAI credential. The sample carries a placeholder credential ID, but in a real delivery we keep yours. Exports include credential names and IDs, never the secret. [V-doc]
3. Open "Alert: AI step failed" and paste your alert webhook URL.
4. Optional: in **Workflow Settings**, set an **Error workflow** that starts with an **Error Trigger** as a second safety net. [V-doc: https://docs.n8n.io/flow-logic/error-handling/]

**Test execution (before 23 Oct)**
1. Open the Webhook node, select **Test URL**, then click **Listen for Test Event** (or **Execute workflow**). The test URL works without publishing. [V-doc: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/]
2. Send a ticket. The values below are a made-up example:
   ```
   curl -sS -X POST "<your Test URL>" -H 'Content-Type: application/json' \
     -d '{"subject":"Charged twice","plan":"Pro","message":"My card was charged two times on 3 Oct. Please fix."}'
   ```
3. Check that the reply has `category`, `urgency`, `summary` and `reply_draft`. Then force the error branch by temporarily setting the model ID to a nonexistent value. Confirm the alert arrives and the caller gets HTTP 202 `queued_for_human_review`.
4. Swap & Verify does more than one manual test. It replays 30 of your real past inputs through the old and new versions while the old model still answers (until 22 Oct). It then reports:
   - how often category and urgency match;
   - JSON validity;
   - empty and refused replies;
   - `completion_tokens`, so you can size `maxTokens`;
   - latency and cost per call.

   It is a measured comparison, not a promise of identical output.

**Go live**
1. Unpublish the old workflow, then publish the new one. The production webhook registers on publish. [V-doc: webhook page]
2. Keep the same webhook path so callers need no change. Two published workflows listening on the same path and method are expected to conflict, so switch them over in that order. [Unverified]

**Rollback**
- **Until 22 Oct:**
  - re-publish the old workflow; or
  - re-import the file you downloaded; or
  - use **Workflow history**. n8n documents that "Versions from the last 24 hours are available for all users"; five days on Cloud Pro; full history on Enterprise. [V-doc: https://docs.n8n.io/workflows/history/]
- **From 23 Oct**, rolling back to `gpt-3.5-turbo` is impossible because the model is gone. Roll back the *other* changes instead (options, validator, alert) and keep a supported model.

**Variants we also handle**
- **AI Agent + "OpenAI Chat Model" sub-node** (`@n8n/n8n-nodes-langchain.lmChatOpenAi`, v1-1.3): the model is in `model`, which is a resource locator from v1.2. Its options include `maxTokens`, `temperature` and `reasoningEffort`. [V-src: `LmChatOpenAi.node.ts` lines 89, 144-213, 400, 542, 551]
- **Legacy hidden `n8n-nodes-base.openAi` node** (v1/1.1): the chat model is in `model` or `chatModel`, with a code default of `gpt-3.5-turbo`. [V-src] n8n's parameter helper can return only non-default values (`packages/workflow/src/node-helpers.ts:747`), so an export may never contain the model string. `validate.py` checks for exactly this case.

## 7. Make and Zapier: where the model is chosen

**Make** [V-doc: https://apps.make.com/openai-modules, page "Updated 05 Oct 2026"]
- **"Generate a completion" module.**
  - Model field: "Select or map the model you want to use." Note on the page: "Only models available for the account are listed for selection."
  - Also documented: Response Format, Reasoning Effort ("low, medium, or high ... Defaults to medium") and Max Output Tokens ("The default value is 2048"). The page adds: "The o1 and o3 models require tokens for both output and reason."
  - Temperature: "Defaults to 1."
- **"Generate a response" module.**
  - Model field: "Select the model that will generate the response."
  - Max Output Tokens: "including visible output tokens and reasoning tokens".
  - Its Prompt Type can be "Reusable prompt". OpenAI's reusable prompts API (`v1/prompts`) shuts down on 30 Nov 2026 [V-doc: deprecations page], so these scenarios need a second change before then.
- **"Select or map"** means the model can come from a mapped variable, such as a data store or an earlier module. Then the literal ID is not in the module itself. [Inference]
- **Export and import.** Scenarios export and import as **blueprint** `.json` files (import limit 2 MB). [V-doc: https://help.make.com/blueprints, "Updated 01 Jun 2026"]
  - `validate.py` reads any JSON, so it can scan a blueprint.
  - We tested it only on a Make-*shaped* fixture, not a real exported blueprint. [Unverified on real blueprints]

**Zapier** [V-doc: help.zapier.com articles 14860148802829 (updated 2026-10-01) and 22497191078797 (updated 2026-05-29)]
- **Two generations of actions.** The ChatGPT (OpenAI) app lists "(Recommended)" actions "Powered by Responses API" (Conversation, Analyze Text, Extract Structured Data and others). It also lists "(Legacy)" actions "Powered by Chat Completions API" (Conversation (Legacy), Classify Text (Legacy), Summarize Text (Legacy), and others).
- **Empty-output risk.** "In some advanced models, additional reasoning tokens are consumed ... If you set the token limit too low, the model may return an empty output text."
- **Advanced fields.**
  - Temperature.
  - Maximum Length: "the combined count of tokens from your prompt and the model's response". If left blank, Zapier "will attempt to automatically calculate this field, based on your selected model".
  - Top P, Stop Sequences, Frequency Penalty and Presence Penalty.
- **[Unverified] Model dropdown.** The help articles we read do not document the Model field's dropdown wording, whether a custom model ID can be typed, or a Zap JSON export. For Zapier we therefore inventory each Zap's AI steps by hand in the editor (Model, Maximum Length, Temperature, legacy vs. recommended action). We do not claim a file-based check.

## 8. Limits of this sample

- No live API calls, so no before/after quality, latency or cost numbers. Those need the client's staging key and real inputs.
- `after.json` and `before.json` were not imported into a running n8n. Node types, versions, parameter names, option values and UI labels were taken from n8n source at the pinned commit and from n8n docs. Both files parse, connections were checked, and the Code-node logic was run in Node.js.
- Whether `gpt-5.6-terra` rejects `temperature`/`top_p` at non-`none` reasoning effort is not documented in the pages we read. It is documented for GPT-6.
- Whether `gpt-5.6-terra` appears in a particular account's model list depends on that account's access. ID mode sends it regardless.
- The cost illustration in section 3 uses assumed token counts.

## 9. Want this done for your workflows?

**Swap & Verify, $290 per bundle of up to 3 n8n/Make/Zapier workflows.** We deliver a fixed workflow export plus a 1-page quality and cost report from a 30-case before/after run on your own inputs, using your staging key. You pay on delivery, by Payment Link, and only if the delivery passes your review. Delivery is within 48h of access and a staging key. AI-assisted, human-reviewed. Contact: hello@modelsunsetdesk.com - https://orkhan103.github.io/model-sunset-desk

## 10. Sources (all read 2026-10-09)

- OpenAI deprecations: https://developers.openai.com/api/docs/deprecations
- OpenAI model pages: https://developers.openai.com/api/docs/models/gpt-5.6-terra and https://developers.openai.com/api/docs/models/gpt-3.5-turbo
- OpenAI reasoning guide: https://developers.openai.com/api/docs/guides/reasoning
- OpenAI GPT-6 guide: https://developers.openai.com/api/docs/guides/latest-model
- OpenAI Chat Completions API reference: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- n8n source at commit 5bc602147761788693427000bbd998279c09c689:
  - `packages/@n8n/nodes-langchain/nodes/vendors/OpenAi/` (`OpenAi.node.ts`, `v1/OpenAiV1.node.ts`, `v1/actions/descriptions.ts`, `v1/actions/text/message.operation.ts`, `v2/actions/text/response.operation.ts`, `methods/listSearch.ts`)
  - `packages/@n8n/ai-utilities/src/model-discovery/providers/openai.ts`
  - `packages/@n8n/nodes-langchain/nodes/llms/LMChatOpenAi/LmChatOpenAi.node.ts`
  - `packages/nodes-base/nodes/OpenAi/ChatDescription.ts`
  - `packages/nodes-base/nodes/{Webhook,Code,RespondToWebhook,HttpRequest/V3,StickyNote}/`
  - `packages/workflow/src/interfaces.ts` and `node-helpers.ts`
  - `packages/frontend/@n8n/i18n/src/locales/en.json`
- n8n docs:
  - https://docs.n8n.io/workflows/export-import/
  - https://docs.n8n.io/workflows/history/
  - https://docs.n8n.io/flow-logic/error-handling/
  - https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/
- Make: https://apps.make.com/openai-modules and https://help.make.com/blueprints
- Zapier:
  - https://help.zapier.com/hc/en-us/articles/14860148802829
  - https://help.zapier.com/hc/en-us/articles/22497191078797

Downloaded copies of these pages are kept as untrusted data under `launch/_untrusted/`; they were never executed.
