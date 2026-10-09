<?php
/**
 * Behavioural test for mu-plugin/otter-model-sunset.php (our own code; no Otter code is executed).
 * Produced 2026-10-09 (AI-assisted, human-reviewed). Usage: php tests/test_mu_plugin.php
 */

define( 'ABSPATH', '/tmp/' );
$GLOBALS['hooks'] = array();
function add_filter( $tag, $cb, $prio = 10, $args = 1 ) { $GLOBALS['hooks'][ $tag ] = $cb; }
function apply_filters( $tag, $value ) { return $value; }
function wp_json_encode( $v ) { return json_encode( $v ); }
function untrailingslashit( $s ) { return rtrim( $s, '/\\' ); }

require __DIR__ . '/../mu-plugin/otter-model-sunset.php';

$failures = 0;
$count    = 0;
function check( $name, $cond ) {
	global $failures, $count;
	$count++;
	echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n";
	if ( ! $cond ) {
		$failures++;
	}
}

check( '0 hooks registered', isset( $GLOBALS['hooks']['otter_ai_otter_openai_payload'], $GLOBALS['hooks']['otter_ai_otter_openai_response'], $GLOBALS['hooks']['http_request_args'] ) );

$form = array(
	'model'         => 'gpt-3.5-turbo',
	'messages'      => array(),
	'functions'     => array( array( 'name' => 'generateForm', 'parameters' => array( 'type' => 'object' ) ) ),
	'function_call' => array( 'name' => 'generateForm' ),
	'temperature'   => 1.3,
);
$out = msd_otter_adapt_payload( $form );
check( '1 payload: swap, effort none, tools, temperature dropped', 'gpt-5.6-terra' === $out['model'] && 'none' === $out['reasoning_effort'] && 'generateForm' === $out['tool_choice']['function']['name'] && ! isset( $out['functions'], $out['temperature'] ) );

$resp = array( 'choices' => array( array( 'message' => array( 'role' => 'assistant', 'content' => null, 'tool_calls' => array( array( 'id' => 'c1', 'type' => 'function', 'function' => array( 'name' => 'generateForm', 'arguments' => '{"fields":[]}' ) ) ) ) ) ) );
$out  = msd_otter_adapt_response( $resp );
check( '2 response: tool_calls mapped to function_call for 3.2.7 parser', '{"fields":[]}' === $out['choices'][0]['message']['function_call']['arguments'] );

$resp = array( 'choices' => array( array( 'message' => array( 'role' => 'assistant', 'content' => null, 'refusal' => 'I can\'t help with that.' ) ) ) );
$out  = msd_otter_adapt_response( $resp );
check( '3 response: refusal surfaced as error', isset( $out['error']['code'] ) && 'model_refusal' === $out['error']['code'] );

$resp = array( 'choices' => array( array( 'message' => array( 'role' => 'assistant', 'content' => '<p>Hi</p>' ) ) ) );
check( '4 response: plain content untouched', msd_otter_adapt_response( $resp ) === $resp );

$key_args = array( 'body' => json_encode( array( 'model' => 'gpt-3.5-turbo', 'messages' => array( array( 'role' => 'user', 'content' => 'Hello!' ) ) ) ) );
$GLOBALS['wp'] = (object) array( 'query_vars' => array( 'rest_route' => '/otter/v1/openai/key' ) );
$out  = msd_otter_adapt_key_check( $key_args, 'https://api.openai.com/v1/chat/completions' );
$body = json_decode( $out['body'], true );
check( '5 key check on Otter route: model swapped + effort none', 'gpt-5.6-terra' === $body['model'] && 'none' === $body['reasoning_effort'] );

$GLOBALS['wp'] = (object) array( 'query_vars' => array( 'rest_route' => '/other-plugin/v1/chat' ) );
check( '6 other REST routes untouched', $key_args === msd_otter_adapt_key_check( $key_args, 'https://api.openai.com/v1/chat/completions' ) );

$GLOBALS['wp'] = (object) array( 'query_vars' => array( 'rest_route' => '/otter/v1/openai/key' ) );
check( '7 non-OpenAI URLs untouched', $key_args === msd_otter_adapt_key_check( $key_args, 'https://example.com/api' ) );

echo "\n$count checks, $failures failed (PHP " . PHP_VERSION . ")\n";
exit( $failures ? 1 : 0 );
