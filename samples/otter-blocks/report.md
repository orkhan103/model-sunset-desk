# Swap & Verify sample: Otter Blocks, gpt-3.5-turbo to gpt-5.6-terra

**Model Sunset Desk: public proof sample.** Produced 2026-10-09 (AI-assisted, human-reviewed). AI-assisted, human-reviewed before any client use.

Subject: Otter Blocks 3.2.7 (Themeisle), a GPL WordPress plugin with 300,000 active installs according to WordPress.org (our scan, `research/wp-scan/plugins_retiring_models.csv`). Source: `downloads.wordpress.org/plugin/otter-blocks.latest-stable.zip`, sha256 `c59d54bd...71edadc0`, downloaded 2026-10-09.

> **Read this first.** No live API calls were made for this sample (budget $0). The patch is real, applies cleanly, and its new logic is unit-tested on PHP 5.6 and 8.3. The regression harness is real and runs on the client's own OpenAI key. The before/after table further down comes from a **dry run on synthetic mock responses**, included to show what the client report looks like. It contains no measurements of either model. We are not affiliated with Themeisle, have not contacted them, and have not opened an issue or pull request anywhere.

## 1. Executive summary

- **What breaks.** On 23 Oct 2026 OpenAI shuts down `gpt-3.5-turbo` (OpenAI deprecations page, entry announced 2026-04-22; recommended replacement `gpt-5.6-terra`). On sites that use Otter's own OpenAI API key (rather than WordPress AI Client connectors), four things then fail outright:
  - saving or changing the API key, because of a hard-coded check at `inc/server/class-prompt-server.php:144`;
  - the AI Block;
  - the AI Form generator;
  - the legacy Patterns picker.

  The last three fail because the prompt templates Otter downloads from Themeisle, which we read on 2026-10-09, all pin `"model": "gpt-3.5-turbo"`.
