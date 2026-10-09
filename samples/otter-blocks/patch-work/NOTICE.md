# Licence and modification notice: Otter Blocks files in this folder

Produced 2026-10-09 (AI-assisted, human-reviewed) (QA reviewer, Model Sunset Desk launch review). Updated 2026-10-09 (GPL compliance pass, same model): in-file modification notices, full licence text, regenerated patch.

- `a/inc/server/class-prompt-server.php` and `a/inc/server/class-otter-openai-backend.php` are unmodified copies of files from
  **Otter Blocks 3.2.7** by Themeisle, downloaded from WordPress.org (`otter-blocks.latest-stable.zip`, sha256
  `c59d54bdaab37d5e4c441b83472daed2f4335600cba5db0142d4cd8c71edadc0`). Re-checked 2026-10-09: both are byte-identical to the
  files inside that zip.
- The plugin declares its licence as **GPL-2.0+** (`otter-blocks.php` header: "License: GPL-2.0+") and "GPLv2 or later" (`readme.txt`),
  read from the downloaded zip on 2026-10-09.
- The files in `b/` are **modified versions** of those two files. They were changed on **2026-10-09** by Model Sunset Desk
  (Orkhan Karimov), using AI coding agents with human review, to move the hard-coded `gpt-3.5-turbo` call off a model that OpenAI
  shuts down on 23 Oct 2026. Every change is shown line by line in `../patch.diff`.
- **Prominent notice in each modified file (GPL-2.0 section 2(a)).** Each file in `b/` carries one dated comment line in its header
  docblock, directly under the file description:
  - `b/inc/server/class-otter-openai-backend.php`: "Modified 2026-10-09 by Model Sunset Desk: swaps OpenAI models retiring
    2026-10-23 for the recommended replacements (adapt_payload) and parses tool_calls and refusals; original © Themeisle,
    GPL-2.0-or-later"
  - `b/inc/server/class-prompt-server.php`: "Modified 2026-10-09 by Model Sunset Desk: the API-key check no longer hard-codes
    gpt-3.5-turbo (uses its replacement with reasoning_effort none); original © Themeisle, GPL-2.0-or-later"
  The notice lines are part of `../patch.diff`, so anyone who applies the patch to Otter 3.2.7 also gets them.
- The modified files and `../patch.diff` are distributed under the same licence: GNU General Public License, version 2 or (at
  your option) any later version. The full GPL-2.0 text ships with this sample as `../LICENSE-GPL-2.0.txt` (verbatim copy of
  https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt, fetched 2026-10-09, sha256
  `edaef632cbb643e4e7a221717a6c441a4c1a7c918e6e4d56debc3d8739b233f6`).
- Source: this folder contains the complete source of every modified file (`b/`), the unmodified originals (`a/`) and the diff
  between them. `../patch.diff` was regenerated on 2026-10-09 with `cd patch-work && diff -ru a b` (after a short free-text
  preamble). Checked the same day: `patch -p1 --dry-run` applies it cleanly to a fresh copy of `a/`, and a real apply yields
  files byte-identical to `b/`.
- `../mu-plugin/otter-model-sunset.php` is a new file written for this sample against Otter's existing hooks; its header
  declares GPL-2.0-or-later.
- This is an unofficial sample. It is not affiliated with, reviewed or endorsed by Themeisle, and it was not submitted upstream.
  There is no warranty, as stated in sections 11 and 12 of the GPL.
