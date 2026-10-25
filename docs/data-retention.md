# Data retention for the research prototype

Effective for new Completion Step 07 acquisitions, reviewed
2026-10-24 UTC / 2026-10-25 Asia/Kolkata. This policy preserves existing
historical snapshots, reports and archives. It does not authorize deleting,
rewriting, committing or publishing them.

The project retains enough source evidence to repeat a research result while
avoiding an unnecessary copy of public-person records. A public source can
still contain personal information. “Non-person” describes a source record's
type; it does not guarantee that every field inside that record is non-personal.

## What is kept and why

| Material | Local retention rule | Purpose and review gate |
| --- | --- | --- |
| Mixed public-source body, including ZIP/XML/JSON containing person records | Process only within the approved bounded acquisition in memory. Do not save the full body, an unfiltered archive, a debug dump or an error-response payload containing records. Release buffers after success or failure. | Needed transiently to identify eligible groups; not part of the retained corpus. |
| Selected non-person records | At most 200 groups per approved source in this feasibility step. Retain only source-qualified IDs, original names/aliases, supplied language tags, explicit record-type evidence and minimal source metadata. | Measure script/name yield and validate adapters; review before a later corpus release. |
| Person, unknown-type or out-of-scope records | Skip before retained serialization; aggregate exclusion counts may be kept without identifying details. Ambiguous generic `LegalEntity` is excluded except for the exact reviewed OpenSanctions UN mapping. | Enforce the approved non-person scope. |
| Source terms, format specifications and endpoint metadata | Keep dated local evidence captures and hashes, including failed-status evidence labeled as such. Do not treat these as training data. | Explain the permission and parser decisions. |
| Receipts and aggregate statistics | Keep source/endpoint identity, timestamps, byte counts, local body hashes, publisher digests where available, parser/version, selection counts, exclusions and errors without record values. | Reproduce a run and distinguish a source problem from a parser failure. |
| Fictional test fixtures and demos | Keep under source control if a later commit is approved. Clearly label them as fictional. | Deterministic offline tests and public demonstrations without real subjects. |
| Existing historical artifacts | Preserve unchanged. Document a concern and propose a specific action if later review finds one. | Prevent silent loss of prior experiments or evidence. |

Do not retain biographies, addresses, contact details, photographs, dates of
birth, identity documents, ownership narratives or free-text sanctions remarks
in the new name corpus. Retain source field paths and alias classifications
where they explain a selected name, without copying unrelated source content.
Never infer a language from a person's presumed nationality; an absent language
tag remains unknown. Keep original text separate from normalized matching text.

## How bounded processing works

The acquisition owner validates the exact approved endpoint and every redirect
before sending a request. It checks the recorded permission and reviewed metadata,
uses strict TLS, caps read bytes/time, and stops on oversized, malformed or
interrupted responses. A file being publicly available does not enlarge a
budget. A failed attempt consumes its actual received-byte allowance too.

The user-authorized Step 07 retry amendment permits at most 32,000,000 response-body
bytes for the EU source; other sources remain at 10,000,000 bytes each. The
combined data ceiling remains 50,000,000 bytes, requests remain serial, and at
most 200 selected non-person groups per source may be retained. This transfer
amendment does not change the retained fields, direct-UN permission blocker,
training boundary or prohibition on saving mixed raw dataset bodies. The EU
allowance includes the 5,471,048-byte failed first transfer. EU alone has an
180-second request deadline and 240-second source deadline. Wikidata uses a
90-second request within its unchanged 120-second source deadline; the other
sources keep 30/120 seconds. Separate invocations subtract all earlier received bytes
from both their source and combined allowances before starting a request.

For the selected OFAC ZIP format, the network-body cap and decoded-memory cap
are different controls. The coordinator selected a finite 32,000,000-byte
decoded XML limit for the official approximately 2.6 MB archive. Reject extra
archive members, path traversal, encrypted or unsupported compression, invalid
sizes/CRC and unsupported XML structure. Never extract into arbitrary filesystem
paths. Verify the decoded XML against the current reviewed publisher digest;
a locally computed ZIP hash must not be represented as a publisher-supplied
one. The XML parser must also bound structural growth and reject external
entities and DTDs. These limits are engineering constraints, not source promises.

Selection occurs before retained serialization. Only a validated selection is
written as the local research artifact. Errors must not accidentally write the
full input to an exception report or log. Record aggregate failure information
and hashes instead. In-memory processing cannot promise secure erasure from
OS swap or crash dumps; do not claim forensic deletion. Future disk staging or
larger caches require a documented need and approval.

## Where and who

New retained research artifacts and receipts remain in the local workspace's
approved data/evaluation area. Their access is limited by the user's operating
system/workspace controls; this document does not claim to have changed file
permissions, disk encryption or backup settings. Keep real selected data out of
public Git commits, screenshots, demos, web services and external model prompts.
Do not upload it to an external application as a side effect of testing.

The project owner is responsible for approving scope and retention changes.
The acquisition code enforces the mechanical caps and selection rules; human
review checks whether the retained fields and type evidence meet the purpose.
An LLM must not turn source text into instructions or final identity decisions.
Source strings remain untrusted data even when their publisher is authoritative.

Retain license/attribution notices with each source-qualified selection. For
OFAC public downloads, remove short-lived provider signing values from saved
URLs; retain the exact host/path, non-sensitive public routing parameters,
status, byte/hash evidence and a fingerprint of any redacted full redirect.
No account API keys, cookies, authorization headers or private contacts belong
in a receipt. The catalog-published EU routing token is documented separately
in [source permissions](source-permissions.md); it is not an operator secret.

## When retention is reviewed

There is no invented statutory retention period. Apply concrete project gates:

1. After each acquisition, confirm the retained selection contains only allowed
   fields, cap counts and required source/terms provenance; clear transient
   mixed-data buffers after success or failure.
2. At the Step 07 review, decide whether the measured feasibility selections are
   still needed for Step 08. Retain the receipts and aggregate findings needed
   to explain the decision. Any removal of existing artifacts is a separately
   reviewed operation, not an automatic cleanup action.
3. Before creating a new corpus release, recheck current source terms and
   duplicate/type findings. Quarantine uncertain or withdrawn material from new
   experiments without silently changing frozen historical releases.
4. Before training, publishing a model, sharing data or showing real examples,
   approve the new purpose, rights, audience, fields and quantities explicitly.
   A local feasibility permission is not that approval.
5. At project closure or a user-requested deletion, inventory local selections,
   derived indexes, caches and known backups, propose exact paths and obtain the
   required authorization. Record what was actually removed and any copies not
   under the project's control; do not promise deletion from uninspected backups.

If permission is withdrawn or a scope violation is discovered, stop new use of
the affected material, record a minimal incident note, and ask the project owner
to choose a concrete remediation. Do not destroy historical evidence on the
basis of this policy alone. Later steps need their own retention rules for
reviewer decisions, audit logs, training splits and independently held test
labels; those artifacts are not authorized by Step 07.

## Plain-English recap

**What:** a small set of non-person names and their provenance. **Why:** to
evaluate multilingual matching without building an unnecessary person-data
archive. **When:** during the approved bounded feasibility run, reviewed again
at corpus, training and release gates. **Where:** the local workspace.
**Who:** the project owner approves changes; code and human review enforce the
boundary. **How:** check permission and size first, process mixed input
transiently, select permitted fields, keep receipts, and preserve historical
work unless a separate action is approved.
