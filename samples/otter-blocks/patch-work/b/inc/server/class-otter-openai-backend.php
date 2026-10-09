<?php
/**
 * Otter OpenAI backend strategy.
 * Modified 2026-10-09 by Model Sunset Desk: swaps OpenAI models retiring 2026-10-23 for the recommended replacements (adapt_payload) and parses tool_calls and refusals; original © Themeisle, GPL-2.0-or-later
 *
 * @package ThemeIsle\GutenbergBlocks\Server
 */

namespace ThemeIsle\GutenbergBlocks\Server;

/**
 * Class Otter_OpenAI_Backend
 */
class Otter_OpenAI_Backend implements AI_Backend {

	/**
	 * OpenAI chat-completions endpoint.
	 *
	 * @var string
	 */
	const BASE_URL = 'https://api.openai.com/v1/chat/completions';

	/**
	 * OpenAI chat models shut down on 2026-10-23, mapped to the replacement
	 * OpenAI recommends for each.
	 *
	 * Source: https://developers.openai.com/api/docs/deprecations (entry
	 * announced 2026-04-22). Filter with `otter_ai_openai_model_replacements`.
	 *
	 * @var array<string, string>
	 */
	const RETIRING_MODEL_REPLACEMENTS = array(
		'gpt-3.5-turbo'           => 'gpt-5.6-terra',
		'gpt-3.5-turbo-0125'      => 'gpt-5.6-terra',
		'o4-mini'                 => 'gpt-5.6-terra',
		'o4-mini-2025-04-16'      => 'gpt-5.6-terra',
		'gpt-4'                   => 'gpt-5.6-sol',
		'gpt-4-0613'              => 'gpt-5.6-sol',
		'gpt-4-turbo'             => 'gpt-5.6-sol',
		'gpt-4-turbo-2024-04-09'  => 'gpt-5.6-sol',
		'gpt-4-1106-preview'      => 'gpt-5.6-sol',
		'gpt-4o-2024-05-13'       => 'gpt-5.6-sol',
		'o1'                      => 'gpt-5.6-sol',
		'o1-2024-12-17'           => 'gpt-5.6-sol',
		'o3-mini'                 => 'gpt-5.6-sol',
		'o3-mini-2025-01-31'      => 'gpt-5.6-sol',
		'gpt-4.1-nano'            => 'gpt-5.6-luna',
		'gpt-4.1-nano-2025-04-14' => 'gpt-5.6-luna',
	);

	/**
	 * Reasoning effort sent after swapping a retiring NON-reasoning model
	 * (gpt-3.5/gpt-4 family). GPT-5.6 models default to `medium`; `none` keeps
	 * the latency and token profile closest to the model being replaced.
	 *
	 * @var string
	 */
	const SWAP_REASONING_EFFORT = 'none';

	/**
	 * Map a retiring model ID to its recommended replacement.
	 *
	 * @param string $model Model ID.
	 * @return string The replacement, or the input unchanged when it is not retiring.
	 */
	public static function get_replacement_model( $model ) {
		/**
		 * Filters the retiring-model => replacement map.
		 *
		 * Return an empty array to disable the automatic swap.
		 *
		 * @param array<string, string> $replacements Retiring model ID => replacement model ID.
		 */
		$replacements = apply_filters( 'otter_ai_openai_model_replacements', self::RETIRING_MODEL_REPLACEMENTS );

		if ( is_array( $replacements ) && isset( $replacements[ $model ] ) && is_string( $replacements[ $model ] ) && '' !== $replacements[ $model ] ) {
			return $replacements[ $model ];
		}

		return $model;
	}

	/**
	 * Model used for the one-off API key check in the Otter dashboard.
	 *
	 * @return string
	 */
	public static function get_key_validation_model() {
		/**
		 * Filters the model used to validate a newly saved OpenAI API key.
		 *
		 * @param string $model Model ID. Defaults to the gpt-3.5-turbo replacement.
		 */
		return (string) apply_filters( 'otter_ai_openai_key_validation_model', self::get_replacement_model( 'gpt-3.5-turbo' ) );
	}

