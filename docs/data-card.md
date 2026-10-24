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
