# Preserving and restoring the v1 research baseline

This guide covers the approved completion-plan **Step 00**. It preserves the
established research prototype before application source fixes. It does not
migrate cases, resume a graph, retrain a model, initialize Git, or publish data.

## What is being protected

The private archive contains the original application, tests, configuration,
dependency lock, proposal and historical documentation; public-source acquisition
receipts and local source exports; source/sample databases; evaluation inputs and
results; both complete downloaded model directories; every embedding-cache pair;
and the complete existing review directory. It also preserves regular files and
link metadata from the installed virtual environment and its Python framework.

The original databases are never opened with SQLite by the preservation utility.
It copies their main files and every present `-wal`, `-shm` and `-journal` file
under the existing application lock. A WAL is SQLite's write-ahead log: committed
rows may still live there before being folded into the main database. Omitting it
can lose committed work. A rollback journal serves a different recovery role and
also must be captured.

Raw copies are retained byte-for-byte. SQLite recovery happens only on further
disposable copies; SQLite's backup API then produces separate consolidated
databases. Those consolidated copies may have different bytes from the raw files
while representing the same committed records. The verifier checks database
integrity, foreign keys, schema, case/packet/submission relationships, the audit
hash chain, checkpoints and saved fictional-demo transcripts.

The saved assistant-created annotation is identified as `simulated_demo` in the
private preservation manifest. Existing case headers, reviewer labels, audit
rows and saved JSON are never rewritten. A local username is not authentication
of a human reviewer; this prototype assists research and human review and makes
no finding about identity or wrongdoing.

## Preconditions and scope

Use the established Python environment on this Mac. `lsof` must be available.
No download, installation, API key or network connection is required. The tool
uses the Python standard library; the optional smoke check imports packages
already present in the restored environment.

Stop review CLIs, source-database tools and background jobs before capture, and
keep them stopped until it finishes. The utility acquires the existing lock
without creation, truncation or chmod and checks open descriptors with `lsof`.
It rejects other readers as well as writers. This supports operational quiescence;
it is not protection against a hostile process deliberately racing filesystem
operations. In particular, the old application changes permissions before taking
its lock. Do not launch it during capture.

The source, workspace and output paths must have no symlink components. Project
symlinks, multiply linked project files, special files, unknown SQLite sidecars,
missing established stores and existing destinations are rejected. Runtime links
are captured as inert metadata, then recreated only within the explicit runtime
restore contract. Archive and restore roots are private directories.

Free space is checked before capture and extraction. The estimate reserves both
an archive and a restore, database working copies, and overhead. A failed run can
leave a private partial directory for diagnosis. It must have no valid
`COMPLETE.json` and cannot pass verification. Never reuse or overwrite that path;
review the failure before choosing a fresh destination.

## Commands

Run from the project directory. These are explicit operations, not automatic
scheduling instructions. Each new phase still needs its own approval.

```sh
.venv/bin/python -B scripts/preserve_v1.py --workspace data/review --output data/review-archives/v1 --dry-run
.venv/bin/python -B scripts/preserve_v1.py --workspace data/review --output data/review-archives/v1 --apply
.venv/bin/python -B scripts/preserve_v1.py --output data/review-archives/v1 --verify
.venv/bin/python -B scripts/preserve_v1.py --output data/review-archives/v1 --restore --restore-to data/review-archives/v1-restore-drill --smoke
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests/test_preserve_v1.py
```

`--dry-run` creates no directories or files and changes no permissions. It checks
membership, lock availability, open-file users and space. It does not prove the
case evidence is coherent; that requires staged SQLite verification during
`--apply`. Reading files may update access times, so unchanged access time is
not promised. Byte content, modes, identities and relevant source modification
metadata are checked during capture.

`--apply` exclusively creates its output directory, writes and fsyncs private
payloads and receipts, verifies originals again, and publishes its completion
receipt last. This is publication of a valid completed archive; the directory
itself can exist while capture is incomplete. No overwrite rename is used.

`--verify` requires the completion receipt, verifies its manifest/receipt hashes,
checks exact file membership, rejects symlinks/hardlinks or permissive archive
permissions, and repeats logical verification on disposable database copies.

`--restore` requires a fresh destination. It restores original project bytes and
recorded modes inside a private parent, recreates validated runtime links,
re-derives database backups from the restored raw database/journal sets, compares
logical receipts, and verifies the archive again. Successful extraction ends
with `RESTORE-COMPLETE.json`. Do not point the command at the live project.