	/**
	 * Whether the model documents `reasoning_effort: none` (GPT-5.6 family).
	 *
	 * @param string $model Model ID.
	 * @return bool
	 */
	public static function supports_reasoning_effort_none( $model ) {
		return 1 === preg_match( '/^gpt-5\.6(-(sol|terra|luna))?$/', (string) $model );
	}

	/**
	 * Adapt an OpenAI-shaped payload to the model it will be sent to.
	 *
	 * 1. Swaps retiring model IDs for their recommended replacement.
	 * 2. Sets `reasoning_effort` after a swap from a non-reasoning model.
	 * 3. Drops sampling parameters (`temperature`, `top_p`, logprobs) for
	 *    reasoning-family models unless a site opts back in.
	 * 4. Converts deprecated `functions`/`function_call` to `tools`/`tool_choice`.
	 *
	 * @param array<string, mixed> $payload The OpenAI-format payload.
	 * @return array<string, mixed>
	 */
	public static function adapt_payload( array $payload ) {
		$requested = isset( $payload['model'] ) && is_string( $payload['model'] ) ? $payload['model'] : '';
		$model     = '' !== $requested ? self::get_replacement_model( $requested ) : '';

		if ( '' !== $model && $model !== $requested ) {
			$payload['model'] = $model;

			if ( ! isset( $payload['reasoning_effort'] ) && 1 !== preg_match( '/^o[1-9]/', $requested ) && self::supports_reasoning_effort_none( $model ) ) {
				/**
				 * Filters the reasoning effort used after a retiring non-reasoning model is swapped.
				 *
				 * Return '' to omit `reasoning_effort` and use the model default.
				 *
				 * @param string               $effort    Reasoning effort.
				 * @param string               $requested The retiring model ID that was requested.
				 * @param string               $model     The replacement model ID.
				 * @param array<string, mixed> $payload   The payload.
				 */
				$effort = (string) apply_filters( 'otter_ai_openai_swap_reasoning_effort', self::SWAP_REASONING_EFFORT, $requested, $model, $payload );

				if ( '' !== $effort ) {
					$payload['reasoning_effort'] = $effort;
				}
			}
		}

		if ( 1 === preg_match( '/^(gpt-5|o[1-9])/', $model ) ) {
			/**
			 * Filters whether sampling parameters are kept for reasoning-family models.
			 *
			 * @param bool                 $keep    Keep `temperature`, `top_p`, `logprobs`, `top_logprobs`. Default false.
			 * @param string               $model   The model ID.
			 * @param array<string, mixed> $payload The payload.
			 */
			if ( ! apply_filters( 'otter_ai_openai_keep_sampling_params', false, $model, $payload ) ) {
				unset( $payload['temperature'], $payload['top_p'], $payload['logprobs'], $payload['top_logprobs'] );
			}
		}

		if ( isset( $payload['functions'] ) && is_array( $payload['functions'] ) && ! isset( $payload['tools'] ) ) {
			$tools = array();

			foreach ( $payload['functions'] as $function ) {
				if ( is_array( $function ) && ! empty( $function['name'] ) ) {
					$tools[] = array(
						'type'     => 'function',
						'function' => $function,
					);
				}
			}

			if ( ! empty( $tools ) ) {
				$function_call = isset( $payload['function_call'] ) ? $payload['function_call'] : null;

				if ( is_array( $function_call ) && ! empty( $function_call['name'] ) ) {
					$payload['tool_choice'] = array(
						'type'     => 'function',
						'function' => array( 'name' => (string) $function_call['name'] ),
					);
				} elseif ( 'none' === $function_call || 'auto' === $function_call ) {
					$payload['tool_choice'] = $function_call;
				}

				$payload['tools'] = $tools;
				unset( $payload['functions'], $payload['function_call'] );
			}
		}

		return $payload;
	}

	/**
	 * Whether an Otter OpenAI API key is configured.
	 *
	 * @return bool
	 */
	public function is_available() {
		return ! empty( get_option( 'themeisle_open_ai_api_key' ) );
	}

