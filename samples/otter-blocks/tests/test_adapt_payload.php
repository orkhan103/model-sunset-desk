<?php
/**
 * Behavioural test for the helpers added by patch.diff (hunk 1 of class-otter-openai-backend.php).
 * Produced 2026-10-09 (AI-assisted, human-reviewed).
 *
 * Executes ONLY the lines the patch adds (our own code), extracted from patch.diff;
 * no plugin code from the downloaded zip is executed. PHP 5.6+ compatible.
 *
 * Usage: php tests/test_adapt_payload.php patch.diff
 */

$patch = isset( $argv[1] ) ? $argv[1] : __DIR__ . '/../patch.diff';
$lines = file( $patch );
$added = array();
$in    = false;
foreach ( $lines as $line ) {
	if ( 0 === strpos( $line, '@@ -20,6' ) ) { // Hunk 1: constants + static helpers.
		$in = true;
		continue;
	}
	if ( $in && 0 === strpos( $line, '@@' ) ) {
		break;
	}
	if ( $in && 0 === strpos( $line, '+' ) ) {
		$added[] = substr( $line, 1 );
	}
}
if ( empty( $added ) ) {
	fwrite( STDERR, "Could not extract hunk 1 from $patch\n" );
	exit( 2 );
}
// diff aligns our first doc-comment opener with the existing one, so the added
// block starts inside a comment and ends with the next method's opener.
if ( '/**' === trim( end( $added ) ) ) {
	array_pop( $added );
}
array_unshift( $added, "\t/**\n" );

// Minimal WordPress stub: filters are configurable per test.
$GLOBALS['test_filters'] = array();
function apply_filters( $tag, $value ) {
	$args = func_get_args();
	if ( isset( $GLOBALS['test_filters'][ $tag ] ) ) {
		return call_user_func_array( $GLOBALS['test_filters'][ $tag ], array_slice( $args, 1 ) );
	}
	return $value;
}

eval( "class Patched_Helpers {\n" . implode( '', $added ) . "\n}" );

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

$form = array(
	'model'         => 'gpt-3.5-turbo',
	'messages'      => array( array( 'role' => 'user', 'content' => 'Contact form' ) ),
	'functions'     => array( array( 'name' => 'generateForm', 'parameters' => array( 'type' => 'object' ) ) ),
	'function_call' => array( 'name' => 'generateForm' ),
);

// 1. Form template (retiring model + legacy function calling).
$GLOBALS['test_filters'] = array();
$out = Patched_Helpers::adapt_payload( $form );
check( '1a gpt-3.5-turbo -> gpt-5.6-terra', 'gpt-5.6-terra' === $out['model'] );
check( '1b reasoning_effort none after swap from non-reasoning model', isset( $out['reasoning_effort'] ) && 'none' === $out['reasoning_effort'] );
check( '1c functions converted to tools', isset( $out['tools'][0]['type'] ) && 'function' === $out['tools'][0]['type'] && 'generateForm' === $out['tools'][0]['function']['name'] );
check( '1d function_call converted to named tool_choice', isset( $out['tool_choice']['function']['name'] ) && 'generateForm' === $out['tool_choice']['function']['name'] );
check( '1e deprecated keys removed', ! isset( $out['functions'] ) && ! isset( $out['function_call'] ) );

// 2. Regenerate path sends temperature 1.3.
$regen = array( 'model' => 'gpt-3.5-turbo', 'messages' => array(), 'temperature' => 1.3, 'stream' => false );
$out   = Patched_Helpers::adapt_payload( $regen );
check( '2a temperature dropped for gpt-5.6-terra by default', ! isset( $out['temperature'] ) );
check( '2b unrelated keys kept', isset( $out['stream'] ) && false === $out['stream'] );

