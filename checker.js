/*!
 * Model Sunset Desk: free exposure checker
 * Produced 2026-10-09 (AI-assisted, human-reviewed).
 *
 * Pure client-side JavaScript. This file contains no network code: no fetch,
 * no XMLHttpRequest, no beacons. The page also sets a Content-Security-Policy
 * with connect-src 'none', so the browser would block a request even if one
 * were attempted. Pasted text never leaves the browser tab.
 *
 * Data (read live 2026-10-09):
 *   [OPENAI]    https://developers.openai.com/api/docs/deprecations
 *               2026-04-22 entry (shutdown 2026-10-23); 2026-06-02 image entry
 *               (2026-12-01); 2026-06-03 Evals / Agent Builder / reusable prompts
 *               entries (read-only 2026-10-31, shutdown 2026-11-30); 2026-06-11
 *               snapshot entries (2026-12-11); 2025-09-26 entries for IDs already
 *               shut down (2026-03-26 and 2026-09-28).
 *   [ANTHROPIC] https://platform.claude.com/docs/en/about-claude/model-deprecations
 *               AI agent retires 2026-11-30 -> AI agent.
 *
 * Matching rules (exact tokens):
 *   - A candidate is a run of [A-Za-z0-9._:@-] starting with a letter or digit.
 *     Trailing . : @ - are trimmed (so "gpt-4." at the end of a sentence counts).
 *   - The run is split on ":" (so "openai:gpt-4" is seen) unless it starts with
 *     "ft:", in which case it is a fine-tuned model ID classified by its base.
 *   - A segment must equal a listed ID exactly (case-insensitive). So "gpt-4"
 *     never matches inside "gpt-4o", "gpt-4.1" or "text-davinci-002".
 *   - gpt-3.5-turbo-* and gpt-4-* variants that the 23 Oct table does not name
 *     are reported as "check" (no date claimed): several were shut down earlier.
 *   - "o1" alone is ambiguous (it is also a common variable name), so it is
 *     only reported in a model-like context: quoted, after "openai:" or
 *     "openai/", or on a line that mentions "model" or "engine".
 *   - Azure-prefixed IDs (azure/..., azure:...) are skipped; Azure OpenAI,
 *     Amazon Bedrock and Google Vertex set their own retirement dates.
 *   - IDs whose shutdown date has already passed (listed on the same page) get
 *     status "past" so the result says "already shut down", not "23 Oct".
 *   - Unicode hyphens (U+2010, U+2011) are read as "-" (text copied from docs).
 *
 * QA revision 2026-10-09 (AI agent, QA reviewer): bare babbage-002 and
 * davinci-002 were shown as "shuts down 23 Oct"; OpenAI's page lists them as
 * shut down on 2026-09-28 (only ft-babbage-002 / ft-davinci-002 are on the
 * 23 Oct list). Added the "past" status and the 2026-03-26 / 2026-09-28 IDs.
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.ModelSunsetChecker = api;
  }
  if (typeof document !== 'undefined' && document && typeof document.addEventListener === 'function') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { bindUI(api, document); });
    } else {
      bindUI(api, document);
    }
  }
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
  'use strict';

  var SRC_OPENAI = 'https://developers.openai.com/api/docs/deprecations';
  var SRC_ANTHROPIC = 'https://platform.claude.com/docs/en/about-claude/model-deprecations';

  var D_MAR26 = '2026-03-26';
  var D_SEP28 = '2026-09-28';
  var D_OCT23 = '2026-10-23';
  var D_NOV30 = '2026-11-30';
  var D_DEC01 = '2026-12-01';
  var D_DEC11 = '2026-12-11';

  var R = {
    terra: 'gpt-5.6-terra',
    sol: 'gpt-5.6-sol',
    luna: 'gpt-5.6-luna',
    solPro: 'gpt-5.6-sol (reasoning.mode: pro)',
    image: 'gpt-image-2.5-sunburst or gpt-image-2.5-flare',
    sonnet: 'AI agent'
  };

  var EXACT = Object.create(null);

  function add(ids, date, replacement, opts) {
    opts = opts || {};
    for (var i = 0; i < ids.length; i++) {
      EXACT[ids[i]] = {
        id: ids[i],
        date: date,
        replacement: replacement,
        provider: opts.provider || 'OpenAI',
        kind: opts.kind || 'listed',
        note: opts.note || '',
        source: opts.source || SRC_OPENAI
      };
    }
  }

  // --- Shut down 23 Oct 2026 (OpenAI, entry announced 2026-04-22) ---
  add(['gpt-3.5-turbo', 'gpt-3.5-turbo-0125', 'gpt-3.5-turbo-completions'], D_OCT23, R.terra);
  add(['gpt-4', 'gpt-4-0613', 'gpt-4-0613-completions', 'gpt-4-completions'], D_OCT23, R.sol);
  add(['gpt-4-1106-preview'], D_OCT23, R.sol, {
    note: 'OpenAI\'s page also lists this ID under an earlier shutdown on 26 Mar 2026, so calls to it may already fail.'
  });
  add(['gpt-4-turbo', 'gpt-4-turbo-2024-04-09', 'gpt-4-turbo-completions'], D_OCT23, R.sol);
  add(['gpt-4.1-nano', 'gpt-4.1-nano-2025-04-14'], D_OCT23, R.luna);
  add(['gpt-4o-2024-05-13'], D_OCT23, R.sol, {
    note: 'Only this dated snapshot is on the list. Plain gpt-4o is not.'
  });
  add(['gpt-image-1'], D_OCT23, R.image);
  add(['o1', 'o1-2024-12-17'], D_OCT23, R.sol);
  add(['o1-pro', 'o1-pro-2025-03-19'], D_OCT23, R.solPro);
  add(['o3-mini', 'o3-mini-2025-01-31'], D_OCT23, R.sol);
  add(['o4-mini', 'o4-mini-2025-04-16'], D_OCT23, R.terra);
  // Fine-tune family labels exactly as written on the deprecations page.
  add(['ft-gpt-3.5-turbo', 'ft-o4-mini-2025-04-16', 'ft-babbage-002', 'ft-davinci-002'], D_OCT23, R.terra, { kind: 'fine-tune' });
  add(['ft-gpt-4'], D_OCT23, R.sol, { kind: 'fine-tune' });
  add(['ft-gpt-4.1-nano-2025-04-14'], D_OCT23, R.luna, { kind: 'fine-tune' });
  // --- Already shut down (same page, entries announced 2025-09-26) ---
  // Base models babbage-002 / davinci-002: shut down 2026-09-28. Their fine-tunes
  // (ft-babbage-002 / ft-davinci-002) are on the 23 Oct list above.
  add(['babbage-002', 'davinci-002'], D_SEP28, R.terra, {
    kind: 'past',
    note: 'OpenAI lists this base model as shut down on 28 Sep 2026, so calls to it already fail. Fine-tuned models on this base (ft:babbage-002 / ft:davinci-002) are on the 23 Oct list.'
  });
  add(['gpt-3.5-turbo-instruct', 'gpt-3.5-turbo-1106'], D_SEP28, R.terra, {
    kind: 'past',
    note: 'OpenAI lists this ID as shut down on 28 Sep 2026, so calls to it already fail.'
  });
  add(['gpt-4-0314', 'gpt-4-0125-preview', 'gpt-4-turbo-preview', 'gpt-4-turbo-preview-completions'], D_MAR26, R.sol, {
    kind: 'past',
    note: 'OpenAI lists this ID as shut down on 26 Mar 2026, so calls to it already fail. That entry named gpt-5 or gpt-4.1 as the replacement; gpt-5.6-sol is what OpenAI now lists for gpt-4 and gpt-4-turbo.'
  });

  // --- Later dates ---
  add(['gpt-image-1-mini', 'gpt-image-1.5', 'chatgpt-image-latest'], D_DEC01, R.image);
  add(['gpt-5-2025-08-07'], D_DEC11, R.sol, { note: 'Dated snapshot. Plain gpt-5 is not on the list.' });
  add(['gpt-5-mini-2025-08-07'], D_DEC11, R.terra, { note: 'Dated snapshot. Plain gpt-5-mini is not on the list.' });
  add(['gpt-5-nano-2025-08-07'], D_DEC11, R.luna, { note: 'Dated snapshot. Plain gpt-5-nano is not on the list.' });
  add(['gpt-5-pro-2025-10-06'], D_DEC11, R.solPro, { note: 'Dated snapshot.' });
  add(['o3-2025-04-16'], D_DEC11, R.sol, { note: 'Dated snapshot. Plain o3 is not on the list.' });
  add(['o3-pro-2025-06-10'], D_DEC11, R.solPro, { note: 'Dated snapshot. Plain o3-pro is not on the list.' });
  add(['AI agent'], D_NOV30, R.sonnet, { provider: 'Anthropic', source: SRC_ANTHROPIC });
  add(['AI agent'], D_NOV30, R.sonnet, {
    provider: 'Anthropic',
    source: SRC_ANTHROPIC,
    kind: 'alias',
    note: 'Undated alias. Anthropic lists the dated snapshot AI agent; check which snapshot your alias resolves to.'
  });

  // IDs that are too short to trust without a model-like context.
  var NEEDS_CONTEXT = { 'o1': true };

  // Variants of a listed family that the 23 Oct table does not name.
  var FAMILIES = [
    // Suffix must look like a real variant (a date/number, or a known variant word),
    // so prose such as "gpt-4-like" or "GPT-4-level" is not reported (QA fix).
    { re: /^gpt-3\.5-turbo-(?:\d|16k|instruct)[a-z0-9.\-]*$/, family: 'gpt-3.5-turbo', replacement: R.terra },
    { re: /^gpt-4-(?:\d|turbo|vision|32k|base)[a-z0-9.\-]*$/, family: 'gpt-4', replacement: R.sol }
  ];
  var FAMILY_NOTE = 'Not named on its own in the 23 Oct table. Several older variants of this family were shut down on earlier dates. Look up this exact ID on OpenAI\'s deprecations page.';

  // Fine-tuned model IDs look like ft:<base>:<org>:<suffix>:<id>.
  function classifyFineTune(base) {
    if (base === 'gpt-3.5-turbo' || base.indexOf('gpt-3.5-turbo-') === 0) return EXACT['ft-gpt-3.5-turbo'];
    if (/^gpt-4\.1-nano(?:-2025-04-14)?$/.test(base)) return EXACT['ft-gpt-4.1-nano-2025-04-14'];
    if (base === 'gpt-4' || /^gpt-4-[a-z0-9]/.test(base)) return EXACT['ft-gpt-4'];
    if (/^o4-mini(?:-2025-04-16)?$/.test(base)) return EXACT['ft-o4-mini-2025-04-16'];
    if (base === 'babbage-002') return EXACT['ft-babbage-002'];
    if (base === 'davinci-002') return EXACT['ft-davinci-002'];
    return null; // e.g. ft:gpt-4o-..., ft:gpt-4o-mini-..., ft:gpt-4.1-..., ft:gpt-4.1-mini-...
  }
  var FT_NOTE = 'Fine-tuned models stay available only until their base model is shut down (OpenAI fine-tuning guide).';

  // Products and APIs with later dates, matched on the raw line.
  var SYSTEMS = [
    {
      re: /(?:^|[^A-Za-z0-9_])(v1\/prompts)(?![A-Za-z0-9_])/g,
      id: 'v1/prompts',
      label: 'Reusable prompts API (v1/prompts)',
      date: D_NOV30,
      replacement: 'Move the prompt content into your application code (OpenAI\'s guidance)',
      note: 'Reusable prompt objects shut down 30 Nov 2026.'
    },
    {
      re: /(?:^|[^A-Za-z0-9_])(pmpt_[A-Za-z0-9]{6,})(?![A-Za-z0-9_])/g,
      id: 'reusable prompt object',
      label: 'Reusable prompt object',
      date: D_NOV30,
      replacement: 'Move the prompt content into your application code (OpenAI\'s guidance)',
      note: 'Looks like a reusable prompt ID. Reusable prompt objects shut down 30 Nov 2026.'
    },
    {
      re: /(?:^|[^A-Za-z0-9_])(v1\/evals)(?![A-Za-z0-9_])/g,
      id: 'v1/evals',
      label: 'OpenAI Evals API',
      date: D_NOV30,
      replacement: 'No direct replacement; OpenAI links a guide to moving to Promptfoo',
      note: 'Existing evals become read-only 31 Oct 2026; Evals shuts down 30 Nov 2026.'
    },
    {
      re: /(\.evals\.(?:create|retrieve|list|update|delete|runs))(?![A-Za-z0-9_])/g,
      id: 'evals (SDK call)',
      label: 'OpenAI Evals API',
      date: D_NOV30,
      replacement: 'No direct replacement; OpenAI links a guide to moving to Promptfoo',
      note: 'Existing evals become read-only 31 Oct 2026; Evals shuts down 30 Nov 2026.'
    }
  ];

  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function formatDate(iso) {
    if (!iso) return 'check';
    var p = iso.split('-');
    return parseInt(p[2], 10) + ' ' + MONTHS[parseInt(p[1], 10) - 1] + ' ' + p[0];
  }

  function statusFor(date) {
    if (!date) return 'check';
    if (date === D_OCT23) return 'oct23';
    return date < D_OCT23 ? 'past' : 'later';
  }

  function makeFinding(lineNo, start, end, text, entry, kind, extraNote) {
    var notes = [];
    if (entry.note) notes.push(entry.note);
    if (extraNote) notes.push(extraNote);
    return {
      line: lineNo,
      column: start + 1,
      start: start,
      end: end,
      text: text,
      id: entry.id,
      kind: kind || entry.kind,
      status: statusFor(entry.date),
      date: entry.date || null,
      dateLabel: formatDate(entry.date),
      replacement: entry.replacement,
      provider: entry.provider || 'OpenAI',
      source: entry.source || SRC_OPENAI,
      note: notes.join(' ')
    };
  }

  function hasModelContext(line, start, end, prevSegment) {
    var q = line.charAt(start - 1);
    if ((q === '"' || q === '\'' || q === '`') && line.charAt(end) === q) return true;
    if (prevSegment && /^openai$/i.test(prevSegment)) return true;
    if (/openai\/$/i.test(line.slice(Math.max(0, start - 7), start))) return true;
    return /model|engine/i.test(line);
  }

  var TOKEN_RE = /[A-Za-z0-9][A-Za-z0-9._:@\-]*/g;
  var CAPS_NOTE = 'Written with capitals, so it may be prose or a display label rather than a value sent to the API.';

  function scanLine(line, lineNo) {
    var found = [];
    var m;
    // Same-length substitution, so columns still index the original text.
    line = line.replace(/[\u2010\u2011]/g, '-');
    TOKEN_RE.lastIndex = 0;
    while ((m = TOKEN_RE.exec(line)) !== null) {
      var raw = m[0];
      var start = m.index;
      var tok = raw.replace(/[.:@\-]+$/, '');
      if (!tok) continue;

      var lead = line.slice(Math.max(0, start - 6), start).toLowerCase();
      if (/azure\/$/.test(lead)) continue;

      if (/^ft:/i.test(tok)) {
        var base = tok.slice(3).split(':')[0].toLowerCase();
        var ft = classifyFineTune(base);
        if (ft) found.push(makeFinding(lineNo, start, start + tok.length, tok, ft, 'fine-tune', FT_NOTE));
        continue; // never re-match the pieces of a fine-tuned ID
      }

      var segments = tok.split(':');
      var offset = start;
      for (var s = 0; s < segments.length; s++) {
        var seg = segments[s];
        var segStart = offset;
        var segEnd = offset + seg.length;
        offset = segEnd + 1;
        if (!seg) continue;
        var prev = s > 0 ? segments[s - 1] : '';
        if (prev && /^azure$/i.test(prev)) continue;

        var lower = seg.toLowerCase();
        var capsNote = seg !== lower ? CAPS_NOTE : '';
        var entry = EXACT[lower];
        if (entry) {
          if (NEEDS_CONTEXT[lower] && !hasModelContext(line, segStart, segEnd, prev)) continue;
          found.push(makeFinding(lineNo, segStart, segEnd, seg, entry, null, capsNote));
          continue;
        }
        for (var f = 0; f < FAMILIES.length; f++) {
          if (FAMILIES[f].re.test(lower)) {
            var fam = {
              id: lower,
              date: null,
              replacement: FAMILIES[f].replacement + ' (replacement for the ' + FAMILIES[f].family + ' family)',
              provider: 'OpenAI',
              kind: 'family',
              note: FAMILY_NOTE,
              source: SRC_OPENAI
            };
            found.push(makeFinding(lineNo, segStart, segEnd, seg, fam, 'family', capsNote));
            break;
          }
        }
      }
    }

    for (var k = 0; k < SYSTEMS.length; k++) {
      var sys = SYSTEMS[k];
      sys.re.lastIndex = 0;
      var sm;
      while ((sm = sys.re.exec(line)) !== null) {
        var text = sm[1];
        var sStart = sm.index + sm[0].length - text.length;
        found.push(makeFinding(lineNo, sStart, sStart + text.length, text, {
          id: sys.id,
          date: sys.date,
          replacement: sys.replacement,
          provider: 'OpenAI',
          kind: 'system',
          note: sys.label + '. ' + sys.note,
          source: SRC_OPENAI
        }, 'system'));
        if (sm[0].length === 0) sys.re.lastIndex++;
      }
    }

    found.sort(function (a, b) { return a.start - b.start; });
    return found;
  }

  var MAX_CHARS = 5000000;

  function check(input) {
    var text = input == null ? '' : String(input);
    if (text.length > MAX_CHARS) {
      return { findings: [], counts: { past: 0, oct23: 0, later: 0, check: 0, total: 0 }, lines: 0, tooLarge: true };
    }
    var lines = text.split(/\r\n|\r|\n/);
    var findings = [];
    for (var i = 0; i < lines.length; i++) {
      if (!lines[i]) continue;
      var f = scanLine(lines[i], i + 1);
      for (var j = 0; j < f.length; j++) findings.push(f[j]);
    }
    var counts = { past: 0, oct23: 0, later: 0, check: 0, total: findings.length };
    for (var n = 0; n < findings.length; n++) counts[findings[n].status]++;
    return { findings: findings, counts: counts, lines: text === '' ? 0 : lines.length, tooLarge: false };
  }

  var STATUS_ORDER = { past: 0, oct23: 1, later: 2, check: 3 };

  function group(findings) {
    var map = Object.create(null);
    var out = [];
    for (var i = 0; i < findings.length; i++) {
      var f = findings[i];
      var key = f.kind === 'fine-tune' || f.kind === 'system' ? f.text : f.id;
      if (!map[key]) {
        map[key] = {
          key: key,
          id: f.id,
          label: f.kind === 'fine-tune' || f.kind === 'system' ? f.text : f.id,
          kind: f.kind,
          status: f.status,
          date: f.date,
          dateLabel: f.dateLabel,
          replacement: f.replacement,
          provider: f.provider,
          note: f.note,
          lines: []
        };
        out.push(map[key]);
      }
      if (map[key].lines.indexOf(f.line) === -1) map[key].lines.push(f.line);
    }
    out.sort(function (a, b) {
      return (STATUS_ORDER[a.status] - STATUS_ORDER[b.status]) ||
        String(a.date || '9999').localeCompare(String(b.date || '9999')) ||
        a.label.localeCompare(b.label);
    });
    return out;
  }

  function toText(result) {
    var rows = ['Model Sunset Desk exposure check (runs locally; data read 9 Oct 2026 from OpenAI and Anthropic deprecation pages)'];
    var g = group(result.findings);
    for (var i = 0; i < g.length; i++) {
      rows.push(
        g[i].label + ' | ' + (g[i].status === 'check' ? 'check this ID' :
          (g[i].status === 'past' ? 'already shut down ' : 'shuts down ') + g[i].dateLabel) +
        ' | replace with ' + g[i].replacement + ' | lines ' + g[i].lines.join(', ')
      );
    }
    if (!g.length) rows.push('No retiring model IDs found.');
    return rows.join('\n');
  }

  return {
    version: '2026-10-09',
    sources: { openai: SRC_OPENAI, anthropic: SRC_ANTHROPIC },
    dates: { mar26: D_MAR26, sep28: D_SEP28, oct23: D_OCT23, nov30: D_NOV30, dec01: D_DEC01, dec11: D_DEC11 },
    catalog: EXACT,
    check: check,
    group: group,
    toText: toText,
    formatDate: formatDate,
    classifyFineTune: classifyFineTune
  };
});

