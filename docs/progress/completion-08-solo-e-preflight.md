# SOLO-E activation preflight and first-case guide

2026-10-25. **Preparation authorized; activation pending essential declarations and schedule approval.** This is a short execution handoff, not a replacement corpus plan. [SOLO-I is closed](completion-08-solo-i-closed.md); its historical browser-blocker wording is superseded by that closure.

Public-copy note: the reviewer identifier and local UID are omitted here. The original private report is preserved locally; this dated preflight is superseded by the subsequent activation report.

## Declarations and checks

| Item | Current evidence / next requirement |
| --- | --- |
| Reviewer | Owner supplied a stable private actor ID. No genuine judgment has been supplied. |
| Local identity | Owner said they will confirm account ownership; this is not yet the confirmation itself. Require an explicit statement that the authorized local-account user will personally submit these reviews. No identity document or credential is requested. |
| Local access | Read-only metadata inspection: the current local UID owns the project, SOLO-I artifact root, packet and ledger; inspected private directories are mode 0700, manifest/form/header are 0400, inspected files have one hard link, and inspected paths are not symlinks. Project root is 0755; the private subtree supplies the restriction. This is a POSIX metadata check, not independent authentication, an ACL audit or a backup/encryption assessment. Recheck actual execution paths at activation. |
| Language competence | Pending actual languages and reading levels. Script recognition alone does not establish a language or translation/transliteration competence. |
| Domain competence | Owner states: self-learning ML researcher, no professional sanctions-screening expertise. Do not infer additional expertise. Confirm ability to compare displayed source IDs and cite evidence for the narrow record-review task. |
| Retention | Owner requests private retention under the project policy. `docs/data-retention.md` explicitly reserves reviewer-decision rules for later steps; proposed SOLO-E rule below requires confirmation. |
| Genuine execution | Existing SOLO-I `_load_config`, `_declaration`, `_event` and `append_submission` reject genuine intake. Existing real ledger contains zero event files. No activation or first-case import has occurred. |

## Proposed bounds awaiting the owner's answer

- At most **4 hours of active human review**, split into sessions of at most **30 minutes**. Begin with **one case, at most 20 minutes**, then stop for validation/import/replay before reviewing the other 39. This is a planning allowance, not a promise all cases can be resolved. Record actual time; stop at the allowance with unfinished cases reported. Do not guess to meet a quota.
- Retain only necessary drafts, private ledger, evidence references, attribution and corrections locally until project-closure or requested-deletion review. Preserve source restrictions and attribution. Deletion or sharing requires separate authorization. No new identity documents, personal contacts or unrelated source fields are needed.
- At most **16,000,000 bytes of new SOLO-E artifacts**; no new network, dependencies or paid resources. Keep inherited normalized-input, combined-artifact, RSS, free-memory, memory-pressure and disk limits. Human scheduling does not enlarge machine execution limits. Apply a maximum 60-minute bound per supervised machine session, and stop on unhealthy guards without automatic retry.

## Authorized preparation path after the missing inputs arrive

Goal: admit actual single-reviewer development feedback without changing original evidence or treating it as independently validated ground truth.

Use a separately versioned execution module `src/watchlist/corpus_solo_execution.py`, focused tests `tests/test_corpus_solo_execution.py`, an execution policy `config/corpus-solo-execution-v1.json`, and new private artifacts under `data/eval-comparisons/completion-08-solo-e/`. Bind the existing SOLO-I packet manifest, closure receipt, owner declaration, retention and approved limits. Preserve the SOLO-I module, packet, blank ledger and v1 configuration. Reuse existing integrity, path, lock, serialization, evidence and resource primitives; do not relabel real input as fictional to get past its gate. Do not rebuild or reselect the pilot. A separate activation acknowledgment must explain that the old form's preparation-only banner describes SOLO-I, and identify the only authorized new intake path.

Expected validation: `.venv/bin/python -B -m pytest -q tests/test_corpus_solo_execution.py -p no:cacheprovider` with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, scoped Ruff lint/format, and one focused integration with the SOLO-I tests after the activation code is stable. Fictional submissions remain isolated. Verify missing declarations, excess competencies, stale evidence, unauthorized paths/actors, correction history, duplicate/conflicting submissions, interruption, resource failure, deterministic replay and unchanged SOLO-I rejection. These are **planned commands/checks, not completed results**. No full-suite rerun is planned.

