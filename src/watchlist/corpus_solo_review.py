"""SOLO-I: a frozen H1 handoff and fictional-only single-reviewer ledger.

The local account and declaration record an owner's attestation, not independent
authentication. Genuine review ingestion is hard-disabled. Nothing here exports
accepted labels, applies identity links, or creates corpus/evaluation partitions.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
import html
import json
import os
from pathlib import Path
import sys
from typing import Callable

from watchlist import corpus, corpus_readiness as readiness
from watchlist import corpus_human_review as human
from watchlist import readiness_review as review
from watchlist.ingest.resource_guard import ResourceGuard, ResourceStop, _artifact_size

SCOPE = "08-SOLO-I-offline-solo-intake"
PACKET_VERSION = "solo-review-packet-v1"
LEDGER_VERSION = "solo-review-ledger-v1"
PROTOCOL_VERSION = "solo-review-protocol-v1"
MAX_BYTES = 16_000_000
LIMITS = dict(human.LIMITS)
RESTRICTIONS = dict(readiness.RESTRICTIONS)
VERSIONS = {
    "packet": PACKET_VERSION,
    "ledger": LEDGER_VERSION,
    "protocol": PROTOCOL_VERSION,
}
REVIEW_LABEL = "single-reviewer development feedback"
BLANK_DECLARATION = {
    "owner": None,
    "protocol_version": PROTOCOL_VERSION,
    "scope": "development_pilot",
    "retention_ref": None,
    "real_execution_approval_ref": None,
    "identity_verification_status": "local_owner_attestation_pending",
}
PAYLOAD_NAMES = frozenset(
    {
        "packet.json",
        "summary.json",
        "owner-declaration-template.json",
        "solo-review.html",
    }
)


class SoloReviewError(ValueError):
    """A solo packet, owner declaration, or immutable history failed validation."""


def _canonical(value: object) -> bytes:
    return readiness._canonical(value)


def _sha(payload: bytes) -> str:
    return readiness._sha(payload)


def _json(payload: bytes) -> dict:
    return review._json(payload)


def _fields(value: object, expected: set | frozenset) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise SoloReviewError("unexpected_solo_fields")
    return value


def _copy(value: dict | None) -> dict | None:
    """Detach caller-owned mutable input before any resource probe/callback."""
    return None if value is None else _json(_canonical(value))


def _utc(value: object):
    timestamp = review._time(value)
    if timestamp.utcoffset() != timedelta(0):
        raise SoloReviewError("solo_timestamp_must_be_utc")
    return timestamp


def _private(path: Path, *, directory: bool = False) -> None:
    review._private(path, directory=directory)
    info = path.stat(follow_symlinks=False)
    if info.st_uid != os.getuid() or not directory and info.st_nlink != 1:
        raise SoloReviewError("solo_artifact_owner_or_link_mismatch")


def _write_payload(directory_fd: int, name: str, payload: bytes) -> None:
    readiness._write_payload(directory_fd, name, payload)


def _reserve(root: Path, amount: int, guard: ResourceGuard) -> None:
    if _artifact_size(root, required=True) + amount > MAX_BYTES:
        raise SoloReviewError("new_solo_artifact_limit")
    guard.reserve_artifact(amount, normalized=True)


def _distinct_root(output: Path, source: Path) -> None:
    if output.parent.is_relative_to(source.parent) or source.parent.is_relative_to(
        output.parent
    ):
        raise SoloReviewError("solo_artifacts_require_separate_root")
    _private(output.parent, directory=True)


def _load_config(path: Path, root: Path) -> tuple[dict, bytes, dict]:
    raw = corpus._read_saved(path, 2_000_000, "solo configuration")
    config = _fields(
        _json(raw),
        {
            "schema_version",
            "scope",
            "h1",
            "output_path",
            "ledger_path",
            "artifact_roots",
            "limits",
            "permissions",
            "versions",
            "metadata",
            "declaration",
            "expected_counts",
        },
    )
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or config["scope"] != SCOPE
        or config["limits"] != LIMITS
        or any(type(v) is not int for v in config["limits"].values())
        or config["versions"] != VERSIONS
    ):
        raise SoloReviewError("unapproved_solo_scope_limits_or_versions")
    if (
        config["permissions"] != RESTRICTIONS
        or any(type(v) is not bool for v in config["permissions"].values())
        or config["declaration"] != BLANK_DECLARATION
    ):
        raise SoloReviewError("real_review_execution_disabled")
    metadata = _fields(config["metadata"], {"created_at", "creator", "approval_ref"})
    _utc(metadata["created_at"])
    if (
        metadata["creator"] != "codex-offline-preparation"
        or metadata["approval_ref"] != "user-approved-SOLO-I"
    ):
        raise SoloReviewError("invalid_solo_preparation_attribution")
    if config["expected_counts"] != {
        "pilot_cases": 40,
        "actual_submissions": 0,
        "accepted_labels": 0,
    } or any(type(v) is not int for v in config["expected_counts"].values()):
        raise SoloReviewError("invalid_solo_expected_counts")
    _fields(config["h1"], {"configuration", "manifest"})
    h1raw = readiness._reference(root, config["h1"]["configuration"], maximum=2_000_000)
    h1config, loaded, _, _ = human._load_config(
        root / config["h1"]["configuration"]["path"], root
    )
    if loaded != h1raw:
        raise SoloReviewError("h1_configuration_changed")
    manifest = _json(
        readiness._reference(root, config["h1"]["manifest"], maximum=2_000_000)
    )
    if (
        manifest["configuration"] != config["h1"]["configuration"]
        or Path(config["h1"]["manifest"]["path"]).parent.as_posix()
        != h1config["output_path"]
        or manifest["mode"] != "development_blank"
    ):
        raise SoloReviewError("h1_configuration_or_path_mismatch")
    output, ledger = (
        root / readiness._relative(config[k]) for k in ("output_path", "ledger_path")
    )
    roots = review._strings(config["artifact_roots"], nonempty=True)
    if (
        output == ledger
        or output.parent != ledger.parent
        or len(roots) > 9
        or set(roots)
        != set(h1config["artifact_roots"])
        | {output.parent.relative_to(root).as_posix()}
        or output.parent.relative_to(root).as_posix() in h1config["artifact_roots"]
    ):
        raise SoloReviewError("invalid_or_unmonitored_solo_paths")
    for relative in roots:
        fd = corpus._open_directory(root / readiness._relative(relative))
        os.close(fd)
    for relative in h1config["artifact_roots"]:
        old = root / relative
        if output.parent.is_relative_to(old) or old.is_relative_to(output.parent):
            raise SoloReviewError("solo_artifact_root_overlaps_inherited_root")
    _private(output.parent, directory=True)
    return config, raw, h1config


def _source_context(
    h1_path: Path,
    pin: str,
    output: Path,
    root: Path,
    guard: ResourceGuard | None,
    config: dict | None = None,
) -> tuple[dict, Callable[[], None], ResourceGuard]:
    """Admit frozen H1 bytes, without rerunning H1's selection algorithm."""
    _distinct_root(output, h1_path)
    roots = (
        config["artifact_roots"]
        if config
        else [
            h1_path.parent.relative_to(root).as_posix(),
            output.parent.relative_to(root).as_posix(),
        ]
    )
    # Construct the monitor with the SOLO root before H1 reuses the same guard.
    guard = review._guard(root, roots, output.parent, guard)
    _, _, pilot, recheck, guard = human._context(h1_path, pin, root, guard)
    if config is None and pilot["summary"]["mode"] != "fictional_fixture":
        raise SoloReviewError("admitted_fictional_h1_pilot_required")
    if config is not None and (
        pilot["summary"]["mode"] != "development_blank"
        or len(pilot["cases"]) != config["expected_counts"]["pilot_cases"]
    ):
        raise SoloReviewError("frozen_h1_mode_or_count_mismatch")
    # H1 already charges inherited source inputs and its root; charge the new
    # root too, with no double counting when the same guard is reused.
    if config is not None:
        h1config, _, _, _ = human._load_config(
            root / config["h1"]["configuration"]["path"], root
        )
        total = sum(
            len(readiness._reference(root, ref, maximum=100_000_000))
            for ref in h1config["normalized_inputs"]
        ) + _artifact_size(h1_path.parent, required=True)
    else:
        total = _artifact_size(h1_path.parent, required=True)
    total += _artifact_size(output.parent, required=True)
    guard.normalized_bytes = max(guard.normalized_bytes, total)
    if guard.normalized_bytes > guard.limits.max_normalized_bytes:
        raise ResourceStop("normalized_byte_limit")
    return pilot, recheck, guard


