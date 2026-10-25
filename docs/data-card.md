# Data card — current research and regression datasets

Updated during approved Completion Step 06, 2026-10-24. This card describes locally preserved data and the repaired evaluation contracts through Completion Step 05. It does not certify current external terms. No new source, online permission check, private personal data, or individual scraping is part of this documentation work.

## Intended use and dataset status

The prototype suggests possible reference-record matches for human research review. A provider's name/alias association is an assertion in that source, not independently verified identity ground truth. Presence on a source record does not establish that a queried person is that record or committed wrongdoing.

| Dataset | Recorded contents | Permitted interpretation of existing evidence |
| --- | --- | --- |
| Packaged fictional baseline | 12 invented entities and 24 aliases, including deliberate shared names; Latin, Arabic and Cyrillic examples. | Known software/regression fixture; coincidental resemblance to real names is possible. |
| Authored bilingual fixture | 10 invented entities with English/Arabic translation or transliteration pairs. | Visible author-created associations, not independently blinded labels or general cross-language accuracy evidence. |
| Historical public selection | 20 non-person `LegalEntity` records and 79 searchable names from one saved OpenSanctions UN export. | Narrow provider-derived regression subset, not a representative population or current sanctions-list service. |
| Test fixtures | Authored small JSON records, synthetic stores and mocked acquisition responses. | Deterministic validation/error cases; no live service is needed. |

All three evaluation datasets have been exposed through development, reports, and inspection. Their old `test` labels do not make them fresh confirmation data. Rebuilding them under `evaluation-v2` changes the contract, not their exposure history. Completion Step 05 audited 94 fictional, 272 public-small, and 64 multilingual current query rows; these are correlated derived queries, not independent entity counts. Fresh corpus permissions, adjudication, duplicate review, and group-disjoint releases remain Completion Steps 07–09.

## Source terms: recorded evidence versus current permission