	/**
	 * Forward the prompt to OpenAI API.
	 *
	 * @param array<string, mixed> $payload The OpenAI-format payload.
	 * @return array<string, mixed>|\WP_Error
	 */
	public function generate( array $payload ) {
		if ( ! $this->is_available() ) {
			return $this->error_response( 'no_api_key', __( 'No OpenAI API key is configured. Add your API key in the Otter dashboard under Integrations.', 'otter-blocks' ), 400 );
		}

		/**
		 * Filters the OpenAI-shaped payload before Otter sends it to OpenAI.
		 *
		 * @param array<string, mixed> $payload The OpenAI-format payload.
		 */
		$payload = apply_filters( 'otter_ai_otter_openai_payload', $payload );

		if ( ! is_array( $payload ) ) {
			return $this->error_response( 'invalid_payload', __( 'The OpenAI request payload is invalid.', 'otter-blocks' ), 400 );
		}

		/**
		 * Filters the OpenAI model used for Otter's OpenAI requests.
		 *
		 * The model normally comes from the fetched prompt templates; return a
		 * different model ID to override it.
		 *
		 * @param string               $model   The model ID from the prompt template.
		 * @param array<string, mixed> $payload The filtered OpenAI-format payload.
		 */
		$model = apply_filters( 'otter_ai_otter_openai_model', isset( $payload['model'] ) ? (string) $payload['model'] : '', $payload );

		if ( '' === $model && empty( $payload['model'] ) ) {
			/**
			 * Filters the legacy OpenAI model used when the client did not pin one.
			 *
			 * @param string               $model   Default model ID.
			 * @param array<string, mixed> $payload The filtered OpenAI-format payload.
			 */
			$model = (string) apply_filters( 'otter_ai_block_generation_model', 'gpt-5-mini', $payload );
		}

		if ( is_string( $model ) && '' !== $model ) {
			$payload['model'] = $model;
		}

		// Prompt templates are fetched remotely and cached for a week, so they
		// can still pin a model OpenAI has shut down. Adapt after all filters ran.
		$payload = self::adapt_payload( $payload );

		// GPT-5/o-series models reject `max_tokens`; `max_completion_tokens` is
		// accepted by all current chat-completions models.
		if ( isset( $payload['max_tokens'] ) ) {
			$payload['max_completion_tokens'] = $payload['max_tokens'];
			unset( $payload['max_tokens'] );
		}

		$request_args = array(
			'method'  => 'POST',
			'headers' => array(
				'Authorization' => 'Bearer ' . get_option( 'themeisle_open_ai_api_key' ),
				'Content-Type'  => 'application/json',
			),
			'body'    => wp_json_encode( $payload ),
			'timeout' => AI_Client_Adaptor::get_request_timeout_seconds(),
		);

		/**
		 * Filters the HTTP arguments used for Otter's OpenAI request.
		 *
		 * @param array<string, mixed> $request_args The wp_remote_post() arguments.
		 * @param array<string, mixed> $payload      The filtered OpenAI-format payload.
		 */
		$request_args = apply_filters( 'otter_ai_otter_openai_request_args', $request_args, $payload );

		if ( ! is_array( $request_args ) ) {
			return $this->error_response( 'invalid_request_args', __( 'The OpenAI request arguments are invalid.', 'otter-blocks' ), 400 );
		}

		// Re-establish the required keys without discarding any other
		// wp_remote_post() argument the filter may have set (sslverify,
		// redirection, httpversion, ...).
		if ( ! isset( $request_args['method'] ) || ! is_string( $request_args['method'] ) ) {
			$request_args['method'] = 'POST';
		}

		if ( ! isset( $request_args['body'] ) || ! is_string( $request_args['body'] ) ) {
			$request_args['body'] = wp_json_encode( $payload );
		}

		if ( ! isset( $request_args['timeout'] ) || ! is_numeric( $request_args['timeout'] ) ) {
			$request_args['timeout'] = AI_Client_Adaptor::get_request_timeout_seconds();
		}

		$headers = array();
		if ( ! isset( $request_args['headers'] ) || ! is_array( $request_args['headers'] ) ) {
			$request_args['headers'] = array();
		}

		foreach ( $request_args['headers'] as $name => $value ) {
			if ( is_scalar( $value ) ) {
				$headers[ (string) $name ] = (string) $value;
			}
		}

		$request_args['headers'] = $headers;

		$response = wp_remote_post(
			self::BASE_URL,
			// The stubs seal the args shape, but wp_remote_post() accepts any
			// WP_Http::request() argument, including filter-supplied extras.
			// phpcs:ignore Squiz.PHP.CommentedOutCode.Found
			// @phpstan-ignore argument.type (sealed array shape in stubs)
			$request_args
		);

		if ( is_wp_error( $response ) ) {
			return $this->error_response( (string) $response->get_error_code(), $response->get_error_message(), 502 );
		}

		$body = wp_remote_retrieve_body( $response );
		$body = json_decode( $body, true );

		if ( json_last_error() !== JSON_ERROR_NONE ) {
			return $this->error_response( 'rest_invalid_json', __( 'Could not parse the response from OpenAI. Try again.', 'otter-blocks' ), 502 );
		}

		$body = is_array( $body ) ? $body : array();

		/**
		 * Filters the decoded OpenAI response before returning it to Otter callers.
		 *
		 * @param array<string, mixed> $body    The decoded OpenAI response body.
		 * @param array<string, mixed> $payload The filtered OpenAI-format payload.
		 */
		$body = apply_filters( 'otter_ai_otter_openai_response', $body, $payload );

		if ( ! is_array( $body ) ) {
			return $this->error_response( 'invalid_response', __( 'The OpenAI response body is invalid.', 'otter-blocks' ), 502 );
		}

		if ( isset( $body['error'] ) && is_array( $body['error'] ) ) {
			$code    = isset( $body['error']['code'] ) ? (string) $body['error']['code'] : 'openai_error';
			$message = isset( $body['error']['message'] ) ? (string) $body['error']['message'] : __( 'An error occurred while processing the request.', 'otter-blocks' );
			$status  = wp_remote_retrieve_response_code( $response );
			$status  = 400 <= $status ? $status : 502;

			return $this->error_response( $code, $message, $status );
		}

		$message = isset( $body['choices'][0]['message'] ) && is_array( $body['choices'][0]['message'] ) ? $body['choices'][0]['message'] : array();
		$content = '';
		$format  = 'text';

		if ( isset( $message['tool_calls'][0]['function']['arguments'] ) && is_string( $message['tool_calls'][0]['function']['arguments'] ) ) {
			// `tools`/`tool_choice` response shape (see adapt_payload()).
			$content = $message['tool_calls'][0]['function']['arguments'];
			$format  = 'json';
		} elseif ( isset( $message['function_call'] ) && is_array( $message['function_call'] ) && isset( $message['function_call']['arguments'] ) ) {
			$content = (string) $message['function_call']['arguments'];
			$format  = 'json';
		} elseif ( isset( $message['content'] ) ) {
			$content = (string) $message['content'];
		}

		if ( '' === $content && isset( $message['refusal'] ) && is_string( $message['refusal'] ) && '' !== $message['refusal'] ) {
			// Surface the model's refusal instead of a generic, auto-retried 502.
			return $this->error_response( 'model_refusal', $message['refusal'], 422 );
		}

		if ( '' === $content ) {
			return $this->error_response( 'empty_response', __( 'OpenAI returned an empty response. Please try again.', 'otter-blocks' ), 502 );
		}

		$used_tokens = isset( $body['usage']['total_tokens'] ) && is_numeric( $body['usage']['total_tokens'] ) ? (int) $body['usage']['total_tokens'] : 0;

		return AI_Response::success( $content, $used_tokens, $format );
	}

	/**
	 * Create an AI generation error response.
	 *
	 * @param string $code    The error code.
	 * @param string $message The error message.
	 * @param int    $status  The HTTP status code.
	 * @return \WP_Error
	 */
	private function error_response( $code, $message, $status = 502 ) {
		return AI_Response::error( $code, $message, 'openai', $status );
	}
}
