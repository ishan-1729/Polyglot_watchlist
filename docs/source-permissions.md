# Source permissions for bounded research acquisition

## Latest Step 08B-2R continuation — 2026-10-25

The separately approved [continuation](progress/completion-08b-02rc.md) successfully acquired OFAC and EU through the unchanged exact routes and narrow source grants, with OpenSanctions reused. The actual native HTTP client used the hash-verified existing certifi bundle with full certificate-chain and hostname verification. The approved OFAC object and publisher pins passed; no unapproved redirect or source was accessed.

The new policy and prospective grants are in `config/data-sources-step08-continuation.json` and the private continuation evidence directory. No completed-purpose grants, corpus release, labels, training or publication were created. Permission for this candidate acquisition does not establish approval for those later uses. Direct UN and Wikidata remain outside authorization. The historical failure records below are unchanged; the latest report supersedes their pending acquisition decision only.

## Step 08B-2R recovery update — 2026-10-25

The user approved separate OFAC/EU recovery and reuse of the completed OpenSanctions selection. The [recovery registry](../config/data-sources-step08-recovery.json) and [permission preflight](../data/eval-comparisons/completion-08b-02r/permissions/preflight.md) preserve the same narrow private, noncommercial factual-name permissions, with explicit source reuse and one exact OFAC storage redirect. No general redirect permission, direct UN grant, Wikidata acquisition, training permission or independent final custody was established.

The recovery stopped after one failed OFAC transport attempt, before an HTTP response; EU was not attempted and no new body bytes were recorded. OpenSanctions was reused unchanged. Prospective grants remain distinct from completed-acquisition bindings: no bound completion grants or corpus release were issued. The [08B-2R report](progress/completion-08b-02r.md) records the local TLS preflight defect/fix, accounting and the next explicit approval boundary. No request may be retried by resetting the consumed claim or treating unused allowance as new authorization.

## Step 08B-2 update — 2026-10-25

The original Step 07 decision below remains historical and bounded to its feasibility purpose. A separate [Step 08B full registry](../config/data-sources-step08-full.json) and [saved permission review](../data/eval-comparisons/completion-08b-02/permissions/permission-review.md) authorize only the subsequently approved private, noncommercial, non-person candidate-preparation package. Its retained caps are 300 OpenSanctions / 12,000 OFAC / 2,000 EU groups; this does not raise the old feasibility profile's 200-group cap.

OpenSanctions CC BY-NC and EU's exact COM_REUSE XML evidence support the narrow purpose with attribution/change notices and exclusions. OFAC's earlier official chapter prefix contains complete section 105(a)–(d) and its closing boundary; combined with current official database import/export guidance, it supports the unchanged factual-name/alias use. The failed fresh chapter recapture is not reclassified as successful; worldwide and third-party clearance are not claimed. Broader use needs review. All candidates remain development-exposed, with no automatic training or final-evaluation eligibility.

Actual acquisition was partial: OpenSanctions completed, OFAC redirected without being followed, and EU was externally interrupted by resource supervision. All three requests are consumed. No final receipt or bound candidate-purpose grant was produced. See the [08B-2 report](progress/completion-08b-02.md) for accounting and the separately proposed recovery decision. No new acquisition is currently authorized. Direct UN remains permission-blocked; Wikidata remains provisional and was not accessed. This update changes neither their historical failures nor the original Step 08 targets.

## Historical Step 07 permission decision

Review date: **2026-10-24 UTC / 2026-10-25 Asia/Kolkata**. This is a recorded
project decision for Completion Step 07, not a legal opinion, live screening
authorization, or a claim that a record establishes identity or wrongdoing.
The proposal in `docs/reference/` is not permission evidence.

The intended use is local, noncommercial research on names of organizations,
companies and vessels. At most 200 selected non-person groups per source may be
retained. Permission to reuse material and permission to spend resources are
separate gates: the initial approval allowed at most 10,000,000 response-body
bytes per source and 50,000,000 data bytes in total, with one request at a time.
The user first approved 28,000,000 bytes for EU. After a partial failed
transfer consumed 5,471,048 bytes, the user authorized the suitable bounded
retry: **32,000,000 session bytes for EU only**, with an EU request deadline
of 180 seconds and source deadline of 240 seconds. Wikidata uses a 90-second
request inside its unchanged 120-second source deadline after diagnosed
timeouts; other requests retain 30/120-second deadlines;
the other sources retain their 10,000,000-byte limits, the combined data ceiling
remains 50,000,000 bytes, and the 200-group-per-source limit is unchanged.
An approved publisher license does not waive those limits. Training, model
downloads, public release, operational use and paid APIs are outside this step.