- **What our scan missed and this review found.** The automated scan flagged line 144. Reading the code showed that line 144 is only the API-key check. The larger exposure is the **remote templates**: Otter caches them for 7 days, so a server-side fix by the vendor can take up to a week to reach a site.
- **What still works.** Otter 3.2.7 is already partly modernised. The page/section generator defaults to `gpt-5-mini` and already renames `max_tokens` to `max_completion_tokens`. The WordPress AI Client backend ignores the model pin. Neither is affected on 23 Oct.
- **The fix.** Two files change (5 diff hunks). The patch adds a filterable map of retiring models to OpenAI's recommended replacements. When it swaps a non-reasoning model, it sets `reasoning_effort: "none"`. It drops `temperature`/`top_p` for GPT-5.x unless a site opts back in, converts the deprecated `functions`/`function_call` to `tools`/`tool_choice`, reads the `tool_calls` response shape, and surfaces model refusals. Every default can be changed through a WordPress filter, and one filter disables the whole swap. A no-core-edit **mu-plugin** with the same behaviour is included for site owners who cannot wait for a plugin release.
- **Verified:**
  - the patch applies to pristine 3.2.7;
  - `php -l` reports no syntax errors on PHP 5.6.40 (the plugin's minimum) or PHP 8.3.35;
  - 24/24 behavioural checks pass for the patch logic and 8/8 for the mu-plugin, on both PHP versions;
  - the harness's Python mirror of the transform passes 10/10.
- **Not verified:**
  - whether `gpt-5.6-terra` accepts `temperature` (the docs do not say), so the patch defaults to the safe choice;
  - the exact error OpenAI returns after shutdown;
  - live quality, latency and cost on these prompts. The harness measures those on the client's key.
- **Cost note (arithmetic on verified list prices).** Per token, `gpt-5.6-terra` costs 4x `gpt-3.5-turbo` for input ($2.00 vs $0.50 per 1M) and 8x for output ($12.00 vs $1.50). The real multiplier depends on measured token counts. That cost lands on the site owner's OpenAI bill.

## 2. Exposure (file:line)

| # | Location (Otter 3.2.7) | What it does | 23 Oct impact |
|---|---|---|---|
| 1 | `inc/server/class-prompt-server.php:144` in `save_api_key()` (lines 119-188) | Validates a newly entered key with a chat completion on hard-coded `'model' => 'gpt-3.5-turbo'`. Any OpenAI error (lines 176-183) returns a `WP_Error` and the key is **not saved** (line 185 never runs). | **Breaks** |
| 2 | Remote templates from `https://api.themeisle.com/templates-cloud/otter-prompts`, fetched by `class-prompt-server.php:312-358` and cached for `WEEK_IN_SECONDS` (line 352) | All 4 templates (`form`, `contentGenerator`, `textTransformation`, `patternsPicker`) pin `"model": "gpt-3.5-turbo"`. `form` and `patternsPicker` also use legacy `functions` + `function_call`. Read 2026-10-09, sha256 `01e20afa...cfda114db3`. | **Breaks** the AI Block, AI Form generator and Patterns picker |
| 3 | `inc/server/class-otter-openai-backend.php:62-76` | The model is taken from the template payload; the `gpt-5-mini` fallback (line 71) applies only when no model is sent | Template pin wins |
| 4 | `inc/server/class-otter-openai-backend.php:178-187` | The response parser reads `message.function_call.arguments` or `message.content` only, and ignores `tool_calls` and `refusal` | Needs extending if requests move to `tools` |
| 5 | `build/blocks/blocks.js` (minified, webpack module 3907) | "Regenerate" merges `temperature: 1.3` into the template request. The page/section pipeline sends `response_format: json_object`, `max_tokens: 8192` and no model. | `temperature` support on GPT-5.6 is undocumented |
| 6 | `build/dashboard/index.js` | The dashboard "Save" button POSTs to `otter/v1/openai/key` and shows any error as a snackbar | User-visible symptom of item 1 |
| 7 | `inc/server/class-ai-backend-resolver.php:55-65` | Uses the WordPress AI Client backend when a provider is configured; otherwise uses Otter's OpenAI-key path | Decides which sites are exposed |
| 8 | `packages/e2e-tests/mu-plugins/otter-e2e-bootstrap.php:141,150,184,719,912` | Test fixtures and mocks that mention `gpt-3.5-turbo(-0125)` | None (tests only) |

## 3. What breaks on 23 Oct 2026

Applies to sites on Otter's OpenAI-key path (item 7). We do not know what share of the 300,000 installs that is.

| Feature | Request path | Expected behaviour after shutdown |
|---|---|---|
| Save or change the OpenAI key (Otter dashboard) | Key check, item 1 | The check fails, so the key is not saved and the dashboard shows OpenAI's error. A key saved earlier stays stored, because the check runs only on save. |
| AI Block (content generator) | `textTransformation` template | Each generation returns an OpenAI error, shown in the block as "Error <code> - <message>" |
| AI Form generator | `form` template | Same; no form fields are generated |
| Patterns picker (blocks saved in that mode) | `patternsPicker` template | Same |
| AI page/section generation | No model sent, so `gpt-5-mini` | **Not affected on 23 Oct.** Follow-up: the `gpt-5-mini` model page lists one snapshot, `gpt-5-mini-2025-08-07`, marked Deprecated, and the deprecations page lists that snapshot for shutdown on **11 Dec 2026** (replacement `gpt-5.6-terra`). Whether the alias will be re-pointed is not stated. |
| Sites using WordPress AI Client connectors | `WP_AI_Client_Backend` | Not affected by the pin, because Otter drops `model` on this path |

The exact HTTP status and error text OpenAI will return for a shut-down model cannot be verified before the shutdown. The harness treats `model_not_found` or HTTP 404 as "old model unavailable".

Themeisle controls the served templates and may update them before 23 Oct. Two things still need a plugin-side fix: the key check is compiled into the plugin, and cached templates can be up to 7 days old. The patch below works whatever model the templates pin.

## 4. Parameter differences, with sources

All OpenAI pages were read live on 2026-10-09 between about 12:30 and 12:50 EDT. "Verified" means the statement appears on the cited page.

| Item | Otter sends today | gpt-5.6-terra per OpenAI docs | Patch action | Source | Status |
|---|---|---|---|---|---|
| `model` | `gpt-3.5-turbo` (key check + 4 templates) | Shutdown 2026-10-23; recommended replacement `gpt-5.6-terra` | Swap via filterable map | [Deprecations](https://developers.openai.com/api/docs/deprecations) | Verified |
| Endpoint | `v1/chat/completions` | Chat Completions and Responses supported | Stay on Chat Completions | [gpt-5.6-terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) | Verified |
| `reasoning_effort` | Not sent | `none, low, medium (default), high, xhigh, max`; GPT-5.6 "defaults to medium" if omitted | Send `none` after swapping a non-reasoning model (filter: `otter_ai_openai_swap_reasoning_effort`) | terra page; [GPT-5.6 guide](https://developers.openai.com/api/docs/guides/latest-model) | Values verified; quality effect to be measured |
| `max_tokens` | Page pipeline: 8192 (already renamed by 3.2.7); templates: none | "Deprecated ... in favor of `max_completion_tokens`, and is not compatible with o-series models"; `max_completion_tokens` includes "visible output tokens and reasoning tokens" | Keep the existing rename | [Chat API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) | Verified |
| `temperature`, `top_p` | `temperature: 1.3` on Regenerate | Not stated for GPT-5.6 on the model page or the API reference. The API reference says parameter support "can differ ... particularly for newer reasoning models". The same guide's GPT-6 section says "When reasoning effort is not none, remove temperature, top_p, and top_logprobs". | Dropped for `gpt-5*`/`o*` by default; opt back in with `otter_ai_openai_keep_sampling_params`; the harness tests both with `--keep-sampling` | API reference; latest-model guide | **Not verified for terra.** Designed defensively |
| `functions`, `function_call` | `form`, `patternsPicker` | "Deprecated in favor of `tools`" / "in favor of `tool_choice`"; terra lists function calling as supported | Convert to `tools` + named `tool_choice` | API reference; terra page | Deprecation verified. Whether terra still accepts the legacy fields is not verified (not relied on) |
| Response shape | Reads `function_call.arguments` or `content` | `message.tool_calls[].function.arguments`; `function_call` "deprecated and replaced by tool_calls" | Read `tool_calls` first; keep both fallbacks | API reference | Verified |
| Refusals | `message.refusal` ignored, so the editor shows "empty response" (502, auto-retried twice) | `message.refusal` documented. GPT-5.6 guide: "users may encounter safeguards that block or refuse some requests"; generation can be "paused for several seconds mid-stream" | Return 422 `model_refusal` with the model's text (not auto-retried) | API reference; GPT-5.6 guide | Field verified; frequency to be measured |
| `response_format: json_object` | Page pipeline only | "older JSON mode ... Using json_schema is preferred" | Unchanged (path not affected on 23 Oct) | API reference | Verified |
| Usage and billing | Editor shows `total_tokens` | Reasoning tokens "are billed as output tokens"; usage reports `reasoning_tokens`, `cached_tokens`, `cache_write_tokens`; GPT-5.6 cache writes billed at 1.25x uncached input | Unchanged; the harness records every field | [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning); API reference; terra page | Verified |
| Price per 1M tokens | gpt-3.5-turbo: $0.50 in / $1.50 out | terra: $2.00 in / $0.20 cached / $12.00 out | Cost moves with the swap; the harness estimates it | [gpt-3.5-turbo](https://developers.openai.com/api/docs/models/gpt-3.5-turbo); terra page | Verified (list prices) |
| Limits | 16,385 context / 4,096 max output | 1,050,000 context / 128,000 max output; knowledge cutoff Feb 16, 2026 | n/a | Model pages | Verified |
| Length and verbosity | n/a | GPT-5.6 "tends to be more concise by default than GPT-5.5"; `verbosity` low/medium/high, default medium | Not set; use it if the harness shows outputs that are too short | GPT-5.6 guide; API reference | Verified (relative to GPT-5.5, not to gpt-3.5) |

## 5. The patch

File: `patch.diff` (unified diff against Otter 3.2.7; apply from the plugin root with `patch -p1 < patch.diff`). Patched copies of both files are in `patch-work/b/`.

**Hunk 1, `class-otter-openai-backend.php`: constants and helpers.** Adds:
- `RETIRING_MODEL_REPLACEMENTS`: every Chat Completions model on OpenAI's 23 Oct list, mapped to the replacement OpenAI recommends (filter `otter_ai_openai_model_replacements`; return an empty array to disable the swap);
- `get_key_validation_model()`: defaults to the `gpt-3.5-turbo` replacement (filter `otter_ai_openai_key_validation_model`);
- `supports_reasoning_effort_none()`: true for the GPT-5.6 family only, which is documented to accept `none`;
- `adapt_payload()`, which does four things:
  - swaps the model;
  - sets `reasoning_effort: none` only when a non-reasoning model was swapped and the request set no effort (o-series sources keep the target's default);
  - drops `temperature`/`top_p`/logprobs for `gpt-5*`/`o*` unless a site opts in;
  - converts `functions`/`function_call` to `tools`/`tool_choice` unless the request already has `tools`.

```diff
--- a/inc/server/class-otter-openai-backend.php
+++ b/inc/server/class-otter-openai-backend.php
@@ -20,6 +21,173 @@
 	const BASE_URL = 'https://api.openai.com/v1/chat/completions';
 
 	/**
+	 * OpenAI chat models shut down on 2026-10-23, mapped to the replacement
+	 * OpenAI recommends for each.
+	 *
+	 * Source: https://developers.openai.com/api/docs/deprecations (entry
+	 * announced 2026-04-22). Filter with `otter_ai_openai_model_replacements`.
+	 *
+	 * @var array<string, string>
+	 */
+	const RETIRING_MODEL_REPLACEMENTS = array(
+		'gpt-3.5-turbo'           => 'gpt-5.6-terra',
+		'gpt-3.5-turbo-0125'      => 'gpt-5.6-terra',
+		'o4-mini'                 => 'gpt-5.6-terra',
+		'o4-mini-2025-04-16'      => 'gpt-5.6-terra',
+		'gpt-4'                   => 'gpt-5.6-sol',
+		'gpt-4-0613'              => 'gpt-5.6-sol',
+		'gpt-4-turbo'             => 'gpt-5.6-sol',
+		'gpt-4-turbo-2024-04-09'  => 'gpt-5.6-sol',
+		'gpt-4-1106-preview'      => 'gpt-5.6-sol',
+		'gpt-4o-2024-05-13'       => 'gpt-5.6-sol',
+		'o1'                      => 'gpt-5.6-sol',
+		'o1-2024-12-17'           => 'gpt-5.6-sol',
+		'o3-mini'                 => 'gpt-5.6-sol',
+		'o3-mini-2025-01-31'      => 'gpt-5.6-sol',
+		'gpt-4.1-nano'            => 'gpt-5.6-luna',
+		'gpt-4.1-nano-2025-04-14' => 'gpt-5.6-luna',
+	);
+
+	/**
+	 * Reasoning effort sent after swapping a retiring NON-reasoning model
+	 * (gpt-3.5/gpt-4 family). GPT-5.6 models default to `medium`; `none` keeps
+	 * the latency and token profile closest to the model being replaced.
+	 *
+	 * @var string
+	 */
+	const SWAP_REASONING_EFFORT = 'none';
+
+	/**
+	 * Map a retiring model ID to its recommended replacement.
+	 *
+	 * @param string $model Model ID.
+	 * @return string The replacement, or the input unchanged when it is not retiring.
+	 */
+	public static function get_replacement_model( $model ) {
+		/**
+		 * Filters the retiring-model => replacement map.
+		 *
+		 * Return an empty array to disable the automatic swap.
+		 *
+		 * @param array<string, string> $replacements Retiring model ID => replacement model ID.
+		 */
+		$replacements = apply_filters( 'otter_ai_openai_model_replacements', self::RETIRING_MODEL_REPLACEMENTS );
+
+		if ( is_array( $replacements ) && isset( $replacements[ $model ] ) && is_string( $replacements[ $model ] ) && '' !== $replacements[ $model ] ) {
+			return $replacements[ $model ];
+		}
+
+		return $model;
+	}
+
+	/**
+	 * Model used for the one-off API key check in the Otter dashboard.
+	 *
+	 * @return string
+	 */
+	public static function get_key_validation_model() {
+		/**
+		 * Filters the model used to validate a newly saved OpenAI API key.
+		 *
+		 * @param string $model Model ID. Defaults to the gpt-3.5-turbo replacement.
+		 */
+		return (string) apply_filters( 'otter_ai_openai_key_validation_model', self::get_replacement_model( 'gpt-3.5-turbo' ) );
+	}
+
+	/**
+	 * Whether the model documents `reasoning_effort: none` (GPT-5.6 family).
+	 *
+	 * @param string $model Model ID.
+	 * @return bool
+	 */
+	public static function supports_reasoning_effort_none( $model ) {
+		return 1 === preg_match( '/^gpt-5\.6(-(sol|terra|luna))?$/', (string) $model );
+	}
+
+	/**
+	 * Adapt an OpenAI-shaped payload to the model it will be sent to.
+	 *
+	 * 1. Swaps retiring model IDs for their recommended replacement.
+	 * 2. Sets `reasoning_effort` after a swap from a non-reasoning model.
+	 * 3. Drops sampling parameters (`temperature`, `top_p`, logprobs) for
+	 *    reasoning-family models unless a site opts back in.
+	 * 4. Converts deprecated `functions`/`function_call` to `tools`/`tool_choice`.
+	 *
+	 * @param array<string, mixed> $payload The OpenAI-format payload.
+	 * @return array<string, mixed>
+	 */
+	public static function adapt_payload( array $payload ) {
+		$requested = isset( $payload['model'] ) && is_string( $payload['model'] ) ? $payload['model'] : '';
+		$model     = '' !== $requested ? self::get_replacement_model( $requested ) : '';
+
+		if ( '' !== $model && $model !== $requested ) {
+			$payload['model'] = $model;
+
+			if ( ! isset( $payload['reasoning_effort'] ) && 1 !== preg_match( '/^o[1-9]/', $requested ) && self::supports_reasoning_effort_none( $model ) ) {
+				/**
+				 * Filters the reasoning effort used after a retiring non-reasoning model is swapped.
+				 *
+				 * Return '' to omit `reasoning_effort` and use the model default.
+				 *
+				 * @param string               $effort    Reasoning effort.
+				 * @param string               $requested The retiring model ID that was requested.
+				 * @param string               $model     The replacement model ID.
+				 * @param array<string, mixed> $payload   The payload.
+				 */
+				$effort = (string) apply_filters( 'otter_ai_openai_swap_reasoning_effort', self::SWAP_REASONING_EFFORT, $requested, $model, $payload );
+
+				if ( '' !== $effort ) {
+					$payload['reasoning_effort'] = $effort;
+				}
+			}
+		}
+
+		if ( 1 === preg_match( '/^(gpt-5|o[1-9])/', $model ) ) {
+			/**
+			 * Filters whether sampling parameters are kept for reasoning-family models.
+			 *
+			 * @param bool                 $keep    Keep `temperature`, `top_p`, `logprobs`, `top_logprobs`. Default false.
+			 * @param string               $model   The model ID.
+			 * @param array<string, mixed> $payload The payload.
+			 */
+			if ( ! apply_filters( 'otter_ai_openai_keep_sampling_params', false, $model, $payload ) ) {
+				unset( $payload['temperature'], $payload['top_p'], $payload['logprobs'], $payload['top_logprobs'] );
+			}
+		}
+
+		if ( isset( $payload['functions'] ) && is_array( $payload['functions'] ) && ! isset( $payload['tools'] ) ) {
+			$tools = array();
+
+			foreach ( $payload['functions'] as $function ) {
+				if ( is_array( $function ) && ! empty( $function['name'] ) ) {
+					$tools[] = array(
+						'type'     => 'function',
+						'function' => $function,
+					);
+				}
+			}
+
+			if ( ! empty( $tools ) ) {
+				$function_call = isset( $payload['function_call'] ) ? $payload['function_call'] : null;
+
+				if ( is_array( $function_call ) && ! empty( $function_call['name'] ) ) {
+					$payload['tool_choice'] = array(
+						'type'     => 'function',
+						'function' => array( 'name' => (string) $function_call['name'] ),
+					);
+				} elseif ( 'none' === $function_call || 'auto' === $function_call ) {
+					$payload['tool_choice'] = $function_call;
+				}
+
+				$payload['tools'] = $tools;
+				unset( $payload['functions'], $payload['function_call'] );
+			}
+		}
+
+		return $payload;
+	}
+
+	/**
 	 * Whether an Otter OpenAI API key is configured.
 	 *
 	 * @return bool
```

**Hunk 2: one call site.** `adapt_payload()` runs after all existing filters (`otter_ai_otter_openai_payload`, `otter_ai_otter_openai_model`, `otter_ai_block_generation_model`) and before the existing `max_tokens` rename. A template, or a site filter, that still names a retiring model is therefore always remapped.

```diff
@@ -75,6 +243,10 @@
 			$payload['model'] = $model;
 		}
 
+		// Prompt templates are fetched remotely and cached for a week, so they
+		// can still pin a model OpenAI has shut down. Adapt after all filters ran.
+		$payload = self::adapt_payload( $payload );
+
 		// GPT-5/o-series models reject `max_tokens`; `max_completion_tokens` is
 		// accepted by all current chat-completions models.
 		if ( isset( $payload['max_tokens'] ) ) {
```

**Hunk 3: response parsing.** Reads `tool_calls[0].function.arguments` first, then the legacy `function_call`, then `content`, so both old and new response shapes work. An empty reply that carries `message.refusal` now returns HTTP 422 `model_refusal` with the model's text. Before, it was a generic 502 "empty response", which the editor auto-retries twice.

```diff
@@ -179,13 +351,22 @@
 		$content = '';
 		$format  = 'text';
 
-		if ( isset( $message['function_call'] ) && is_array( $message['function_call'] ) && isset( $message['function_call']['arguments'] ) ) {
+		if ( isset( $message['tool_calls'][0]['function']['arguments'] ) && is_string( $message['tool_calls'][0]['function']['arguments'] ) ) {
+			// `tools`/`tool_choice` response shape (see adapt_payload()).
+			$content = $message['tool_calls'][0]['function']['arguments'];
+			$format  = 'json';
+		} elseif ( isset( $message['function_call'] ) && is_array( $message['function_call'] ) && isset( $message['function_call']['arguments'] ) ) {
 			$content = (string) $message['function_call']['arguments'];
 			$format  = 'json';
 		} elseif ( isset( $message['content'] ) ) {
 			$content = (string) $message['content'];
 		}
 
+		if ( '' === $content && isset( $message['refusal'] ) && is_string( $message['refusal'] ) && '' !== $message['refusal'] ) {
+			// Surface the model's refusal instead of a generic, auto-retried 502.
+			return $this->error_response( 'model_refusal', $message['refusal'], 422 );
+		}
+
 		if ( '' === $content ) {
 			return $this->error_response( 'empty_response', __( 'OpenAI returned an empty response. Please try again.', 'otter-blocks' ), 502 );
 		}
```

**Hunks 4-5, `class-prompt-server.php`: the line-144 key check.** Builds the same "Hello!" request with `get_key_validation_model()`, adding `reasoning_effort: none` when the model supports it. It is still a real chat completion, as before, so restricted project keys that can call models but cannot list them keep validating.

```diff
--- a/inc/server/class-prompt-server.php
+++ b/inc/server/class-prompt-server.php
@@ -131,6 +132,27 @@
 			return new \WP_REST_Response( array( 'message' => __( 'API key saved.', 'otter-blocks' ) ), 200 );
 		}
 
+		// gpt-3.5-turbo shuts down on 2026-10-23; validate with its replacement.
+		$validation_model = Otter_OpenAI_Backend::get_key_validation_model();
+		$validation_body  = array(
+			'model'    => $validation_model,
+			'messages' => array(
+				array(
+					'role'    => 'system',
+					'content' => 'You are a helpful assistant.',
+				),
+				array(
+					'role'    => 'user',
+					'content' => 'Hello!',
+				),
+			),
+		);
+
+		// GPT-5.6 models reason by default (`medium`); a key check needs none.
+		if ( Otter_OpenAI_Backend::supports_reasoning_effort_none( $validation_model ) ) {
+			$validation_body['reasoning_effort'] = 'none';
+		}
+
 		$response = wp_remote_post(
 			self::BASE_URL,
 			array(
@@ -139,21 +161,7 @@
 					'Authorization' => 'Bearer ' . $api_key,
 					'Content-Type'  => 'application/json',
 				),
-				'body'    => wp_json_encode(
-					array(
-						'model'    => 'gpt-3.5-turbo',
-						'messages' => array(
-							array(
-								'role'    => 'system',
-								'content' => 'You are a helpful assistant.',
-							),
-							array(
-								'role'    => 'user',
-								'content' => 'Hello!',
-							),
-						),
-					)
-				),
+				'body'    => wp_json_encode( $validation_body ),
 				'timeout' => 2 * MINUTE_IN_SECONDS,
 			)
 		);
```

**Modification notices (GPL-2.0 section 2(a)).** Each changed file also gets one dated comment line in its header docblock that says what changed and that the original is (c) Themeisle under GPL-2.0-or-later. These two comment-only hunks change no behaviour, and the hunk numbers above count code hunks only. Licence text: `LICENSE-GPL-2.0.txt`; notice: `patch-work/NOTICE.md`.

```diff
--- a/inc/server/class-otter-openai-backend.php
+++ b/inc/server/class-otter-openai-backend.php
@@ -1,6 +1,7 @@
 <?php
 /**
  * Otter OpenAI backend strategy.
+ * Modified 2026-10-09 by Model Sunset Desk: swaps OpenAI models retiring 2026-10-23 for the recommended replacements (adapt_payload) and parses tool_calls and refusals; original © Themeisle, GPL-2.0-or-later
  *
  * @package ThemeIsle\GutenbergBlocks\Server
  */
--- a/inc/server/class-prompt-server.php
+++ b/inc/server/class-prompt-server.php
@@ -1,6 +1,7 @@
 <?php
 /**
  * Prompt server logic.
+ * Modified 2026-10-09 by Model Sunset Desk: the API-key check no longer hard-codes gpt-3.5-turbo (uses its replacement with reasoning_effort none); original © Themeisle, GPL-2.0-or-later
  *
  * @package ThemeIsle\GutenbergBlocks\Server
  */
```

**Backward compatibility.**
- The WordPress AI Client path is untouched.
- Requests with no retiring model keep their model.
- The page/section pipeline (`gpt-5-mini`, no `temperature`) is unchanged apart from the existing `max_tokens` rename.
- All existing Otter filters still run.
- Nothing is stored in the database, and no option, table or REST route changes.
- The code avoids syntax newer than PHP 5.6. `php -l` passes on 5.6.40 and 8.3.35.
- One behavioural change applies to any model: `functions` are sent as `tools`. If a site disables the swap and stays on `gpt-3.5-turbo` until 23 Oct, that relies on `gpt-3.5-turbo-0125` supporting `tools`. That is our prior knowledge and was not re-verified on 2026-10-09; `--candidate gpt-3.5-turbo` in the harness would show it.

**No-core-edit alternative for site owners** (`mu-plugin/otter-model-sunset.php`). Editing plugin files is undone by the next plugin update. The mu-plugin applies the same transform through Otter's existing hooks:
- `otter_ai_otter_openai_payload` adapts the request;
- `otter_ai_otter_openai_response` maps `tool_calls` back to the `function_call` shape the 3.2.7 parser reads, and turns an empty reply with `refusal` into an error that shows the refusal text (Otter reports it as a 502, so the editor may retry);
- an `http_request_args` hook, scoped to Otter's `/otter/v1/openai/key` REST request only, fixes the key check.

To install, copy it to `wp-content/mu-plugins/`. To remove, delete the file.

## 6. Test plan and dry-run demo

**Done for this sample (no API spend):**

| Check | Result |
|---|---|
| `patch -p1 --dry-run` on a fresh copy of the 3.2.7 source | Applies cleanly (5 code hunks plus 2 comment-only notice hunks; re-checked 2026-10-09 after the notices were added); the result is byte-identical to `patch-work/b/` |
| `php -l` on patched files and the mu-plugin (official `php:5.6-cli` and `php:8.3-cli` images, no network) | No syntax errors |
| `tests/test_adapt_payload.php`: 24 checks on the code hunk 1 adds, extracted from `patch.diff` (no Otter code executed) | 24/24 passed on PHP 5.6.40; 24/24 passed on PHP 8.3.35 |
| `tests/test_mu_plugin.php`: 8 checks | 8/8 passed on PHP 5.6.40; 8/8 passed on PHP 8.3.35 |
| `tests/test_transform_mirror.py`: harness mirror matches patch behaviour | 10/10 passed (Python 3.14) |
| Harness live-mode guards: missing key; pre-flight cost cap | Both abort before any request (`harness/out/live-guards.console.txt`) |

**Not done here:**
- running the patched plugin inside WordPress (we do not execute downloaded third-party code);
- any live model call.

Both are part of client acceptance:
1. Install on staging and save the key; expect "API key saved."
2. Generate one AI Block, one AI form and one Regenerate.
3. Confirm "Token used" appears and nothing returns HTTP 400.
4. Run the harness live.

**Regression harness (`harness/`).**
- 30 cases matching the exposed features: 16 AI Block (including HTML-preservation, language and length cases), 10 AI Form (including file uploads, French and Spanish), and 4 Patterns picker (one with the Pro add-on).
- Four cases are Regenerate requests and two are policy-edge cases.
- Each case runs on the old request (`gpt-3.5-turbo`, while it exists) and on the patched request (`gpt-5.6-terra`, plus any `--candidate`).
- Recorded per request: format validity as the editor sees it, per-case expectations, refusals, output length, latency, token usage (including reasoning and cache tokens), a cost estimate from `pricing.json` (OpenAI list prices read 2026-10-09; editable), and the model name the API reported.
- Live mode uses only the client's `OPENAI_API_KEY`, refuses to start above `--max-cost-usd`, and asks for confirmation.
- A full live run of 60 requests has a rough pre-flight estimate of about **$0.31** at list prices, assuming 700 output tokens per request. That is an estimate, not a measurement.

**Dry-run demo output (synthetic).** Command: `python3 -I harness/run_harness.py --dry-run --out harness/out/dry-run`. Full output: `harness/out/dry-run/comparison.md`.

> **SYNTHETIC MOCK DATA, NOT MEASUREMENTS.** The mock outputs were written by hand and are identical across arms, except for seven labelled variations (old arm 3, new arm 4) injected to show that the detectors fire. Both arms get the same latency noise and token counts. The cost row is therefore list-price arithmetic only.

| Metric | old | new:gpt-5.6-terra |
|---|---|---|
| Requests | 30 | 30 |
| HTTP 200 | 30/30 (100%) | 30/30 (100%) |
| Format valid | 29/30 (97%) | 28/30 (93%) |
| Expectations met (excl. policy-edge) | 25/28 (89%) | 26/28 (93%) |
| Refusals | 0 | 1 |
| Errors | 0 | 0 |
| Latency median (ms) | 1279 | 1167 |
| Latency p90 (ms) | 1918 | 1918 |
| Mean words, AI Block outputs | 51.9 | 46.4 |
| Mean output chars, all | 341.4 | 327.8 |
| Prompt tokens | 10135 | 10135 |
| Completion tokens (incl. reasoning) | 2548 | 2494 |
| Reasoning tokens | 0 | 0 |
| Est. cost, this run (USD) | 0.008889 | 0.050198 |
| Est. cost per 1,000 requests (USD) | 0.2963 | 1.6733 |
| Model reported by API | gpt-3.5-turbo-0125 | gpt-5.6-terra |

Flagged cases from the same dry run. Each flag corresponds to an injected variation, and every one was detected:

| Case | Feature | Regen | Old: valid / words / ms | new:gpt-5.6-terra: valid / words / ms | Flags |
|---|---|---|---|---|---|
| B05 | textTransformation |  | yes / 50 / 1482 | NO / 51 / 1521 | FORMAT-REGRESSION, EXPECTATION-REGRESSION |
| B09 | textTransformation |  | yes / 65 / 1692 | yes / 17 / 763 | EXPECTATION-REGRESSION, LENGTH-SHIFT -74% |
| B16 | textTransformation |  | yes / 42 / 689 | NO / 0 / 605 | FORMAT-REGRESSION, REFUSAL-CHANGE, LENGTH-SHIFT -100%, POLICY-EDGE |
| F05 | form |  | yes / 4 / 2248 | yes / 5 / 2248 | EXPECTATION-FIXED |
| F09 | form |  | NO / 0 / 1270 | yes / 6 / 1890 | FORMAT-FIXED, EXPECTATION-FIXED, COUNT-SHIFT 0->6 |
| F10 | form |  | yes / 6 / 1404 | yes / 4 / 1110 | COUNT-SHIFT 6->4, POLICY-EDGE |
| P02 | patternsPicker |  | yes / 4 / 526 | yes / 5 / 535 | EXPECTATION-FIXED |

What the patch changes on the wire, from `requests.jsonl` of the same run:

**B01 (textTransformation)**

| Key | Old request | New request |
|---|---|---|
| `model` | `"gpt-3.5-turbo"` | `"gpt-5.6-terra"` |
| `reasoning_effort` | `(absent)` | `"none"` |

**F01 (form)**

| Key | Old request | New request |
|---|---|---|
| `function_call` | `{"name": "generateForm"}` | `(absent)` |
| `functions` | `[{"name": "generateForm", "description": "Generate form fields for the task.", "parameters...` | `(absent)` |
| `model` | `"gpt-3.5-turbo"` | `"gpt-5.6-terra"` |
| `reasoning_effort` | `(absent)` | `"none"` |
| `tool_choice` | `(absent)` | `{"type": "function", "function": {"name": "generateForm"}}` |
| `tools` | `(absent)` | `[{"type": "function", "function": {"name": "generateForm", "description": "Generate form f...` |

**P01 (patternsPicker)**

| Key | Old request | New request |
|---|---|---|
| `function_call` | `{"name": "pickPatterns"}` | `(absent)` |
| `functions` | `[{"name": "pickPatterns", "description": "Pick the patterns relevant for the page.", "para...` | `(absent)` |
| `model` | `"gpt-3.5-turbo"` | `"gpt-5.6-terra"` |
| `reasoning_effort` | `(absent)` | `"none"` |
| `tool_choice` | `(absent)` | `{"type": "function", "function": {"name": "pickPatterns"}}` |
| `tools` | `(absent)` | `[{"type": "function", "function": {"name": "pickPatterns", "description": "Pick the patter...` |

**B04 (textTransformation, regenerate)**

| Key | Old request | New request |
|---|---|---|
| `model` | `"gpt-3.5-turbo"` | `"gpt-5.6-terra"` |
| `reasoning_effort` | `(absent)` | `"none"` |
| `temperature` | `1.3` | `(absent)` |

A second dry run (`harness/out/dry-run-post-shutdown/`) replays a **synthetic** post-shutdown `model_not_found` for the old model. The harness marks the old arm unavailable after the first failure, skips the remaining old calls, and points to `--baseline` for comparison against a pre-shutdown run.

**Suggested acceptance criteria for a client run:**
- zero `NEW-ERROR` flags;
- new-arm format validity no lower than old-arm;
- every flagged case reviewed and accepted by a human;
- cost per 1,000 requests reported and accepted by the client.

## 7. Risks and rollback

| Risk | Likelihood / evidence | Mitigation |
|---|---|---|
| Higher API cost per request | Certain per token: 4x input, 8x output at list price (verified prices) | Measure with the harness. `--candidate gpt-5.6-luna` tests a cheaper model ($0.20 / $1.20), but OpenAI recommends terra for gpt-3.5-turbo. |
| Output drift (length, tone, HTML habits such as code fences) | Unknown until measured | Run the harness on the client's inputs; consider `verbosity` or a prompt tweak |
| `temperature` rejected by terra | Undocumented | Dropped by default; `--keep-sampling` measures whether it is accepted |
| `reasoning_effort: none` lowers quality on harder prompts | Unknown | `--swap-effort low` comparison; filter `otter_ai_openai_swap_reasoning_effort` |
| More refusals or safeguard pauses | GPT-5.6 guide documents safeguards that can refuse or pause | Refusal text is now surfaced; policy-edge cases are in the harness |
| Key's project has no access to gpt-5.6-terra | Possible on restricted projects | The error names the model; filter `otter_ai_openai_key_validation_model` |
| A plugin update overwrites a direct patch | Certain for in-place edits | Use the mu-plugin, or upstream the patch |
| Vendor ships its own fix | Likely at some point | Both are idempotent: an already-swapped model is left alone; delete the mu-plugin afterwards |
| Not changed by this patch: the page pipeline caps output at 8192 completion tokens on `gpt-5-mini` at its default effort; OpenAI's reasoning guide recommends "reserving at least 25,000 tokens" when experimenting | Observed in code, not measured | Out of scope; noted for the 11 Dec follow-up |

**Rollback.** Run `patch -R -p1 < patch.diff`, or reinstall Otter 3.2.7 from WordPress.org. For the mu-plugin, delete the file. To disable only the swap: `add_filter( 'otter_ai_openai_model_replacements', '__return_empty_array' );`. No data migration is involved. After 23 Oct, a rollback brings back the broken state.

## 8. What a client would receive

This sample corresponds to **Swap & Verify** ($290 per repo, or per bundle of up to 3 n8n/Make/Zapier workflows). The client pays on delivery through a Payment Link sent with the PR and report, and does not pay if the delivery does not pass their review. Delivery is within 48 hours of receiving access and a staging key, weekends included.

1. A pull request into the client's repository (or a fixed workflow export) that replaces retiring model IDs with OpenAI's recommended replacement and fixes parameter and response-shape differences, as in section 5.
2. A 30-case before/after regression on the client's own inputs, run with the client's staging API key, which the client revokes afterwards. It covers format validity, refusals, length, latency, tokens and estimated cost, as in section 6.
3. A one-page quality and cost report, with flagged cases shown side by side for the client's decision.
4. Rollback instructions.

Not included:
- any guarantee of output parity, quality, uptime or compliance (we promise a measured comparison and a PR);
- production access or passwords (delivery is PR-only).

Client data is used only for the engagement and deleted within 7 days of delivery. Liability is capped at the fee paid. Scope is written per engagement in one paragraph, with an acceptance test, before work starts.

Contact: Orkhan Karimov, Model Sunset Desk, hello@modelsunsetdesk.com, https://orkhan103.github.io/model-sunset-desk.

## 9. Verification log

**Verified live on 2026-10-09** (page copies saved under `launch/_untrusted/openai-docs-otter/`; the Otter zip and served templates under `launch/_untrusted/otter-blocks/`):

1. [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations):
   - `gpt-3.5-turbo-0125`, `gpt-3.5-turbo` and `gpt-3.5-turbo-completions` shut down 2026-10-23, replacement `gpt-5.6-terra`, entry announced 2026-04-22;
   - `gpt-5-mini-2025-08-07` shuts down 2026-12-11 (replacement `gpt-5.6-terra`); plain `gpt-5-mini` is not listed;
   - nothing about `functions`/`function_call`.
2. [gpt-5.6-terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra): effort values and default, endpoints, features, limits, prices, cache-write rule, single snapshot. The [sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) and [luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) pages list the same effort values.
3. [gpt-3.5-turbo](https://developers.openai.com/api/docs/models/gpt-3.5-turbo) and [gpt-5-mini](https://developers.openai.com/api/docs/models/gpt-5-mini): prices, limits, snapshots (marked Deprecated).
4. [Chat Completions create reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create): `max_tokens`, `max_completion_tokens`, `functions`, `function_call`, `tools`, `tool_choice`, `reasoning_effort`, `temperature`, `response_format`, `verbosity`, `refusal`, `finish_reason` and usage fields, quoted in section 4.
5. [Latest-model guide](https://developers.openai.com/api/docs/guides/latest-model) (GPT-6 and GPT-5.6 sections) and the [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning): quoted in sections 4 and 7.
6. Otter 3.2.7 source (zip sha256 `c59d54bdaab37d5e4c441b83472daed2f4335600cba5db0142d4cd8c71edadc0`), read in full for the AI path. Served templates: one read-only GET of the endpoint the plugin itself calls, using the placeholder `site_url=https://example.com` (sha256 `01e20afab2e124737f631d9d48e24753b50a8acf5a87e08f7d9ca8cfda114db3`).

**Not verified (stated as such wherever used):**
- `temperature`/`top_p` support on gpt-5.6-terra;
- acceptance of legacy `functions` by gpt-5.6-terra;
- the exact post-shutdown error;
- whether or when Themeisle updates the served templates;
- whether the `gpt-5-mini` alias is re-pointed before 11 Dec;
- `tools` support on `gpt-3.5-turbo-0125` (prior knowledge);
- the share of Otter sites on the OpenAI-key path;
- behaviour inside a running WordPress;
- any live model quality, latency or cost on these prompts.

Files in this sample: `README.md` (index), `report.md`/`report.html` (this report), `patch.diff`, `LICENSE-GPL-2.0.txt`, `patch-work/` (with `NOTICE.md`), `mu-plugin/`, `tests/`, `harness/`, `tools/`.
