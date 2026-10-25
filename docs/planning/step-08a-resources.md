# Step 08A — resource proposal for a later Step 08B

Date: 2026-10-25, Asia/Kolkata. **Planning only. Nothing in this note authorizes network access, acquisition, spending, implementation or a larger retention limit.** The central Step 08A plan owns the eventual proposal and approval request. Step 07 is already closed under its approved three-source revision; its historical budgets and receipts remain separate.

This note sizes a bounded first tranche. A tranche is one explicitly limited batch of work: here it lets the project owner approve known resource ceilings before any new request. The owner approves the limits, the future acquisition process records actual use, and a human reviews yield before any later tranche. It does not promise that the full corpus targets will be met.

## Measured locally

The [read-only probe receipt](../../data/eval-comparisons/completion-08a/resource-probe.json) records the actual commands and arithmetic inputs. Commands were `sysctl -n hw.memsize`, `vm_stat`, `memory_pressure -Q` (query only), and a Python standard-library disk/file-size probe. No names, IDs, private stores, credentials, model files or stress benchmark were inspected.

| Observation | Recorded result | Meaning and limit |
|---|---:|---|
| Physical RAM | 17,179,869,184 bytes = 16 GiB | Total installed RAM, not free working memory. |
| OS memory query | 47% system-wide memory free | A momentary OS diagnostic. It is not a measured acquisition memory peak or an allocation guarantee. |
| Raw VM snapshot | 6,269 free pages; 236,404 inactive pages; 382,522 compressor pages; 16,384 bytes/page | These categories use different definitions from the OS free-memory percentage. Do not add them as guaranteed available RAM. |
| Workspace filesystem free | 53,721,161,728 bytes = 50.03 GiB | Snapshot at 2026-10-24 22:24:29 UTC. Recheck immediately before any approved run. |
| Three current normalized files | 1,152,233 bytes total | File sizes measured with `stat`; contents were not reanalysed for this resource note. |
| Acquisition peak RSS, decode/tree amplification, throughput | **Unmeasured** | RSS means the memory physically held by a process. No resource-fit or latency claim follows from the small files. |

MB below means 1,000,000 bytes. GiB means 1,073,741,824 bytes.

## Proposed fresh-session body budget

Retain the original **100,000,000-byte Step 08B proposal**, including metadata and failures, but allocate only **59,000,000 bytes** to the initial active tranche. The remaining **41,000,000 bytes are unallocated**. They do not permit automatic expansion, transfers between source caps, a new API route or another tranche. Additional work requires measured yield and explicit approval.

| Exclusive body-byte bucket | Proposed active cap | Retention / investigation envelope |
|---|---:|---|
| Terms, metadata, schemas and official service-contract review | 5,000,000 | Only necessary evidence and request receipts; no dataset bytes charged here. |
| OpenSanctions UN distribution | 5,000,000 | At most 300 eligible non-person provider groups. |
| OFAC SDN | 4,000,000 | At most 12,000 eligible non-person provider groups; decoded XML remains bounded separately at 32,000,000 bytes. |
| EU consolidated | 30,000,000 | At most 2,000 eligible non-person provider groups. |
| Separately reviewed Wikidata API pilot | 15,000,000 | At most 200 retained groups, 500 examined candidate QIDs, 800 examined type nodes, and 250 actual HTTP requests. |
| **Active total** | **59,000,000** | **No direct-UN dataset request.** |
| **Unallocated remainder** | **41,000,000** | Requires a new explicit allocation/approval before use. |

These are new-session proposals; they neither refund nor spend the Step 07 remainder. Keep the old 40,006,347 dataset bytes and 3,290,827 terms bytes in their historical ledgers. Future counters persist across invocations/resumes in the approved Step 08B session. Every returned body byte, including failed reads, error/challenge bodies, redirects, retries and repeated data, is charged once to its bucket and once to the overall total. Headers/TLS/DNS overhead remains outside a body-byte cap and must be described as such. A request is counted when attempted, even if no body arrives. No byte or request allowance resets after a failure.

The three previously completed bodies total 31,508,510 bytes. Against the proposed per-source caps, their historical sizes leave 1,973,211 / 1,417,879 / 4,100,400 bytes respectively. **None of those remainders covers a second complete copy of its previous source file.** The finalized proposal permits one attempt per bulk source and no automatic retry. Source drift can also make the first current copy exceed its cap; that is a stop-and-review result.

## Proposed request, time and memory stops

