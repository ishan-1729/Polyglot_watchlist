# Step 08 H1-I — offline reviewer intake and development pilot handoff

2026-10-25. Authorized by the user's H1-I approval and the exact [C3 next-package specification](completion-08b-c3.md#next-executable-package--h1-i-human-review-intake-and-pilot-handoff). This is an implementation package using completed C1/C2/C3 evidence. It does not reopen acquisition or change original Step 08 requirements.

**Decision: H1-I offline implementation and preparation COMPLETE; full Step 08 remains incomplete.** The integration, supervised preparation, independent regeneration and preservation checks passed. Actual human-review execution, new acquisition, accepted release, training, Step 09 and publication remain unapproved. A handoff prepared for people is not a human judgment. The negative-stratum shortfalls below require explicit acceptance of the prepared pilot composition before execution.

## What this package implements

The private H1-I preparation binds the candidate inventory to verified C1/C2/C3 evidence and prepares a deterministic 40-case development pilot: 20 proposed-positive name cases and 20 negative hypotheses from existing unresolved duplicate pairs. Negative and duplicate queue copies of the same pair count as one case. Uncertain/flagged evidence is retained for review, not silently cleared. Reviewer-facing exports are neutral; the sampling category and selection audit remain coordinator material. Nothing is selected by model performance or drawn from protected final material.

The new versioned intake mechanics preserve independent initial responses, identity/access attribution, evidence references, uncertainty, timing and adjudication. Corrections append new linked events; they do not rewrite old answers or become a new independent first pass. A corrected review invalidates an adjudication based on its superseded version. The current genuine-execution gate stays closed; only isolated fictional submissions exercise the state machine.

## Files and functions

| File | Purpose |
| --- | --- |
| [corpus_human_review.py](../../src/watchlist/corpus_human_review.py) | New H1-I implementation. `Pilot` (106) holds an admitted immutable preparation; `_stratum` (135) requires separate pure-script case witnesses; `build_pilot` (182) commits the source inventory and selects cases deterministically with traceable diversity/family-reuse diagnostics. `_neutral` and `_html_export` preserve source evidence while hiding proposed answers and escaping untrusted text. |
| Same module: preparation and validation | `_write_pilot` (686) writes private files without replacement and publishes the manifest last. `_load_config`, `_account`, `_configured` and `_final_inputs` bind source/config versions and budgets. `prepare_human_review` (960) and `validate_human_review` (1097) prepare and independently regenerate the artifact. `_context` (1128) provides final input rechecking to ledger/export operations after the last resource callback. |
| Same module: intake and handoff | `_declaration` (1191) validates declared principal/role/access independence; it does not authenticate humans. `create_intake_ledger` (1290), `_event` (1348), `_apply` (1464), `_graph_consistency` (1526), replay/append APIs (1552 onward) validate evidence, corrections, supersession, conflicts and externally pinned history. `export_template` (1772), `adjudicator_handoff` (1828) and `main` (1916) support private draft/handoff CLI operations; genuine submission remains denied. |
| [test_corpus_human_review.py](../../tests/test_corpus_human_review.py) | Fictional regression and cross-component fixtures for selection, neutral exports, independent actors/access, stale evidence, corrections, replay, corruption and interrupted writes. |
| [corpus-human-review-v1.json](../../config/corpus-human-review-v1.json) | Explicit C3 config/manifest pins, 24 normalized input references (51,582,461 existing bytes), seven artifact roots, preferred selection diagnostics and all actual actors/access/decisions blank. |
| [Private H1-I artifacts](../../data/eval-comparisons/completion-08b-h1-i/) | Pilot, empty intake ledger, supervisor/worker receipts, test logs and preservation evidence. `run_handoff.py` prepares/validates and replays the empty ledger; `execute_supervised.py` permits one serial run with unchanged resource guards and no automatic retry. |
| [Reviewer onboarding guide](../../data/eval-comparisons/completion-08b-h1-i/REVIEWER-START.md) | Practical owner appointment record, reviewer questions, independent return procedure, adjudicator responsibilities and correction rules. Prepared locally; not issued to reviewers. |
| [data-card.md](../data-card.md) | Append-only H1-I progress/limitations addendum. Existing historical sections remain intact. |