## Decisions

**User-approved closure amendment, 2026-10-25:** OpenSanctions UN, OFAC and EU
are the required successful Step 07 acquisitions. Direct UN and Wikidata are
**investigated but not acquired**, excluded from the required successful set
by explicit approval. Their failures/restrictions remain below; neither is
represented as successful. Future use requires separate authorization and
review. The registry keeps UN blocked and Wikidata pending project acquisition
authorization, without retracting the recorded CC0 structured-data terms.
The [approved closure record](progress/completion-07-approved.md) supersedes
earlier pending-decision status without modifying historical reports.

| Source ID | Current permission decision | Acquisition implication |
| --- | --- | --- |
| `opensanctions_un` | Approved for the narrow noncommercial local use under the publisher's CC BY-NC 4.0 grant. | Pinned UN FTM export is 3,026,789 bytes according to its official index; HEAD returned 200. Apply the source-specific type rule below. |
| `un_consolidated` | Blocked: the reviewed UN terms do not establish permission for the proposed compilation and transformations. | Do not acquire a new direct-UN corpus. Historical artifacts remain unchanged. The examined XML URL also returned HEAD 404. |
| `ofac_sdn` | Approved for narrow factual name/alias research, supported by OFAC's explicit database import/export guidance and the US-government-work rule in 17 USC 105. | Official `SDN_XML.ZIP` is 2,582,121 bytes; its XML is 29,245,041 bytes. Transfer and decompression limits are distinct. Use a bounded archive adapter, current schema and decoded-content digest. |
| `eu_consolidated` | Reuse permission established for the catalog's named distributions under the European Commission reuse notice; CSV 1.0 separately names CC BY 4.0. | The selected XML is 25,899,600 bytes. EU's amended 32 MB session cap includes the 5,471,048-byte failed attempt and the successful retry: 31,370,648 bytes consumed, 629,352 bytes remaining. Schema validation and the unchanged combined cap still apply. |
| `wikidata_orgs` | Structured-data CC0 permission recorded; new project acquisition authorization is pending. | Investigated but not acquired. The smaller query returned HTTP 504 with no retained selection. Separate review/authorization is required for any future SPARQL, Action API or REST use. |

“Approved” above concerns the limited purpose and fields in this document. It
does not assert worldwide clearance for every upstream work, permission to use
logos or third-party prose, or approval to distribute a trained model.

## Source evidence and conditions