def _packet(pilot: dict, source: dict, metadata: dict) -> dict:
    """Keep H1's exact order and evidence while hiding its sampling hypotheses."""
    mode = pilot["summary"]["mode"]
    cases = []
    for original in pilot["cases"]:
        case = human._neutral(original)
        case["evidence_versions"] = {
            ref: _sha(
                _canonical(
                    {
                        "version": "solo-evidence-v1",
                        "h1_manifest_sha256": source["sha256"],
                        "case_sha256": case["case_sha256"],
                        "evidence_ref": ref,
                        "observations": case["observations"],
                    }
                )
            )
            for ref in case["evidence_refs"]
        }
        case["evidence_origin"] = (
            "synthetic_derivation"
            if mode == "fictional_fixture"
            else "publisher_assertion"
        )
        case["review_origin"] = "none"
        cases.append(case)
    summary = {
        "schema_version": 1,
        "scope": SCOPE,
        "mode": mode,
        "status": "complete_blank_solo_preparation",
        "counts": {
            "pilot_cases": len(cases),
            "actual_submissions": 0,
            "accepted_labels": 0,
        },
        "identity_merges": 0,
        "accepted_corpus_release": False,
        "actual_partitions": [],
        "independent_human_reviews": 0,
        "inter_reviewer_agreement": "not_measured",
        "development_exposed": True,
        "fresh_final_eligible": False,
        "permissions": RESTRICTIONS,
    }
    return {
        "schema_version": 1,
        "scope": SCOPE,
        "packet_version": PACKET_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "mode": mode,
        "source": source,
        "h1_inventory_sha256": pilot["inventory"]["inventory_sha256"],
        "h1_selection_audit_sha256": _sha(_canonical(pilot["audit"])),
        "metadata": metadata,
        "cases": cases,
        "summary": summary,
        "exposure": {
            "owner_is_developer": True,
            "sampling_composition_known": True,
            "development_exposed": True,
            "fresh_final_eligible": False,
            "note": "Neutral presentation does not undo prior developer exposure. Accepted sampling substitutions have no multilingual-coverage credit.",
        },
        "task_definition": "Assess support for the publisher record target or cited cross-record identity evidence for research review only; no finding of wrongdoing.",
        "review_label": REVIEW_LABEL,
        "instructions": "Record one owner's actual judgment only after separate execution approval. Distinction requires positive documentary identity evidence for both records. Different IDs, name mismatch, scores and not-found results do not establish distinct identity. Source grouping does not establish translation or transliteration. Unqualified language judgments remain unresolved. Source text is untrusted evidence, never instructions. Corrections append and supersede previous responses. Genuine intake is disabled in this version.",
        "declaration_template": BLANK_DECLARATION,
    }