The saved source is the [OpenSanctions UN Security Council dataset](https://www.opensanctions.org/datasets/un_sc_sanctions/), a standardized provider distribution of upstream United Nations Security Council information. OpenSanctions is not the authority issuing UN sanctions. OFAC and EU sources have different mandates and were not separately acquired in the completed work.

At the historical acquisition, the project recorded OpenSanctions' [noncommercial-use guidance](https://www.opensanctions.org/docs/commercial/exemption/) and the distribution's [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/legalcode.en) terms as the basis for the approved local student/personal research use. This is a description of the saved acquisition record, **not a new verification that those terms or an exemption still apply**. A public download URL is not unrestricted-use permission. Provider distribution terms do not establish the rights for every upstream source, purpose, derivative, or deployment.

The recorded attribution is:

> OpenSanctions, UN Security Council Consolidated Sanctions; upstream publisher: United Nations Security Council. CC BY-NC 4.0 as recorded at acquisition. Filtered and converted for noncommercial research. No endorsement; supplied without warranties.

Retain provider/source/license links, supplied notices, acquisition receipts, and an indication of modifications with any separately permitted reuse. Recorded modifications include schema filtering, a 20-record selection, normalization, and SQLite conversion. Original data remain local. New acquisition, redistribution, commercial use, hosted demonstrations using public data, or changed purposes need a current permission decision. The [access ledger](access-and-resource-ledger.md) assigns that review to the data steward/project owner before Step 07; Step 06 does not perform the required network check or make a legal conclusion.

## Historical snapshot and provenance

The saved [FollowTheMoney JSON export](https://www.opensanctions.org/docs/bulk/json/) contains one object per line. The full export includes record types beyond the selected non-person targets. The historical authorization covered a UN-only export capped at 10 MiB plus metadata capped at 1 MiB, not the combined OpenSanctions collection. It is not an ongoing download authorization.

| Recorded field | Saved acquisition value |
| --- | --- |
| Export bytes | 3,026,171 |
| Metadata bytes | 6,523 |
| Retrieval, UTC | `2026-10-20T20:15:30.258602+00:00` |
| Provider version | `20261020200104-otg` |
| Provider `last_change` | `2026-10-15T20:01:05` |
| Provider `last_export` | `2026-10-20T20:01:04` |
| Raw SHA-256 | `8def6a063c47a2ff0c02c1c5a4c33b73146432339d51eca7af025e8c795a9bac` |
| Metadata SHA-256 | `a8e20e7edcca703371f14bd663e906352ac2ec2d44ccc28e9820e26f32f77edb` |

These are historical receipt values, not a claim that a current `latest` endpoint returns the same bytes. Provider timestamps without a timezone are preserved without inventing one. Retrieval time differs from source-update time. Reproduction uses saved bytes, receipts, metadata, selection policy and parser version. A digest detects differences against trusted saved evidence; it is not an independent guarantee of truth or authenticity when all evidence can be replaced together.

## Selection, names, and duplicates

The historical parser reported 2,918 input records, 269 eligible non-person targets, 20 selected in ascending provider-ID order, and 79 stored/searchable names. All selected records use the broad source type `LegalEntity`, retained as `legal_entity`; they are not relabeled as companies. An ID-sorted 20-record selection is biased and too small for operational-performance claims. Inventory of unselected records is not permission to expand the corpus.

Original name/alias/weakAlias values were round-tripped in the historical preservation audit. That checked storage fidelity, not real-world identity or legal status. Exact repeated values within an ID/property are deduplicated. Different original strings that normalize alike remain evidence; similarity alone never merges provider IDs. Conflicting repeated-ID metadata fails import. Unsupported structures fail explicitly rather than inventing missing values. Unsearchable/weak aliases retain exclusion reasons and are not used for retrieval.

Groups follow explicit provider IDs/referents, including links through unselected records. Every alias remains with its entity group. Same-name records without provider links remain distinct. The provider's grouping is not independently verified identity. Unknown duplicates and cross-source overlap remain unresolved until a reviewed corpus release addresses them.

## Partitions, labels and leakage controls

A **partition** describes how an example may be used: `train`, `development`, `calibration_fit`, `threshold_selection`, or `test`. **Presence** describes whether a target is in the fixed reference corpus. **Ambiguity** describes whether the target label is unambiguous, ambiguous, or unlabelable. These are separate facts. Neither `absent` nor `ambiguity` is a current partition name.

The preserved public split has 7 train, 3 development, 2 calibration-fit, 2 threshold-selection, and 6 test entities. No training or calibration was performed on these roles. Historical comparisons have already exposed their selected evaluation examples. New current-contract comparison factories map old `ambiguity` groups explicitly to development diagnostics and old fictional absence declarations to development. They do not silently place these examples in a fresh test partition. Exact legacy rows remain available only through the explicit regression adapter.

Completion Step 05 binds each generated/authored query to its original alias, transformation, source, group, partition and reference view before retrieval. It audits absent queries too. Held-out alias text is removed from searchable aliases and from current display-name metadata when necessary. Retrievers receive query text and the selected retained view; evaluators use labels only after candidates return. Public assignment groups must agree with stored source groups.

Script evidence uses a conservative Unicode-name/category approximation for Latin, Arabic, Cyrillic and Han, with explicit unknowns. It is not language detection or a full Unicode Script_Extensions implementation. A cross-script claim requires nonempty, known, disjoint script sets between query text and the target's retained aliases. Mixed or unknown text cannot acquire a cross-script label merely because coarse strings differ.

## Storage, reuse and release boundaries

| Local path | Role |
| --- | --- |
| `data/raw/un_sc_sanctions/entities.ftm.json`, `index.json` | Preserved downloaded bytes and metadata. |
| `data/manifests/source.json`, `ingestion-report.json`, `splits.json` | Historical receipt, selection diagnostics and group assignments. |
| `data/samples/un-organisations.ftm.json` | Selected original content reserialized as JSON, not byte-identical export lines. |
| `data/watchlist.sqlite`, `data/sample.sqlite` | Preserved historical v2 sources; normal loading rejects them. |
| `data/source-v3/watchlist.sqlite`, `sample.sqlite` | Explicit independently rebuilt v3 snapshots for new local source-backed work. |
| `data/eval-comparisons/` | New isolated regression outputs; not a source or license grant. |

The v3 loader recognizes the full owned schema and verifies a logical-content manifest before serving evidence. Reimport checks preserved content rather than accepting a snapshot ID alone. Rebuilding v2 requires independent saved source evidence and a new destination; it does not bless arbitrary edited rows. See [source migration](maintenance/source-database-migration.md) and [Completion Step 03](progress/completion-03.md).

Raw/public data, model files, caches, local review notes, and preservation archives do not belong in distributable packages or public demonstration inputs. The dependency/license inventory covers code packages separately; it cannot authorize these data artifacts. Any external transfer needs the relevant current terms, scope and explicit approval.

## 5W1H recap

- **What:** fictional fixtures and one historical, limited provider-derived source, with preserved ancestry.
- **Why:** check matching and storage behavior without turning a name similarity into an identity claim.
- **When:** validate source/view/query contracts before retrieval; obtain current terms before new access or reuse.
- **Where:** local source snapshots and isolated regression outputs; original evidence remains preserved.
- **Who:** the project owner/data steward approves access and labels; a human reviews possible matches.
- **How:** keep original text/provenance, group aliases together, separate labels from partitions, audit withheld views, and report denominator limits.

## Completion Step 08B-C1 addendum — 2026-10-25

The preceding sections describe the historical Step 06 state. Three-source acquisition subsequently succeeded; [C1 completion evidence](progress/completion-08b-c1.md) now records strict offline admission and private readiness preparation from the unchanged Step 08B-2R continuation receipt.

The preparation preserves **12,090 organizations, 1,568 vessels and 40,568 complete name-evidence entries**. Source-local counts are OpenSanctions UN 269/918, OFAC 11,610/25,323 and EU 1,779/14,327 (records/names). These are source assertions, not independently established entities. The inherited grants and historical source permissions remain traceable; C1 makes no new current legal determination and grants no additional use.

There are **1,259 unreviewed equality candidate pairs** (663 exact, 596 normalized-only), forming **657 unresolved review components** involving 1,607 records. Weak-name, length and duplicate flags affect **2,864 records** in total. All 2,153 explicit weak names and 17 overlength names retain their original evidence and restrictions; valid sibling names remain. Missing language stays unknown for 27,858 entries. The 10,794 records without these flags are not accepted or cleared.

The private `data/eval-comparisons/completion-08b-c1/preparation/` manifest has SHA-256 `bb84c60fd09a4ff11fb93ddb5cb37d630c18b684cbc8d0d216ec3cabc047b195`. It binds a preparation, **not an accepted corpus release**. Validation regenerates the queues from the independently pinned continuation evidence. C1 created zero human decisions, labels, identity merges or fresh-final eligibility. Existing development exposure remains; no final-test labels or examples were created. Real review, supplementary/fresh coverage, independent absence, custody, accepted release and Step 09 remain subject to the existing plan and explicit approvals.

## Completion Step 08B-C2 addendum — 2026-10-25

[C2 completion](progress/completion-08b-c2.md) adds private, versioned blank development review packets and an empty local ledger. The four queues contain 1,259 duplicate candidates, 2,864 flagged records, 6,856 proposed-positive name pairs and 1,259 negative hypotheses: **12,238 task entries, zero human decisions**. The negative hypotheses reference the same 1,259 pairs as the duplicate queue; they are not verified negatives or additional independent reviewed cases.

Packets retain references to original C1 names, aliases, source-qualified IDs, snapshots, nomination witnesses and restrictions. The resolver validates that ancestry before returning source text. Weak/overlength aliases remain preserved; proposed-positive selection excludes their restricted evidence. Unknown language remains unknown. Real review submission is disabled and the real actor registry is empty; fictional submission/adjudication tests do not create real labels.

Packet manifest SHA-256: `64d7b9d7ff120b0363d1cfae6ccee324cb61df8a8a44d3d836e4e70fec2868a3`. Initial ledger head: `cd9b8e4f7d320d8a29368d9b8618a03fa8595b5e96532a030bdd05f4c238d7e3`. Validation/replay passed with every real case unreviewed and accepted labels, identity merges and releases all zero. No corpus coverage or final-test independence is established by these software artifacts. Actual human review, family/absence validation, multilingual supply and independent custody remain required before Step 08 closure.

## Completion Step 08B-C3 addendum — 2026-10-25

[C3 completion](progress/completion-08b-c3.md) adds deterministic offline family-graph and reference-view/absence mechanics. The supervised real preparation and independent regeneration passed with **13,658 observations, 40,568 name entries, 1,259 unresolved equality pairs and 12,238 blank review tasks**. The unchanged real ledger contains zero events/adjudications. All existing observations form a provisional development reference view; no actual absent cohort was selected.

Identity, canonical record equivalence, dependence and uncertain links have separate meanings. C2 identity adjudication is not authority to collapse canonical records. The real graph retains 13,658 provisional singleton groups and quarantines 1,638 observations for unresolved graph evidence. Evidence-specific weak/length restrictions remain separately preserved; this graph diagnostic does not replace C1's 2,864-record union of flags or certify other records as cleared. Candidate similarities and raw provider referents never establish identity.

Fictional tests demonstrate all-copy absence, descendant/cache ancestry, homonym and multi-target ambiguity checks, historical held-alias leakage, contradiction rejection and failure-safe writes. They are not actual human labels. Every actual accepted reference/absent-family count, label count, identity-merge count and final-protected count remains zero. Existing 169/1,070/27 Latin–Arabic/Cyrillic/Han source-local candidate counts are development-exposed, unreviewed and not independent final coverage.

C3 preparation manifest file SHA-256: `cc13c34381d187c7469df8828fe180459975e51f1129e56a4fc48f698ba6eda4`. It binds a **provisional dry run**, not an accepted release. All 99 protected historical/input pins and 11 executed code/configuration pins verified unchanged. No acquisition, network transaction, human execution, release/publication, training or Step 09 occurred. H1-I human-review intake implementation is proposed next; genuine reviewer appointments/execution, permitted multilingual supplementation and separate final custody remain explicit gates.

## Completion Step 08 H1-I addendum — 2026-10-25

[H1-I completion](progress/completion-08b-h1-i.md) adds a private, deterministic **40-case development pilot**, neutral reviewer forms, onboarding and an empty versioned intake ledger. The 20 positive proposals and 20 negative hypotheses represent 60 observations and 570 original name-evidence entries. Forty conservative review-family units have zero reuse; they are not human-confirmed independent families. Twenty-four cases retain flagged and graph-quarantined evidence. Negative hypotheses reuse unresolved duplicate candidates and are not verified negatives.

Positive/negative script strata are Latin–Arabic 4/3, Latin–Cyrillic 8/2, Latin–Han 2/0, other organizations 4/13 and vessels 2/2. The preferred negative profile is short by 1 Arabic, 6 Cyrillic and 2 Han cases; nine explicit other-organization fills preserve the 20-case category size without meeting those strata. Execution requires the owner's acceptance of this exact composition or an approved revision. Source case marginals are EU 29, OFAC 14 and OpenSanctions UN 11; cross-source cases contribute to both marginals. These are development diagnostics, not accepted coverage or language identification.

Pilot manifest SHA-256: `2f235e847e1e6b49db280f44ebe95d5f0a7783dc680babf786e741fd48cea16d`. Inventory logical commitment: `bee5358d7d24d0adca9d14231f835cc2b1b19d76bf816a494737815625a6e78b`. Empty ledger header/genesis: `1735d40127cc13a383f7833f1f1a803ff7588981ee5137b562f74ca551b94dbf`. Independent regeneration and replay passed; all 124 protected historical/input pins and 13 executed pins remained unchanged. The single C2/C3/H1 integration passed 311 tests, including 94 H1 tests, using fictional submissions only.

Actual submissions, adjudications, accepted labels, identity merges, accepted reference/absent families and protected final families remain **zero**. Genuine intake is hard-disabled until separately authorized activation and verified human access. The existing development-exposed Han candidates cannot supply fresh final coverage. Approximately 5,000 reference and 2,000 independent absent families, at least 200 positive and 200 negative candidate reviews, adjudication of used hard negatives, and at least 100 independent final positives per claimed direction remain required. Reviewer appointments/execution, actual family/absence validation, multilingual supply, independent custody and accepted-release approval remain mandatory; H1-I does not close Step 08. No acquisition, human execution, release, training, Step 09 or publication occurred.


## Approved solo-researcher Step 08 track — 2026-10-25

The owner explicitly approved the [solo protocol revision](progress/step-08-solo-protocol-proposal.md) and bounded SOLO-I implementation. This dated amendment adds a separate solo research track; preceding requirements and completed independent-track reports remain historical and unchanged. SOLO-I prepares software and blank development handoffs only. It does not authorize genuine human review ingestion, new acquisition, accepted corpus release, training, Step 09 or publication.

For the solo track, one identified researcher's documented verification replaces the unavailable two independent first reviewers and separate adjudicator. Source-supported evidence is allowed under the proposal's explicit weak-supervision policy: distinguish evidence origin (publisher assertion, independent documentary support, synthetic derivation) from review origin (none, single human, genuine independent human review). Automatic source-supported eligibility is not a claim that every family has been manually reviewed. Unsupported negatives, unresolved duplicate relationships, contradictory links and weak-name exceptions remain excluded; there are no automatic identity merges. Every used hard negative still needs positive evidence of distinction and recorded solo verification. A repeated opinion or AI output is not independent ground truth.

Retain approximately 5,000 usable reference families, 2,000 independent absent-query families, at least 200 positive and 200 negative distinct candidate inspections, fresh permitted sanctions-domain evidence and at least 100 eligible independent final families per claimed Latin–Arabic, Latin–Cyrillic and Latin–Han direction. Keep original source/script/type inspection allocations unless separately revised. The accepted 40-case workflow pilot includes nine disclosed negative-stratum substitutions; these provide no multilingual-coverage credit and do not revise the later 400-case allocation. Uncertainty, family independence, original source IDs/aliases, permissions, lineage and all-copy absence checks remain mandatory.

Inter-reviewer agreement is **not measured**. Self-holdout procedures do not constitute independent custody or independent final confirmation. All currently retained source observations remain development-exposed. Preserve group-disjoint train/development/calibration-fit/threshold/test design, immutable commitments, exposure tracking and predeclared evaluation; a local hash does not prove secrecy. Do not claim independently adjudicated ground truth, independent validation, real-world identity probabilities or operational sanctions-screening guarantees. Supplemental organizations cannot replace the sanctions-domain population.

The original C1/C2/C3/H1-I implementation and multi-reviewer ledgers remain preserved for possible future independent evaluation. Solo judgments must not be imported as fabricated independent adjudications. Step 08 can close only under the explicitly named solo protocol after actual corpus/coverage/evidence gates pass and release is separately approved; this amendment does not mark it complete. The independent-review version is not retroactively satisfied. For later steps, calibration describes the disclosed research label task (Step 17), a solo reviewer study is N=1 descriptive (Step 22), and a solo final evaluation cannot claim independent confirmation (Steps 09/28). Those steps still require their own authorization.


### SOLO-I measured preparation — 2026-10-25

[SOLO-I implementation evidence](progress/completion-08-solo-i.md) records 397 passing integration tests (86 new solo cases), scoped lint/format success and one successful 4.91-second supervised blank preparation. The new packet preserves the exact H1-I order and original evidence for 40 cases, 60 observations and 570 name entries; no selection was regenerated. Its manifest SHA-256 is `0922533880513eefc98ce0ead4adc2abc3618d388ded2bdbdfd0cd124238862d`. The separate empty ledger head is `60e3f5b7508cfd2dcdf21e6fcb12ace0ff7492c5d548ac6cea75ebbd2d2464ad`. Actual submissions, adjudications, accepted labels, identity merges and partitions remain zero; both intake tracks still reject genuine execution.

**The required real-browser fictional smoke check is blocked by the browser URL security policy.** A local fictional-only manual checklist is prepared. Software/preparation success does not complete this browser acceptance item, establish human validation, or close Step 08. All original targets, development exposure and separate SOLO-E/acquisition/corpus/ML approval gates remain in force.
