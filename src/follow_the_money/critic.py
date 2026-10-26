"""An independent deterministic LangGraph critic challenges every claim."""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from follow_the_money.cases import Claim, claim_text
from follow_the_money.contracts import (
    BitcoinTx,
    FreezeEvent,
    Label,
    Transfer,
    USDT_TRON,
    digest,
)
from follow_the_money.heuristics import (
    detect_change,
    detect_coinjoin,
    detect_peel_chain,
)


def challenge(raw: dict, evidence: dict, labels: list[dict]) -> dict:
    """Recompute support from structured evidence, never trust claim prose."""
    supported, reason = False, "unsupported_claim_kind"
    try:
        claim = Claim.model_validate_json(json.dumps(raw))
        records = [record for txid in claim.txids for record in evidence.get(txid, [])]
        if any(txid not in evidence for txid in claim.txids) or any(
            r["value"]["txid"] not in claim.txids for r in records
        ):
            reason = "missing_txid_evidence"
        elif claim.kind == "transfer":
            for record in records:
                if record["chain"] != claim.chain:
                    continue
                if claim.chain == "bitcoin":
                    tx = BitcoinTx.model_validate_json(json.dumps(record["value"]))
                    senders = {i.prevout.address for i in tx.inputs if i.prevout}
                    index = claim.output_index
                    supported = (
                        len(claim.addresses) == 2
                        and tx.confirmed
                        and not detect_coinjoin(tx).suspected
                        and index is not None
                        and index < len(tx.outputs)
                        and claim.addresses[0] in senders
                        and tx.outputs[index].address == claim.addresses[1]
                        and tx.outputs[index].value == claim.amount
                    )
                else:
                    if "action" in record["value"]:
                        continue
                    transfer = Transfer.model_validate_json(json.dumps(record["value"]))
                    supported = (
                        transfer.contract == USDT_TRON
                        and transfer.decimals == 6
                        and claim.addresses == (transfer.sender, transfer.recipient)
                        and claim.amount == transfer.amount
                    )
                if supported:
                    break
            reason = (
                "transaction_supports_possible_flow"
                if supported
                else "flow_not_supported"
            )
        elif claim.kind == "freeze_signal" and claim.chain == "tron":
            for record in records:
                if record["chain"] != "tron" or "action" not in record["value"]:
                    continue
                event = FreezeEvent.model_validate(record["value"])
                supported = (
                    event.contract == USDT_TRON and event.address in claim.addresses
                )
                if supported:
                    break
            reason = (
                "historical_contract_event_only" if supported else "event_not_supported"
            )
        elif (
            claim.kind
            in {"common_input_hypothesis", "change_hypothesis", "peel_hypothesis"}
            and claim.chain == "bitcoin"
        ):
            txs = [
                BitcoinTx.model_validate_json(json.dumps(r["value"]))
                for r in records
                if r["chain"] == "bitcoin"
            ]
            if claim.kind == "common_input_hypothesis":
                supported = any(
                    set(claim.addresses)
                    <= {i.prevout.address for i in tx.inputs if i.prevout}
                    and len(claim.addresses) >= 2
                    and not detect_coinjoin(tx).suspected
                    for tx in txs
                )
            elif claim.kind == "change_hypothesis":
                supported = any(
                    claim.output_index is not None
                    and claim.output_index < len(tx.outputs)
                    and detect_change(tx).candidate == claim.output_index
                    and tx.outputs[claim.output_index].address in claim.addresses
                    for tx in txs
                )
            else:
                supported = detect_peel_chain(txs).detected
            supported = supported and claim.confidence <= 0.8
            reason = (
                "heuristic_only_with_alternatives"
                if supported
                else "heuristic_not_supported"
            )
        elif claim.kind == "published_label":
            for value in labels:
                label = Label.model_validate(value)
                if (
                    digest(value) == claim.label_sha256
                    and label.chain == claim.chain
                    and label.address in claim.addresses
                ):
                    supported = any(
                        label.address in addresses(r)
                        for r in records
                        if r["chain"] == claim.chain
                    )
            reason = (
                "published_assertion_not_ownership"
                if supported
                else "label_or_transaction_mismatch"
            )
        if (
            claim.text
            != claim_text(claim.kind, claim.chain, claim.addresses, claim.amount)
            or claim.claim_id
            != digest({k: v for k, v in raw.items() if k != "claim_id"})
            or claim.confidence > 0.8
        ):
            supported, reason = False, "untrusted_prose_or_identity_or_confidence"
    except (ValueError, KeyError, TypeError, IndexError):
        supported, reason = False, "malformed_claim_or_evidence"
    return {
        "claim_id": raw.get("claim_id", "invalid"),
        "retained": supported,
        "reason": reason,
        "challenge": "A transaction's outputs do not prove who controls an address or which input funded which output. Labels can be stale; collaborative payments and service activity can invalidate wallet hypotheses.",
        "alternative": "Independent counterparties, change, collaborative spending or a historical label can explain the observation.",
        "confidence_cap": 0.8 if supported else 0.0,
    }


def addresses(record: dict) -> set[str]:
    value = record["value"]
    if record["chain"] == "tron":
        if "action" in value:
            return {value["address"]}
        return {value["sender"], value["recipient"]}
    return {
        i["prevout"]["address"]
        for i in value["inputs"]
        if i["prevout"] and i["prevout"]["address"]
    } | {o["address"] for o in value["outputs"] if o["address"]}


class CriticState(TypedDict):
    claims: list[dict]
    evidence: dict
    labels: list[dict]
    critic: list[dict]


def build_critic():
    graph = StateGraph(CriticState)
    graph.add_node(
        "challenge_every_claim",
        lambda state: {
            "critic": [
                challenge(c, state["evidence"], state["labels"])
                for c in state["claims"]
            ]
        },
    )
    graph.add_edge(START, "challenge_every_claim")
    graph.add_edge("challenge_every_claim", END)
    return graph.compile()
