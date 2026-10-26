# Runbook — restore from backup

Research prototype over fictional data. The detailed procedure, principles and anchor handling are in [docs/maintenance/restore.md](../maintenance/restore.md); this page is the short operator checklist with Step 27 measurements.

## When

- Audit verification failed and the cause is not an I/O problem ([audit runbook](audit-verification-failure.md)).
- The workspace volume was lost or corrupted.
- A rollback to a known-good generation is required.

## Checklist

1. **Stop writers** to the live workspace (API, MCP server, UI, CLI scripts). Readiness of the old workspace no longer matters.
2. **Choose a set** and verify it:
   `python -B -m watchlist.review.backup verify --backup <backup dir>` → `"ok": true`. If not, take the next older set.
3. **Dry run** (restores to a temporary directory, verifies, removes it):
   `python -B -m watchlist.review.backup restore --backup <backup dir> --dry-run --review-config config/review-v2.json`
   Record `elapsed_seconds` and `case_count`.
4. **Restore into a NEW directory** (never in place):
   `python -B -m watchlist.review.backup restore --backup <backup dir> --destination <new dir> --review-config config/review-v2.json`
   `"ok": true` and `"issues": []` are required. With `--review-config` every case's audit chain is verified through the read-only service.
5. **Measure the loss window**: run `verify-anchor` against the newest anchor kept elsewhere using the restored directory; cases or events it reports as missing are what was lost since the backup. Record them. Do not claim zero loss without this check.
6. **Activate**: start the API on `<new dir>/review` (`python -B -m watchlist.api serve --workspace <new dir>/review --config config/review-v2.json …`) and check `GET /ready` → `200`, then spot-check `GET /v2/cases` and one `…/audit/verify`.
7. Keep the old workspace untouched until the restored one has been used successfully; retire it later with the retention procedure.

## Measured drill (2026-10-26, this machine, fictional data)

Scratch workspace with 3 fictional cases (`awaiting_review`), created with `v2 init` + 3× `v2 start`, all in the session scratch directory (not the repository):

| Command | Result | Time |
| --- | --- | --- |
| `backup create` | exit 0 | 4.75 s wall (process start included) |
| `backup verify` | exit 0, `ok: true` | — |
| `backup restore --destination … --review-config …` | exit 0, `ok: true`, `case_count: 3`, `issues: []` | `elapsed_seconds` 17.06; 21.24 s wall |
| `backup restore --dry-run --review-config …` | `ok: true`, `case_count: 3` | `elapsed_seconds` 16.21 |

The restore time is dominated by the deep audit verification through the read-only review service (workflow imports and per-case checks), not by copying bytes. Loss window in this drill: none, because no writes happened after the backup; a live restore must measure it with step 5.

Not drilled in Step 27: restore of a memory store, restore across machines/OSes, restore into a container volume.
