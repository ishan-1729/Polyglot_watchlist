"""H1-I neutral pilot preparation and fictional-only human-intake mechanics.

Declarations and local access receipts document claimed authorization, not human
authentication. Genuine review execution remains hard-disabled. No submission,
adjudication or correction grants a label, identity merge, release or partition.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
import html
import json
import os
from pathlib import Path
import sys
from typing import Callable

from watchlist import corpus, corpus_readiness as readiness
from watchlist import corpus_adjudication as adjudication
from watchlist import readiness_review as review
from watchlist.ingest.resource_guard import ResourceGuard, ResourceStop, _artifact_size
from watchlist.scripts import script_set

SCOPE = "08B-H1-I-offline-human-intake"
PILOT_VERSION = "human-review-pilot-v1"
LEDGER_VERSION = "human-intake-ledger-v1"
PROTOCOL_VERSION = "human-intake-protocol-v1"
MAX_BYTES = 16_000_000
LIMITS = {
    "max_new_artifact_bytes": MAX_BYTES,
    "max_pilot_cases": 40,
    "max_events": 10_000,
    "max_event_bytes": 65_536,
    "session_seconds": 3600,
}
RESTRICTIONS = dict(readiness.RESTRICTIONS)
SELECTION = {
    "version": "pilot-selection-v1",
    "per_category": 20,
    "preferred_strata": {
        "latin_arabic_organizations": 4,
        "latin_cyrillic_organizations": 8,
        "latin_han_organizations": 2,
        "other_organizations": 4,
        "vessels": 2,
    },
    "source_minimum": 2,
    "shortfall_policy": "report_then_hash_fill_same_category",
}
BLANK_DECLARATION = {
    "owner": None,
    "actors": [],
    "access": [],
    "protocol_version": PROTOCOL_VERSION,
    "scope": "development_pilot",
    "retention_ref": None,
    "real_execution_approval_ref": None,
    "identity_verification_status": "external_prerequisite_unmet",
}
ROLES = ("reviewer_a", "reviewer_b", "adjudicator")
QUESTION = "What relationship, if any, does the cited evidence support between these name forms and their source records? Preserve uncertainty and distinguish source alias assertions from cross-record identity."
PAYLOAD_NAMES = frozenset(
    {
        "inventory.json",
        "pilot-audit.json",
        "cases.jsonl",
        "reviewer-a.json",
        "reviewer-b.json",
        "reviewer-a.html",
        "reviewer-b.html",
        "onboarding.json",
        "summary.json",
    }
)
_TOKEN = object()


class HumanReviewError(ValueError):
    """A local preparation or fictional intake boundary failed."""


def _canonical(value: object) -> bytes:
    return readiness._canonical(value)


def _sha(payload: bytes) -> str:
    return readiness._sha(payload)


def _json(payload: bytes) -> dict:
    return review._json(payload)


def _fields(value: object, expected: set | frozenset) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise HumanReviewError("unexpected_human_intake_fields")
    return value


def _seal(value: dict, key: str) -> dict:
    return {**value, key: _sha(_canonical(value))}


class Pilot(Mapping[str, object]):
    """Admitted immutable pilot; detached exports cannot authorize a new fixture."""

    __slots__ = ("_encoded", "_graph")

    def __init__(
        self, value: dict, graph: adjudication.FamilyGraph, *, token: object = None
    ) -> None:
        if token is not _TOKEN:
            raise HumanReviewError("admitted_pilot_required")
        object.__setattr__(self, "_encoded", _canonical(value))
        object.__setattr__(self, "_graph", graph)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("pilot_is_immutable")

    def to_dict(self) -> dict:
        return _json(self._encoded)

    def __getitem__(self, key: str) -> object:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())


def _stratum(case: dict, observations: dict[str, dict]) -> str:
    if any(
        observations[oid]["entity_type"] == "vessel" for oid in case["observation_ids"]
    ):
        return "vessels"
    witness_scripts = {
        frozenset(script_set(a["value"]))
        for oid in case["observation_ids"]
        for a in observations[oid]["aliases"]
        if a["evidence_id"] in case["evidence_refs"]
    }
    for script, name in (
        ("HAN", "han"),
        ("ARABIC", "arabic"),
        ("CYRILLIC", "cyrillic"),
    ):
        if {frozenset({"LATIN"}), frozenset({script})} <= witness_scripts:
            return "latin_" + name + "_organizations"
    return "other_organizations"


def _neutral(case: dict) -> dict:
    return {
        key: case[key]
        for key in (
            "case_id",
            "case_sha256",
            "question",
            "observations",
            "evidence_refs",
            "identity_evidence_refs",
            "required_competencies",
            "restrictions",
        )
    } | {
        "source_text_is_untrusted": True,
        "response": None,
        "development_exposed": True,
        "fresh_final_eligible": False,
        "unresolved_context": {
            "component_ids": case["component_ids"],
            "graph_quarantined": case["graph_quarantined"],
            "identity_confirmed": False,
        },
    }


def build_pilot(
    graph: adjudication.FamilyGraph,
    *,
    packet_path: Path,
    expected_packet_sha256: str,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> Pilot:
    """Select at most 20+20 unique existing tasks, with explicit diagnostic fill.

    Hash ordering is fixed before answers. Conservative dependence and uncertain
    components discourage family reuse; no resulting count asserts independence.
    The complete source inventory is committed without duplicating all names.
    """
    data, rows, _ = adjudication._admitted(graph)
    root = Path(project_root).absolute()
    packet = readiness._path(root, packet_path)
    guard = review._guard(
        root, [packet.parent.relative_to(root).as_posix()], packet.parent, guard
    )
    packet_bytes, packet_summary, source_cases = review._load_packet(
        packet, expected_packet_sha256, guard
    )
    if (
        expected_packet_sha256 != data["packet_sha256"]
        or packet_summary["c1_manifest_sha256"] != data["c1_manifest_sha256"]
    ):
        raise HumanReviewError("pilot_graph_packet_binding_mismatch")
    observations = {o["observation_id"]: o for o in rows}
    components = adjudication._Components(len(rows))
    for group in data["dependence_groups"] + [q["members"] for q in data["quarantine"]]:
        for member in group[1:]:
            components.join(group[0], member)
    family = {o["observation_id"]: components.root(i) for i, o in enumerate(rows)}
    candidates = []
    seen_pairs = set()
    for source in sorted(source_cases.values(), key=lambda c: c["case_id"]):
        graph._check()
        if source["kind"] not in {"proposed_positive", "negative_candidate"}:
            continue
        pair = tuple(source["observation_ids"])
        if source["kind"] == "negative_candidate":
            if pair in seen_pairs:
                raise HumanReviewError("duplicate_negative_candidate_pair")
            seen_pairs.add(pair)
        category = "positive" if source["kind"] == "proposed_positive" else "negative"
        candidates.append(
            {
                "source": source,
                "category": category,
                "stratum": _stratum(source, observations),
                "families": sorted({family[oid] for oid in pair}),
                "sources": sorted({observations[oid]["source_id"] for oid in pair}),
                "order": _sha(
                    _canonical(
                        [SELECTION["version"], data["graph_sha256"], source["case_id"]]
                    )
                ),
            }
        )
    inventory_base = {
        "schema_version": 1,
        "pilot_version": PILOT_VERSION,
        "mode": data["mode"],
        "source_packet_sha256": expected_packet_sha256,
        "c1_manifest_sha256": data["c1_manifest_sha256"],
        "graph_sha256": data["graph_sha256"],
        "source_ledger_head_sha256": data["ledger_head_sha256"],
        "candidate_set_sha256": _sha(_canonical([c["source"] for c in candidates])),
        "counts": {
            "observations": len(rows),
            "available_positive": sum(c["category"] == "positive" for c in candidates),
            "available_negative": sum(c["category"] == "negative" for c in candidates),
        },
        "selection": SELECTION,
        "development_exposed": True,
        "fresh_final_eligible": False,
        "accepted_labels": 0,
    }
    inventory = _seal(inventory_base, "inventory_sha256")
    inventory["adjudicator_export_id"] = "handoff-" + _sha(
        _canonical([inventory["inventory_sha256"], "adjudicator"])
    )
    selected, trace = [], []
    used, family_uses, source_uses = set(), Counter(), Counter()
    shortages = {}

    def take(pool: list[dict], count: int, category: str, requested: str) -> int:
        chosen = 0
        while chosen < count:
            graph._check()
            remaining = [c for c in pool if c["source"]["case_id"] not in used]
            if not remaining:
                break
            candidate = min(
                remaining,
                key=lambda c: (
                    sum(family_uses[f] for f in c["families"]),
                    -sum(
                        max(0, SELECTION["source_minimum"] - source_uses[s])
                        for s in c["sources"]
                    ),
                    c["order"],
                    c["source"]["case_id"],
                ),
            )
            used.add(candidate["source"]["case_id"])
            selected.append(candidate)
            family_uses.update(candidate["families"])
            source_uses.update(candidate["sources"])
            trace.append(
                {
                    "c2_case_id": candidate["source"]["case_id"],
                    "category": category,
                    "requested_stratum": requested,
                    "actual_stratum": candidate["stratum"],
                    "family_reuse": sum(
                        family_uses[f] > 1 for f in candidate["families"]
                    ),
                }
            )
            chosen += 1
        return chosen

    for category in ("positive", "negative"):
        pool = [c for c in candidates if c["category"] == category]
        shortages[category] = {}
        for stratum in (
            "latin_han_organizations",
            "latin_arabic_organizations",
            "latin_cyrillic_organizations",
            "vessels",
            "other_organizations",
        ):
            target = SELECTION["preferred_strata"][stratum]
            actual = take(
                [c for c in pool if c["stratum"] == stratum], target, category, stratum
            )
            shortages[category][stratum] = target - actual
        count = sum(c["category"] == category for c in selected)
        take(
            pool,
            SELECTION["per_category"] - count,
            category,
            "explicit_same_category_shortfall_fill",
        )
    cases = []
    for candidate in selected:
        graph._check()
        source = candidate["source"]
        originals = [observations[oid] for oid in source["observation_ids"]]
        case_id = (
            "fictional-pilot-" if data["mode"] == "fictional_fixture" else "pilot-"
        ) + _sha(
            _canonical(
                [PILOT_VERSION, inventory["inventory_sha256"], source["case_id"]]
            )
        )
        case = {
            **source,
            "case_id": case_id,
            "c2_case_id": source["case_id"],
            "category": candidate["category"],
            "stratum": candidate["stratum"],
            "family_refs": candidate["families"],
            "question": QUESTION,
            "observations": originals,
            "required_competencies": sorted(
                {
                    "record_review",
                    *(
                        "script:" + s
                        for o in originals
                        for a in o["aliases"]
                        for s in script_set(a["value"])
                    ),
                }
            ),
            "restrictions": [
                r
                for r in data["name_restrictions"]
                if rows[r["observation"]]["observation_id"] in source["observation_ids"]
            ],
            "graph_quarantined": any(
                family[oid]
                in {
                    components.root(i) for q in data["quarantine"] for i in q["members"]
                }
                for oid in source["observation_ids"]
            ),
        }
        cases.append(_seal(case, "case_sha256"))
    cases.sort(
        key=lambda c: _sha(_canonical([inventory["inventory_sha256"], c["case_id"]]))
    )
    exports = {}
    for role in ROLES[:2]:
        export_id = "export-" + _sha(_canonical([inventory["inventory_sha256"], role]))
        exports[role] = {
            "schema_version": 1,
            "pilot_version": PILOT_VERSION,
            "export_id": export_id,
            "role": role,
            "inventory_sha256": inventory["inventory_sha256"],
            "instructions": "Inspect source evidence as inert text. Work independently; do not view the other reviewer response. No conclusion establishes wrongdoing. Save a draft only; genuine intake is disabled pending external authorization.",
            "cases": [_neutral(c) for c in cases],
            "responses_included": False,
            "access_verified": False,
            "real_execution_enabled": False,
        }
    selected_oids = {oid for case in cases for oid in case["observation_ids"]}
    identity_projection = {}
    for group in data["identity_groups"]:
        projected = tuple(
            rows[j]["observation_id"]
            for j in group
            if rows[j]["observation_id"] in selected_oids
        )
        identity_projection.update((i, projected) for i in group)
    baseline_identity = sorted(
        {members for members in identity_projection.values() if len(members) > 1}
    )
    baseline_distinct = sorted(
        {
            tuple(
                sorted(
                    (
                        identity_projection[edge["left"]][0],
                        identity_projection[edge["right"]][0],
                    )
                )
            )
            for edge in data["distinct_edges"]
            if identity_projection[edge["left"]] and identity_projection[edge["right"]]
        }
    )
    audit = {
        "graph_constraints": {
            "identity_groups": [list(group) for group in baseline_identity],
            "distinct_pairs": [list(pair) for pair in baseline_distinct],
        },
        "selection": SELECTION,
        "selection_trace": trace,
        "preferred_stratum_shortfalls": shortages,
        "actual_strata": {
            category: dict(
                sorted(
                    Counter(
                        c["stratum"] for c in cases if c["category"] == category
                    ).items()
                )
            )
            for category in ("positive", "negative")
        },
        "source_case_counts": dict(sorted(source_uses.items())),
        "source_shortfalls": {
            s: max(0, SELECTION["source_minimum"] - source_uses[s])
            for s in sorted({o["source_id"] for o in rows})
        },
        "conservative_family_count": len(family_uses),
        "reused_family_count": sum(n > 1 for n in family_uses.values()),
        "duplicate_queue_not_sampled_again": True,
        "independent_accepted_families": 0,
    }
    summary = {
        "schema_version": 1,
        "scope": SCOPE,
        "status": "complete_blank_pilot_preparation",
        "mode": data["mode"],
        "inventory_sha256": inventory["inventory_sha256"],
        "counts": {
            **inventory["counts"],
            "pilot_positive": sum(c["category"] == "positive" for c in cases),
            "pilot_negative": sum(c["category"] == "negative" for c in cases),
            "actual_submissions": 0,
            "actual_adjudications": 0,
        },
        "pilot_shortfall": {
            category: 20 - sum(c["category"] == category for c in cases)
            for category in ("positive", "negative")
        },
        "preferred_stratum_shortfalls": shortages,
        "actual_strata": audit["actual_strata"],
        "source_case_counts": audit["source_case_counts"],
        "source_shortfalls": audit["source_shortfalls"],
        "conservative_family_count": audit["conservative_family_count"],
        "reused_family_count": audit["reused_family_count"],
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_corpus_release": False,
        "permissions": RESTRICTIONS,
        "actual_partitions": [],
    }
    onboarding = {
        "declaration_template": BLANK_DECLARATION,
        "protocol_version": PROTOCOL_VERSION,
        "required_external_actions": [
            "Name an accountable owner and separately approve pilot execution, population, time/budget and retention.",
            "Verify two independent human reviewers and a separate adjudicator; keep identity documents outside this workspace.",
            "Verify declared language/domain competence for every displayed script; script does not identify a language.",
            "Give each reviewer only their neutral export through an owner-approved access process; retain separate delivery receipts.",
            "Review coverage shortages before execution. JSON actor rows, local files and receipts are not authentication.",
            "Real intake remains disabled in this version; a separately approved activation implementation is required.",
        ],
        "draft_workflow": [
            "Open only the assigned reviewer HTML locally.",
            "Select a case and inspect original names, qualifiers and source provenance.",
            "After separate execution approval, enter a decision and citations and download a local draft.",
            "Use export-template for a blank JSON copy; never edit immutable pilot or ledger files.",
            "Only isolated fictional fixtures can use the current submit/adjudicate CLI.",
        ],
    }
    value = {
        "inventory": inventory,
        "cases": cases,
        "audit": audit,
        "exports": exports,
        "onboarding": onboarding,
        "summary": summary,
        "metadata": packet_summary["metadata"],
    }
    if len(_canonical(value)) > MAX_BYTES:
        raise HumanReviewError("pilot_expansion_byte_limit")
    guard.check()
    review._verify_packet_saved(packet, expected_packet_sha256, packet_bytes)
    graph._verify()
    return Pilot(value, graph, token=_TOKEN)


_FORM_SCRIPT = r"""const packet=JSON.parse(document.getElementById('packet').textContent);
const $=id=>document.getElementById(id);
const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n};
const choice=(value,label)=>{const o=node('option',label);o.value=value;return o};
const names=c=>c.observations.flatMap((o,i)=>o.aliases.map(a=>({...a,record:i+1})));
const field=(parent,label,value)=>{parent.append(node('dt',label),node('dd',typeof value==='string'?value:JSON.stringify(value)))};
for(const [i,c] of packet.cases.entries()){
  const label=c.observations.map(o=>o.primary_name).join(' / ');
  $('case').append(choice(c.case_id,'Case '+(i+1)+' — '+label.slice(0,140)));
}
function show(){
  const c=packet.cases.find(c=>c.case_id===$('case').value);
  for(const id of ['event','outcome','rationale','duration','uncertain','conflict','scope','relation','adequacy'])$(id).value='';
  for(const id of ['records','citations','context'])$(id).replaceChildren();
  for(const id of ['query','reference'])$(id).replaceChildren(choice('','No name selected'));
  $('question').textContent=c?c.question:'';
  $('case-id').textContent=c?'Case reference: '+c.case_id:'';
  $('evidence').textContent=c?JSON.stringify(c,null,2):'';
  $('case-status').textContent='Decision fields cleared for this case. Owner pin, actor and receipt fields are retained.';
  if(!c)return;
  const suffix=globalThis.crypto?.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  $('event').value=(c.case_id.startsWith('fictional-')?'fictional-submission-':'submission-')+suffix;
  for(const [i,o] of c.observations.entries()){
    const section=document.createElement('section'),dl=document.createElement('dl');
    section.append(node('h3','Source record '+(i+1)+': '+o.primary_name));
    for(const [key,label] of [['source_id','Source'],['snapshot_id','Snapshot'],['provider_id','Provider record ID'],['observation_id','Observation ID'],['source_record_key','Source record key'],['source_role','Source role'],['entity_type','Record type'],['provider_schema','Provider schema'],['classification_basis','Classification basis'],['provider_datasets','Provider datasets'],['provider_topics','Provider topics'],['referents','Provider referents']])field(dl,label,o[key]);
    section.append(dl);
    const table=document.createElement('table'),header=document.createElement('tr');
    for(const label of ['Original name','Source field','Stated language','Source attributes','Evidence ID'])header.append(node('th',label));
    table.append(header);
    for(const a of o.aliases){
      const row=document.createElement('tr');
      for(const value of [a.value,a.field,a.language===null?'Not stated':a.language,JSON.stringify(a.attributes),a.evidence_id])row.append(node('td',value));
      table.append(row);
    }
    section.append(table);$('records').append(section);
  }
  const context=document.createElement('dl');
  field(context,'Unresolved graph context',c.unresolved_context);
  field(context,'Source and name restrictions',c.restrictions);
  field(context,'Required reviewer competence',c.required_competencies);
  field(context,'Source identity evidence references',c.identity_evidence_refs);
  $('context').append(context);
  const byId=new Map(names(c).map(a=>[a.evidence_id,a]));
  for(const id of c.evidence_refs){
    const a=byId.get(id),label=document.createElement('label'),box=document.createElement('input');
    box.type='checkbox';box.value=id;
    const description=a?'Record '+a.record+' name: '+a.value:'Source identity evidence';
    label.append(box,document.createTextNode(description+' ['+id+']'));
    $('citations').append(label,document.createElement('br'));
    if(a)for(const field of ['query','reference'])$(field).append(choice(id,'Record '+a.record+': '+a.value+' ['+id+']'));
  }
}
$('case').onchange=show;
$('form').onsubmit=e=>{
  e.preventDefault();const c=packet.cases.find(c=>c.case_id===$('case').value);if(!c)return;
  const r={submission_id:$('event').value,pilot_sha256:$('pin').value,case_id:c.case_id,case_sha256:c.case_sha256,actor_id:$('actor').value,export_id:packet.export_id,access_receipt_ref:$('receipt').value,outcome:$('outcome').value,rationale:$('rationale').value,evidence_refs:Array.from($('citations').querySelectorAll('input:checked'),x=>x.value),created_at:new Date().toISOString(),origin:c.case_id.startsWith('fictional-')?'fictional_human':'human',uncertain:$('uncertain').value==='yes',conflict_declared:$('conflict').value==='yes',duration_seconds:Number($('duration').value),independent_first_pass:true,identity_scope:$('scope').value,relationship_annotation:$('relation').value,direction:{query_evidence_id:$('query').value||null,reference_evidence_id:$('reference').value||null,adequacy:$('adequacy').value},supersedes:null,correction_reason:null};
  if(!r.evidence_refs.length){alert('Select the evidence you inspected before saving this draft.');return}
  const q=r.direction.query_evidence_id,v=r.direction.reference_evidence_id;
  if((!q||!v)&&(q||v||r.direction.adequacy!=='unresolved')||q&&v&&(q===v||!r.evidence_refs.includes(q)||!r.evidence_refs.includes(v))){alert('Choose two different cited names, or leave both names blank with unresolved adequacy.');return}
  const b=new Blob([JSON.stringify(r,null,2)+'\n'],{type:'application/json'}),u=URL.createObjectURL(b),a=document.createElement('a');
  a.href=u;a.download=r.submission_id+'.json';a.click();URL.revokeObjectURL(u);
  $('case-status').textContent='Local draft downloaded. It has not been submitted or accepted.';
};
"""


def _html_export(export: dict) -> bytes:
    """Use inert escaped text and a constant local form; no network or evaluation."""
    embedded = (
        json.dumps(export, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    def select(name: str, options: tuple[str, ...]) -> str:
        return (
            "<label>"
            + html.escape(name)
            + ' <select required id="'
            + name
            + '"><option value="">Choose</option>'
            + "".join("<option>" + html.escape(o) + "</option>" for o in options)
            + "</select></label><br>"
        )

    fields = "".join(
        "<label>"
        + label
        + ' <input required id="'
        + name
        + '" type="'
        + kind
        + '"></label><br>'
        for name, label, kind in (
            ("pin", "Pilot manifest SHA-256 from owner", "text"),
            ("actor", "Authorized actor ID", "text"),
            ("receipt", "Owner access receipt reference", "text"),
        )
    )
    page = (
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'\"><title>Neutral development review draft</title><style>body{max-width:70rem;margin:2rem auto;padding:0 1rem;font:16px sans-serif;line-height:1.45}pre,td,dd,p{white-space:pre-wrap;overflow-wrap:anywhere}label{display:block;margin:.5rem 0}textarea{width:95%;height:7rem}input,select{max-width:95%;font:inherit}table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{border:1px solid #aaa;padding:.4rem;text-align:left;vertical-align:top}dt{font-weight:bold}dd{margin:0 0 .5rem}section,fieldset,details{margin:1rem 0;padding:1rem;border:1px solid #aaa}button{padding:.7rem;font:inherit}</style><h1>Neutral development review draft</h1><p>Preparation only. Genuine review execution requires separate owner approval, verified people and access. This form downloads a local draft and sends nothing. Current intake rejects real submissions.</p><p>"
        + html.escape(export["instructions"])
        + '</p><form id="form"><fieldset><legend>Owner-provided session references</legend>'
        + fields
        + '</fieldset><label>Case <select required id="case"><option value="">Choose</option></select></label><p>Changing the case clears unsaved decision fields. Download a draft before switching cases.</p><p id="case-status" role="status" aria-live="polite"></p><p id="case-id"></p><p id="question"></p><div id="records"></div><div id="context"></div><details><summary>Original structured evidence</summary><pre id="evidence"></pre></details><fieldset><legend>Independent first-pass draft for the selected case</legend><label>Generated submission ID <input required readonly id="event"></label><label>Time spent in seconds <input required id="duration" type="number" min="1" max="86400" step="1"></label>'
        + select("outcome", tuple(sorted(review.OUTCOMES)))
        + select("uncertain", ("yes", "no"))
        + select("conflict", ("yes", "no"))
        + select(
            "scope", ("source_record_alias", "cross_record_identity", "unresolved")
        )
        + select("relation", tuple(sorted(review.RELATIONSHIPS)))
        + '<label>Rationale<textarea required id="rationale"></textarea></label><fieldset><legend>Inspected evidence citations</legend><div id="citations"></div></fieldset><label>Query name <select id="query"><option value="">No name selected</option></select></label><label>Reference name <select id="reference"><option value="">No name selected</option></select></label>'
        + select("adequacy", ("unresolved", "adequate", "inadequate"))
        + '</fieldset><button>Download local draft</button></form><script type="application/json" id="packet">'
        + embedded
        + "</script><script>"
        + _FORM_SCRIPT
        + "</script></html>"
    )
    return page.encode("utf-8")


def _payloads(value: dict) -> dict[str, bytes]:
    result = {
        "inventory.json": _canonical(
            {**value["inventory"], "metadata": value["metadata"]}
        ),
        "pilot-audit.json": _canonical(value["audit"]),
        "cases.jsonl": b"".join(_canonical(c) for c in value["cases"]),
        "onboarding.json": _canonical(value["onboarding"]),
        "summary.json": _canonical(value["summary"]),
    }
    for role, filename in (("reviewer_a", "reviewer-a"), ("reviewer_b", "reviewer-b")):
        result[filename + ".json"] = _canonical(value["exports"][role])
        result[filename + ".html"] = _html_export(value["exports"][role])
        if sum(map(len, result.values())) > MAX_BYTES:
            raise HumanReviewError("pilot_output_byte_limit")
    return result


def _manifest(payloads: dict[str, bytes], configuration: dict | None) -> bytes:
    summary = _json(payloads["summary.json"])
    return _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "pilot_version": PILOT_VERSION,
            "mode": summary["mode"],
            "configuration": configuration,
            "files": {
                name: {"sha256": _sha(raw), "bytes": len(raw)}
                for name, raw in sorted(payloads.items())
            },
            "inventory_sha256": summary["inventory_sha256"],
            "permissions": RESTRICTIONS,
            "actual_submissions": 0,
            "accepted_labels": 0,
            "accepted_corpus_release": False,
        }
    )


def _write_payload(directory_fd: int, name: str, payload: bytes) -> None:
    readiness._write_payload(directory_fd, name, payload)


def _reserve(root: Path, amount: int, guard: ResourceGuard) -> None:
    if _artifact_size(root, required=True) + amount > MAX_BYTES:
        raise HumanReviewError("new_human_intake_artifact_limit")
    guard.reserve_artifact(amount, normalized=True)


def _write_pilot(
    output: Path,
    payloads: dict[str, bytes],
    manifest: bytes,
    guard: ResourceGuard,
    recheck: Callable[[], None],
) -> None:
    """Never replace existing work; completion follows the final byte checks."""
    parent = corpus._open_directory(output.parent)
    directory = None
    try:
        if output.exists() or output.is_symlink():
            raise FileExistsError("pilot_output_exists")
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
        for name, raw in payloads.items():
            review._private(output / name)
            if corpus._read_saved(output / name, MAX_BYTES, "pilot payload") != raw:
                raise HumanReviewError("pilot_changed_before_completion")
        readiness._same_directory(output, directory)
        if set(os.listdir(directory)) != PAYLOAD_NAMES:
            raise HumanReviewError("unexpected_pilot_files")
        _write_payload(directory, "manifest.json", manifest)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def write_fictional_pilot(
    pilot: Pilot,
    output: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    if type(pilot) is not Pilot or pilot["summary"]["mode"] != "fictional_fixture":
        raise HumanReviewError("admitted_fictional_pilot_required")
    root = Path(project_root).absolute()
    output = readiness._path(root, output)
    guard = review._guard(
        root, [output.parent.relative_to(root).as_posix()], output.parent, guard
    )
    payloads = _payloads(pilot.to_dict())
    manifest = _manifest(payloads, None)
    _write_pilot(output, payloads, manifest, guard, pilot._graph._verify)
    return _sha(manifest)


def _load_config(path: Path, root: Path) -> tuple[dict, bytes, dict, dict]:
    raw = corpus._read_saved(path, 2_000_000, "human intake configuration")
    config = _fields(
        _json(raw),
        {
            "schema_version",
            "scope",
            "c3",
            "output_path",
            "ledger_path",
            "artifact_roots",
            "normalized_inputs",
            "limits",
            "permissions",
            "versions",
            "metadata",
            "expected_counts",
            "selection",
            "declaration",
        },
    )
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or config["scope"] != SCOPE
        or config["limits"] != LIMITS
        or any(type(v) is not int for v in config["limits"].values())
    ):
        raise HumanReviewError("unapproved_human_intake_scope_or_limits")
    if (
        config["permissions"] != RESTRICTIONS
        or any(type(v) is not bool for v in config["permissions"].values())
        or config["declaration"] != BLANK_DECLARATION
    ):
        raise HumanReviewError("real_review_execution_disabled")
    if config["selection"] != SELECTION or config["versions"] != {
        "pilot": PILOT_VERSION,
        "ledger": LEDGER_VERSION,
        "protocol": PROTOCOL_VERSION,
    }:
        raise HumanReviewError("unapproved_human_intake_versions_or_selection")
    metadata = _fields(config["metadata"], {"created_at", "creator", "approval_ref"})
    review._time(metadata["created_at"])
    if (
        metadata["creator"] != "codex-offline-preparation"
        or metadata["approval_ref"] != "user-approved-08B-H1-I"
    ):
        raise HumanReviewError("invalid_human_intake_attribution")
    _fields(config["c3"], {"configuration", "manifest"})
    c3raw = readiness._reference(root, config["c3"]["configuration"], maximum=2_000_000)
    c3config, loaded, c2config = adjudication._load_config(
        root / config["c3"]["configuration"]["path"], root
    )
    if loaded != c3raw:
        raise HumanReviewError("c3_configuration_changed")
    manifest = _json(
        readiness._reference(root, config["c3"]["manifest"], maximum=2_000_000)
    )
    if (
        manifest["configuration"] != config["c3"]["configuration"]
        or Path(config["c3"]["manifest"]["path"]).parent.as_posix()
        != c3config["output_path"]
    ):
        raise HumanReviewError("c3_configuration_or_path_mismatch")
    roots = review._strings(config["artifact_roots"], nonempty=True)
    output, ledger = (
        root / readiness._relative(config[k]) for k in ("output_path", "ledger_path")
    )
    if (
        len(roots) > 8
        or not set(c3config["artifact_roots"]) <= set(roots)
        or output.parent != ledger.parent
        or output == ledger
        or output.parent.relative_to(root).as_posix() not in roots
        or output.parent.relative_to(root).as_posix() in c3config["artifact_roots"]
    ):
        raise HumanReviewError("invalid_or_unmonitored_human_intake_paths")
    for relative in roots:
        fd = corpus._open_directory(root / readiness._relative(relative))
        os.close(fd)
    refs = config["normalized_inputs"]
    if type(refs) is not list or not 1 <= len(refs) <= 32:
        raise HumanReviewError("invalid_human_intake_normalized_inputs")
    provided = {}
    for ref in refs:
        _fields(ref, {"path", "sha256"})
        name = readiness._relative(ref["path"])
        review._hash(ref["sha256"])
        if name in provided:
            raise HumanReviewError("duplicate_normalized_reservation")
        provided[name] = ref["sha256"]
    required = {ref["path"]: ref["sha256"] for ref in c3config["normalized_inputs"]}
    c3directory = Path(c3config["output_path"])
    required.update(
        {
            (c3directory / name).as_posix(): ref["sha256"]
            for name, ref in manifest["files"].items()
        }
    )
    required[config["c3"]["manifest"]["path"]] = config["c3"]["manifest"]["sha256"]
    if not required.items() <= provided.items():
        raise HumanReviewError("normalized_input_coverage_missing")
    counts = _fields(
        config["expected_counts"],
        {
            "observations",
            "available_positive",
            "available_negative",
            "pilot_positive",
            "pilot_negative",
            "actual_submissions",
            "actual_adjudications",
        },
    )
    if (
        any(type(n) is not int or n < 0 for n in counts.values())
        or counts["pilot_positive"] != 20
        or counts["pilot_negative"] != 20
        or counts["actual_submissions"]
        or counts["actual_adjudications"]
    ):
        raise HumanReviewError("invalid_human_intake_expected_counts")
    return config, raw, c3config, c2config


def _account(root: Path, config: dict, guard: ResourceGuard) -> None:
    total = 0
    for ref in config["normalized_inputs"]:
        guard.check()
        total += len(readiness._reference(root, ref, maximum=100_000_000))
    total += _artifact_size((root / config["output_path"]).parent, required=True)
    guard.normalized_bytes = max(guard.normalized_bytes, total)
    if guard.normalized_bytes > guard.limits.max_normalized_bytes:
        raise ResourceStop("normalized_byte_limit")


def _configured(
    root: Path, config: dict, c3config: dict, c2config: dict, guard: ResourceGuard
) -> tuple[Pilot, dict[str, bytes]]:
    _account(root, config, guard)
    adjudication.validate_adjudication(
        root / c3config["output_path"],
        project_root=root,
        config_path=root / config["c3"]["configuration"]["path"],
        guard=guard,
    )
    c1directory = (root / c2config["c1"]["manifest"]["path"]).parent
    c1 = {
        name: corpus._read_saved(c1directory / name, readiness.MAX_BYTES, "C1 evidence")
        for name in readiness.PAYLOAD_NAMES | {"manifest.json"}
    }
    graph = adjudication.build_family_graph(
        c1,
        c1_manifest_sha256=c2config["c1"]["manifest"]["sha256"],
        packet_path=root / c2config["output_path"],
        ledger_path=root / c2config["ledger_path"],
        expected_packet_sha256=c3config["c2"]["manifest"]["sha256"],
        expected_head=c3config["c2"]["expected_head"],
        project_root=root,
        guard=guard,
    )
    actual_graph = _json(
        corpus._read_saved(
            root / c3config["output_path"] / "graph.json", MAX_BYTES, "C3 graph"
        )
    )
    if graph.to_dict() != actual_graph:
        raise HumanReviewError("c3_graph_commitment_mismatch")
    pilot = build_pilot(
        graph,
        packet_path=root / c2config["output_path"],
        expected_packet_sha256=c3config["c2"]["manifest"]["sha256"],
        project_root=root,
        guard=guard,
    )
    value = pilot.to_dict()
    value["metadata"] = config["metadata"]
    pilot = Pilot(value, graph, token=_TOKEN)
    if pilot["summary"]["counts"] != config["expected_counts"]:
        raise HumanReviewError("pilot_counts_differ_from_approval")
    return pilot, c1


def _final_inputs(
    root: Path,
    path: Path,
    raw: bytes,
    config: dict,
    c3config: dict,
    c2config: dict,
    c1: dict[str, bytes],
) -> None:
    c3raw = readiness._reference(root, config["c3"]["configuration"], maximum=2_000_000)
    adjudication._final_input_pins(
        root,
        root / config["c3"]["configuration"]["path"],
        c3raw,
        c3config,
        c2config,
        c1,
    )
    for ref in config["normalized_inputs"]:
        readiness._reference(root, ref, maximum=100_000_000)
    readiness._reference(root, config["c3"]["manifest"], maximum=2_000_000)
    if corpus._read_saved(path, 2_000_000, "human intake config") != raw:
        raise HumanReviewError("human_intake_configuration_changed")


def prepare_human_review(
    config_path: Path,
    output: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    root = Path(project_root).absolute()
    config_path, output = (
        readiness._path(root, config_path),
        readiness._path(root, output),
    )
    config, raw, c3config, c2config = _load_config(config_path, root)
    if output != root / config["output_path"]:
        raise HumanReviewError("unapproved_human_intake_output_path")
    if output.exists() or output.is_symlink():
        raise FileExistsError("pilot_output_exists")
    guard = review._guard(root, config["artifact_roots"], output.parent, guard)
    pilot, c1 = _configured(root, config, c3config, c2config, guard)
    payloads = _payloads(pilot.to_dict())
    manifest = _manifest(
        payloads,
        {"path": config_path.relative_to(root).as_posix(), "sha256": _sha(raw)},
    )
    _write_pilot(
        output,
        payloads,
        manifest,
        guard,
        lambda: _final_inputs(root, config_path, raw, config, c3config, c2config, c1),
    )
    return pilot["summary"]


def _load_pilot(path: Path, pin: str) -> tuple[dict, dict[str, bytes]]:
    manifest_raw = corpus._read_saved(
        path / "manifest.json", 2_000_000, "pilot manifest"
    )
    if _sha(manifest_raw) != review._hash(pin):
        raise HumanReviewError("pilot_manifest_pin_mismatch")
    manifest = _fields(
        _json(manifest_raw),
        {
            "schema_version",
            "scope",
            "pilot_version",
            "mode",
            "configuration",
            "files",
            "inventory_sha256",
            "permissions",
            "actual_submissions",
            "accepted_labels",
            "accepted_corpus_release",
        },
    )
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["scope"] != SCOPE
        or manifest["pilot_version"] != PILOT_VERSION
        or manifest["permissions"] != RESTRICTIONS
        or type(manifest["actual_submissions"]) is not int
        or manifest["actual_submissions"] != 0
        or type(manifest["accepted_labels"]) is not int
        or manifest["accepted_labels"] != 0
        or manifest["accepted_corpus_release"] is not False
    ):
        raise HumanReviewError("invalid_pilot_boundary")
    _fields(manifest["files"], PAYLOAD_NAMES)
    payloads = {}
    directory = corpus._open_directory(path)
    try:
        review._private(path, directory=True)
        if set(os.listdir(directory)) != PAYLOAD_NAMES | {"manifest.json"}:
            raise HumanReviewError("incomplete_or_extra_pilot_files")
        for name, ref in manifest["files"].items():
            review._private(path / name)
            raw = corpus._read_saved(path / name, MAX_BYTES, "pilot payload")
            if ref != {"sha256": _sha(raw), "bytes": len(raw)}:
                raise HumanReviewError("pilot_content_pin_mismatch")
            payloads[name] = raw
        if sum(map(len, payloads.values())) > MAX_BYTES:
            raise HumanReviewError("pilot_input_byte_limit")
        readiness._same_directory(path, directory)
    finally:
        os.close(directory)
    inventory = _json(payloads["inventory.json"])
    metadata = inventory.pop("metadata")
    cases = review._rows(payloads["cases.jsonl"], LIMITS["max_pilot_cases"])
    value = {
        "inventory": inventory,
        "cases": cases,
        "audit": _json(payloads["pilot-audit.json"]),
        "exports": {
            "reviewer_a": _json(payloads["reviewer-a.json"]),
            "reviewer_b": _json(payloads["reviewer-b.json"]),
        },
        "onboarding": _json(payloads["onboarding.json"]),
        "summary": _json(payloads["summary.json"]),
        "metadata": metadata,
    }
    if (
        manifest["mode"] != value["summary"]["mode"]
        or manifest["inventory_sha256"] != inventory["inventory_sha256"]
        or _payloads(value) != payloads
    ):
        raise HumanReviewError("pilot_reconstruction_mismatch")
    if manifest["mode"] == "fictional_fixture":
        if manifest["configuration"] is not None or any(
            not o["source_id"].startswith("fictional_")
            or not o["observation_id"].startswith("fictional-")
            or any(not a["evidence_id"].startswith("fictional-") for a in o["aliases"])
            for c in cases
            for o in c["observations"]
        ):
            raise HumanReviewError("fictional_pilot_namespace_required")
    elif manifest["mode"] != "development_blank":
        raise HumanReviewError("invalid_pilot_mode")
    return value, {**payloads, "manifest.json": manifest_raw}


def _verify_pilot(path: Path, saved: dict[str, bytes]) -> None:
    directory = corpus._open_directory(path)
    try:
        review._private(path, directory=True)
        if set(os.listdir(directory)) != set(saved):
            raise HumanReviewError("pilot_changed_during_operation")
        for name, expected in saved.items():
            review._private(path / name)
            if corpus._read_saved(path / name, MAX_BYTES, "pilot artifact") != expected:
                raise HumanReviewError("pilot_changed_during_operation")
        readiness._same_directory(path, directory)
    finally:
        os.close(directory)


def validate_human_review(
    input_path: Path,
    *,
    project_root: Path,
    config_path: Path | None = None,
    guard: ResourceGuard | None = None,
) -> dict:
    root = Path(project_root).absolute()
    config_path = readiness._path(
        root, config_path or "config/corpus-human-review-v1.json"
    )
    input_path = readiness._path(root, input_path)
    config, raw, c3config, c2config = _load_config(config_path, root)
    if input_path != root / config["output_path"]:
        raise HumanReviewError("unapproved_human_intake_input_path")
    guard = review._guard(root, config["artifact_roots"], input_path.parent, guard)
    pilot, c1 = _configured(root, config, c3config, c2config, guard)
    payloads = _payloads(pilot.to_dict())
    manifest = _manifest(
        payloads,
        {"path": config_path.relative_to(root).as_posix(), "sha256": _sha(raw)},
    )
    actual, saved = _load_pilot(input_path, _sha(manifest))
    if actual != pilot.to_dict():
        raise HumanReviewError("human_intake_regeneration_mismatch")
    guard.check()
    _final_inputs(root, config_path, raw, config, c3config, c2config, c1)
    _verify_pilot(input_path, saved)
    return pilot["summary"]


def _context(
    pilot_path: Path,
    pin: str,
    project_root: Path,
    guard: ResourceGuard | None,
    ledger_path: Path | None = None,
) -> tuple[Path, Path | None, dict, Callable[[], None], ResourceGuard]:
    root = Path(project_root).absolute()
    pilot = readiness._path(root, pilot_path)
    ledger = readiness._path(root, ledger_path) if ledger_path is not None else None
    if ledger is not None and (ledger == pilot or ledger.parent != pilot.parent):
        raise HumanReviewError("intake_ledger_must_be_separate_pilot_sibling")
    manifest_raw = corpus._read_saved(
        pilot / "manifest.json", 2_000_000, "pilot manifest"
    )
    if _sha(manifest_raw) != review._hash(pin):
        raise HumanReviewError("pilot_manifest_pin_mismatch")
    manifest = _json(manifest_raw)
    final_inputs: Callable[[], None] | None = None
    if manifest["mode"] == "development_blank":
        reference = _fields(manifest["configuration"], {"path", "sha256"})
        config_path = root / readiness._relative(reference["path"])
        config, raw, c3config, c2config = _load_config(config_path, root)
        if (
            _sha(raw) != reference["sha256"]
            or pilot != root / config["output_path"]
            or ledger is not None
            and ledger != root / config["ledger_path"]
        ):
            raise HumanReviewError("intake_configuration_or_path_mismatch")
        guard = review._guard(root, config["artifact_roots"], pilot.parent, guard)
        _account(root, config, guard)
        c1directory = (root / c2config["c1"]["manifest"]["path"]).parent
        c1 = {
            "input-manifest.json": corpus._read_saved(
                c1directory / "input-manifest.json", readiness.MAX_BYTES, "C1 pins"
            )
        }

        def final_inputs() -> None:
            _final_inputs(root, config_path, raw, config, c3config, c2config, c1)
    elif manifest["mode"] == "fictional_fixture" and manifest["configuration"] is None:
        guard = review._guard(
            root, [pilot.parent.relative_to(root).as_posix()], pilot.parent, guard
        )
        guard.normalized_bytes = max(
            guard.normalized_bytes, _artifact_size(pilot.parent, required=True)
        )
        if guard.normalized_bytes > guard.limits.max_normalized_bytes:
            raise ResourceStop("normalized_byte_limit")
    else:
        raise HumanReviewError("invalid_pilot_mode")
    value, saved = _load_pilot(pilot, pin)

    def recheck() -> None:
        """Recheck every input after the last resource/user callback."""
        if final_inputs is not None:
            final_inputs()
        _verify_pilot(pilot, saved)

    return pilot, ledger, value, recheck, guard


def _declaration(value: dict | None, pilot: dict) -> dict:
    if pilot["summary"]["mode"] != "fictional_fixture":
        if value not in (None, BLANK_DECLARATION):
            raise HumanReviewError("real_review_execution_disabled")
        return json.loads(_canonical(BLANK_DECLARATION))
    declaration = _fields(value, set(BLANK_DECLARATION))
    if (
        declaration["protocol_version"] != PROTOCOL_VERSION
        or declaration["scope"] != "development_pilot"
        or declaration["real_execution_approval_ref"] is not None
        or declaration["identity_verification_status"] != "fictional_declaration_only"
    ):
        raise HumanReviewError("fictional_declaration_required")
    owner = _fields(
        declaration["owner"],
        {"owner_id", "authorization_ref", "identity_verification_ref"},
    )
    for item in [*owner.values(), declaration["retention_ref"]]:
        if not review._text(item).startswith("fictional-"):
            raise HumanReviewError("fictional_owner_reference_required")
    actors = declaration["actors"]
    if type(actors) is not list or len(actors) != 3:
        raise HumanReviewError("three_independent_fictional_actors_required")
    stripped = []
    for actor in actors:
        _fields(
            actor,
            {
                "actor_id",
                "principal_id",
                "independence_group",
                "kind",
                "authorization_ref",
                "competencies",
                "roles",
                "identity_verification_ref",
            },
        )
        if not review._text(actor.get("identity_verification_ref")).startswith(
            "fictional-"
        ):
            raise HumanReviewError("fictional_identity_verification_reference_required")
        stripped.append(
            {k: v for k, v in actor.items() if k != "identity_verification_ref"}
        )
    registry = review._actors(tuple(stripped), "fictional_fixture")
    for key in ("principal_id", "independence_group"):
        if len({actor[key] for actor in registry}) != 3:
            raise HumanReviewError("independent_human_principals_required")
    actors_by_id = {a["actor_id"]: a for a in registry}
    accesses = declaration["access"]
    if type(accesses) is not list or len(accesses) != 3:
        raise HumanReviewError("three_role_access_receipts_required")
    seen_roles, seen_actors, seen_receipts = set(), set(), set()
    for access in accesses:
        _fields(
            access,
            {
                "actor_id",
                "principal_id",
                "role",
                "export_id",
                "authorization_ref",
                "access_receipt_ref",
            },
        )
        role = access["role"]
        actor = actors_by_id.get(access["actor_id"])
        export = (
            pilot["inventory"]["adjudicator_export_id"]
            if role == "adjudicator"
            else pilot["exports"].get(role, {}).get("export_id")
        )
        if (
            role not in ROLES
            or role in seen_roles
            or actor is None
            or actor["actor_id"] in seen_actors
            or access["principal_id"] != actor["principal_id"]
            or access["export_id"] != export
            or ("adjudicate" if role == "adjudicator" else "review")
            not in actor["roles"]
        ):
            raise HumanReviewError("invalid_role_or_export_access")
        for key in ("authorization_ref", "access_receipt_ref"):
            if not review._text(access[key]).startswith("fictional-"):
                raise HumanReviewError("fictional_access_reference_required")
        if access["access_receipt_ref"] in seen_receipts:
            raise HumanReviewError("independent_access_receipts_required")
        seen_roles.add(role)
        seen_actors.add(actor["actor_id"])
        seen_receipts.add(access["access_receipt_ref"])
    return {
        **declaration,
        "actors": sorted(actors, key=lambda a: a["actor_id"]),
        "access": sorted(accesses, key=lambda a: a["role"]),
    }


def create_intake_ledger(
    pilot_path: Path,
    ledger_path: Path,
    *,
    expected_pilot_sha256: str,
    declaration: dict | None = None,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    pilot_path, ledger, pilot, recheck, guard = _context(
        pilot_path, expected_pilot_sha256, project_root, guard, ledger_path
    )
    declared = _declaration(declaration, pilot)
    header = _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "ledger_version": LEDGER_VERSION,
            "pilot_sha256": expected_pilot_sha256,
            "inventory_sha256": pilot["inventory"]["inventory_sha256"],
            "mode": pilot["summary"]["mode"],
            "declaration": declared,
            "created_at": pilot["metadata"]["created_at"],
            "permissions": RESTRICTIONS,
            "accepted_labels": 0,
            "accepted_corpus_release": False,
        }
    )
    parent = corpus._open_directory(ledger.parent)
    directory = None
    try:
        _reserve(ledger.parent, 2 * len(header), guard)
        readiness._same_directory(ledger.parent, parent)
        os.mkdir(ledger.name, 0o700, dir_fd=parent)
        directory = os.open(
            ledger.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.mkdir("events", 0o700, dir_fd=directory)
        lock = os.open(
            ".lock",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        os.fsync(lock)
        os.close(lock)
        guard.check()
        recheck()
        readiness._same_directory(ledger, directory)
        _write_payload(directory, "header.json", header)
        os.fsync(parent)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return _sha(header)


def _event(raw: dict, kind: str, pilot: dict, declared: dict, pin: str) -> dict:
    identifier = "submission_id" if kind == "submission" else "adjudication_id"
    keys = {
        identifier,
        "pilot_sha256",
        "case_id",
        "case_sha256",
        "actor_id",
        "export_id",
        "access_receipt_ref",
        "outcome",
        "rationale",
        "evidence_refs",
        "created_at",
        "origin",
        "uncertain",
        "conflict_declared",
        "duration_seconds",
        "independent_first_pass",
        "identity_scope",
        "relationship_annotation",
        "direction",
        "supersedes",
        "correction_reason",
    }
    if kind == "adjudication":
        keys.add("submission_ids")
    value = _fields(raw, keys)
    for key in (
        identifier,
        "case_id",
        "actor_id",
        "outcome",
        "export_id",
        "access_receipt_ref",
        "identity_scope",
    ):
        review._text(value[key])
    if value["outcome"] not in review.OUTCOMES:
        raise HumanReviewError("invalid_intake_outcome")
    cases = {c["case_id"]: c for c in pilot["cases"]}
    case = cases.get(value["case_id"])
    if (
        case is None
        or value["pilot_sha256"] != pin
        or value["case_sha256"] != case["case_sha256"]
    ):
        raise HumanReviewError("stale_or_unknown_pilot_case")
    if not review._text(value[identifier]).startswith("fictional-"):
        raise HumanReviewError("fictional_event_id_required")
    access = next(
        (a for a in declared["access"] if a["actor_id"] == value["actor_id"]), None
    )
    role = "adjudicator" if kind == "adjudication" else None
    if (
        access is None
        or (role is not None and access["role"] != role)
        or (role is None and access["role"] not in ROLES[:2])
        or access["export_id"] != value["export_id"]
        or access["access_receipt_ref"] != value["access_receipt_ref"]
    ):
        raise HumanReviewError("unauthorized_export_or_access_receipt")
    if (
        type(value["duration_seconds"]) is not int
        or not 1 <= value["duration_seconds"] <= 86400
        or type(value["independent_first_pass"]) is not bool
    ):
        raise HumanReviewError("invalid_duration_or_review_context")
    if value["identity_scope"] not in {
        "source_record_alias",
        "cross_record_identity",
        "unresolved",
    }:
        raise HumanReviewError("invalid_identity_claim_scope")
    if value["outcome"].startswith("supported_") and value["identity_scope"] != (
        "source_record_alias"
        if case["kind"] == "proposed_positive"
        else "cross_record_identity"
    ):
        raise HumanReviewError("identity_claim_scope_mismatch")
    if value["supersedes"] is None:
        if value["correction_reason"] is not None or value[
            "independent_first_pass"
        ] is not (kind == "submission"):
            raise HumanReviewError("invalid_initial_review_context")
    elif (
        not review._text(value["supersedes"]).startswith("fictional-")
        or not review._text(value["correction_reason"])
        or value["independent_first_pass"]
    ):
        raise HumanReviewError("invalid_correction_context")
    base_keys = {
        identifier,
        "case_id",
        "actor_id",
        "outcome",
        "rationale",
        "evidence_refs",
        "created_at",
        "origin",
        "uncertain",
        "conflict_declared",
        "relationship_annotation",
        "direction",
    }
    if kind == "adjudication":
        base_keys.add("submission_ids")
    base = {k: value[k] for k in base_keys} | {"packet_sha256": pin}
    registry = {
        a["actor_id"]: {k: v for k, v in a.items() if k != "identity_verification_ref"}
        for a in declared["actors"]
    }
    review._event_payload(base, kind, cases, registry, pin)
    return json.loads(_canonical(value))


def _apply(
    value: dict, kind: str, states: dict, events: dict, first_reviews: dict
) -> None:
    identifier = value["submission_id" if kind == "submission" else "adjudication_id"]
    if identifier in events:
        raise HumanReviewError("duplicate_or_replayed_intake_event")
    state = states[value["case_id"]]
    previous = value["supersedes"]
    if previous is not None:
        old = events.get(previous)
        if (
            old is None
            or old["kind"] != kind
            or old["payload"]["case_id"] != value["case_id"]
            or old["payload"]["actor_id"] != value["actor_id"]
        ):
            raise HumanReviewError("wrong_correction_ancestor")
    if kind == "submission":
        current = state["active_reviews"].get(value["actor_id"])
        if current != previous:
            raise HumanReviewError("duplicate_reviewer_or_stale_correction")
        if previous is None:
            first_reviews[value["case_id"]].append(identifier)
        state["active_reviews"][value["actor_id"]] = identifier
        if state["adjudication_id"] is not None:
            state["invalidated_adjudication_ids"].append(state["adjudication_id"])
            state["adjudication_id"] = None
        state["outcome"] = None
    else:
        if previous != state["latest_adjudication_id"]:
            raise HumanReviewError("stale_adjudication_supersession")
        active = set(state["active_reviews"].values())
        if len(active) != 2 or set(value["submission_ids"]) != active:
            raise HumanReviewError("exact_two_active_reviews_required")
        state["adjudication_id"] = identifier
        state["latest_adjudication_id"] = identifier
        state["outcome"] = value["outcome"]
    events[identifier] = {"kind": kind, "payload": value}
    initial = first_reviews[value["case_id"]]
    state["first_pass_agreement"] = (
        None
        if len(initial) != 2
        else events[initial[0]]["payload"]["outcome"]
        == events[initial[1]]["payload"]["outcome"]
    )
    state["active_submission_ids"] = sorted(state["active_reviews"].values())
    if state["adjudication_id"] is not None:
        state["status"] = (
            "adjudicated_fixture"
            if state["outcome"].startswith("supported_")
            else "adjudicated_unresolved"
        )
    elif len(state["active_reviews"]) == 2:
        state["status"] = (
            "awaiting_readjudication"
            if state["latest_adjudication_id"]
            else "awaiting_adjudication"
        )
    else:
        state["status"] = "awaiting_second_review"


def _graph_consistency(pilot: dict, states: dict, events: dict) -> None:
    """Reject active contradictory identity paths without applying labels to C3."""
    ids = sorted({oid for c in pilot["cases"] for oid in c["observation_ids"]})
    index = {oid: i for i, oid in enumerate(ids)}
    groups = adjudication._Components(len(ids))
    distinct = []
    for group in pilot["audit"]["graph_constraints"]["identity_groups"]:
        for member in group[1:]:
            groups.join(index[group[0]], index[member])
    for pair in pilot["audit"]["graph_constraints"]["distinct_pairs"]:
        distinct.append([index[oid] for oid in pair])
    cases = {c["case_id"]: c for c in pilot["cases"]}
    for cid, state in states.items():
        decision = state["adjudication_id"]
        if decision is None or len(cases[cid]["observation_ids"]) != 2:
            continue
        value = events[decision]["payload"]
        pair = [index[oid] for oid in cases[cid]["observation_ids"]]
        if value["outcome"] == "supported_same":
            groups.join(*pair)
        elif value["outcome"] == "supported_distinct":
            distinct.append(pair)
    if any(groups.root(left) == groups.root(right) for left, right in distinct):
        raise HumanReviewError("transitive_identity_contradiction")


def _replay(
    ledger: Path,
    eventfd: int,
    pilot: dict,
    declared: dict,
    pin: str,
    head: str,
    guard: ResourceGuard,
) -> tuple[dict, dict, list[tuple[str, bytes]]]:
    review._hash(head)
    header = corpus._read_saved(ledger / "header.json", 2_000_000, "intake header")
    expected = {
        "schema_version": 1,
        "scope": SCOPE,
        "ledger_version": LEDGER_VERSION,
        "pilot_sha256": pin,
        "inventory_sha256": pilot["inventory"]["inventory_sha256"],
        "mode": pilot["summary"]["mode"],
        "declaration": declared,
        "created_at": pilot["metadata"]["created_at"],
        "permissions": RESTRICTIONS,
        "accepted_labels": 0,
        "accepted_corpus_release": False,
    }
    review._private(ledger / "header.json")
    if header != _canonical(expected):
        raise HumanReviewError("intake_header_or_declaration_mismatch")
    files = sorted(os.listdir(eventfd))
    if len(files) > LIMITS["max_events"] or files != [
        f"{n:012d}.json" for n in range(1, len(files) + 1)
    ]:
        raise HumanReviewError("intake_event_gap_or_extra_file")
    if pilot["summary"]["mode"] != "fictional_fixture" and files:
        raise HumanReviewError("real_review_execution_disabled")
    states = {
        c["case_id"]: {
            "status": "unreviewed",
            "active_reviews": {},
            "active_submission_ids": [],
            "adjudication_id": None,
            "latest_adjudication_id": None,
            "invalidated_adjudication_ids": [],
            "first_pass_agreement": None,
            "outcome": None,
            "release_blocked": True,
        }
        for c in pilot["cases"]
    }
    events, first_reviews = {}, defaultdict(list)
    saved = [("header.json", header)]
    current, timestamp, total = (
        _sha(header),
        review._time(expected["created_at"]),
        len(header),
    )
    for sequence, name in enumerate(files, 1):
        guard.check()
        review._private(ledger / "events" / name)
        raw = corpus._read_saved(
            ledger / "events" / name, LIMITS["max_event_bytes"], "intake event"
        )
        total += len(raw)
        if total > MAX_BYTES:
            raise HumanReviewError("intake_ledger_byte_limit")
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
        body = {k: v for k, v in event.items() if k != "event_sha256"}
        if (
            type(event["schema_version"]) is not int
            or event["schema_version"] != 1
            or type(event["sequence"]) is not int
            or event["sequence"] != sequence
            or event["previous_sha256"] != current
            or event["kind"] not in {"submission", "adjudication"}
            or event["event_sha256"] != _sha(_canonical(body))
            or raw != _canonical(event)
        ):
            raise HumanReviewError("corrupt_intake_chain")
        value = _event(event["payload"], event["kind"], pilot, declared, pin)
        if review._time(value["created_at"]) < timestamp:
            raise HumanReviewError("backdated_intake_event")
        _apply(value, event["kind"], states, events, first_reviews)
        _graph_consistency(pilot, states, events)
        current, timestamp = event["event_sha256"], review._time(value["created_at"])
        saved.append(("events/" + name, raw))
    if current != head:
        raise HumanReviewError("intake_head_mismatch_or_truncation")
    result = {
        "event_count": len(files),
        "head_sha256": current,
        "submission_count": sum(e["kind"] == "submission" for e in events.values()),
        "adjudication_count": sum(e["kind"] == "adjudication" for e in events.values()),
        "correction_count": sum(
            e["payload"]["supersedes"] is not None for e in events.values()
        ),
        "active_adjudication_count": sum(
            s["adjudication_id"] is not None for s in states.values()
        ),
        "case_states": states,
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_corpus_release": False,
    }
    return result, events, saved


def replay_intake(
    ledger_path: Path,
    *,
    pilot_path: Path,
    expected_pilot_sha256: str,
    expected_head: str,
    declaration: dict | None = None,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    pilot_path, ledger, pilot, recheck, guard = _context(
        pilot_path, expected_pilot_sha256, project_root, guard, ledger_path
    )
    declared = _declaration(declaration, pilot)
    with review._locked(ledger) as (_, eventfd, check_lock):
        result, _, saved = _replay(
            ledger,
            eventfd,
            pilot,
            declared,
            expected_pilot_sha256,
            expected_head,
            guard,
        )
        guard.check()
        review._verify_saved_ledger(ledger, eventfd, saved)
        recheck()
        check_lock()
        return result


def _append(
    ledger_path: Path,
    payload: dict,
    kind: str,
    *,
    pilot_path: Path,
    expected_pilot_sha256: str,
    expected_head: str,
    declaration: dict | None,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    pilot_path, ledger, pilot, recheck, guard = _context(
        pilot_path, expected_pilot_sha256, project_root, guard, ledger_path
    )
    if pilot["summary"]["mode"] != "fictional_fixture":
        raise HumanReviewError("real_review_execution_disabled")
    declared = _declaration(declaration, pilot)
    with review._locked(ledger) as (_, eventfd, check_lock):
        result, events, saved = _replay(
            ledger,
            eventfd,
            pilot,
            declared,
            expected_pilot_sha256,
            expected_head,
            guard,
        )
        value = _event(payload, kind, pilot, declared, expected_pilot_sha256)
        last = _json(saved[-1][1])
        previous_time = (
            last["payload"]["created_at"] if "payload" in last else last["created_at"]
        )
        if review._time(value["created_at"]) < review._time(previous_time):
            raise HumanReviewError("backdated_intake_event")
        first_reviews = defaultdict(list)
        for identifier, event in events.items():
            if event["kind"] == "submission" and event["payload"]["supersedes"] is None:
                first_reviews[event["payload"]["case_id"]].append(identifier)
        _apply(value, kind, result["case_states"], events, first_reviews)
        _graph_consistency(pilot, result["case_states"], events)
        sequence = result["event_count"] + 1
        if sequence > LIMITS["max_events"]:
            raise HumanReviewError("intake_event_limit")
        body = {
            "schema_version": 1,
            "sequence": sequence,
            "previous_sha256": expected_head,
            "kind": kind,
            "payload": value,
        }
        head = _sha(_canonical(body))
        raw = _canonical({**body, "event_sha256": head})
        if len(raw) > LIMITS["max_event_bytes"]:
            raise HumanReviewError("intake_event_byte_limit")
        _reserve(ledger.parent, 2 * len(raw), guard)
        guard.check()
        review._verify_saved_ledger(ledger, eventfd, saved)
        recheck()
        check_lock()
        _write_payload(eventfd, f"{sequence:012d}.json", raw)
        return head


def append_submission(ledger_path: Path, submission: dict, **kwargs) -> str:
    """Append a fictional initial submission or an explicit same-actor correction."""
    return _append(ledger_path, submission, "submission", **kwargs)


def append_adjudication(ledger_path: Path, decision: dict, **kwargs) -> str:
    """Resolve the latest two reviews; supersession never deletes prior history."""
    return _append(ledger_path, decision, "adjudication", **kwargs)


def export_template(
    pilot_path: Path,
    *,
    role: str,
    case_id: str,
    expected_pilot_sha256: str,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    pilot_path, _, pilot, recheck, guard = _context(
        pilot_path, expected_pilot_sha256, project_root, guard
    )
    if role not in ROLES:
        raise HumanReviewError("unknown_template_role")
    case = next((c for c in pilot["cases"] if c["case_id"] == case_id), None)
    if case is None:
        raise HumanReviewError("unknown_pilot_case")
    identifier = "adjudication_id" if role == "adjudicator" else "submission_id"
    result = {
        identifier: None,
        "pilot_sha256": expected_pilot_sha256,
        "case_id": case_id,
        "case_sha256": case["case_sha256"],
        "actor_id": None,
        "export_id": pilot["inventory"]["adjudicator_export_id"]
        if role == "adjudicator"
        else pilot["exports"][role]["export_id"],
        "access_receipt_ref": None,
        "outcome": None,
        "rationale": None,
        "evidence_refs": [],
        "created_at": None,
        "origin": "fictional_human"
        if pilot["summary"]["mode"] == "fictional_fixture"
        else "human",
        "uncertain": None,
        "conflict_declared": None,
        "duration_seconds": None,
        "independent_first_pass": role != "adjudicator",
        "identity_scope": None,
        "relationship_annotation": "unresolved",
        "direction": {
            "query_evidence_id": None,
            "reference_evidence_id": None,
            "adequacy": "unresolved",
        },
        "supersedes": None,
        "correction_reason": None,
    }
    if role == "adjudicator":
        result["submission_ids"] = []
    guard.check()
    recheck()
    return result


def adjudicator_handoff(
    ledger_path: Path,
    case_id: str,
    *,
    actor_id: str,
    export_id: str,
    access_receipt_ref: str,
    pilot_path: Path,
    expected_pilot_sha256: str,
    expected_head: str,
    declaration: dict | None,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    pilot_path, ledger, pilot, recheck, guard = _context(
        pilot_path, expected_pilot_sha256, project_root, guard, ledger_path
    )
    if pilot["summary"]["mode"] != "fictional_fixture":
        raise HumanReviewError("real_review_execution_disabled")
    declared = _declaration(declaration, pilot)
    access = next(a for a in declared["access"] if a["role"] == "adjudicator")
    if (actor_id, export_id, access_receipt_ref) != (
        access["actor_id"],
        access["export_id"],
        access["access_receipt_ref"],
    ):
        raise HumanReviewError("adjudicator_access_required")
    with review._locked(ledger) as (_, eventfd, check_lock):
        result, events, saved = _replay(
            ledger,
            eventfd,
            pilot,
            declared,
            expected_pilot_sha256,
            expected_head,
            guard,
        )
        state = result["case_states"].get(case_id)
        if state is None or len(state["active_submission_ids"]) != 2:
            raise HumanReviewError("handoff_requires_two_active_reviews")
        case = next(c for c in pilot["cases"] if c["case_id"] == case_id)
        response = {
            "case": _neutral(case),
            "export_id": export_id,
            "ledger_head_sha256": expected_head,
            "submissions": [
                events[i]["payload"] for i in state["active_submission_ids"]
            ],
            "history": [
                event
                for event in events.values()
                if event["payload"]["case_id"] == case_id
            ],
            "first_pass_agreement": state["first_pass_agreement"],
            "state": state,
            "accepted_label": False,
            "access_is_declared_not_authenticated": True,
        }
        guard.check()
        review._verify_saved_ledger(ledger, eventfd, saved)
        recheck()
        check_lock()
        return response


def deny_network(event: str, arguments: tuple) -> None:
    review.deny_network(event, arguments)


def _write_cli_json(
    output: Path, value: dict, pilot_path: Path, pin: str, root: Path
) -> None:
    pilot, _, _, recheck, guard = _context(pilot_path, pin, root, None)
    output = readiness._path(root, output)
    if output.parent != pilot.parent:
        raise HumanReviewError("draft_output_must_be_private_pilot_sibling")
    raw = _canonical(value)
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
    parser = argparse.ArgumentParser(
        description="Offline pilot preparation; genuine intake remains disabled"
    )
    parser.add_argument(
        "action",
        choices=(
            "prepare",
            "validate",
            "create-ledger",
            "export-template",
            "submit",
            "adjudicate",
            "replay",
            "handoff",
        ),
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--config", type=Path, default=Path("config/corpus-human-review-v1.json")
    )
    for name in ("pilot", "ledger", "output", "payload", "declaration"):
        parser.add_argument("--" + name, type=Path)
    for name in (
        "pilot-sha256",
        "expected-head",
        "role",
        "case-id",
        "actor-id",
        "export-id",
        "access-receipt-ref",
    ):
        parser.add_argument("--" + name)
    args = parser.parse_args(argv)
    sys.addaudithook(deny_network)
    root = args.project_root.absolute()
    try:
        if args.action == "prepare":
            result = prepare_human_review(args.config, args.output, project_root=root)
        elif args.action == "validate":
            result = validate_human_review(
                args.pilot, config_path=args.config, project_root=root
            )
        else:
            declaration = (
                _json(
                    corpus._read_saved(
                        readiness._path(root, args.declaration),
                        2_000_000,
                        "access declaration",
                    )
                )
                if args.declaration
                else None
            )
            context = {
                "pilot_path": args.pilot,
                "expected_pilot_sha256": args.pilot_sha256,
                "project_root": root,
            }
            if args.action == "create-ledger":
                result = {
                    "head_sha256": create_intake_ledger(
                        ledger_path=args.ledger, declaration=declaration, **context
                    )
                }
            elif args.action == "export-template":
                draft = export_template(role=args.role, case_id=args.case_id, **context)
                _write_cli_json(args.output, draft, args.pilot, args.pilot_sha256, root)
                result = {"status": "blank_template_saved"}
            else:
                context.update(
                    expected_head=args.expected_head, declaration=declaration
                )
                if args.action in {"submit", "adjudicate"}:
                    payload = _json(
                        corpus._read_saved(
                            readiness._path(root, args.payload),
                            LIMITS["max_event_bytes"],
                            "intake draft",
                        )
                    )
                    action = (
                        append_submission
                        if args.action == "submit"
                        else append_adjudication
                    )
                    result = {"head_sha256": action(args.ledger, payload, **context)}
                elif args.action == "replay":
                    state = replay_intake(args.ledger, **context)
                    result = {k: v for k, v in state.items() if k != "case_states"}
                else:
                    handoff = adjudicator_handoff(
                        args.ledger,
                        args.case_id,
                        actor_id=args.actor_id,
                        export_id=args.export_id,
                        access_receipt_ref=args.access_receipt_ref,
                        **context,
                    )
                    _write_cli_json(
                        args.output, handoff, args.pilot, args.pilot_sha256, root
                    )
                    result = {"status": "private_handoff_saved"}
    except (ValueError, OSError, TypeError, KeyError):
        print(json.dumps({"status": "failed_closed", "scope": SCOPE}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
