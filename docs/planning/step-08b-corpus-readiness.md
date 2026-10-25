# Step 08 corpus readiness — post-acquisition plan

2026-10-25. Planning and offline analysis only. No accepted corpus, review packets containing real cases, labels, final examples or partitions were created. This plan updates current quantities without rewriting the historical Step 08A or acquisition reports. The original [completion-plan Step 08](../project-completion-plan.md) remains binding.

## 1. Evidence and practical supply

The three-source acquisition is complete. Its receipts, hashes, permissions and resource checks are already verified; do not reopen acquisition infrastructure without a concrete changed input or failure. Use [continuation results](../../data/eval-comparisons/completion-08b-02rc/audit-results.json) and the new [intersection analysis](../../data/eval-comparisons/completion-08b-03-plan/analysis.json).

| Source | Organizations | Vessels | Name entries, including primary | Organizations with ≥2 distinct original names |
| --- | ---: | ---: | ---: | ---: |
| OpenSanctions UN | 269 | 0 | 918 | 154 |
| OFAC | 10,042 | 1,568 | 25,323 | 5,524 |
| EU | 1,779 | 0 | 14,327 | 1,570 |
| Total | **12,090** | **1,568** | **40,568** | **7,248** |

There are 38,717 organization name entries and 1,851 vessel entries. Source-local rows are not independent identities. There are 39,173 distinct original strings, 38,090 normalized strings, 7,423 multi-name groups across both types and 6,235 single-name groups. All 13,658 groups remain development-exposed; zero have reviewed usability or fresh-final eligibility.

| Measured flag/intersection | All groups | Organizations | Vessels |
| --- | ---: | ---: | ---: |
| In 1,259 normalized-name duplicate candidate pairs | 1,607 | 1,561 | 46 |
| Have at least one explicitly weak name | 1,476 | 1,441 | 35 |
| Have an application-rejected overlength name | 4 | 4 | 0 |
| Duplicate flag AND weak name | 223 | 216 | 7 |
| Any of the three flags | **2,864** | **2,790** | **74** |
| None of these three flags | 10,794 | 9,300 | 1,494 |
| ≥2 distinct normalized, nonweak, application-accepted names | 6,856 | 6,711 | 145 |
| Previous condition AND none of these three flags | **4,880** | **4,751** | **129** |

No-flag means only “not detected by these checks,” not cleared or identity-independent. Weakness and length are initially name-level restrictions; do not discard an entire otherwise supported group just because one alias is weak. The four length-affected groups do not overlap the equality candidates. All have some compatible names; the 17 original long entries remain intact. No truncation or 200-codepoint limit change is proposed.

The 1,259 pairs form **657 candidate review components**: 431 of size 2, 202 of size 3, 11 of size 4, four of size 5, four of size 6, two of size 7, and one each of size 11, 12 and 14. Components organize work, not equivalence. The pairs comprise 663 exact candidates plus 596 additional normalization candidates; 1,078 are cross-source and 181 within-source. More duplicates may exist beyond equality discovery.

The 5,000-reference/2,000-absence target requires about 7,000 accepted independent families, not 7,000 source rows. Organizations alone require a 57.90% accepted-independent yield from 12,090 rows; including vessels would require 51.25% from 13,658, but cannot silently change a claimed organization population. Recommend organizations as the primary corpus and separately declared vessel strata; the owner must decide the final type mixture. A single-name family may be a valid reference or controlled-absence family. It cannot automatically supply a natural held-alias positive query. Thus 4,751 is a warning about alias-rich unflagged supply, not an additional blanket corpus requirement or proof that 5,000 references are impossible.

## 2. Contracts already implemented versus missing

| Existing component | Reuse | Remaining narrow gap |
| --- | --- | --- |
| `corpus.py`, candidate schema v2 | Immutable candidate observations/names, source evidence, hashes, refusal to overwrite, false ML/final eligibility | Explicit admission of the successful continuation envelope and its separate historical lineage; no relabeling as original direct/recovery receipt. Current source formats do not accept it. |
| `ingest/link_records.py` | Exact-name/referent/continuity nominations, reviewed relation types, conflicting-cycle detection, quarantine propagation | Add a separately versioned normalized-name nomination method matching the audited NFKC/casefold/whitespace rule. Do not pass it as an exact-name or human decision. |
| `label_review.py` | Evidence/case/actor/submission/adjudication structures, weak-name purpose gates | Current packet mode is **fictional only**, final custody is rejected, and summaries deliberately count zero real reviews. Real packet preparation and authenticated real submission ingestion require explicit new modes and tests. |
| Existing audit helpers | Script/language/provenance/duplicate aggregate calculations | Export reviewable nomination and quarantine evidence in a private preparation artifact; implement complete reviewed-release acceptance later. |
| Candidate SQLite schema | Retained source rows and their original evidence | It explicitly is **not a reviewed-corpus schema**. Do not mark v2 candidate DBs “research-v1 accepted.” Reviewed graph, review/absence ledgers and release validation need a new schema/format version. |