`--without-runtime` exists for isolated fictional test fixtures. It is not the
full recovery baseline used for this project.

## Archive layout and privacy

```text
v1/
  payload/project/          Original selected project files
  payload/environment/      Installed .venv regular files
  payload/python-framework/ Python framework regular files
  databases/                Consolidated derivative SQLite copies
  manifest.json             Private inventory, link/mode metadata and attribution
  verification.json         Private logical evidence receipts
  COMPLETE.json             Manifest and verification digests, written last
```

All archive directories use mode `0700` and regular files use `0600`. Original
modes are recorded in the manifest; they are not applied to the archive payload.
The restored tree contains `project/`, `project/.venv/`, `python-framework/` and
`databases/`. Original nested project/runtime modes are restored below its private
root; implicit container directories remain private.
The backup and restore locations are excluded by `data/review-archives/` in
`.gitignore`. This is not encryption: filesystem access by the owner or a
privileged process can still expose the contents.

The public `docs/releases/v1-manifest.json` is an allowlisted summary. It contains
source/configuration/dependency hashes, aggregate counts, recorded model/source
descriptors and verification outcomes. Review identifiers, usernames, notes,
queries, aliases, raw records, split assignments and absolute local paths belong
only in private evidence. Do not publish the full archive or copy its raw receipt
contents into documentation.

Caches such as `__pycache__`, pytest caches, `.DS_Store`, `.pyc` and `.pyo` files
are excluded. Unlisted root files (including `.env` and unrelated secrets) are
not captured. The archive output itself is excluded. The final Step 00 report
and public summary manifest are generated after capture and are excluded to
avoid self-reference. Existing historical reports remain included. This is a
reviewed allowlist, not a general secret detector: future source/configuration
changes still require inspection before sharing anything.

## What the runtime check proves

The v1 runtime contract is the established macOS CPython 3.14 framework. The
smoke check invokes the restored virtual-environment Python entry point with
`-B -I -S`: no bytecode writes, isolated import handling, and no site startup or
editable `.pth` processing. Only restored application source and site-packages
are explicitly added. It checks application and dependency import locations and
installed distribution metadata; it performs no inference, training or case
execution. Offline library settings and Python audit checks block network/model/
database access in this check. Imports can write only to a separate private
temporary scratch directory, which is removed afterward. These checks are not a
general sandbox for arbitrary native code.

This is **same-host recovery**, not a portable offline installer. The preserved
virtual environment retains absolute interpreter/console-script references, and
native binaries depend on the original Python framework and macOS libraries.
Framework bytes are preserved and verified after extraction, but execution of an
independently relocated framework is not claimed. Use the documented isolated
interpreter check, not old console scripts whose shebangs may point to the live
project. The project has no established complete offline wheelhouse. A package
list or `uv.lock` alone does not prove offline rebuilding on another machine.

The installed Tcl and Tk frameworks each contain an existing `PrivateHeaders`
link whose target is absent. These two links are preserved exactly and marked as
having missing targets. They are not silently repaired or presented as complete
development headers. Runtime link resolution is checked against the captured
tree, including links through `Versions/Current`, with bounded traversal and no
escape from the declared runtime roots.

Model receipt hashes are checked against preserved/restored file inventory; this
proves model asset availability, not successful inference. Licensing descriptors
are historical records, not fresh legal validation. The local E5 receipt/card
declare MIT but a standalone license/notice file was not present; no missing
license evidence is invented or downloaded during Step 00.

Local SHA-256 receipts detect accidental damage or changes relative to the saved
manifest. Someone able to replace both data and manifests could rewrite those
receipts; they are not independent trusted signatures or immutable audit anchors.
The archive and restore on one disk also do not protect against loss of that
disk. An off-device copy requires a separately approved destination and privacy/
licensing review.

## Completion and the next boundary

The actual commands, test counts, capture digests, restored runtime result and
remaining limitations are recorded in `docs/progress/completion-00.md`. Do not
claim completion from this guide alone. Step 01 will add a read-only archive
reader that separates historical inspection from strict workflow execution.
That is a separate phase; application defects and source-hash compatibility must
not be repaired as an incidental part of this preservation step. Git
initialization, staging, commits and pushes were not included in Step 00 approval.
