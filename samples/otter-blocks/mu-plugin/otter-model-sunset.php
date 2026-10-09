<?php
/**
 * Plugin Name: Otter Blocks model sunset shim (gpt-3.5-turbo -> gpt-5.6-terra)
 * Description: Keeps Otter Blocks' OpenAI-key AI features working after OpenAI shuts down gpt-3.5-turbo on 2026-10-23, without editing Otter's files. Delete this file once Otter ships its own fix.
 * Version: 0.1.0
 * Requires PHP: 5.6
 * License: GPL-2.0-or-later
 *
 * Produced 2026-10-09 (AI-assisted, human-reviewed) (Model Sunset Desk sample). AI-assisted; human review required before use.
 * Written against Otter Blocks 3.2.7. Not affiliated with or endorsed by Themeisle.
 *
 * Install: copy to wp-content/mu-plugins/otter-model-sunset.php (must-use plugins load automatically).
 * Remove:  delete the file. No options, tables or stored data are created.
 *
 * What it does (same transform as patch.diff, applied through Otter's existing hooks):
 *  1. otter_ai_otter_openai_payload: swaps retiring model IDs for OpenAI's recommended replacement, sets
 *     reasoning_effort "none" after a swap from a non-reasoning model, drops temperature/top_p for GPT-5.x,
 *     converts deprecated functions/function_call to tools/tool_choice.
 *  2. otter_ai_otter_openai_response: turns tool_calls back into the function_call shape Otter 3.2.7 parses,
 *     and turns an empty reply with message.refusal into an error that shows the refusal text.
 *  3. http_request_args, ONLY during Otter's /otter/v1/openai/key REST request: the API-key check
 *     (hard-coded gpt-3.5-turbo, class-prompt-server.php:144) is sent with the replacement model.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Retiring chat model => OpenAI-recommended replacement.
 * Source: https://developers.openai.com/api/docs/deprecations (shutdown 2026-10-23), read 2026-10-09.
 *
 * @return array<string, string>
 */
function msd_otter_model_replacements() {
	$map = array(
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
	$filtered = apply_filters( 'otter_ai_openai_model_replacements', $map );
	return is_array( $filtered ) ? $filtered : $map;
}

/**
 * Adapt an OpenAI chat-completions payload (same logic as patch.diff adapt_payload()).
 *
 * @param array<string, mixed> $payload Payload.
 * @return array<string, mixed>
 */
function msd_otter_adapt_payload( $payload ) {
	if ( ! is_array( $payload ) ) {
		return $payload;
	}

	$map       = msd_otter_model_replacements();
	$requested = isset( $payload['model'] ) && is_string( $payload['model'] ) ? $payload['model'] : '';
	$model     = ( '' !== $requested && isset( $map[ $requested ] ) && is_string( $map[ $requested ] ) && '' !== $map[ $requested ] ) ? $map[ $requested ] : $requested;

	if ( '' !== $model && $model !== $requested ) {
		$payload['model'] = $model;

		if ( ! isset( $payload['reasoning_effort'] ) && 1 !== preg_match( '/^o[1-9]/', $requested ) && 1 === preg_match( '/^gpt-5\.6(-(sol|terra|luna))?$/', $model ) ) {
			$effort = (string) apply_filters( 'otter_ai_openai_swap_reasoning_effort', 'none', $requested, $model, $payload );
			if ( '' !== $effort ) {
				$payload['reasoning_effort'] = $effort;
			}
		}
	}

	if ( 1 === preg_match( '/^(gpt-5|o[1-9])/', $model ) && ! apply_filters( 'otter_ai_openai_keep_sampling_params', false, $model, $payload ) ) {
		unset( $payload['temperature'], $payload['top_p'], $payload['logprobs'], $payload['top_logprobs'] );
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

add_filter( 'otter_ai_otter_openai_payload', 'msd_otter_adapt_payload', 20 );

/**
 * Make tool_calls / refusal responses readable by Otter 3.2.7's parser.
 *
 * @param array<string, mixed> $body Decoded OpenAI response.
 * @return array<string, mixed>
 */
function msd_otter_adapt_response( $body ) {
	if ( ! is_array( $body ) || ! isset( $body['choices'][0]['message'] ) || ! is_array( $body['choices'][0]['message'] ) ) {
		return $body;
	}

	$message = $body['choices'][0]['message'];

	if ( empty( $message['function_call'] ) && isset( $message['tool_calls'][0]['function']['arguments'] ) ) {
		$body['choices'][0]['message']['function_call'] = array(
			'name'      => isset( $message['tool_calls'][0]['function']['name'] ) ? (string) $message['tool_calls'][0]['function']['name'] : '',
			'arguments' => (string) $message['tool_calls'][0]['function']['arguments'],
		);
		return $body;
	}

	$has_content = isset( $message['content'] ) && '' !== (string) $message['content'];
	if ( ! $has_content && empty( $message['function_call'] ) && isset( $message['refusal'] ) && is_string( $message['refusal'] ) && '' !== $message['refusal'] ) {
		// Otter 3.2.7 would report a generic empty_response; show the model's refusal instead.
		$body['error'] = array(
			'code'    => 'model_refusal',
			'message' => $message['refusal'],
		);
	}

	return $body;
}

add_filter( 'otter_ai_otter_openai_response', 'msd_otter_adapt_response', 20 );

/**
 * Adapt the API-key check, scoped to Otter's /otter/v1/openai/key REST request only.
 *
 * @param array<string, mixed> $args HTTP request args.
 * @param string               $url  Request URL.
 * @return array<string, mixed>
 */
function msd_otter_adapt_key_check( $args, $url ) {
	$route = isset( $GLOBALS['wp'] ) && is_object( $GLOBALS['wp'] ) && isset( $GLOBALS['wp']->query_vars['rest_route'] ) ? (string) $GLOBALS['wp']->query_vars['rest_route'] : '';

	if ( '/otter/v1/openai/key' !== untrailingslashit( $route ) || 0 !== strpos( (string) $url, 'https://api.openai.com/v1/chat/completions' ) ) {
		return $args;
	}

	if ( ! is_array( $args ) || ! isset( $args['body'] ) || ! is_string( $args['body'] ) ) {
		return $args;
	}

	$payload = json_decode( $args['body'], true );
	if ( is_array( $payload ) ) {
		$adapted = msd_otter_adapt_payload( $payload );
		if ( $adapted !== $payload ) {
			$args['body'] = wp_json_encode( $adapted );
		}
	}

	return $args;
}

add_filter( 'http_request_args', 'msd_otter_adapt_key_check', 20, 2 );