// 3. Block pipeline: model already gpt-5-mini (not retiring on 2026-10-23).
$chat = array( 'model' => 'gpt-5-mini', 'messages' => array(), 'response_format' => array( 'type' => 'json_object' ), 'max_tokens' => 8192 );
$out  = Patched_Helpers::adapt_payload( $chat );
check( '3a gpt-5-mini unchanged', 'gpt-5-mini' === $out['model'] );
check( '3b no reasoning_effort injected when no swap happened', ! isset( $out['reasoning_effort'] ) );
check( '3c response_format and max_tokens untouched (renamed later by existing code)', isset( $out['response_format'] ) && 8192 === $out['max_tokens'] );

// 4. Reasoning source model keeps the target model default effort.
$out = Patched_Helpers::adapt_payload( array( 'model' => 'o4-mini', 'messages' => array() ) );
check( '4a o4-mini -> gpt-5.6-terra', 'gpt-5.6-terra' === $out['model'] );
check( '4b no reasoning_effort forced for o-series source', ! isset( $out['reasoning_effort'] ) );

// 5. Site disables the swap: model kept, temperature kept, tools conversion still applied.
$GLOBALS['test_filters'] = array( 'otter_ai_openai_model_replacements' => function () { return array(); } );
$out = Patched_Helpers::adapt_payload( $form + array( 'temperature' => 1.3 ) );
check( '5a empty map keeps gpt-3.5-turbo', 'gpt-3.5-turbo' === $out['model'] );
check( '5b temperature kept for non-reasoning model', isset( $out['temperature'] ) && 1.3 === $out['temperature'] );
check( '5c no reasoning_effort for non-reasoning model', ! isset( $out['reasoning_effort'] ) );
check( '5d tools conversion independent of swap', isset( $out['tools'] ) && ! isset( $out['functions'] ) );

// 6. Site opts back in to sampling params.
$GLOBALS['test_filters'] = array( 'otter_ai_openai_keep_sampling_params' => function () { return true; } );
$out = Patched_Helpers::adapt_payload( $regen );
check( '6 keep_sampling_params=true keeps temperature', isset( $out['temperature'] ) && 1.3 === $out['temperature'] );

// 7. Site prefers the model default effort.
$GLOBALS['test_filters'] = array( 'otter_ai_openai_swap_reasoning_effort' => function () { return ''; } );
$out = Patched_Helpers::adapt_payload( $form );
check( '7 swap effort filter "" omits reasoning_effort', ! isset( $out['reasoning_effort'] ) );

// 8. Caller-provided effort wins.
$GLOBALS['test_filters'] = array();
$out = Patched_Helpers::adapt_payload( $form + array( 'reasoning_effort' => 'low' ) );
check( '8 explicit reasoning_effort preserved', 'low' === $out['reasoning_effort'] );

// 9. Key validation model.
check( '9a key validation model defaults to gpt-5.6-terra', 'gpt-5.6-terra' === Patched_Helpers::get_key_validation_model() );
check( '9b gpt-5.6-terra supports effort none', Patched_Helpers::supports_reasoning_effort_none( 'gpt-5.6-terra' ) );
check( '9c gpt-5-mini not treated as supporting none', ! Patched_Helpers::supports_reasoning_effort_none( 'gpt-5-mini' ) );
$GLOBALS['test_filters'] = array( 'otter_ai_openai_key_validation_model' => function () { return 'gpt-5.6-luna'; } );
check( '9d key validation model filterable', 'gpt-5.6-luna' === Patched_Helpers::get_key_validation_model() );

// 10. Payload that already uses tools is not rewritten.
$GLOBALS['test_filters'] = array();
$both = $form + array( 'tools' => array( array( 'type' => 'function', 'function' => array( 'name' => 'x' ) ) ) );
$out  = Patched_Helpers::adapt_payload( $both );
check( '10 existing tools left alone', 'x' === $out['tools'][0]['function']['name'] && isset( $out['functions'] ) );

echo "\n$count checks, $failures failed (PHP " . PHP_VERSION . ")\n";
exit( $failures ? 1 : 0 );