Acceptance: all declarations explicit; actual paths private and owned; approved bounds enforced; pinned evidence unchanged; only the new development ledger enabled; no genuine entry until the owner's first draft passes; immutable append acknowledgment and replay agree after import. Unsupported outcomes stay unresolved. Technical validation checks consistency, not the truth of the owner's judgment.

## First-case field guide — use only after activation succeeds

Open the existing local form using the activated handoff. Use the first case in its existing order; do not choose a convenient answer or change composition. Read the question, record IDs, original names, source qualifiers and complete-evidence section. No genuine case answer is reproduced here.

| Form field | Plain-English instruction |
| --- | --- |
| Case | The specific question being inspected. Switching cases clears unsaved answers. |
| Packet manifest SHA-256 | A fingerprint of the exact evidence version. Copy the activated handoff's value; do not guess or edit it. |
| Declared owner actor ID | Use the actor ID in the approved private declaration. |
| Submission ID | Keep the generated unique ID for this response. A correction gets a new ID. |
| Time spent / UTC time | Record actual seconds spent. Leaving UTC time blank uses download time. Never use the fictional test timestamp. |
| Outcome | `supported_same`: cited evidence supports the declared same-record/identity scope. `supported_distinct`: documentary evidence supports distinction. `insufficient_evidence`: evidence or competence is insufficient. `ineligible`: outside the permitted task. No option asserts wrongdoing. |
| Target scope | `publisher_record`: what a source says belongs to its record. `cross_record_identity`: a relation between different records, requiring documentary support. `unresolved`: no supported relation established. |
| Uncertain | Say yes when unsure. A supported conclusion cannot simultaneously claim unresolved uncertainty. |
| Evidence conflict | Whether inspected evidence contradicts the proposed conclusion. Do not hide a conflict to make validation pass. |
| Relationship | Translation changes language; transliteration represents a name in another script; spelling/abbreviation/historic describe those specific relations. Choose only what your competence and citations support; otherwise `unresolved`. Source grouping alone does not establish a linguistic relation. |
| Rationale | Your own explanation of what the inspected evidence supports or fails to establish. Codex must not invent it. |
| Inspected evidence citations | Tick only evidence you actually inspected. Include the relevant witnesses, not merely every checkbox. |
| Query / reference names | For a directional claim, select two different cited names: query is the searched name, reference is its comparison target. Otherwise leave both blank. |
| Direction adequacy | Whether the evidence supports that ordered comparison for this task. Requires relevant language competence. With no selected pair, use `unresolved`. |
| Superseded submission ID / correction reason | Both blank on the first response. After an accepted import, a correction references the latest accepted response for the same case and explains the change; original events remain. |

Download before switching cases: **there is no autosave**. Download creates a draft, not a ledger entry. Return only its local filename/path; keep names and judgments out of chat where practical. After activation, Codex checks the draft against the pinned packet, owner, competence, citations, chronology and budget, imports only a valid owner-supplied response into the new ledger, and reports its event ID/head and verified replay count. If invalid, retain the draft and explain the error without manufacturing a replacement judgment. Do not proceed to the other cases until the first import is confirmed.

## Work performed in this preflight

Read `AGENTS.md`, the existing handoff, retention policy, solo proposal, relevant completion/custody requirements and existing validation/form code using `cat`, `rg` and `sed`. A small standard-library `.venv/bin/python -B` metadata inspection checked ownership/modes/link types and the empty event directory. No evidence cases, protected final answers, external sources or real responses were inspected; no tests or preparation jobs were repeated. This report is the only new file; no code, permission, policy or ledger was changed.

**5W1H:** What: prepare bounded genuine development review. Why: collect attributable feedback without fabricated independence. Who: the owner judges; Codex checks mechanics. When: after explicit declarations and guard admission. Where: the existing local form and a new private execution ledger. How: versioned authorization, pinned evidence, conservative competence checks and append-only corrections.