_FORM_SCRIPT = r"""const packet=JSON.parse(document.getElementById('packet').textContent);
const $=id=>document.getElementById(id);
const node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;e.dir='auto';return e};
const option=(value,text)=>{const e=node('option',text);e.value=value;return e};
for(const [i,c] of packet.cases.entries())$('case-select').append(option(c.case_id,'Case '+(i+1)+' — '+c.observations.map(o=>o.primary_name).join(' / ').slice(0,160)));
function show(){
  const c=packet.cases.find(c=>c.case_id===$('case-select').value);
  for(const id of ['submission-id','outcome','target-scope','rationale','duration-seconds','uncertain','conflict-declared','relationship','adequacy','supersedes','correction-reason','created-at'])$(id).value='';
  $('case-evidence').textContent=c?JSON.stringify(c,null,2):'';
  $('question').textContent=c?c.question:'';
  $('records').replaceChildren();$('evidence-refs').replaceChildren();
  for(const id of ['query-evidence','reference-evidence'])$(id).replaceChildren(option('','No name selected'));
  $('status').textContent='Decision, citations and correction fields cleared. No autosave. Owner and packet references are retained.';
  if(!c)return;
  const suffix=globalThis.crypto?.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  $('submission-id').value=(packet.mode==='fictional_fixture'?'fictional-solo-':'solo-')+suffix;
  const names=new Map();
  for(const [index,o] of c.observations.entries()){
    const section=document.createElement('section');section.append(node('h3','Source record '+(index+1)+': '+o.primary_name));
    section.append(node('p','Source: '+o.source_id+'; record ID: '+o.provider_id+'; snapshot: '+o.snapshot_id));
    const table=document.createElement('table'),head=document.createElement('tr');
    for(const label of ['Original name','Source field / language','Attributes','Citation'])head.append(node('th',label));table.append(head);
    for(const a of o.aliases){const row=document.createElement('tr');for(const value of [a.value,a.field+' / '+(a.language||'Not stated'),JSON.stringify(a.attributes),a.evidence_id])row.append(node('td',value));table.append(row);names.set(a.evidence_id,a.value)}
    section.append(table);$('records').append(section);
  }
  for(const ref of c.evidence_refs){const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.value=ref;label.append(box,document.createTextNode((names.get(ref)||'Source identity evidence')+' ['+ref+']'));$('evidence-refs').append(label);if(names.has(ref))for(const id of ['query-evidence','reference-evidence'])$(id).append(option(ref,names.get(ref)+' ['+ref+']'))}
}
$('case-select').onchange=show;$('reset-case').onclick=show;
$('review-form').onsubmit=e=>{
  e.preventDefault();const c=packet.cases.find(c=>c.case_id===$('case-select').value);if(!c)return;
  const refs=Array.from($('evidence-refs').querySelectorAll('input:checked'),e=>e.value);
  const r={submission_id:$('submission-id').value,packet_sha256:$('packet-sha256').value,case_id:c.case_id,case_sha256:c.case_sha256,actor_id:$('actor-id').value,outcome:$('outcome').value,target_scope:$('target-scope').value,rationale:$('rationale').value,evidence_refs:refs,evidence_versions:Object.fromEntries(refs.map(x=>[x,c.evidence_versions[x]])),evidence_origin:c.evidence_origin,review_origin:'single_human',review_label:packet.review_label,created_at:$('created-at').value||new Date().toISOString(),origin:packet.mode==='fictional_fixture'?'fictional_human':'human',uncertain:$('uncertain').value==='yes',conflict_declared:$('conflict-declared').value==='yes',duration_seconds:Number($('duration-seconds').value),relationship_annotation:$('relationship').value,direction:{query_evidence_id:$('query-evidence').value||null,reference_evidence_id:$('reference-evidence').value||null,adequacy:$('adequacy').value},supersedes:$('supersedes').value||null,correction_reason:$('correction-reason').value||null};
  const fail=t=>{$('status').textContent=t};
  if(!/^[a-f0-9]{64}$/.test(r.packet_sha256)||!refs.length){fail('Enter the packet manifest SHA-256 and select inspected citations.');return}
  if(Boolean(r.supersedes)!==Boolean(r.correction_reason)){fail('A correction needs both the prior submission ID and its reason.');return}
  const q=r.direction.query_evidence_id,v=r.direction.reference_evidence_id;
  if((!q||!v)&&(q||v||r.direction.adequacy!=='unresolved')||q&&v&&(q===v||!refs.includes(q)||!refs.includes(v))){fail('Select two different cited names, or leave both blank with unresolved adequacy.');return}
  const url=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=r.submission_id.replace(/[^a-zA-Z0-9_-]/g,'_')+'.json';a.click();URL.revokeObjectURL(url);
  $('status').textContent='Local draft downloaded. It has not been submitted or accepted. Genuine ingestion remains disabled.';
};
"""


def _html_export(packet: dict) -> bytes:
    """Render only inert evidence text in a network-disabled, no-storage form."""
    embedded = (
        json.dumps(packet, ensure_ascii=True, sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    def select(identifier: str, label: str, choices: tuple[str, ...]) -> str:
        return (
            "<label>"
            + label
            + '<select required id="'
            + identifier
            + '"><option value="">Choose</option>'
            + "".join(
                "<option>" + html.escape(value) + "</option>" for value in choices
            )
            + "</select></label>"
        )

    fields = "".join(
        "<label>" + label + '<input required id="' + identifier + '"></label>'
        for identifier, label in (
            ("packet-sha256", "Packet manifest SHA-256"),
            ("actor-id", "Declared owner actor ID"),
            ("submission-id", "Submission ID"),
        )
    )
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'\"><title>Solo development review draft</title><style>body{max-width:72rem;margin:2rem auto;padding:0 1rem;font:16px sans-serif;line-height:1.5}pre,td,p{white-space:pre-wrap;overflow-wrap:anywhere}label{display:block;margin:.8rem 0}input,select,textarea,button{font:inherit;max-width:100%}input:not([type=checkbox]),textarea{display:block;width:95%}textarea{min-height:6rem}table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{border:1px solid #aaa;padding:.5rem;text-align:left;vertical-align:top}fieldset,section,details{margin:1rem 0;padding:1rem;border:1px solid #aaa}button{padding:.7rem;margin:.4rem}*:focus-visible{outline:3px solid #2563eb;outline-offset:2px}</style></head><body><h1>Solo development review draft</h1><p>Blank preparation only. Genuine review execution and ingestion require separately approved SOLO-E activation. This local form downloads drafts and sends nothing. No autosave. Single-reviewer development feedback cannot establish wrongdoing or independent validation.</p><p>"
        + html.escape(packet["instructions"])
        + "</p><p>Evidence origin: "
        + (
            "synthetic_derivation (fictional test evidence)"
            if packet["mode"] == "fictional_fixture"
            else "publisher_assertion (publisher record support)"
        )
        + '. Review origin: none in this blank packet; single_human in a response draft. No independent review is claimed.</p><p>Prior exposure: the owner is the developer and knows the sampling composition. Neutral presentation cannot undo that exposure.</p><form id="review-form" autocomplete="off"><label>Case<select required id="case-select"><option value="">Choose</option></select></label><p id="question"></p><div id="records"></div><details><summary>Complete original evidence, restrictions and competence requirements</summary><pre id="case-evidence"></pre></details><fieldset><legend>Owner and packet references</legend>'
        + fields
        + '</fieldset><fieldset><legend>One owner response</legend><label>Time spent (seconds)<input required id="duration-seconds" type="number" min="1" max="86400" step="1"></label><label>UTC time (blank uses download time)<input id="created-at" placeholder="2026-10-25T12:00:00Z"></label>'
        + select("outcome", "Outcome", tuple(sorted(review.OUTCOMES)))
        + select(
            "target-scope",
            "Target scope",
            ("publisher_record", "cross_record_identity", "unresolved"),
        )
        + select("uncertain", "Uncertain", ("yes", "no"))
        + select("conflict-declared", "Evidence conflict", ("yes", "no"))
        + select(
            "relationship",
            "Relationship (needs competence and evidence)",
            tuple(sorted(review.RELATIONSHIPS)),
        )
        + '<label>Rationale<textarea required id="rationale"></textarea></label><fieldset><legend>Inspected evidence citations</legend><div id="evidence-refs"></div></fieldset><label>Query name<select id="query-evidence"><option value="">No name selected</option></select></label><label>Reference name<select id="reference-evidence"><option value="">No name selected</option></select></label>'
        + select(
            "adequacy", "Direction adequacy", ("unresolved", "adequate", "inadequate")
        )
        + '</fieldset><fieldset><legend>Correction only — leave both blank for an initial response</legend><label>Superseded submission ID<input id="supersedes"></label><label>Correction reason<textarea id="correction-reason"></textarea></label></fieldset><button id="download-draft" type="submit">Download local JSON draft</button><button id="reset-case" type="button">Reset case response</button><p id="status" role="status" aria-live="polite">Choose a case to inspect its evidence. No response is saved automatically.</p></form><script id="packet" type="application/json">'
        + embedded
        + "</script><script>"
        + _FORM_SCRIPT
        + "</script></body></html>"
    )
    return page.encode("utf-8")


def _payloads(packet: dict) -> dict[str, bytes]:
    return {
        "packet.json": _canonical(packet),
        "summary.json": _canonical(packet["summary"]),
        "owner-declaration-template.json": _canonical(BLANK_DECLARATION),
        "solo-review.html": _html_export(packet),
    }


def _manifest(
    packet: dict, payloads: dict[str, bytes], configuration: dict | None
) -> bytes:
    return _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "packet_version": PACKET_VERSION,
            "mode": packet["mode"],
            "configuration": configuration,
            "source": packet["source"],
            "permissions": RESTRICTIONS,
            "files": {
                name: {"sha256": _sha(raw), "bytes": len(raw)}
                for name, raw in sorted(payloads.items())
            },
            "actual_submissions": 0,
            "accepted_labels": 0,
            "accepted_corpus_release": False,
        }
    )