All requests are serial; Wikidata API requests start at most once per second, and stricter official service rules take precedence. These bounds match the [central Step 08A proposal](../step-08a-plan.md). The future implementation must enforce them and record their effective values before networking. Current Step 07 code has a 200-group retention ceiling; the larger limits and the proposed RSS watchdog are not implemented by this plan.

| Bucket | Proposed request bound, including redirect hops | Per-request / whole-bucket wall limit |
|---|---|---|
| Metadata and official contract review | At most 16 HTTP transactions including redirects; no automatic retries; at most 512,000 received body bytes per response and 5,000,000 total | 30 seconds / within the 60-minute overall window |
| OpenSanctions | One attempt; at most 2 exactly reviewed redirects, hence at most 3 HTTP transactions | 30 seconds / 120 seconds |
| OFAC | One attempt; at most 2 exactly reviewed redirects, hence at most 3 HTTP transactions | 30 seconds / 120 seconds; decoded XML cap 32,000,000 bytes |
| EU | One attempt; at most 2 exactly reviewed redirects, hence at most 3 HTTP transactions | 180 seconds / 240 seconds |
| Wikidata API pilot | At most 250 HTTP transactions including discovery/type calls and reviewed redirects; one attempt per logical request; at most 10 IDs per batch **only if the official contract permits it** | 30 seconds / 1,800 seconds; at most 2,000,000 received and 4,000,000 decoded bytes per response |

The three bulk sources share a maximum of **nine HTTP transactions**, including all reviewed redirect hops; no second attempt is included. Every request-count, per-response, source-byte and total-byte cap applies together. For example, 16 responses of 512,000 bytes would exceed the 5 MB metadata bucket, and 250 maximum-sized API responses would exceed the 15 MB API bucket; neither product is an allowance.

Use a **3,600-second total live-run wall limit**, including metadata, request spacing, parsing, supervision and local admission work; human review is separate. Individual limits are ceilings, not promises that every count can be reached. Even fast 250-request Wiki work needs at least 249 seconds between request starts, plus actual response time. A long response consumes the wall budget; a later invocation cannot reset the session counters. The Wiki pilot stops on **429, any 5xx response or timeout**, with no automatic retry or REST fallback. A verification challenge, unreviewed redirect, stale/missing permission, malformed data, changed schema, insufficient byte budget or any deadline also stops the affected branch. Preserve a failure receipt and make no automatic route/batch/source substitution.

For any API proposal, first review the official endpoint contract, allowed parameters/fields, batching, rate policy, continuation rules and licensing in the separately authorized metadata step. The API pilot needs explicit scoped authorization after that preflight. The budget is not permission to use Action API, REST, SPARQL or a fallback route. Candidate/type-node counts are investigation caps; type uncertainty may consume them without producing a retained group.

Propose one active acquisition/parse source at a time, with a **1.5 GiB soft stop and 2 GiB hard stop on aggregate acquisition-process RSS**, including any worker children. A soft stop means issue no next request, preserve a safe aggregate receipt, then exit; the hard limit must terminate the bounded worker. The central plan adopts proposed host-admission gates of at least **10 GiB free disk and a 25% OS free-memory reading** before starting, with a stop if the same OS query falls below **20%**, reports pressure trouble, or the worker hits an RSS ceiling. These percentages are proposed operational gates, not scientific guarantees. A later approved pilot must measure actual peak RSS and validate that the monitor works. The present 47% reading and 50.03 GiB free disk support trying that bounded pilot; they do not prove full XML/tree parsing fits. No model is loaded alongside acquisition.

## Disk and retention scenarios

[Existing aggregate evidence](../../data/eval-comparisons/completion-07/closure-review/feasibility-workload.json) reports 269 OpenSanctions, 11,610 OFAC and 1,779 EU parser-eligible groups before the 200-per-source cap: **13,658 source-local candidates**, not independently usable identities. Proposed bulk caps total 14,300 groups; adding the Wiki pilot gives a maximum 14,500 retained groups. Actual eligibility, names per record, duplication and script yield remain unknown at that scale.

| Source | Current 200-group file | Flat projection at proposed retention cap |
|---|---:|---:|
| OpenSanctions | 372,949 bytes | 559,424 bytes at 300 groups |
| OFAC | 188,926 bytes | 11,335,560 bytes at 12,000 groups |
| EU | 590,358 bytes | 5,903,580 bytes at 2,000 groups |
| **Bulk total** | **1,152,233 bytes** | **About 17.80 MB** |

