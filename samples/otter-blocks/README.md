# Otter Blocks: Swap & Verify proof sample (index)

Produced 2026-10-09 (AI-assisted, human-reviewed). Model Sunset Desk public proof sample; AI-assisted, human-reviewed.
Subject: Otter Blocks 3.2.7 (GPL, Themeisle). Not affiliated with Themeisle. Nothing here was published, submitted upstream or sent to anyone.
**No live API calls were made (budget $0).** Every before/after number in this folder comes from a dry run on synthetic mock responses.

Start with **`report.html`** (standalone; same content as `report.md`).

| Path | What it is |
|---|---|
| `report.md`, `report.html` | The deliverable: executive summary, exposure (file:line), what breaks on 23 Oct, parameter-diff table with sources, the patch hunk by hunk, test plan and dry-run demo, risks and rollback, what a client receives, verification log |
| `patch.diff` | Unified diff against Otter 3.2.7 (5 code hunks plus 2 comment-only modification-notice hunks). From the plugin root: `patch -p1 < patch.diff`. Regenerated 2026-10-09 with `cd patch-work && diff -ru a b` |
| `LICENSE-GPL-2.0.txt` | Full GNU GPL version 2 text, verbatim from https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt (fetched 2026-10-09, sha256 `edaef632...8739b233f6`) |
| `patch-work/a/`, `patch-work/b/` | Original (byte-identical to the 3.2.7 zip) and patched copies of the two changed files (GPL-2.0-or-later). Each `b/` file has a dated one-line modification notice in its header comment |
| `patch-work/NOTICE.md` | Licence, copyright and modification notice for the copied Otter files |
| `mu-plugin/otter-model-sunset.php` | No-core-edit alternative for site owners: the same transform through Otter's existing hooks. Copy it to `wp-content/mu-plugins/` |
| `tests/` | `test_adapt_payload.php` (24 checks, PHP 5.6 and 8.3), `test_mu_plugin.php` (8 checks), `test_transform_mirror.py` (10 checks), plus saved outputs |
| `harness/` | Regression harness (Python 3 stdlib): 30 cases, old vs new arms, dry-run mocks, pricing input, demo outputs. See `harness/README.md` |
| `tools/` | `build_report.py` (rebuilds the report from the generated artifacts), `md2html.py`, `html2txt.py` (used to read the saved OpenAI pages), `report.template.md`, `qa/` preview screenshot |

Rebuild everything:

```bash
# patch.diff = its 9-line preamble + diff -ru (exit status 1 just means the files differ):
{ head -n 9 patch.diff; (cd patch-work && diff -ru a b); } > patch.diff.new; mv patch.diff.new patch.diff
python3 -I harness/mocks/build_mocks.py
python3 -I harness/run_harness.py --dry-run --out harness/out/dry-run
python3 -I tests/test_transform_mirror.py > tests/test_transform_mirror.output.txt
docker run --rm --network none -v "$PWD:/w:ro" -w /w php:5.6-cli php tests/test_adapt_payload.php patch.diff
docker run --rm --network none -v "$PWD:/w:ro" -w /w php:8.3-cli php tests/test_mu_plugin.php
python3 -I tools/build_report.py
```

Inputs kept outside this folder, as untrusted downloads that were never executed: `launch/_untrusted/otter-blocks/` (plugin zip, sha256 `c59d54bd...71edadc0`, and the served prompt templates) and `launch/_untrusted/openai-docs-otter/` (copies of the OpenAI pages read on 2026-10-09).

The report's contact line uses the owner placeholders OWNER_NAME, CONTACT_EMAIL and SITE_URL (double-brace form); `launch/site/README.md` step 3 fills them when the site copy is built.

## Licence (GPL-2.0-or-later)

Otter Blocks is GPL-2.0-or-later software, (c) Themeisle. The two modified files in `patch-work/b/` and `patch.diff` are distributed under the same licence. The full licence text is in `LICENSE-GPL-2.0.txt`. Each modified file states in its header comment that it was modified on 2026-10-09 by Model Sunset Desk, what changed, and that the original is (c) Themeisle under GPL-2.0-or-later (GPL-2.0 section 2(a)). Details, hashes and the complete-source statement: `patch-work/NOTICE.md`. Our own new files (`mu-plugin/`, `tests/`, `harness/`, `tools/`) are separate; the mu-plugin header declares GPL-2.0-or-later.

## Verification after the GPL compliance pass (2026-10-09, ~14:00 EDT)

Produced 2026-10-09 (AI-assisted, human-reviewed).

| Check | Result |
|---|---|
| `patch-work/a/` vs the files inside the 3.2.7 zip (sha256 `c59d54bd...71edadc0`) | Both byte-identical |
| `patch -p1 --dry-run < patch.diff` on a fresh copy of `patch-work/a/` | Clean, exit 0, no fuzz or offset |
| Real apply on that copy, then `diff -r` against `patch-work/b/` | Byte-identical; reverse dry run (`-R`) also clean |
| `php -l` on both `b/` files (`php:5.6-cli`, `php:8.3-cli`, `--network none`) | No syntax errors |
| `tests/test_adapt_payload.php patch.diff` | 24/24 passed on PHP 5.6.40; 24/24 on PHP 8.3.35 (output identical to the saved file) |
| `tests/test_mu_plugin.php` (+ `php -l` on the mu-plugin) | 8/8 passed on PHP 5.6.40; 8/8 on PHP 8.3.35 (identical) |
| `python3 -I tests/test_transform_mirror.py` | 10/10 passed on Python 3.14 (identical) |
| `python3 -I tools/build_report.py` | Report rebuilt. Only changes: b-side line numbers in five hunk headers (+1), a new "Modification notices" paragraph showing the two notice hunks, the hunk count in the test-plan row, and the file list. No finding, verdict or number changed |

The notice lines are comments. They change no behaviour and no conclusion of the report.