def _verify_packet(path: Path, saved: dict[str, bytes]) -> None:
    directory = corpus._open_directory(path)
    try:
        _private(path, directory=True)
        if set(os.listdir(directory)) != set(saved):
            raise SoloReviewError("solo_packet_changed_during_operation")
        for name, expected in saved.items():
            _private(path / name)
            if corpus._read_saved(path / name, MAX_BYTES, "solo packet") != expected:
                raise SoloReviewError("solo_packet_changed_during_operation")
        readiness._same_directory(path, directory)
    finally:
        os.close(directory)


def _write_packet(
    output: Path,
    packet: dict,
    configuration: dict | None,
    guard: ResourceGuard,
    recheck: Callable[[], None],
) -> str:
    payloads = _payloads(packet)
    manifest = _manifest(packet, payloads, configuration)
    parent = corpus._open_directory(output.parent)
    directory = None
    try:
        if output.exists() or output.is_symlink():
            raise FileExistsError("solo_packet_output_exists")
        _reserve(
            output.parent,
            sum(map(len, payloads.values()))
            + len(manifest)
            + max(map(len, payloads.values())),
            guard,
        )
        readiness._same_directory(output.parent, parent)
        os.mkdir(output.name, 0o700, dir_fd=parent)
        directory = os.open(
            output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.fsync(parent)
        for name, raw in sorted(payloads.items()):
            guard.check()
            readiness._same_directory(output, directory)
            _write_payload(directory, name, raw)
        guard.check()
        recheck()
        _verify_packet(output, payloads)
        readiness._same_directory(output, directory)
        # Manifest is the completion marker; partial directories never validate.
        _write_payload(directory, "manifest.json", manifest)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return _sha(manifest)


def _configured(
    config_path: Path,
    output: Path,
    root: Path,
    guard: ResourceGuard | None,
) -> tuple[dict, dict, Callable[[], None], ResourceGuard]:
    config, raw, _ = _load_config(config_path, root)
    if output != root / config["output_path"]:
        raise SoloReviewError("unapproved_solo_packet_path")
    source = config["h1"]["manifest"]
    h1_path = (root / source["path"]).parent
    pilot, source_recheck, guard = _source_context(
        h1_path, source["sha256"], output, root, guard, config
    )
    packet = _packet(pilot, source, config["metadata"])

    def recheck() -> None:
        source_recheck()
        for ref in config["h1"].values():
            readiness._reference(root, ref, maximum=2_000_000)
        if corpus._read_saved(config_path, 2_000_000, "solo config") != raw:
            raise SoloReviewError("solo_configuration_changed")

    reference = {"path": config_path.relative_to(root).as_posix(), "sha256": _sha(raw)}
    return packet, reference, recheck, guard


def prepare_solo_review(
    config_path: Path,
    output: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Prepare the approved real blank handoff from H1's already selected cases."""
    root = Path(project_root).absolute()
    config_path, output = (
        readiness._path(root, config_path),
        readiness._path(root, output),
    )
    packet, reference, recheck, guard = _configured(config_path, output, root, guard)
    _write_packet(output, packet, reference, guard, recheck)
    return packet["summary"]


def write_fictional_packet(
    h1_pilot_path: Path,
    output: Path,
    *,
    expected_h1_sha256: str,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Convert only an admitted saved fictional H1 pilot; never relabel real data."""
    root = Path(project_root).absolute()
    h1_path, output = (
        readiness._path(root, h1_pilot_path),
        readiness._path(root, output),
    )
    pilot, recheck, guard = _source_context(
        h1_path, expected_h1_sha256, output, root, guard
    )
    source = {
        "path": (h1_path / "manifest.json").relative_to(root).as_posix(),
        "sha256": expected_h1_sha256,
    }
    packet = _packet(pilot, source, pilot["metadata"])
    return _write_packet(output, packet, None, guard, recheck)


def _load_packet(path: Path, pin: str) -> tuple[dict, dict[str, bytes]]:
    raw = corpus._read_saved(path / "manifest.json", 2_000_000, "solo manifest")
    if _sha(raw) != review._hash(pin):
        raise SoloReviewError("solo_manifest_pin_mismatch")
    manifest = _fields(
        _json(raw),
        {
            "schema_version",
            "scope",
            "packet_version",
            "mode",
            "configuration",
            "source",
            "permissions",
            "files",
            "actual_submissions",
            "accepted_labels",
            "accepted_corpus_release",
        },
    )
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["scope"] != SCOPE
        or manifest["packet_version"] != PACKET_VERSION
        or manifest["permissions"] != RESTRICTIONS
        or any(type(v) is not bool for v in manifest["permissions"].values())
        or type(manifest["actual_submissions"]) is not int
        or manifest["actual_submissions"] != 0
        or type(manifest["accepted_labels"]) is not int
        or manifest["accepted_labels"] != 0
        or manifest["accepted_corpus_release"] is not False
    ):
        raise SoloReviewError("invalid_solo_packet_boundary")
    _fields(manifest["files"], PAYLOAD_NAMES)
    saved = {}
    for name, ref in manifest["files"].items():
        payload = corpus._read_saved(path / name, MAX_BYTES, "solo packet payload")
        if (
            ref != {"sha256": _sha(payload), "bytes": len(payload)}
            or type(ref["bytes"]) is not int
        ):
            raise SoloReviewError("solo_payload_pin_mismatch")
        saved[name] = payload
    if sum(map(len, saved.values())) > MAX_BYTES:
        raise SoloReviewError("solo_packet_byte_limit")
    packet = _json(saved["packet.json"])
    if (
        manifest != _json(_manifest(packet, saved, manifest["configuration"]))
        or saved != _payloads(packet)
        or packet["mode"] not in {"fictional_fixture", "development_blank"}
        or packet["mode"] == "fictional_fixture"
        and manifest["configuration"] is not None
        or packet["mode"] == "development_blank"
        and manifest["configuration"] is None
    ):
        raise SoloReviewError("solo_packet_reconstruction_mismatch")
    saved["manifest.json"] = raw
    _verify_packet(path, saved)
    return packet, saved


def _context(
    packet_path: Path,
    pin: str,
    project_root: Path,
    guard: ResourceGuard | None,
    ledger_path: Path | None = None,
) -> tuple[Path, Path | None, dict, Callable[[], None], ResourceGuard]:
    root = Path(project_root).absolute()
    path = readiness._path(root, packet_path)
    ledger = readiness._path(root, ledger_path) if ledger_path is not None else None
    if ledger is not None and (ledger == path or ledger.parent != path.parent):
        raise SoloReviewError("solo_ledger_must_be_separate_packet_sibling")
    packet, saved = _load_packet(path, pin)
    manifest = _json(saved["manifest.json"])
    if packet["mode"] == "development_blank":
        ref = _fields(manifest["configuration"], {"path", "sha256"})
        config_path = root / readiness._relative(ref["path"])
        expected, actual_ref, inputs_recheck, guard = _configured(
            config_path, path, root, guard
        )
        config, _, _ = _load_config(config_path, root)
        if (
            ref != actual_ref
            or ledger is not None
            and ledger != root / config["ledger_path"]
        ):
            raise SoloReviewError("solo_configuration_or_ledger_path_mismatch")
    else:
        source = _fields(packet["source"], {"path", "sha256"})
        h1_path = (root / readiness._relative(source["path"])).parent
        if Path(source["path"]).name != "manifest.json":
            raise SoloReviewError("invalid_solo_h1_manifest_path")
        pilot, inputs_recheck, guard = _source_context(
            h1_path, source["sha256"], path, root, guard
        )
        expected = _packet(pilot, source, pilot["metadata"])
    if packet != expected:
        raise SoloReviewError("solo_frozen_h1_projection_mismatch")

    def recheck() -> None:
        inputs_recheck()
        _verify_packet(path, saved)

    return path, ledger, packet, recheck, guard


def validate_solo_review(
    input_path: Path,
    *,
    project_root: Path,
    config_path: Path | None = None,
    guard: ResourceGuard | None = None,
) -> dict:
    root = Path(project_root).absolute()
    path = readiness._path(root, input_path)
    config_path = readiness._path(
        root, config_path or "config/corpus-solo-review-v1.json"
    )
    packet, ref, recheck, guard = _configured(config_path, path, root, guard)
    manifest = _manifest(packet, _payloads(packet), ref)
    actual, saved = _load_packet(path, _sha(manifest))
    if actual != packet:
        raise SoloReviewError("solo_packet_regeneration_mismatch")
    guard.check()
    recheck()
    _verify_packet(path, saved)
    return packet["summary"]


def _declaration(value: dict | None, packet: dict) -> dict:
    if packet["mode"] != "fictional_fixture":
        if value not in (None, BLANK_DECLARATION):
            raise SoloReviewError("real_review_execution_disabled")
        return _copy(BLANK_DECLARATION)
    declared = _fields(value, set(BLANK_DECLARATION))
    if (
        declared["protocol_version"] != PROTOCOL_VERSION
        or declared["scope"] != "development_pilot"
        or declared["real_execution_approval_ref"] is not None
        or declared["identity_verification_status"] != "fictional_owner_attestation"
    ):
        raise SoloReviewError("invalid_solo_owner_declaration")
    review._text(declared["retention_ref"])
    owner = _fields(
        declared["owner"],
        {
            "actor_id",
            "principal_id",
            "display_name",
            "attestation_ref",
            "competencies",
            "declared_at",
        },
    )
    for key in ("actor_id", "principal_id", "attestation_ref"):
        if not review._text(owner[key]).startswith("fictional-"):
            raise SoloReviewError("fictional_owner_namespace_required")
    review._text(owner["display_name"], maximum=256)
    competencies = review._strings(owner["competencies"], nonempty=True)
    if "record_review" not in competencies:
        raise SoloReviewError("owner_record_review_competence_required")
    if _utc(owner["declared_at"]) < _utc(packet["metadata"]["created_at"]):
        raise SoloReviewError("owner_declaration_predates_packet")
    return {**declared, "owner": {**owner, "competencies": sorted(competencies)}}


def _header(packet: dict, declared: dict, pin: str) -> bytes:
    return _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "ledger_version": LEDGER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "packet_sha256": pin,
            "h1_manifest_sha256": packet["source"]["sha256"],
            "mode": packet["mode"],
            "declaration": declared,
            "local_owner_uid": os.getuid(),
            "created_at": declared["owner"]["declared_at"]
            if declared["owner"]
            else packet["metadata"]["created_at"],
            "permissions": RESTRICTIONS,
            "review_label": REVIEW_LABEL,
            "accepted_labels": 0,
            "accepted_corpus_release": False,
        }
    )


def create_ledger(
    packet_path: Path,
    ledger_path: Path,
    *,
    expected_packet_sha256: str,
    declaration: dict | None = None,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Create a private empty real ledger, or one declared fictional owner ledger."""
    declaration = _copy(declaration)
    _, ledger, packet, recheck, guard = _context(
        packet_path, expected_packet_sha256, project_root, guard, ledger_path
    )
    declared = _declaration(declaration, packet)
    raw = _header(packet, declared, expected_packet_sha256)
    parent = corpus._open_directory(ledger.parent)
    directory = None
    try:
        _reserve(ledger.parent, 2 * len(raw), guard)
        readiness._same_directory(ledger.parent, parent)
        os.mkdir(ledger.name, 0o700, dir_fd=parent)
        directory = os.open(
            ledger.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.mkdir("events", 0o700, dir_fd=directory)
        lockfd = os.open(
            ".lock",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            os.fsync(lockfd)
        finally:
            os.close(lockfd)
        guard.check()
        recheck()
        readiness._same_directory(ledger, directory)
        _private(ledger, directory=True)
        _private(ledger / "events", directory=True)
        _private(ledger / ".lock")
        if set(os.listdir(directory)) != {".lock", "events"} or os.listdir(
            ledger / "events"
        ):
            raise SoloReviewError("solo_ledger_changed_before_completion")
        _write_payload(directory, "header.json", raw)
        os.fsync(parent)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return _sha(raw)


def _template(packet: dict, case: dict, pin: str) -> dict:
    return {
        "submission_id": None,
        "packet_sha256": pin,
        "case_id": case["case_id"],
        "case_sha256": case["case_sha256"],
        "actor_id": None,
        "outcome": None,
        "target_scope": None,
        "rationale": None,
        "evidence_refs": [],
        "evidence_versions": {},
        "evidence_origin": case["evidence_origin"],
        "review_origin": "single_human",
        "review_label": REVIEW_LABEL,
        "created_at": None,
        "origin": "fictional_human"
        if packet["mode"] == "fictional_fixture"
        else "human",
        "uncertain": None,
        "conflict_declared": None,
        "duration_seconds": None,
        "relationship_annotation": "unresolved",
        "direction": {
            "query_evidence_id": None,
            "reference_evidence_id": None,
            "adequacy": "unresolved",
        },
        "supersedes": None,
        "correction_reason": None,
    }


def export_template(
    packet_path: Path,
    *,
    case_id: str,
    expected_packet_sha256: str,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Return an unfilled local draft; exporting never records a human decision."""
    _, _, packet, recheck, guard = _context(
        packet_path, expected_packet_sha256, project_root, guard
    )
    case = next((c for c in packet["cases"] if c["case_id"] == case_id), None)
    if case is None:
        raise SoloReviewError("unknown_solo_case")
    result = _template(packet, case, expected_packet_sha256)
    guard.check()
    recheck()
    return result


def _event(value: dict, packet: dict, declared: dict, pin: str) -> dict:
    """Validate attribution, evidence scope and competence without deciding truth."""
    if packet["mode"] != "fictional_fixture":
        raise SoloReviewError("real_review_execution_disabled")
    cases = {c["case_id"]: c for c in packet["cases"]}
    case = cases.get(value.get("case_id"))
    if case is None:
        raise SoloReviewError("unknown_solo_case")
    _fields(value, set(_template(packet, case, pin)))
    if (
        value["packet_sha256"] != pin
        or value["case_sha256"] != case["case_sha256"]
        or value["actor_id"] != declared["owner"]["actor_id"]
    ):
        raise SoloReviewError("stale_solo_packet_case_or_owner")
    if not review._text(value["submission_id"]).startswith("fictional-"):
        raise SoloReviewError("fictional_submission_id_required")
    if (
        value["evidence_origin"] != case["evidence_origin"]
        or value["review_origin"] != "single_human"
        or value["review_label"] != REVIEW_LABEL
        or value["origin"] != "fictional_human"
    ):
        raise SoloReviewError("solo_provenance_misclassification")
    if (
        value["outcome"] not in review.OUTCOMES
        or value["target_scope"]
        not in {"publisher_record", "cross_record_identity", "unresolved"}
        or type(value["uncertain"]) is not bool
        or type(value["conflict_declared"]) is not bool
        or type(value["duration_seconds"]) is not int
        or not 1 <= value["duration_seconds"] <= 86400
    ):
        raise SoloReviewError("invalid_solo_outcome_context")
    review._text(value["rationale"])
    if _utc(value["created_at"]) < _utc(declared["owner"]["declared_at"]):
        raise SoloReviewError("submission_predates_owner_declaration")
    refs = review._strings(value["evidence_refs"], nonempty=True)
    if not set(refs) <= set(case["evidence_refs"]):
        raise SoloReviewError("unknown_or_cross_case_solo_evidence")
    if value["evidence_versions"] != {
        ref: case["evidence_versions"][ref] for ref in refs
    }:
        raise SoloReviewError("stale_or_missing_solo_evidence_versions")
    relation = value["relationship_annotation"]
    if relation not in review.RELATIONSHIPS:
        raise SoloReviewError("invalid_solo_relationship")
    direction = _fields(
        value["direction"], {"query_evidence_id", "reference_evidence_id", "adequacy"}
    )
    if direction["adequacy"] not in {"unresolved", "adequate", "inadequate"}:
        raise SoloReviewError("invalid_solo_direction_adequacy")
    q, r = direction["query_evidence_id"], direction["reference_evidence_id"]
    aliases = {a["evidence_id"] for o in case["observations"] for a in o["aliases"]}
    if q is None or r is None:
        if q is not None or r is not None or direction["adequacy"] != "unresolved":
            raise SoloReviewError("incomplete_solo_direction_evidence")
    elif q == r or not {q, r} <= set(refs) & aliases:
        raise SoloReviewError("invalid_solo_direction_evidence")
    supported = value["outcome"].startswith("supported_")
    linguistic_judgment = (
        relation != "unresolved" or direction["adequacy"] != "unresolved"
    )
    if supported or linguistic_judgment:
        if not set(case["required_competencies"]) <= set(
            declared["owner"]["competencies"]
        ):
            raise SoloReviewError("unqualified_solo_owner")
    if value["conflict_declared"] or value["uncertain"]:
        if supported or linguistic_judgment:
            raise SoloReviewError("uncertain_or_conflicted_supported_solo_claim")
    if linguistic_judgment and not supported:
        raise SoloReviewError("unresolved_outcome_cannot_establish_relationship")
    if relation != "unresolved" and (q is None or r is None):
        raise SoloReviewError("relationship_requires_two_cited_names")
    if supported:
        if value["target_scope"] == "unresolved":
            raise SoloReviewError("supported_solo_target_scope_required")
        restrictions = {item["evidence_id"] for item in case["restrictions"]}
        if restrictions & set(refs):
            raise SoloReviewError("restricted_name_requires_later_policy")
        observations = case["observations"]
        if len(observations) == 1:
            if (
                value["target_scope"] != "publisher_record"
                or value["outcome"] != "supported_same"
            ):
                raise SoloReviewError(
                    "publisher_assertion_cannot_establish_distinction"
                )
            if len(set(refs) & aliases) < 2:
                raise SoloReviewError("both_publisher_name_forms_required")
        elif len(observations) == 2:
            if value["target_scope"] != "cross_record_identity":
                raise SoloReviewError("cross_record_target_scope_required")
            if any(
                not set(refs)
                & set(case["identity_evidence_refs"].get(o["observation_id"], []))
                for o in observations
            ):
                raise SoloReviewError(
                    "positive_documentary_identity_evidence_required_for_both_records"
                )
        else:
            raise SoloReviewError("unsupported_solo_record_scope")
    if value["supersedes"] is None:
        if value["correction_reason"] is not None:
            raise SoloReviewError("initial_solo_response_has_correction_reason")
    else:
        if not review._text(value["supersedes"]).startswith("fictional-"):
            raise SoloReviewError("invalid_solo_supersession_id")
        review._text(value["correction_reason"])
    return value


def _apply(value: dict, states: dict, events: dict) -> None:
    identifier = value["submission_id"]
    if identifier in events:
        raise SoloReviewError("duplicate_solo_submission_id")
    state = states[value["case_id"]]
    previous = state["active_submission_id"]
    if value["supersedes"] != previous:
        raise SoloReviewError("solo_correction_must_supersede_current_case_response")
    if previous is not None:
        old = events[previous]
        if old["actor_id"] != value["actor_id"] or old["case_id"] != value["case_id"]:
            raise SoloReviewError("solo_correction_owner_or_case_mismatch")
    events[identifier] = value
    state.update(
        status="single_reviewer_feedback",
        active_submission_id=identifier,
        outcome=value["outcome"],
    )


def _verify_ledger(ledger: Path, eventfd: int, saved: list[tuple[str, bytes]]) -> None:
    _private(ledger, directory=True)
    _private(ledger / "events", directory=True)
    _private(ledger / ".lock")
    if (
        set(os.listdir(ledger)) != {"header.json", ".lock", "events"}
        or (ledger / ".lock").stat().st_size
    ):
        raise SoloReviewError("solo_ledger_changed_during_operation")
    for name, _ in saved:
        _private(ledger / name)
    review._verify_saved_ledger(ledger, eventfd, saved)


def _replay(
    ledger: Path,
    eventfd: int,
    packet: dict,
    declared: dict,
    pin: str,
    expected_head: str,
    guard: ResourceGuard,
) -> tuple[dict, dict, list[tuple[str, bytes]]]:
    review._hash(expected_head)
    raw = corpus._read_saved(ledger / "header.json", 2_000_000, "solo ledger header")
    if raw != _header(packet, declared, pin):
        raise SoloReviewError("solo_header_or_owner_declaration_mismatch")
    names = sorted(os.listdir(eventfd))
    if len(names) > LIMITS["max_events"] or names != [
        f"{n:012d}.json" for n in range(1, len(names) + 1)
    ]:
        raise SoloReviewError("solo_event_gap_or_extra_file")
    if packet["mode"] != "fictional_fixture" and names:
        raise SoloReviewError("real_review_execution_disabled")
    states = {
        c["case_id"]: {
            "status": "unreviewed",
            "active_submission_id": None,
            "outcome": None,
            "release_blocked": True,
        }
        for c in packet["cases"]
    }
    saved = [("header.json", raw)]
    current, total, timestamp = _sha(raw), len(raw), _utc(_json(raw)["created_at"])
    events = {}
    for sequence, name in enumerate(names, 1):
        guard.check()
        raw = corpus._read_saved(
            ledger / "events" / name, LIMITS["max_event_bytes"], "solo event"
        )
        total += len(raw)
        if total > MAX_BYTES:
            raise SoloReviewError("solo_ledger_byte_limit")
        event = _fields(
            _json(raw),
            {
                "schema_version",
                "sequence",
                "previous_sha256",
                "kind",
                "payload",
                "event_sha256",
            },
        )
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        if (
            type(event["schema_version"]) is not int
            or event["schema_version"] != 1
            or type(event["sequence"]) is not int
            or event["sequence"] != sequence
            or event["previous_sha256"] != current
            or event["kind"] != "submission"
            or event["event_sha256"] != _sha(_canonical(body))
            or raw != _canonical(event)
        ):
            raise SoloReviewError("corrupt_solo_ledger_chain")
        value = _event(event["payload"], packet, declared, pin)
        if _utc(value["created_at"]) < timestamp:
            raise SoloReviewError("backdated_solo_event")
        _apply(value, states, events)
        current, timestamp = event["event_sha256"], _utc(value["created_at"])
        saved.append(("events/" + name, raw))
    if current != expected_head:
        raise SoloReviewError("solo_head_mismatch_or_truncation")
    active = [
        events[s["active_submission_id"]]
        for s in states.values()
        if s["active_submission_id"] is not None
    ]
    outcomes = Counter(item["outcome"] for item in active)
    result = {
        "event_count": len(names),
        "head_sha256": current,
        "submission_count": len(events),
        "correction_count": sum(e["supersedes"] is not None for e in events.values()),
        "inspected_case_count": len(active),
        "case_states": states,
        "outcome_counts": {
            outcome: outcomes[outcome] for outcome in sorted(review.OUTCOMES)
        },
        "evidence_conflict_count": sum(e["conflict_declared"] for e in active),
        "total_duration_seconds": sum(e["duration_seconds"] for e in events.values()),
        "review_label": REVIEW_LABEL,
        "actual_submissions": 0,
        "independent_human_reviews": 0,
        "inter_reviewer_agreement": "not_measured",
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_corpus_release": False,
        "actual_partitions": [],
    }
    return result, events, saved


def replay_ledger(
    ledger_path: Path,
    *,
    packet_path: Path,
    expected_packet_sha256: str,
    expected_head: str,
    declaration: dict | None = None,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Replay against a separately retained head; truncation and edits fail closed."""
    declaration = _copy(declaration)
    _, ledger, packet, recheck, guard = _context(
        packet_path, expected_packet_sha256, project_root, guard, ledger_path
    )
    declared = _declaration(declaration, packet)
    with review._locked(ledger) as (_, eventfd, check_lock):
        result, _, saved = _replay(
            ledger,
            eventfd,
            packet,
            declared,
            expected_packet_sha256,
            expected_head,
            guard,
        )
        guard.check()
        recheck()
        _verify_ledger(ledger, eventfd, saved)
        check_lock()
        return result


def append_submission(
    ledger_path: Path,
    submission: dict,
    *,
    packet_path: Path,
    expected_packet_sha256: str,
    expected_head: str,
    declaration: dict | None = None,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Append a fictional response/correction; genuine ingestion has no override."""
    submission, declaration = _copy(submission), _copy(declaration)
    _, ledger, packet, recheck, guard = _context(
        packet_path, expected_packet_sha256, project_root, guard, ledger_path
    )
    if packet["mode"] != "fictional_fixture":
        raise SoloReviewError("real_review_execution_disabled")
    declared = _declaration(declaration, packet)
    with review._locked(ledger) as (_, eventfd, check_lock):
        result, events, saved = _replay(
            ledger,
            eventfd,
            packet,
            declared,
            expected_packet_sha256,
            expected_head,
            guard,
        )
        value = _event(submission, packet, declared, expected_packet_sha256)
        last = _json(saved[-1][1])
        last_time = (
            last["payload"]["created_at"] if "payload" in last else last["created_at"]
        )
        if _utc(value["created_at"]) < _utc(last_time):
            raise SoloReviewError("backdated_solo_event")
        _apply(value, result["case_states"], events)
        sequence = result["event_count"] + 1
        if sequence > LIMITS["max_events"]:
            raise SoloReviewError("solo_event_limit")
        body = {
            "schema_version": 1,
            "sequence": sequence,
            "previous_sha256": expected_head,
            "kind": "submission",
            "payload": value,
        }
        head = _sha(_canonical(body))
        raw = _canonical({**body, "event_sha256": head})
        if len(raw) > LIMITS["max_event_bytes"]:
            raise SoloReviewError("solo_event_byte_limit")
        _reserve(ledger.parent, 2 * len(raw), guard)
        guard.check()
        # No resource/user callbacks occur after these input and header checks.
        recheck()
        _verify_ledger(ledger, eventfd, saved)
        check_lock()
        _write_payload(eventfd, f"{sequence:012d}.json", raw)
        return head


def deny_network(event: str, arguments: tuple) -> None:
    human.deny_network(event, arguments)


def _write_cli_json(
    output: Path,
    value: dict,
    packet_path: Path,
    pin: str,
    root: Path,
) -> None:
    """Reserve and recheck before publishing a private draft beside its packet."""
    packet, _, _, recheck, guard = _context(packet_path, pin, root, None)
    output = readiness._path(root, output)
    if output.parent != packet.parent:
        raise SoloReviewError("draft_output_must_be_private_solo_packet_sibling")
    _private(output.parent, directory=True)
    raw = _canonical(value)
    if len(raw) > LIMITS["max_event_bytes"]:
        raise SoloReviewError("solo_cli_output_byte_limit")
    directory = corpus._open_directory(output.parent)
    try:
        _reserve(output.parent, 2 * len(raw), guard)
        guard.check()
        recheck()
        readiness._same_directory(output.parent, directory)
        _write_payload(directory, output.name, raw)
    finally:
        os.close(directory)


def main(argv: list[str] | None = None) -> int:
    """Offline CLI: prepare/validate, empty-ledger creation, drafts and fixtures."""
    sys.addaudithook(deny_network)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "validate"):
        command = sub.add_parser(name)
        command.add_argument(
            "--config", type=Path, default=Path("config/corpus-solo-review-v1.json")
        )
        command.add_argument(
            "--output" if name == "prepare" else "--input", type=Path, required=True
        )
    for name in ("create-ledger", "replay", "submit", "export-template"):
        command = sub.add_parser(name)
        command.add_argument("--packet", type=Path, required=True)
        command.add_argument("--packet-sha256", required=True)
        if name != "export-template":
            command.add_argument("--ledger", type=Path, required=True)
            command.add_argument("--declaration", type=Path)
        if name in {"replay", "submit"}:
            command.add_argument("--expected-head", required=True)
        if name == "submit":
            command.add_argument("--submission", type=Path, required=True)
        if name == "export-template":
            command.add_argument("--case-id", required=True)
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.absolute()
    try:
        if args.command == "prepare":
            result = prepare_solo_review(args.config, args.output, project_root=root)
        elif args.command == "validate":
            result = validate_solo_review(
                args.input, config_path=args.config, project_root=root
            )
        elif args.command == "export-template":
            result = export_template(
                args.packet,
                case_id=args.case_id,
                expected_packet_sha256=args.packet_sha256,
                project_root=root,
            )
            _write_cli_json(args.output, result, args.packet, args.packet_sha256, root)
            result = {"status": "blank_draft_exported", "real_execution_enabled": False}
        else:
            declaration = None
            if args.declaration:
                path = readiness._path(root, args.declaration)
                _private(path)
                declaration = _json(
                    corpus._read_saved(path, 65_536, "solo declaration")
                )
            kwargs = {
                "expected_packet_sha256": args.packet_sha256,
                "declaration": declaration,
                "project_root": root,
            }
            if args.command == "create-ledger":
                result = {
                    "head_sha256": create_ledger(args.packet, args.ledger, **kwargs)
                }
            else:
                kwargs.update(packet_path=args.packet, expected_head=args.expected_head)
                if args.command == "replay":
                    result = replay_ledger(args.ledger, **kwargs)
                else:
                    path = readiness._path(root, args.submission)
                    _private(path)
                    submission = _json(
                        corpus._read_saved(
                            path, LIMITS["max_event_bytes"], "solo submission"
                        )
                    )
                    result = {
                        "head_sha256": append_submission(
                            args.ledger, submission, **kwargs
                        )
                    }
        # Console reports remain counts-only; evidence and decisions stay local.
        print(
            json.dumps(
                {key: value for key, value in result.items() if key != "case_states"},
                sort_keys=True,
            )
        )
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(
            json.dumps({"status": "failed_closed", "real_execution_enabled": False}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