The flat projection assumes the first 200 groups' average size persists. It is **not a measured full-corpus size**. Two-times and five-times scenarios are about 35.60 MB and 88.99 MB. For Wiki only, an explicitly assumed 5,000 bytes per retained group would make 200 groups about 1 MB; no Wiki record-size evidence currently exists. These examples size a pilot, not a complete release or vector index.

The central proposal includes a combined **100,000,000-byte normalized-selection cap** alongside the **2 GiB ceiling for all new working artifacts** (selections, reviewed metadata, receipts, temporary approved artifacts and one checked copy). Keep the 10 GiB host free-space floor throughout the run. A five-times bulk scenario plus the illustrative Wiki file is about 90 MB; oversize alias records can still hit the cap. Stop and report incompleteness instead of silently truncating fields or calling a partial release complete. Keep mixed raw bulk bodies and decoded XML in bounded memory; no new raw bulk file, person record, model copy or database copy is proposed. Existing artifacts remain preserved.

## Human review hours and money — assumptions, not measurements

The unchanged Step 08 contract proposes about 5,000 usable reference groups and 2,000 independently validated absent-query groups, at least 200 positive and 200 negative candidate reviews, and 100 independent final groups per claimed script direction. The current 600 groups and the 13,658 eligible source records do not establish those targets. A Wiki pilot capped at 200 cannot by itself meet the 2,000 absent-group proposal. Budget exhaustion or insufficient yield means the full Step 08 target remains unfinished.

| Review scenario | Explicit time assumption | Illustrative one-reviewer hours |
|---|---|---:|
| Shared screen of 7,000 accepted families: 5,000 reference plus 2,000 disjoint absent families | 2–5 minutes each; the current 600, if accepted, are included | 233.3–583.3 |
| Screen the current 600 groups | 2–5 minutes each | 20–50 |
| Screen 5,000 proposed retained reference groups | 1–3 minutes each | 83.3–250 |
| Screen all 13,658 observed eligible candidate groups | 1–3 minutes each | 227.6–682.9 |
| Validate 2,000 absent-query groups against a declared index/view | 3–10 minutes each | 100–333.3 |
| Review 400 candidate labels: 200 positive + 200 negative | 3–10 minutes each | 20–66.7 |

The shared 7,000-family scenario is `7,000 × (2–5) / 60 = 233.3–583.3 hours`, approximately 233–583 hours. It is one screening pass before difficult identity work, disagreement or independent review; it assumes 7,000 accepted distinct families exist. Do not add the current 600 screens again. The 600-, 5,000- and 13,658-group screening rows are alternative/overlapping scenarios, and the separate absence-validation row describes a different depth of work. Label review can overlap group/absence work, so these rows are not a project total. Each extra independently reviewing person adds their own hours. For the 400-label block alone, two full reviewers would require about **40–133.3 hours**; if an assumed 20% disagree and adjudication takes an assumed 10–20 minutes per case, add **13.3–26.7 hours**, giving **53.3–160 hours** for that block. This is neither a project-total estimate nor an upper bound. Multilingual evidence, legal uncertainty, rejected candidates and recruitment can increase effort. Measure a small separately approved review pilot before committing the whole workload.

Use a transparent money formula: `cost = sum(review_hours_by_role × approved_hourly_rate_by_role) + separately_approved_service_costs`. As an arithmetic example only, **100 hours × an assumed ₹1,000/hour = ₹100,000**. The rate is not a quote, market claim or approved payment. Volunteer effort can have zero cash cost while still consuming those hours. No paid API, cloud service, GPU job or reviewer contract is authorized; no present API price/entitlement was checked offline.

## Decision gates for the central plan

1. Approve exact endpoints, fields, attribution/terms evidence, the 59 MB allocation, request/time/retention caps and the 41 MB unallocated balance; do not infer approval from the earlier 100 MB proposal.
2. Separately approve and validate the necessary full-retention path, byte/request accounting and RSS/disk/time stops with synthetic local cases before any real request. No such implementation was added in Step 08A.
3. Run only the approved bounded tranche. Report actual requests, all charged bytes, retained/eligible groups, normalized-file bytes, peak RSS, elapsed time, failures and usable independent/script yield.
4. Review measured yield and human effort before allocating more. Preserve the original population, absence and direction targets unless the user explicitly revises them. This resource note changes none of those acceptance gates.

What: plan a bounded resource envelope. Why: larger retention and human review have costs that a successful small download does not measure. When: offline Step 08A, before any Step 08B approval. Where: this local host and new private artifacts. Who: the project owner approves resources; the future worker enforces them; reviewers supply measured effort. How: use read-only host facts and saved aggregate counts, then label every extrapolation and proposed stop explicitly.
