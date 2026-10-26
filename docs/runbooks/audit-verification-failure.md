# Runbook — audit verification failure (`"ok": false`, `inconsistent`, `storage_inconsistent`)

Research prototype over fictional data. The audit chain is **limited tamper evidence** kept by the same owner on the same disk; it detects accidental damage and naive edits, not a careful owner who rewrites both records and hashes. An independent anchor (see [backup and anchors](../maintenance/restore.md)) kept on other media extends this.

## Symptoms

- `GET /v2/cases/{id}/audit/verify` or `python -B -m watchlist.review v2 verify` returns `"ok": false` with `issues`, for example:
  - `audit event 1: event hash mismatch`
  - `audit: case_created payload differs from saved record`
- A case status `inconsistent`; writes to it are refused.
- API `500 {"code": "storage_inconsistent"}` ("Saved review records are inconsistent; nothing was repaired.").
- `python -m watchlist.review.backup verify-anchor` reports issues (missing cases, shorter chain, different head).

**Exit codes:** `v2 verify` prints the result and currently exits `0` even when `"ok": false` (observed 2026-10-26). Scripts must check the JSON `ok` field. `backup verify-anchor` exits `1` on issues.

## Drill (performed 2026-10-26, fictional scratch copy)

A restored copy of a 3-case fictional workspace had one `audit_events.payload_json` value edited with the no-update trigger dropped and recreated (so the schema identity still matched). `v2 verify` on that copy returned `ok: false` with exactly the two issues above; the untouched copy returned `ok: true`. (Dropping the trigger without recreating it is caught earlier: `workspace_invalid`, "review ledger schema differs from the owned v2 schema".)

## Steps

1. **Stop writes** to the workspace (stop API/MCP/UI writers). Reads are safe.
2. **Preserve evidence**: take a backup set now (`python -m watchlist.review.backup create --workspace <ws> --destination <new dir>`); if the backup refuses, copy the stopped workspace directory as files. Record time, operator and the `issues` text.
3. **Rule out the storage layer.** A `storage_inconsistent` 500 is also what the service currently reports for *any* non-lock SQLite error, including a read-only file or a full disk (see [operations §5](../operations.md#5-failure-behaviour-tested-in-teststest_load_failurepy-and-teststest_security_hardeningpy)). Check free space and file permissions first; if that was the cause, fix it and re-run `verify` — a genuine chain problem persists, an I/O problem does not.
4. **Scope it**: verify every case (`v2 list`, then `v2 verify` per case) and, if you keep anchors, `backup verify-anchor` against the newest anchor stored elsewhere.
5. **Decide** (project owner): restore the newest backup whose verification passes, using the [restore runbook](restore-from-backup.md). A restored older generation will show cases missing relative to a newer anchor; that list is the loss window and must be recorded. Cases whose reviews were lost are re-reviewed by a human; nothing is re-created automatically.
6. Never repair rows or re-hash the chain to make verification pass. That converts tamper evidence into a forgery.

## Owner / escalation

Project owner (user) decides between restore and continued investigation. The review-service owner is informed of any `inconsistent` case that is not explained by an edit or an I/O failure.