/* ---------- Browser UI (only runs when a document exists) ---------- */
function bindUI(api, doc) {
  'use strict';
  var input = doc.getElementById('checker-input');
  var runBtn = doc.getElementById('checker-run');
  var exampleBtn = doc.getElementById('checker-example');
  var clearBtn = doc.getElementById('checker-clear');
  var out = doc.getElementById('checker-results');
  if (!input || !runBtn || !out) return;

  var EXAMPLE = [
    '# support_bot.py',
    'reply = client.chat.completions.create(',
    '    model="gpt-3.5-turbo",',
    '    response_format={"type": "json_object"},',
    ')',
    'summary = client.chat.completions.create(model="gpt-4o-mini", messages=msgs)',
    'classifier = "ft:gpt-3.5-turbo-0125:acme:tickets:9xYzAb12"',
    'image = client.images.generate(model="gpt-image-1", prompt=p)',
    '',
    '# .env',
    'OPENAI_MODEL=gpt-4.1',
    'REASONING_MODEL=o4-mini',
    'FALLBACK_MODEL=gpt-4',
    '',
    '// n8n node export (excerpt)',
    '{ "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",',
    '  "parameters": { "model": { "__rl": true, "value": "gpt-4-turbo", "mode": "list" } } }',
    '',
    '// Anthropic',
    'const draft = await anthropic.messages.create({ model: "AI agent" });'
  ].join('\n');

  var lastResult = null;

  function el(tag, cls, text) {
    var node = doc.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function statusText(g) {
    if (g.status === 'past') return 'Already shut down ' + g.dateLabel;
    if (g.status === 'oct23') return 'Shuts down ' + g.dateLabel;
    if (g.status === 'later') return 'Later: ' + g.dateLabel;
    return 'Check this ID';
  }

  function render(result, sourceText) {
    out.textContent = '';

    if (result.tooLarge) {
      out.appendChild(el('p', 'results__msg', 'That is over 5 MB. Paste one file or one workflow export at a time.'));
      return;
    }
    if (!sourceText.trim()) {
      out.appendChild(el('p', 'results__msg', 'Paste something first: code, a config file or a workflow JSON export.'));
      input.focus();
      return;
    }

    var c = result.counts;
    var summary = el('div', 'results__summary');
    if (!c.total) {
      summary.classList.add('is-clear');
      summary.appendChild(el('p', 'results__headline', 'No retiring model IDs found in ' + result.lines + ' line' + (result.lines === 1 ? '' : 's') + '.'));
      summary.appendChild(el('p', 'results__fine', 'This covers IDs written out in the text you pasted. IDs built at runtime, stored in a database or chosen in a vendor dashboard will not show up here.'));
      out.appendChild(summary);
      return;
    }

    var groups = api.group(result.findings);
    var parts = [];
    if (c.past) parts.push(c.past + ' already shut down');
    if (c.oct23) parts.push(c.oct23 + ' on the 23 Oct list');
    if (c.later) parts.push(c.later + ' with a later date');
    if (c.check) parts.push(c.check + ' to look up');
    summary.appendChild(el('p', 'results__headline',
      c.total + ' reference' + (c.total === 1 ? '' : 's') + ' in ' + result.lines + ' line' + (result.lines === 1 ? '' : 's') + ': ' + parts.join(', ') + '.'));
    summary.appendChild(el('p', 'results__fine', 'Checked in this tab against the OpenAI and Anthropic deprecation pages as read on 9 Oct 2026. Nothing was sent anywhere.'));
    out.appendChild(summary);

    // Table: one row per ID.
    var wrap = el('div', 'results__tablewrap');
    var table = el('table', 'results__table');
    var thead = el('thead');
    var hr = el('tr');
    ['Model ID found', 'Lines', 'Recommended replacement', 'Date'].forEach(function (h) { hr.appendChild(el('th', null, h)); });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = el('tbody');
    groups.forEach(function (g) {
      var tr = el('tr', 'row row--' + g.status);
      var tdId = el('td', 'cell-id');
      tdId.setAttribute('data-label', 'Model ID found');
      tdId.appendChild(el('span', 'id struck struck--flow', g.label));
      if (g.note) tdId.appendChild(el('span', 'cell-note', g.note));
      tr.appendChild(tdId);
      var shown = g.lines.slice(0, 12).join(', ') + (g.lines.length > 12 ? ' +' + (g.lines.length - 12) + ' more' : '');
      var tdLines = el('td', 'cell-lines', shown);
      tdLines.setAttribute('data-label', 'Lines');
      tr.appendChild(tdLines);
      var tdRepl = el('td', 'cell-repl', g.replacement);
      tdRepl.setAttribute('data-label', 'Replace with');
      tr.appendChild(tdRepl);
      var tdDate = el('td', 'cell-date status--' + g.status, statusText(g));
      tdDate.setAttribute('data-label', 'Date');
      tr.appendChild(tdDate);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    out.appendChild(wrap);

    // Redlined lines: the pasted lines with the retiring ID struck through.
    var linesText = sourceText.split(/\r\n|\r|\n/);
    var list = el('ol', 'redlines');
    list.setAttribute('aria-label', 'Matching lines');
    var MAX_LINES = 120;
    result.findings.slice(0, MAX_LINES).forEach(function (f) {
      var li = el('li', 'redline redline--' + f.status);
      li.appendChild(el('span', 'redline__n', 'L' + f.line));
      var code = el('code', 'redline__code');
      var src = linesText[f.line - 1] || '';
      var from = Math.max(0, f.start - 48);
      var to = Math.min(src.length, f.end + 48);
      code.appendChild(doc.createTextNode((from > 0 ? '…' : '') + src.slice(from, f.start)));
      code.appendChild(el('span', 'struck struck--flow', src.slice(f.start, f.end)));
      code.appendChild(doc.createTextNode(src.slice(f.end, to) + (to < src.length ? '…' : '')));
      li.appendChild(code);
      li.appendChild(el('span', 'redline__note', '→ ' + f.replacement + ' · ' +
        (f.status === 'check' ? 'check date' : (f.status === 'past' ? 'already shut down ' : '') + f.dateLabel)));
      list.appendChild(li);
    });
    out.appendChild(list);
    if (result.findings.length > MAX_LINES) {
      out.appendChild(el('p', 'results__fine', 'Showing the first ' + MAX_LINES + ' of ' + result.findings.length + ' matching lines. The table above covers all of them.'));
    }

    var actions = el('div', 'results__actions');
    var copyBtn = el('button', 'btn btn--line btn--small', 'Copy results as text');
    copyBtn.type = 'button';
    copyBtn.addEventListener('click', function () {
      var text = api.toText(lastResult);
      var done = function () {
        copyBtn.textContent = 'Copied';
        setTimeout(function () { copyBtn.textContent = 'Copy results as text'; }, 2000);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { copyBtn.textContent = 'Copy failed: select the table instead'; });
      } else {
        copyBtn.textContent = 'Copy is not available in this browser';
      }
    });
    actions.appendChild(copyBtn);
    var cta = el('a', 'btn btn--ink btn--small', 'Get a quote for these');
    cta.href = '#offers';
    actions.appendChild(cta);
    out.appendChild(actions);

  }

  function run() {
    var text = input.value;
    lastResult = api.check(text);
    render(lastResult, text);
  }

  runBtn.addEventListener('click', run);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      run();
    }
  });
  if (exampleBtn) {
    exampleBtn.addEventListener('click', function () {
      input.value = EXAMPLE;
      run();
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      input.value = '';
      out.textContent = '';
      lastResult = null;
      input.focus();
    });
  }
}