**OpenSanctions.** The current [noncommercial-use explanation](https://www.opensanctions.org/docs/commercial/exemption/)
expressly covers student projects and personal noncommercial research, permits
bulk downloads without signup, and identifies the database as CC BY-NC 4.0.
Business use and operational compliance use have separate commercial terms.
The [CC BY-NC 4.0 legal code](https://creativecommons.org/licenses/by-nc/4.0/legalcode.en)
permits noncommercial reproduction, sharing and adaptation, subject to its
attribution, license, change-notice and other conditions. Retain OpenSanctions
credit, original UN publisher/source information, the license link, snapshot
date and a description of selection/normalization. This publisher grant does
not resolve every underlying third-party right; do not label the raw UN source
as public domain or assume the grant authorizes direct-UN acquisition.

The [UN dataset page](https://www.opensanctions.org/datasets/un_sc_sanctions/)
links the captured [index](https://data.opensanctions.org/datasets/latest/un_sc_sanctions/index.json)
and the pinned FTM artifact below. The index reports version
`20261024160105-nsw`, exported at `2026-10-24T16:01:05`. Index checksums are
provider values; the acquisition must independently hash the actual body.
An HTTP HEAD success without a Content-Length is not proof of its size.

**Direct UN.** The [UN terms of use](https://www.un.org/en/about-us/terms-of-use)
allow certain personal, noncommercial downloading but say:

> without any right to resell or redistribute them or to compile or create derivative works therefrom

The proposed normalized research corpus requires compilation and changes, so
this limited grant is insufficient for the proposed direct-source use. The
[Security Council list page](https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list)
returned a JavaScript verification page with HTTP 202; it was not treated as a
verified source-specific override. The unresolved action is to obtain and
review an applicable narrower reuse grant, or separately authorize a publisher
permission inquiry. No inquiry has been sent. A fictional parser can still be
tested without asserting permission to ingest actual UN records.

The successfully captured [UN copyright page](https://www.un.org/en/about-us/copyright/)
repeats the general reservation of rights, refers to the terms, and directs
permission requests to [UN Publications: Rights and Permissions](https://shop.un.org/rights-permissions).
The precise routes to resolve this deliverable are:

1. Locate and capture an applicable UN Security Council list-specific reuse
   grant, or review a written permission the project owner already holds. It
   must cover the proposed compilation and transformations, not just viewing
   or downloading the list.
2. With separate authorization to contact the publisher, submit a narrow
   permission inquiry through the official rights route. A proposed inquiry is:
   “May a noncommercial student research prototype retain up to 200 non-person
   entity records from the Security Council Consolidated List, containing only
   source IDs, names/aliases, type evidence and provenance; normalize and index
   those names; and evaluate possible record matches locally? Please confirm
   permission for the compilation and transformations, required attribution,
   retention conditions, and any other applicable terms. Public redistribution,
   operational screening and model release are excluded from this request.”
   This is a draft only; no form, email or message has been submitted.
3. If suitable permission cannot be established, ask the user to explicitly
   revise the direct-source deliverable. A separately permitted publisher
   version remains a distinct source and must not silently stand in for a
   completed direct-UN acquisition. The fictional direct-UN parser can remain
   documented as such.

The 2026-10-25 closure re-review captured the official rights page successfully.
Under **Databases**, it states: “Permission is required to reuse content from
any and all United Nations’ online platforms and databases (namely,
bibliographic, legal and statistical databases).” The publication-excerpt
exception does not establish a grant for this proposed transformed database.
The official sanctions-information URL redirected to `main.un.org`, which
returned HTTP 202 with an access-verification challenge. That path stopped;
no challenge was bypassed, no new XML endpoint was established, and no UN
dataset request or publisher message was made. The prior candidate's HEAD 404
remains historical evidence, not proof that every current UN endpoint fails.

The missing approval is a list-specific applicable grant or written
rights-holder permission covering the bounded non-person record compilation,
name normalization/indexing and local matching evaluation, with attribution,
modification and retention conditions. User permission to investigate cannot
replace publisher permission. See the [dated re-review and exact receipts](../data/eval-comparisons/completion-07/closure-review/un-permission-review/report.md).

**OFAC.** The official [flat-file tutorial](https://ofac.treasury.gov/sdn-list-data-formats-data-schemas/tutorial-on-the-use-of-list-related-legacy-flat-files)
describes relational database import, linking aliases to primary names, and
export. The [specification](https://ofac.treasury.gov/media/29976/download?inline)
identifies OFAC as publisher of the lists. The [Copyright Office's Title 17,
section 105 text](https://www.copyright.gov/title17/92chap1.html#105) states the
US-government-work rule. This supports the narrow factual fields used here;
it is not a claim that all Treasury web content or third-party assets are
public domain everywhere. Credit US Department of the Treasury / OFAC, identify
the publication date and changes, and never imply endorsement.

The [SLS page](https://ofac.treasury.gov/sanctions-list-service) and
[technical notice](https://ofac.treasury.gov/sdn-list-data-formats-data-schemas/ofac-technical-actions-in-reverse-chronological-order/20240516_44)
identify the official distribution service and require a User-Agent. The
official app's read-only metadata request is an empty POST to
`https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/SdnList`.
Its captured response records file sizes, current publisher digests and
`lastUpdated: 2026-10-21T00:00:00`. The ZIP has **no publisher archive digest**
(`hashCodes: null`); do not invent one. Record its locally computed SHA-256 and
verify the decoded XML against the provider's published digest:

`421c5f6ee841eb7c0e327eb0d6bdbe24cbb58091e3cbfd77d83dd41c7b5a5e08`

The current official `XML.xsd` uses namespace
`https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML`,
root `sdnList`, header `publshInformation`, and child `uid` elements in
`sdnEntry` and `aka`. It does **not** establish the older provisional
`tempuri.org`/UID-attribute profile as the current format. The XSD permits
unbounded repeated entries; finite parser limits are project safeguards, not
limits promised by the schema. No ZIP-member layout was inspected during this
metadata-only review; the acquisition must validate it.

**European Union.** The [official catalog metadata](https://data.europa.eu/api/hub/search/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions)
explicitly attaches `COM_REUSE` to XML/CSV 1.1 and `CC_BY_4_0` to CSV 1.0.
`PUBLIC` access status alone was not used as a license. The
[Commission legal notice](https://commission.europa.eu/legal-notice_en) describes
reuse with credit and change notices and identifies exclusions for third-party
works, certain personal material and protected assets. The catalog links
[Decision 2011/833/EU](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32011D0833);
direct captures of that legal-text endpoint returned HTTP 202 verification
pages, so those captures are not represented as the decision text. The
distribution-specific catalog grant and successfully captured Commission notice
are the reviewed permission evidence. Credit European Union / European
Commission, DG FISMA; preserve the source and publication metadata and indicate
transformations. The consolidated list is not the legally authentic Official
Journal. A dataset is not proof of current legal status or wrongdoing.

The public catalog itself supplies `token=dG9rZW4tMjAxNw` in the download URLs.
This is a publicly published routing parameter, not a private account API key.
Credential-free versions returned HEAD 403; the exact catalog URLs returned
HEAD 200 without redirects. This does not authorize arbitrary token use or
account access. The catalog UI is a JavaScript shell, and the examined FSF
landing page returned 401; no smaller complete official selector was verified.

The separately published [XML 1.1 XSD](https://webgate.ec.europa.eu/fsd/fsf/public/files/xsdFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw)
was retrieved successfully without downloading sanctions records. It is 16,116
bytes, declares version 1.1 and namespace
`http://eu.europa.ec/fpi/fsd/export`, and defines root `export` with required
`generationDate` and `globalFileId` attributes. Critically, `subjectType` has
both a free-text `code` and a required `classificationCode`: the latter is
restricted to `E` (enterprise) and `P` (physical person). Use that explicit
classification for the non-person boundary and retain both fields.

`sanctionEntity` and `nameAlias` inherit a required `logicalId`. Name attributes
include optional `wholeName`, `nameLanguage` and `strong`. The `strong` boolean
marks a main name; it is not a match-confidence value. The schema distinguishes
`nameLanguage` from `regulationLanguage`; do not fill a missing name-language
tag with the regulation language. A real acquisition still has to meet the
schema-aware parser's structure and field checks; the presence of an XSD is
not proof that a particular downloaded body is valid.

**Wikidata.** The [copyright page](https://www.wikidata.org/wiki/Wikidata:Copyright)
places structured main/Property/Lexeme/EntitySchema data under CC0; wiki prose
has different terms. Only structured organization labels/aliases, language
tags, QIDs and type evidence are in scope. CC0 does not require attribution,
but retain “Wikidata contributors”, item URLs, query text/hash and retrieval
date for reproducibility. The [query-service manual](https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual)
documents GET/POST at `https://query.wikidata.org/sparql`, the 60-second server
deadline and 429/Retry-After behavior. HTTP 429 stops acquisition without a
retry. Only transport failures and HTTP 502/503/504 permit a bounded retry,
within the registry's two-attempt ceiling and the same source/combined byte
budgets and source deadline. The [User-Agent policy](https://foundation.wikimedia.org/wiki/Special:MyLanguage/User-Agent_policy)
calls for a descriptive client and operator contact. The confirmed public
project URL `https://github.com/raiha-siddiqui/Polyglot_watchlist` is the contact
reference; do not invent an email or send messages to the publisher.

Attempt 05 selected at most 200 sorted direct-organization candidates before
human exclusion and still returned HTTP 504. In the authorized closure review,
attempt 06 removed global sorting and selected at most **20 service-order
candidates** with direct `wdt:P31 wd:Q43229`. It then excluded candidates whose
explicit `P31` type has a `P279*` path to human `Q5`, including the zero-length
path for direct human declarations, before expanding all names. Excluded
candidates were not replaced. No outer row limit or language filter truncates
the remaining groups' labels/aliases. This changes sample selection, not
permitted types, fields, source role or resource ceilings. Live service order
is not promised to be stable; saved artifacts and parser ordering remain the
reproducibility evidence. No vendor-specific optimizer hint was introduced.

The smaller query also returned **HTTP 504**, with zero response-body bytes
read and no retained selection. The exact query, reduced-budget command and
attempt receipt are preserved. Removing avoidable sort work justified this
one attempt, but neither its failure nor earlier 504s identifies the server's
internal execution problem. No further retry is authorized automatically by
unused bytes. A successful permitted selection or explicit scope revision is
was still needed at that investigation snapshot. The user subsequently approved
the documented investigated-not-acquired disposition for Step 07. No future
endpoint or acquisition is authorized by that closure revision.

## Exact resources and size evidence

| Artifact | Reviewed URL | Size evidence / status |
| --- | --- | --- |
| OpenSanctions UN FTM | `https://data.opensanctions.org/artifacts/un_sc_sanctions/20261024160105-nsw/entities.ftm.json` | Index: 3,026,789 bytes; HEAD 200, no redirect, no Content-Length. |
| Direct UN XML candidate | `https://scsanctions.un.org/resources/xml/en/consolidated.xml` | HEAD 404; rights unresolved independently of access. |
| OFAC ZIP | `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_XML.ZIP` | SLS metadata: 2,582,121 bytes; HEAD 200 without length and with misleading `text/xml`. Do not infer GET body from HEAD's type. |
| OFAC XML schema | `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML.xsd` | GET 302 to reviewed official storage object, then 200; 7,400 bytes. |
| EU XML 1.1 | `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | HEAD Content-Length 25,899,600; last modified 2026-10-23. |
| EU CSV 1.1 | `https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | HEAD Content-Length 25,288,456. |
| EU CSV 1.0 | `https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList/content?token=dG9rZW4tMjAxNw` | HEAD Content-Length 18,997,662; still over the initial cap. |
| EU XSD 1.1 | `https://webgate.ec.europa.eu/fsd/fsf/public/files/xsdFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | GET 200; 16,116 bytes; SHA-256 `1c01a73e4598c5c41c1a847fb81513214cfafeaed5c3ea7e9343949c413a8799`. |

The metadata also offers OFAC SDN.CSV + ALT.CSV totaling 6,807,881 bytes, but
complete alias joins need two resources and current alias HEAD returned 400.
The selected compressed XML avoids that incomplete-source issue. Advanced and
enhanced XML are separate unsupported formats. Each current acquisition must
recheck size and schema; these observations are not a permanent guarantee.

The OFAC schema redirect identifies host
`wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com` and exact path
`/Export-XSDs/XML.xsd`. The ZIP metadata identifies exact object path
`/Published/c855675f-4385-4bb5-b89a-59ccb73a83e6/2026-10-20/4166a9f5-d268-432a-a70b-65bd16bcd16a/SDN_XML.ZIP`.
Review the object path before any redirected request; do not allow a whole
storage domain indiscriminately. Provider-issued short-lived signing query
values are removed from saved receipts; a SHA-256 fingerprint of the full
redirect URL preserves an audit reference without retaining the signature.
The exact unsigned ZIP object returned HEAD 403. The coordinator approved the
publisher-issued signed public-download flow with the exact object path and a
finite standard query-key allowlist. This does not authorize private operator
keys or a general storage-host exception. The actual archive and its member
structure still require acquisition-time validation.

## Non-person and field boundary

Retain only source IDs, original names/aliases, source-provided language tags,
explicit type evidence and the minimal provenance needed to reproduce a
selection. Generic FTM `LegalEntity` is ambiguous: the
[official schema](https://followthemoney.tech/explorer/schemata/LegalEntity/)
includes people as well as organizations. It is excluded by default.

There is one reviewed source-specific exception: the pinned OpenSanctions UN
source's [crawler](https://github.com/opensanctions/opensanctions/blob/main/datasets/_global/un_sc_sanctions/crawler.py)
calls the maintained [UN helper](https://github.com/opensanctions/opensanctions/blob/main/zavod/zavod/shed/un_sc.py),
which maps UN `ENTITY` elements to `LegalEntity` and `INDIVIDUAL` elements to
`Person`. The exception must require the exact approved source, its
`un_sc_sanctions` dataset membership and sanction topic; retain the original
provider schema and mapping evidence. It does not generalize to another
dataset or establish that every non-person is specifically a company.

Keep strong aliases, previous names and weak aliases distinguishable. A weak
alias is not automatically a trustworthy positive name-match label. No source
license creates evaluation truth, resolves duplicates or permits leakage
between training and test groups. See [the retention policy](data-retention.md).

## Attribution, redistribution and later training

| Source | Required or project-retained notice | Redistribution and later model work |
| --- | --- | --- |
| OpenSanctions UN | OpenSanctions + UN source, CC BY-NC 4.0 link, snapshot and change notices. | Noncommercial sharing/adaptation subject to the license; commercial use needs separate terms. Corpus/model release and training need their own approved phase and assessment of retained content and applicable rights. |
| Direct UN | Keep historical source notices; no new reuse grant asserted. | Proposed compilation, transformation, training and redistribution remain blocked pending applicable permission. |
| OFAC | OFAC/Treasury source, publication date, change notice; no endorsement. | Narrow factual reuse is supported; third-party assets/prose and model/public-release plans are not cleared by this review. |
| EU | European Union/Commission DG FISMA, source, date and changes; honor the particular distribution's terms. | Reuse grant does not waive exclusions or authorize a public deployment. Later training/release must preserve applicable notices and review third-party rights. |
| Wikidata | CC0 link and contributor/source/query provenance retained as project practice. | CC0 supports structured-data reuse; other Wikimedia content, marks and service access have separate terms. Training/release remain later scope decisions. |

## Evidence quality and unresolved work

The immutable response captures and per-request receipts live under
[`data/eval-comparisons/completion-07/permissions/`](../data/eval-comparisons/completion-07/permissions/).
[`http-receipts.json`](../data/eval-comparisons/completion-07/permissions/http-receipts.json)
records UTC timestamps, methods, allowlisted hosts, redirects, statuses, body
byte counts, completeness and SHA-256. HEAD receipts hash an empty body; that
is **not** a dataset digest. A complete 202 verification page, 404 response or
empty 200 is not successful content verification.

The Copyright Office chapter capture stopped at 450,000 bytes; the complete
section 105 passage is within the saved prefix, but the file is explicitly
marked incomplete. Terms responses were bounded separately from dataset
acquisition. The ledger counts read HTTP body bytes, not TLS/header overhead,
wire-level traffic, or an estimate of dataset sizes. No dataset body was
downloaded by this permission-review helper.

At the earlier amended review close, 60 receipts cover 3,250,904 captured/read HTTP body
bytes against the 5,000,000-byte terms/metadata ceiling. All 37 saved bodies matched
their recorded byte lengths and SHA-256 values, and the ledger sum matched the
budget total. Success counts do not replace content review: failed, empty and
verification-page captures remain explicitly identified. The later official EU
XSD capture establishes its namespace and subject-classification semantics;
actual acquired-body validation remains a separate required check.

The closure re-review adds three serial official UN rights/information requests
and **39,923 bytes**, bringing terms/metadata reads to **3,290,827 / 5,000,000**,
with **1,709,173 bytes remaining**. The original ledger is preserved; new
receipts are in the linked UN re-review directory. The
[closure accounting receipt](../data/eval-comparisons/completion-07/closure-review/final-budget-and-retention.json)
reconciles both ledgers and all acquisition attempts. Response-body accounting
does not measure unread error bodies or protocol overhead.

The project owner must resolve the direct-UN permission issue before enabling
it. The EU-only transfer amendment is approved; it does not enable direct UN
or enlarge any other source budget. Any later source, endpoint, license,
purpose or quantity change requires
another review. Successful permission review is not successful acquisition:
actual body hashes, schema checks, selected counts and yield belong in the
acquisition receipt and Step 07 report.