No dependencies, source snapshots, original models, prior review stores, historical progress reports or C1/C2/C3 implementation files are changed. Before work, 124 protected input/history files were pinned, including C3 evidence. This is a local package; no Git publication occurs.

## Commands and tests actually run

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_corpus_human_review.py tests/test_readiness_review.py tests/test_corpus_adjudication.py -p no:cacheprovider
.tools/qa/bin/python -I -B -m ruff check --isolated --target-version py314 src/watchlist/corpus_human_review.py tests/test_corpus_human_review.py data/eval-comparisons/completion-08b-h1-i/run_handoff.py data/eval-comparisons/completion-08b-h1-i/execute_supervised.py
.tools/qa/bin/python -I -B -m ruff format --check --isolated --target-version py314 src/watchlist/corpus_human_review.py tests/test_corpus_human_review.py data/eval-comparisons/completion-08b-h1-i/run_handoff.py data/eval-comparisons/completion-08b-h1-i/execute_supervised.py
node --check data/eval-comparisons/completion-08b-h1-i/form-script.js
node data/eval-comparisons/completion-08b-h1-i/check_form.cjs
.venv/bin/python -B data/eval-comparisons/completion-08b-h1-i/execute_supervised.py
```

The single [C2/C3/H1 integration](../../data/eval-comparisons/completion-08b-h1-i/integration-tests.log) passed **311 tests in 15.57 seconds**: 94 H1-I, 105 C2 and 112 C3 cases. Final scoped [Ruff lint](../../data/eval-comparisons/completion-08b-h1-i/ruff-check.log) and [format](../../data/eval-comparisons/completion-08b-h1-i/ruff-format.log) passed. The unchanged full 2,606-test suite, dependency checks and prior secret scan were not repeated.

Focused development runs included [48 passed / 44 deselected](../../data/eval-comparisons/completion-08b-h1-i/pytest-h1-focused-regressions.log) and [2 CLI regressions passed / 92 deselected](../../data/eval-comparisons/completion-08b-h1-i/pytest-h1-cli-regressions-rerun.log). These overlap the 311 integration cases. Early fixture/API assumptions were corrected to the actual contracts, including conservative UNKNOWN script handling and immutable mode 0400 output; no protection or assertion was weakened to permit an implementation defect.

The [fictional form smoke check](../../data/eval-comparisons/completion-08b-h1-i/form-check.log) exercised the exact constant JavaScript using Node's built-in VM and a small DOM stub: blank decisions, text-only evidence rendering, citation/direction validation, parseable JSON drafts, generated IDs, case switching and retention of owner fields. It made no network request or ledger write. This is a functional JavaScript check, **not a claim of a browser rendering/end-to-end UI test**. The checked script SHA-256 is `75c3ac94c7aab47b8b1ec21a6302cd3a8dc91d30d942cee1c5fcb574e3b6aa4f`.

Resolved in-scope issues: the initial script selector compared title-case strings with the shared classifier's uppercase output; it now uses correct script values and requires separate pure-script witnesses rather than mixed-script unions. Initial forms could retain an old answer on a case change; decision fields/citations now reset. A final resource callback could change pinned upstream C3 evidence just before empty-ledger publication; the regression reproduced this and the final input-check closure now prevents publication. Baseline C3 identity/distinction constraints also remain enforced when checking fictional H1 adjudication paths. The successful CLI tests cover both template and adjudicator output after that closure change.

Fictional workflow example: A and B submit independent opinions; the adjudicator cites those exact two submission IDs. If A corrects a response, the original remains, first-pass agreement is preserved, and the old adjudication becomes inactive. A new adjudication must cite the current pair and explicitly supersede its predecessor. At every stage `accepted_labels` remains zero; nothing is merged into the real corpus.

## Selection and acceptance evidence

The single [supervised run](../../data/eval-comparisons/completion-08b-h1-i/supervision.json) exited successfully in **41.53 seconds**, with sampled aggregate peak RSS **394,067,968 bytes**. The [worker receipt](../../data/eval-comparisons/completion-08b-h1-i/worker-outcome.json) records successful preparation, independent regeneration and empty-ledger replay. All 40 cases remain unreviewed: zero submissions, corrections, adjudications, accepted labels or identity merges. No network transactions occurred.

The prepared pilot has **40 distinct cases: 20 positive proposals and 20 negative hypotheses**, representing 60 distinct observations and 570 distinct original name-evidence entries. Its 40 conservative review-family units have zero reuse; these are grouping safeguards, not independently confirmed identities. Twenty-four cases include flagged evidence and graph-quarantined observations. Neither those cases nor the other cases have been cleared for corpus use.

| Selected stratum | Positive proposals | Negative hypotheses | Preferred per category |
| --- | ---: | ---: | ---: |
| Latin–Arabic organizations | 4 | 3 | 4 |
| Latin–Cyrillic organizations | 8 | 2 | 8 |
| Latin–Han organizations | 2 | 0 | 2 |
| Other organizations | 4 | 13 | 4 |
| Vessels | 2 | 2 | 2 |
| Total | 20 | 20 | 20 |

The positive profile is met. Negative shortages are **1 Arabic, 6 Cyrillic and 2 Han cases** relative to the preferred profile. Nine explicit fills within the negative category increased other-organization cases from 4 to 13. This keeps the 20/20 pilot size; it does **not** satisfy the missing script strata or establish verified negative labels. The owner must accept this exact development-pilot composition or authorize a specific revision before H1-E. Full Step 08 multilingual requirements remain unchanged.

Source case marginals are EU **29**, OFAC **14** and OpenSanctions UN **11**, all meeting the minimum of two. They sum to 54 because a cross-source case contributes to both source marginals; there are still only 40 cases. Script diagnostics do not establish language or reviewer competence.

Private handoff artifacts: [Reviewer A form](../../data/eval-comparisons/completion-08b-h1-i/pilot/reviewer-a.html), [Reviewer B form](../../data/eval-comparisons/completion-08b-h1-i/pilot/reviewer-b.html), [onboarding guide](../../data/eval-comparisons/completion-08b-h1-i/REVIEWER-START.md), [summary](../../data/eval-comparisons/completion-08b-h1-i/pilot/summary.json), and [coordinator-only selection audit](../../data/eval-comparisons/completion-08b-h1-i/pilot/pilot-audit.json). These have not been issued to reviewers. The audit and proposed sampling categories must stay out of independent first-review handoffs.

Immutable commitments:

- Pilot manifest file SHA-256: `2f235e847e1e6b49db280f44ebe95d5f0a7783dc680babf786e741fd48cea16d`.
- Candidate inventory logical commitment: `bee5358d7d24d0adca9d14231f835cc2b1b19d76bf816a494737815625a6e78b`.
- Empty ledger header / externally pinned genesis head: `1735d40127cc13a383f7833f1f1a803ff7588981ee5137b562f74ca551b94dbf`.

The pilot and ledger occupy **1,470,823 bytes**. During preparation the normalized-input reservation was **53,413,657 / 100,000,000 bytes**, and the combined-artifact reservation was **76,568,139 / 2,147,483,648 bytes**. Host free memory was 50% at admission and 49% at the final check, with no pressure warning; free disk was 35,673,092,096 then 35,671,502,848 bytes. The unchanged RSS, host-memory, disk and duration safeguards passed. These sampled observations do not claim continuous measurement between samples.

[Preservation verification](../../data/eval-comparisons/completion-08b-h1-i/preservation-check.json) checked **124 protected historical/input files and 13 executed code/configuration files**, with zero mismatches. No restoration was necessary. The [completion record](../../data/eval-comparisons/completion-08b-h1-i/completion.json) binds final code, documentation, test logs and receipts and records the exact final H1-I artifact size against its 16,000,000-byte ceiling.

| H1-I acceptance criterion | Result / evidence |
| --- | --- |
| Deterministic, versioned 40-case development handoff | Passed: independent regeneration, committed inventory and manifest; 20/20 composition and explicit stratum shortfalls. |
| Original names, evidence ancestry and uncertainty preserved | Passed: admitted C1/C2/C3 evidence, 570 original name entries, quarantine retained; no merge or fabricated label. |
| Neutral independent-review preparation | Passed for offline artifacts: separate blank exports, no proposed answers/model scores; actual identity verification and isolated access remain S1/H1-E prerequisites. |
| Evidence versions, actor separation, conflicts and correction history | Passed in fictional tests: 311 cross-component cases, including 94 new H1 cases. Genuine intake remains hard-disabled. |
| Safe writes, corruption/interruption rejection and replay | Passed in focused/integration tests and real empty-ledger replay; no prior artifact replaced. |
| Resource limits and preservation | Passed: one serial preparation, zero network, unchanged 124 protected and 13 executed pins. |
| Actual reviews, protected final custody and accepted corpus | Not delivered by H1-I; separately authorized human/corpus gates remain mandatory. |

No known reproducible in-scope defect remains from these checks. Tests are not proof of all possible defects. Actual browser rendering was not tested, and self-entered identity/access declarations plus local file modes are not production authentication or separate human custody. Activating genuine intake must bind externally verified access before accepting any real answer.

The actual corpus baseline remains 12,090 organization observations, 1,568 vessels, 40,568 name entries, 1,259 unreviewed equality pairs, 657 equality components and 2,864 C1-flagged observations. C3's separate graph quarantine includes 1,638 observations. All are development-exposed; none is automatically an accepted independent family or fresh final example. H1-I prepares work for reviewers rather than changing these facts.

## Appointments and the least administrative setup

Use the [onboarding guide](../../data/eval-comparisons/completion-08b-h1-i/REVIEWER-START.md). Maintain one owner-controlled roster with verified person/principal reference, actor ID, role, language/domain competence, conflicts, assigned case scope, access route, retention and availability. Keep identity documents and credentials outside this chat. Blank machine-readable declarations are templates, not proof that a person was verified.

| Role | Must be independent from | May overlap with |
| --- | --- | --- |
| Reviewer A and Reviewer B | Each other as human principals; each other's first answers | Other development duties only if competence, independent answering and declared conflicts permit. A developer's review cannot establish independent protected-final review. |
| Adjudicator | Both first reviewers on the same case | Custodian/evaluator, if explicitly approved, competent, conflict-free and not a developer/model tuner. |
| Final custodian/evaluator | Development/model tuning and unrestricted agent access | Custodian and evaluator are explicitly one possible combined role; adjudication overlap is conditional as above. |
| Owner/coordinator | Cannot impersonate reviewers or invent access verification | Curator and intake coordinator. Serving as one development reviewer requires the actual reviewer conditions and leaves a distinct second reviewer and adjudicator necessary. |

Thus **three suitably qualified non-developer people can cover the two first reviews plus adjudicator/custodian/evaluator in principle**. This is a staffing option, not proof those people or their competencies are available. Protected-case reviewers must also avoid model-tuning and disclosure. Separately administered protected storage, access evidence and a no-feedback protocol remain required; another local folder or mode 0700 is not custody.

Before execution, the owner must confirm people and relevant competencies, population/type scope, the exact pilot version and shortfalls, permitted evidence and transfer route, retention, time/payment budget and authenticated access. No hiring, spending, contact, transfer or genuine submission has occurred under H1-I.

## Shortest permitted path through the remaining data requirements

### Independent absent-query families: use the existing pool first

1. Execute the separately authorized development pilot and measure evidence sufficiency, disagreement and review time. Expand genuine review only after the protocol/people can support it; retain at least 200 positive-candidate and 200 negative-candidate distinct reviews, with every used hard negative adjudicated.
2. Resolve or quarantine cross-source identity/dependence relationships and assess eligibility for each counted family. Use existing permitted observations first. Approximately 7,000 eligible independent organization families would require **57.90% usable-independent yield from 12,090 organization observations**; that yield is unmeasured. Vessels remain a separate type and cannot silently fill organization shortages. The 400-case review minimum does not certify all 7,000 families.
3. Under an approved cohort-construction package, select approximately 5,000 reference families and 2,000 disjoint controlled-absence families before examining model performance. Single-name families may contribute to absence even if they cannot supply a held-alias positive. Preserve all natural name evidence and independent identity support.
4. Freeze one explicit complete reference universe. C3 checks that every equivalent/dependent copy, alias and declared descendant of absent targets is excluded. Resolve name collisions and ambiguous target sets; retain uncertainty rather than fabricate a negative. Controlled absence means **absent from that reference view**, not absent from every sanctions list or evidence of innocence/wrongdoing.
5. Measure actual independent yield before requesting more acquisition. Do not acquire 2,000 Wikidata rows merely to call them absent. C4 applies actual eligible decisions to cohorts; C5 authorizes an accepted immutable release. Step 09 remains later and separate.

### Latin–Han: separate supplemental learning from fresh sanctions evaluation

Existing planning measured 27 source-local Han candidates (20 outside equality components); all are development-exposed. They can support reviewed development learning but do not reduce the fresh-final shortage to 73. The original **at least 100 independent final positive groups per claimed direction** remains unmet in full. A family counts in both directions only if both directions are independently supported.

The shortest evidenced supplemental route is a finite Wikidata Action API package using the [saved official metadata findings](completion-08b-01.md). `wbgetentities`/`wbsearchentities` and structured-data CC0 were verified as metadata; no entity/search acquisition occurred. Reuse that work, not another broad infrastructure audit. Before any live request, approve finite curator-reviewed QIDs/search strings, permitted fields, revision/completeness/rank/redirect contracts, direct organization typing and complete human exclusion, polite user-agent, storage and limits. The saved proposal contemplates an at-most-20-QID smoke stage before a separately accepted pilot capped at 200 retained organizations, 500 examined candidates, 800 type nodes/depth 20, 250 transactions, 15 MB received and 30 minutes. **These are dormant proposals, not current allowances or measured yield.** A verified seed list and exact request package are still missing; no request is executable under H1-I authorization.

In parallel, appoint the final custodian before obtaining fresh sanctions-domain material. They must privately screen against all development exposure. Supplemental general organizations cannot replace the sanctions-domain population. Neither a new alias nor a new snapshot makes an exposed family fresh. Under a strict 15% final allocation, 100 eligible fresh final families would imply at least 667 pre-exclusion eligible families per direction; a later explicitly approved stratified allocation may reserve 100 directly. These are arithmetic scenarios, not an approved partition change or acquisition yield.

A useful refinement from already saved [OFAC official metadata](../../data/eval-comparisons/completion-08b-01/metadata/batch-01/metadata-06.body): the historical listing advertises enhanced SDN ZIP **6,793,008 bytes** / XML **109,924,494 bytes**, and advanced ZIP **5,737,099** / XML **127,668,232**, with schema paths. Thus historical availability and advertised sizes have local evidence. Native-script fields, actual Han yield, current fetch contract and fresh-family yield remain unverified. Both exceed the old OFAC 4 MB received / 32 MB decoded envelope; no silent reuse of those limits or permissions is allowed. Enriching the same old families would not produce fresh final cases. This supplements, rather than rewrites, earlier planning reports.

Direct UN remains permission-blocked. REST, WDQS retries, GLEIF, ROR or broader OpenSanctions distributions are not authorized substitutes. Choose one exact permitted source package, verify its intended use and require explicit bounded approval before acquiring anything. If legal, independent sanctions-domain coverage cannot be obtained, the requirement remains unfinished until the owner explicitly approves a scope revision; it cannot be hidden behind a general-organization benchmark.

## Next executable gate

**H1-E — verified development pilot activation and human execution, proposed only.** After H1-I acceptance and S1 appointments/access evidence, approve the exact pilot commitment, population and selection shortfalls; bind the owner-authorized principals, competencies, retention and approved return channels; authorize the narrowly versioned genuine-intake activation and run the 40-case pilot. Do not modify the historical blank H1-I artifact or relabel real input as fictional. Record actual human submissions and adjudications in a new authorized ledger, then measure first-pass agreement, uncertainty, exclusion and time. Code changes for activation/access must receive focused tests and a new pinned execution policy before any real submission. All hard negatives used later require adjudication and family eligibility. Neither H1-E nor its appointments authorize new acquisition, an accepted release, training or Step 09.

**Exact proposed implementation scope:** narrowly extend `src/watchlist/corpus_human_review.py` and `tests/test_corpus_human_review.py`; create `config/corpus-human-review-v2.json`, `docs/progress/completion-08b-h1-e.md` and private `data/eval-comparisons/completion-08b-h1-e/`; append a dated data-card addendum. Keep v1 configuration, blank pilot, ledger and completion evidence immutable. Bind a new ledger to the existing pilot commitment and a separately verified owner roster/access policy. No shared C1/C2/C3 contract changes or new dependencies are proposed. Actual identity documents, credentials and human submissions stay in approved private storage, outside configuration files and chat.

**Dependencies and commands:** the owner first supplies the S1 role/access decisions and explicitly approves the exact 40-case composition. Use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_corpus_human_review.py -p no:cacheprovider` for changed intake/access behavior, scoped Ruff, and one C2/C3/H1 integration at final connection if activation affects those contracts. Verify genuine-mode denial without approved policy, principal/channel binding, reviewer separation, current evidence/head checks, conflicts/corrections and interrupted writes using fictional fixtures. Final CLI invocation details depend on the approved access route; document them before accepting real submissions. A typed actor ID or a copied receipt string must never substitute for the external access check.