No application code or schema is changed by this plan. APIs and commands described below are proposed, not currently executable features.

## 3. Immutable release design

Keep three different artifact states: `readiness_preparation` (draft nominations, no decisions), `candidate_release` (validated source assertions, no accepted labels), and `reviewed_corpus_release` (all declared acceptance gates met). Neither state automatically implies training authorization or independent final eligibility.

Proposed private reviewed release layout, created only after separate release approval:

```text
data/corpora/research-v1/
  manifest.json                  # format/schema versions, parent, declared populations, acceptance state
  corpus.sqlite                  # frozen observations, reviewed graphs, labels and eligible memberships
  evidence/source-index.json     # exact immutable snapshot/receipt/permission refs and hashes
  evidence/attribution.md        # source credit, permitted purposes, transformation notices
  lineage/transforms.json        # code/config versions; original→derived ancestry
  review/packet-index.json       # hashes and authorized review provenance; development material only
  review/decision-ledger.jsonl    # append-only events frozen into this version
  quarantine/ledger.jsonl         # excluded names, records, relations and unresolved reasons
  views/reference-definition.json# proposed fixed universe; Step 09 later binds actual role-specific views
  validation/acceptance.json     # counts/gates/exclusions; no protected case-level diagnostics
  custody/attestation.json        # whole protected-artifact commitment/access proof refs, no final labels
```

Do not copy protected final material into this developer-visible tree. The independent custodian produces a separate sealed companion in an independently controlled environment, with a release-level commitment and aggregate attestation. The logical study release binds both parts; a development-only artifact can be published privately as such only with approval and cannot close full Step 08. The custodian owns internal case-level manifests; shared developers get no final names, provider IDs, per-case hashes or labels. The SQLite reviewed schema is future work, not a migration of historical candidate databases.

Identifiers and provenance:

- `source_record_key = [source_id, exact_provider_id]`, using canonical structured serialization. Preserve case and namespaces; never concatenate ambiguous strings or turn a raw provider referent into a guessed cross-source ID.
- Preserve the existing `candidate-snapshot-v1` identity based on receipt-format, source, selection, receipt and permission hashes for existing formats. The continuation adapter must declare a new receipt-format identity and bind the original selection origin, failed-session receipt and continuation receipt. A source observation is `candidate-observation-v1(snapshot_id, source_record_key)`; all original evidence remains source-qualified even after grouping.
- `name_evidence_id` binds observation plus original text, field, supplied language and complete attributes. Equal strings with different qualifiers remain different evidence. Derived normalization/transliteration IDs bind original evidence, exact transform/code/config version and output; no generated form becomes a natural alias.
- Keep record-equivalence groups, supported real-world identity assertions and broader leakage families as distinct versioned graphs. Use reviewed decision IDs and graph-version hashes in membership IDs. A split or corrected identity creates a new group/version with explicit predecessor links, never a reused misleading ID.
- Every eligible member traces to retained selection bytes, completed transfer receipt, parser and source version/content-hash fallback, non-person classification, terms capture/grant, purpose/field limits and review decisions. Preserve actual raw-body hashes as transfer-time evidence; raw mixed files were discarded and cannot be reconstructed or newly persisted merely for release packaging.
- Manifest binds file hashes and deterministic logical row hashes, input source revisions, schema version, parent release, review/graph/exposure versions, reference/absence cohorts, transforms, limitations, approvals and acceptance results. SQLite physical bytes are not a portable logical identity. Do not include a file's own hash in a circular manifest calculation.
- Build into a new private staging directory, fsync, validate completely, then activate at a never-used destination. Refuse overwrite, symlinks, path escape, stale/incomplete evidence and failed review gates. A crash leaves an explicitly unaccepted staging artifact; no active release changes. Corrections yield `research-v2` or a separately named new version with a change ledger; revoked permission suspends new use without silently destroying history.

Acceptance is an evidence-backed gate, not a `complete=true` flag: source hashes/permissions; exact provenance; valid type/strata; resolved graph contradictions; uncertainty excluded before counting; eligible reviewed labels; required 200/200 review counts; every used hard negative adjudicated; independent 5,000/2,000 family cohorts; unchanged directional targets; actual protected custody; bounded integrity validation; no old-artifact mutation. Report separate source-row, canonical-group, leakage-family, query, submission and accepted-label counts.

## 4. Duplicate and quarantine workflow

