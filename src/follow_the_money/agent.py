"""Replay-first LangGraph planner/frontier/tools/reflection/critic/approval loop."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from follow_the_money.cases import TraceRequest, make_claim, proposal_payload
from follow_the_money.contracts import NOTICE, FtmError, Page, digest
from follow_the_money.critic import build_critic
from follow_the_money.heuristics import ClusterBook, detect_change, detect_coinjoin
from follow_the_money.planner import plan
from follow_the_money.resolver import EntityResolver
from follow_the_money.storage import Ledger


class AgentState(TypedDict):
    case_id: str
    thread_id: str
    request: dict
    plan: dict
    frontier: list[dict]
    current: dict
    visited: list[str]
    claims: list[dict]
    critic: list[dict]
    evidence: dict
    labels: list[dict]
    clusters: dict
    endpoints: list[dict]
    resolutions: list[dict]
    trace: list[dict]
    budget: dict
    stop_reason: str
    status: str
    evidence_sha256: str
    approval: dict
    report: dict
    memory: dict
    memory_context: dict


@dataclass
class Dependencies:
    client: Any
    labels: Any
    ledger: Ledger
    resolver: EntityResolver
    score: Callable | None = None
    rank_override: Callable | None = None
    memory: Any = None
    failpoint: Callable = lambda stage: None


def initial_state(case_id: str, thread_id: str, request: TraceRequest) -> AgentState:
    return AgentState(
        case_id=case_id,
        thread_id=thread_id,
        request=request.to_dict(),
        plan={},
        frontier=[],
        current={},
        visited=[],
        claims=[],
        critic=[],
        evidence={},
        labels=[],
        clusters=ClusterBook(cap=request.cluster_cap).snapshot(),
        endpoints=[],
        resolutions=[],
        trace=[],
        budget={"calls": 0, "network_calls": 0, "max_calls": request.max_calls},
        stop_reason="",
        status="preparing",
        evidence_sha256="",
        approval={},
        report={},
        memory={},
        memory_context={"links": [], "rules": []},
    )


def frontier_key(item: dict) -> str:
    return digest(
        {k: item.get(k) for k in ("address", "cursor", "source_txid", "source_vout")}
    )


def build_graph(saver, deps: Dependencies):
    critic_graph = build_critic()

    def planner(state):
        request = TraceRequest.model_validate(state["request"])
        return {
            "plan": plan(request),
            "frontier": [
                {
                    "address": request.seed,
                    "hops": 0,
                    "cursor": None,
                    "heuristic": 0.5,
                    "received_at": 0,
                    "source_txid": request.seed_txid,
                    "source_vout": request.seed_vout,
                    "order": 0,
                    "incoming_units": 0,
                }
            ],
        }

    def pick(state):
        frontier = [
            dict(f)
            for f in state["frontier"]
            if frontier_key(f) not in state["visited"]
        ]
        if not frontier:
            return {"frontier": [], "current": {}, "stop_reason": "frontier_exhausted"}
        for item in frontier:
            item["score"] = item["heuristic"]
            item["ranking"] = {
                "method": "heuristic_fallback",
                "ood": True,
                "reason": "no_validated_model",
            }
            if deps.score is not None and state["request"]["strategy"] == "priority":
                try:
                    result = deps.score(dict(item), state["request"]["chain"])
                    if (
                        result.get("ood") is False
                        and math.isfinite(result["score"])
                        and 0 <= result["score"] <= 1
                    ):
                        item["score"], item["ranking"] = result["score"], result
                except (ValueError, TypeError, KeyError, RuntimeError):
                    item["ranking"]["reason"] = "model_error"
        if state["request"]["strategy"] == "bfs":
            frontier.sort(key=lambda f: (f["hops"], f["order"], f["address"]))
        else:
            frontier.sort(
                key=lambda f: (-f["score"], f["hops"], f["order"], f["address"])
            )
        chosen = frontier[0]
        if deps.rank_override is not None:
            try:
                suggested = deps.rank_override([dict(f) for f in frontier])
            except Exception:
                suggested = None
            replacement = next((f for f in frontier if f["address"] == suggested), None)
            event = {
                "priority_choice": chosen["address"],
                "suggested": suggested
                if isinstance(suggested, str) and len(suggested) <= 128
                else None,
                "accepted": replacement is not None,
                "changed": replacement is not None
                and replacement["address"] != chosen["address"],
            }
            deps.ledger.event(
                state["case_id"],
                "ranking_override",
                event,
                key=f"override:{state['case_id']}:{digest(state['visited'])}",
            )
            if replacement is not None:
                chosen = replacement
        frontier.remove(chosen)
        return {
            "current": chosen,
            "frontier": frontier,
            "visited": [*state["visited"], frontier_key(chosen)],
        }

    def freeze_signals(state):
        request = state["request"]
        if request["chain"] != "tron" or not request["check_freeze_signals"]:
            return {}
        method = getattr(deps.client, "get_freeze_events", None)
        if method is None:
            return {
                "trace": [
                    {"action": "backtrack", "reason": "freeze_provider_unavailable"}
                ]
            }
        query = {"chain": "tron", "tool": "get_freeze_events"}
        result = deps.ledger.tool(
            state["case_id"],
            query,
            lambda: [e.to_dict() for e in method()],
            max_calls=request["max_calls"],
            failpoint=deps.failpoint,
        )
        evidence, claims = {}, []
        if result["ok"]:
            for event in result["value"]:
                if event["address"] == request["seed"]:
                    evidence.setdefault(event["txid"], []).append(
                        {"chain": "tron", "value": event}
                    )
                    claims.append(
                        make_claim(
                            "freeze_signal",
                            "tron",
                            (event["txid"],),
                            (event["address"],),
                            confidence=0.5,
                        )
                    )
        return {
            "evidence": evidence,
            "claims": claims,
            "budget": {
                "calls": deps.ledger.calls(state["case_id"]),
                "network_calls": 0,
                "max_calls": request["max_calls"],
            },
            "trace": [
                {
                    **query,
                    "action": "continue",
                    "reason": "historical_events"
                    if result["ok"]
                    else result["error"]["code"],
                }
            ],
        }

    def tools_node(state):
        if not state["current"]:
            return {}
        if state["current"].get("analyst_stop"):
            return {
                "trace": [
                    *state["trace"],
                    {
                        "address": state["current"]["address"],
                        "action": "backtrack",
                        "reason": "analyst_stop_rule",
                    },
                ]
            }
        current, request = state["current"], state["request"]
        address, chain = current["address"], request["chain"]
        claims, labels, resolutions = (
            list(state["claims"]),
            list(state["labels"]),
            list(state["resolutions"]),
        )
        book = ClusterBook.restore(state["clusters"])
        published = deps.labels.lookup_labels(chain, address)
        for label in published:
            if label.to_dict() not in labels:
                labels.append(label.to_dict())
            if current["source_txid"] in state["evidence"]:
                claims.append(
                    make_claim(
                        "published_label",
                        chain,
                        (current["source_txid"],),
                        (address,),
                        label_sha256=digest(label.to_dict()),
                        confidence=0.5,
                    )
                )
            if label.category == "sanctioned" and label.owner_name:
                resolution = deps.resolver.resolve_entity_name(
                    label, case_id=state["case_id"]
                )
                if resolution not in resolutions:
                    resolutions.append(resolution)
        stops = [
            label
            for label in published
            if label.category in {"exchange", "service", "mixer"}
        ]
        if stops or not book.linkable(address):
            book.mark_service(address)
            endpoint = {
                "address": address,
                "txid": current["source_txid"],
                "categories": sorted({label.category for label in stops}),
                "hops": current["hops"],
            }
            return {
                "claims": unique_claims(claims),
                "labels": labels,
                "resolutions": resolutions,
                "clusters": book.snapshot(),
                "endpoints": [*state["endpoints"], endpoint],
                "stop_reason": "service_endpoint"
                if request["goal"] == "find_service_endpoint"
                else "",
                "trace": [
                    *state["trace"],
                    {
                        "address": address,
                        "action": "stop",
                        "reason": "published_service_or_cluster_cap",
                        "hops": current["hops"],
                        "heuristic": current["heuristic"],
                        "incoming_units": current.get("incoming_units", 0),
                    },
                ],
            }
        if current["hops"] >= request["max_hops"]:
            return {
                "labels": labels,
                "claims": unique_claims(claims),
                "resolutions": resolutions,
                "trace": [
                    *state["trace"],
                    {
                        "address": address,
                        "action": "backtrack",
                        "reason": "hop_limit",
                        "hops": current["hops"],
                    },
                ],
            }
        query = {
            "chain": chain,
            "tool": "get_address_txs" if chain == "bitcoin" else "get_trc20_transfers",
            "address": address,
            "cursor": current["cursor"],
            "frontier_key": frontier_key(current),
        }
        method = (
            deps.client.get_address_txs
            if chain == "bitcoin"
            else deps.client.get_trc20_transfers
        )
        try:
            result = deps.ledger.tool(
                state["case_id"],
                query,
                lambda: method(address, current["cursor"]).to_dict(),
                max_calls=request["max_calls"],
                failpoint=deps.failpoint,
            )
        except FtmError as exc:
            if exc.code != "budget_exhausted":
                raise
            return {"stop_reason": "budget_exhausted"}
        budget = {
            "calls": deps.ledger.calls(state["case_id"]),
            "network_calls": 0,
            "max_calls": request["max_calls"],
        }
        if not result["ok"]:
            return {
                "budget": budget,
                "trace": [
                    *state["trace"],
                    {**query, "action": "backtrack", "reason": result["error"]["code"]},
                ],
                "labels": labels,
                "resolutions": resolutions,
            }
        page = Page.model_validate_json(json.dumps(result["value"]))
        evidence = {k: list(v) for k, v in state["evidence"].items()}
        frontier = list(state["frontier"])
        added = 0
        coinjoin = False
        matched_outpoint = False
        for tx in page.transactions if chain == "bitcoin" else page.transfers:
            record = {"chain": chain, "value": tx.to_dict()}
            entries = evidence.setdefault(tx.txid, [])
            if record not in entries:
                if (
                    chain == "bitcoin"
                    and entries
                    and any(
                        {k: v for k, v in entry["value"].items() if k != "provenance"}
                        != {
                            k: v
                            for k, v in record["value"].items()
                            if k != "provenance"
                        }
                        for entry in entries
                    )
                ):
                    raise FtmError(
                        "conflicting_evidence",
                        "One Bitcoin txid has conflicting recorded bodies",
                    )
                entries.append(record)
            if chain == "bitcoin":
                if (
                    not tx.confirmed
                    or tx.timestamp is None
                    or tx.timestamp < current["received_at"]
                ):
                    continue
                if address not in {i.prevout.address for i in tx.inputs if i.prevout}:
                    continue
                if current["source_txid"] and not any(
                    (i.txid, i.vout) == (current["source_txid"], current["source_vout"])
                    and i.prevout is not None
                    and i.prevout.address == address
                    for i in tx.inputs
                ):
                    continue
                if current["source_txid"]:
                    matched_outpoint = True
                if detect_coinjoin(tx).suspected:
                    coinjoin = True
                    continue
                decision = book.cluster_common_input(tx)
                if decision.stop:
                    continue
                senders = tuple(
                    sorted(
                        {
                            i.prevout.address
                            for i in tx.inputs
                            if i.prevout and i.prevout.address
                        }
                    )
                )
                if len(senders) > 1:
                    claims.append(
                        make_claim(
                            "common_input_hypothesis",
                            chain,
                            (tx.txid,),
                            senders,
                            confidence=0.6,
                        )
                    )
                change = detect_change(tx)
                if (
                    change.candidate is not None
                    and tx.outputs[change.candidate].address
                ):
                    claims.append(
                        make_claim(
                            "change_hypothesis",
                            chain,
                            (tx.txid,),
                            (tx.outputs[change.candidate].address,),
                            output_index=change.candidate,
                            confidence=min(0.8, change.probabilities[change.candidate]),
                        )
                    )
                targets = [
                    (o.address, o.value, i, tx.timestamp)
                    for i, o in enumerate(tx.outputs)
                    if o.address and o.value > 0
                ]
                total = max(1, sum(o.value for o in tx.outputs))
            else:
                if tx.sender != address or tx.timestamp < current["received_at"]:
                    continue
                targets = [(tx.recipient, tx.amount, None, tx.timestamp)]
                total = max(1, tx.amount)
            for target, amount, index, timestamp in targets:
                claims.append(
                    make_claim(
                        "transfer",
                        chain,
                        (tx.txid,),
                        (address, target),
                        amount=amount,
                        output_index=index,
                        confidence=0.6,
                    )
                )
                item = {
                    "address": target,
                    "hops": current["hops"] + 1,
                    "cursor": None,
                    "source_txid": tx.txid,
                    "source_vout": index,
                    "received_at": timestamp,
                    "heuristic": 0.25 + 0.5 * amount / total,
                    "incoming_units": amount,
                    "order": len(state["visited"]) + len(frontier),
                }
                if frontier_key(item) not in state["visited"] and not any(
                    frontier_key(f) == frontier_key(item) for f in frontier
                ):
                    frontier.append(item)
                    added += 1
        if page.next_cursor and not matched_outpoint:
            frontier.append(
                {
                    **current,
                    "cursor": page.next_cursor,
                    "order": len(state["visited"]) + len(frontier),
                }
            )
        limited = len(frontier) > 1000 or len(claims) > 2000 or len(evidence) > 2500
        return {
            "frontier": frontier[:1000],
            "claims": unique_claims(claims)[:2000],
            "evidence": evidence,
            "labels": labels,
            "resolutions": resolutions,
            "clusters": book.snapshot(),
            "budget": budget,
            "stop_reason": "resource_limit" if limited else "",
            "trace": [
                *state["trace"],
                {
                    **query,
                    "action": "continue" if added or page.next_cursor else "backtrack",
                    "hops": current["hops"],
                    "discovered": added,
                    "complete_page": page.complete,
                    "outpoint_scan_complete": matched_outpoint,
                    "reason": "coinjoin_stop" if coinjoin else "recorded_page",
                    "ranking": current["ranking"],
                    "heuristic": current["heuristic"],
                    "incoming_units": current.get("incoming_units", 0),
                },
            ],
        }

    def reflect(state):
        if state["stop_reason"]:
            return {}
        if not state["frontier"]:
            return {"stop_reason": "frontier_exhausted"}
        return {}

    def critique(state):
        result = critic_graph.invoke(
            {
                "claims": state["claims"],
                "evidence": state["evidence"],
                "labels": state["labels"],
                "critic": [],
            }
        )
        context = dict(state["memory_context"])
        if deps.memory is not None:
            addresses = sorted(
                {state["request"]["seed"]}
                | {a for c in state["claims"] for a in c["addresses"]}
            )
            recalled = deps.memory.query_case_memory(
                state["request"]["chain"],
                addresses,
                exclude_case=state["case_id"],
                blocked_members=state["clusters"]["service"],
            )
            context.update(recalled)
        return {"critic": result["critic"], "memory_context": context}

    def analyst_rules(state):
        if deps.memory is None or not state["current"]:
            return {}
        rules = deps.memory.rules(
            state["request"]["chain"], state["current"]["address"]
        )
        context = dict(state["memory_context"])
        context["rules"] = list(
            {(r["id"], r["revision"]): r for r in [*context["rules"], *rules]}.values()
        )
        return {
            "memory_context": context,
            "current": {
                **state["current"],
                "analyst_stop": any(r["action"] == "stop" for r in rules),
            },
        }

    def prepare(state):
        return {
            "evidence_sha256": digest(proposal_payload(state)),
            "status": "awaiting_approval",
        }

    def human_approval(state):
        answer = interrupt(
            {
                "case_id": state["case_id"],
                "evidence_sha256": state["evidence_sha256"],
                "claim_count": len(state["claims"]),
                "withdrawn": sum(not c["retained"] for c in state["critic"]),
                "draft_requested": state["request"]["draft_request"],
                "notice": NOTICE,
            }
        )
        if answer.get("evidence_sha256") != state["evidence_sha256"] or answer.get(
            "decision"
        ) not in {"approve", "reject"}:
            raise FtmError("stale_approval", "Approval does not match this evidence")
        return {"approval": answer}

    def report(state):
        retained = {c["claim_id"] for c in state["critic"] if c["retained"]}
        approved = state["approval"]["decision"] == "approve"
        claims = (
            [c for c in state["claims"] if c["claim_id"] in retained]
            if approved
            else []
        )
        draft = None
        if approved and state["request"]["draft_request"]:
            draft = {
                "status": "DRAFT_ONLY",
                "sent": False,
                "text": "Draft research information request for independent human editing and separate authorization. No recipient or sending capability is configured.",
                "txids": sorted({txid for c in claims for txid in c["txids"]}),
            }
        return {
            "status": "completed" if approved else "rejected",
            "report": {
                "case_id": state["case_id"],
                "notice": NOTICE,
                "claims": claims,
                "withdrawn_count": len(state["claims"]) - len(retained),
                "human_withheld_count": len(retained) if not approved else 0,
                "critic": state["critic"],
                "budget": state["budget"],
                "stop_reason": state["stop_reason"],
                "evidence_sha256": state["evidence_sha256"],
                "draft_request": draft,
                "approval": state["approval"],
                "memory_context": state["memory_context"],
                "evidence_kinds": sorted(
                    {
                        r["value"]["provenance"]["evidence_kind"]
                        for rows in state["evidence"].values()
                        for r in rows
                    }
                ),
            },
        }

    def remember(state):
        if deps.memory is not None and state["status"] == "completed":
            return {"memory": deps.memory.publish(state)}
        return {
            "memory": {
                "status": "not_configured" if deps.memory is None else "not_published"
            }
        }

    graph = StateGraph(AgentState)
    for name, node in (
        ("planner", planner),
        ("freeze_signals", freeze_signals),
        ("pick", pick),
        ("analyst_rules", analyst_rules),
        ("tools", tools_node),
        ("reflect", reflect),
        ("critic", critique),
        ("prepare", prepare),
        ("human_approval", human_approval),
        ("report", report),
        ("memory", remember),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "freeze_signals")
    graph.add_edge("freeze_signals", "pick")
    graph.add_edge("pick", "analyst_rules")
    graph.add_edge("analyst_rules", "tools")
    graph.add_edge("tools", "reflect")
    graph.add_conditional_edges(
        "reflect",
        lambda state: "critic" if state["stop_reason"] else "pick",
        {"critic": "critic", "pick": "pick"},
    )
    for left, right in (
        ("critic", "prepare"),
        ("prepare", "human_approval"),
        ("human_approval", "report"),
        ("report", "memory"),
    ):
        graph.add_edge(left, right)
    graph.add_edge("memory", END)
    return graph.compile(checkpointer=saver)


def unique_claims(claims: list[dict]) -> list[dict]:
    return list({c["claim_id"]: c for c in claims}.values())