**Proposed limits and acceptance:** zero source acquisition/network/API/paid services/new dependencies under the local implementation; at most 16,000,000 new artifact bytes and one serial supervised activation/validation run of at most 60 minutes, with inherited 100,000,000-byte normalized-input, 2 GiB combined-artifact, RSS 1.5/2 GiB, free-memory 25%/20%, no-pressure-warning and 10 GiB disk safeguards. These are proposed limits requiring H1-E approval, not a new allowance. Human work duration, payment (if any), permitted data transfer and individual access must be separately agreed in S1; the machine-run deadline is not a reviewer time budget. Accept only attributable independent real responses; retain insufficient evidence and unresolved disagreements; report actual counts and time without guaranteeing 40 usable labels. No accepted cohort/release follows automatically.

Source supplementation and protected custody are separate gates that can be arranged concurrently. The next immediate human action is to name the two reviewers, separate adjudicator and custodian arrangement and verify competencies/access. The next project action after their pilot is measured review expansion and actual cohort construction, not another broad planning cycle.

## Beginner-friendly 5W1H

- **What:** blank review handoffs, a small development pilot and a traceable intake mechanism.
- **Why:** collect reliable independent human judgments before treating names or pairs as ML labels.
- **When:** after C1–C3, before actual review execution, accepted corpus construction or training.
- **Where:** private local development artifacts; future final-test material belongs in separate custody.
- **Who:** Codex builds/tests mechanics; the owner verifies appointments/access; humans review/adjudicate; the custodian protects independent final evidence.
- **How:** deterministic selection, neutral evidence, separate first reviews, version-bound submissions, append-only corrections and unchanged resource guards.