1. Reproduce equality nominations deterministically from the pinned selections. Deduplicate by unordered observation pair; retain every evidence/method witness, with exact versus normalized methods distinct. Expected equality subset is 1,259 unique pairs, not 1,259 identities. Preserve qualified referents as unresolved evidence; a missing endpoint or ambiguous namespace never becomes a confirmed edge.
2. Prioritize cross-cohort-risk and cross-script components, then large/conflicting components and the remaining stable queue. Freeze the rule before seeing model performance. Of the 169 Arabic, 1,070 Cyrillic and 27 Han source-local pair candidates, respectively 118, 255 and seven lie in equality review components. The corresponding outside-component counts are 51, 815 and 20; none is a count of independent/final positives.
3. Review all nominated edges touching any proposed accepted family. Review may establish `record_equivalent`, `same_entity`, `dependent_example`, `related_entity`, `distinct_entity`, `dismissed_candidate` or `unresolved`, with evidence and dated authority. Parent/subsidiary/brand similarity is not identity. Dismissing a name collision is not proof of a negative label.
4. Human conclusions require adequate permitted support. Name-only source assertions can support a record-target alias question, but may be insufficient for cross-source legal identity. Require explicit independent source cross-reference or other permitted entity-specific evidence where needed. Record `needs_permitted_evidence`; do not collect registration numbers, addresses, narratives or other currently excluded fields without a separate field/source permission decision.
5. Resolve transitive conflicts (A=B, B=C, A≠C) before acceptance. Unresolved edges quarantine both endpoints and their affected dependency component. Group-level uncertainty blocks reference/absence eligibility and hard negatives; aliases cannot escape by copying to another source or changing ID. An unresolved component may be retained excluded, but cannot contribute accepted counts or share unresolved links into accepted cohorts.
6. Weak-name restrictions remain evidence/purpose-specific: 2,153 entries, 1,476 groups. EU `strong=false` is an alternate-name qualifier, not equivalent to an OFAC weak alias. Missing language remains unknown. Overlength entries are quarantined from the existing matcher; preserve exact originals and valid sibling names. Excluding a name must not change the underlying identity or erase absence evidence.
7. Record every decision/supersession; never auto-union equality components. Maintain accepted identity closure, conservative dependence closure, unresolved frontier and exclusion ledger separately. Later duplicate discovery invalidates affected frozen memberships/labels and requires a new release.

Similarity mining beyond the existing equality/referent rules would be a separately specified nomination stage, not a reason to load models now. Not finding a collision is never evidence of distinction.

## 5. Approximately 2,000 independent absent-query families

The primary construction remains **controlled index absence**, not “not sanctioned.” After adequate identity/eligibility review, select about 7,000 disjoint families into a proposed 5,000-reference universe R and 2,000 absence cohort A. A family from R removed in an ad hoc per-query index does not count toward A. Natural background nonmembers are optional, separately permissioned and separately reported; a Wikidata ID does not prove absence.

Step 08 must construct and actually validate a fixed **corpus-level reference universe** with the reviewed absence cohort; a tested function or planned count alone does not meet the 2,000-family requirement. Step 09 alone authorizes train/development/calibration/threshold/final allocation and role-specific query/index views. Corpus-level absence decisions bind the Step 08 universe; they remain `pending_view_validation` for any later changed or role-specific view until rechecked against its actual frozen membership. Final-test labels are certified inside custody against that later final view. This preserves the Step 08 absence deliverable without creating Step 09 partitions early.

Future validation procedure:

1. Freeze proposed cohort-selection rule, population/type strata, release/graph/permissions versions and human membership evidence. Choose whole eligible leakage families, without model scores or a search for easy negatives. Preserve sampling order, exclusions and rejected/replaced candidates.
2. Require R∩A empty under both accepted identity and dependence closure. No unresolved cross-cohort path may remain; resolve it with adequate evidence or quarantine affected membership. Preserve original provider IDs, alias history, referents and renamed/reissued copies when checking the exposure/membership graph.
3. Construct **one declared reference universe**, excluding every observation/equivalent/dependent representation of each A family. Filter membership before normalization, index building, display fallbacks, embedding caches and reviewer memory exports; verify no descendant remains in any searchable field. Each absent family still needs a supported natural query name and human identity evidence.
4. Compare candidates against the complete proposed reference universe, not a capped source sample or top-k retrieval list. Exhaustive mechanical ID/graph/alias ancestry checks prove exclusion relative to the reviewed graph; they do **not** prove that the graph captures every unknown real-world equivalence. Human identity/non-equivalence review and unresolved-link quarantine remain necessary. Retrieval can nominate further review, never certify absence from a low score.
5. Bound the label to release hash, frozen reference membership/view hash, graph version, natural query-evidence ID, construction `all_equivalent_copies_withheld`, human review/adjudication refs and validation receipt. A changed view or graph invalidates the label until revalidated. Store `supported_presence`, `unresolved_membership`, `ineligible` distinctly; unknown must never become absent.
6. Ensure A contains approximately 2,000 **independent** accepted families; several aliases, directions or perturbations from one family count once. Report controlled and natural-absence populations separately and do not infer real screening prevalence or open-world clearance.

Required fictional acceptance cases: same provider ID across snapshots; cross-source equivalent copy; changed/old alias; normalization-derived copy; cached reference resurrection; unresolved cross-cohort edge; a supported multi-answer target; same family proposed for R and A; altered view digest; query-only per-case deletion; a missed top-k result despite a present target. Each must reject false absence or produce the explicit non-absence state. Positive held-alias withholding is a different operation: remove all query evidence descendants across equivalent copies while retaining an independent permitted target representation. Validate each direction separately.
