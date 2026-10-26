"""Offline fixed-task evaluations with explicit data classes and measured costs."""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
from pathlib import Path
import statistics
import time
from uuid import uuid4

from follow_the_money.cases import Approval, TraceRequest, make_claim
from follow_the_money.contracts import digest
from follow_the_money.critic import challenge
from follow_the_money.fixtures import build_fixtures
from follow_the_money.service import TraceService

TASKS = (
    {
        "id": "branching-service",
        "chain": "bitcoin",
        "seed": "syn_seed_a",
        "endpoint": "syn_exchange",
        "max_calls": 12,
        "max_hops": 5,
    },
    {
        "id": "coinjoin-stop",
        "chain": "bitcoin",
        "seed": "syn_coinjoin",
        "max_calls": 5,
        "max_hops": 5,
    },
    {
        "id": "tron-transfer",
        "chain": "tron",
        "seed": "syn_tron_seed",
        "endpoint": "syn_tron_exchange",
        "max_calls": 6,
        "max_hops": 3,
    },
)
VALUE_FEATURES = ("parent_value_fraction", "hops", "log_incoming_units")


def value_features(item: dict) -> tuple[float, ...]:
    return (
        float(item["heuristic"]),
        float(item["hops"]),
        math.log1p(item.get("incoming_units", 0)),
    )


def success(state: dict, task: dict) -> bool:
    if task["id"] == "coinjoin-stop":
        return (
            any(t.get("reason") == "coinjoin_stop" for t in state["trace"])
            and not state["clusters"]["groups"]
            and not state["claims"]
        )
    return any(e["address"] == task["endpoint"] for e in state["endpoints"])


def behavior_hash(state: dict) -> str:
    """Exclude random request/case IDs and timing; retain actual behavior."""
    return digest(
        {
            "claims": state["claims"],
            "critic": state["critic"],
            "trace": state["trace"],
            "endpoints": state["endpoints"],
            "budget": state["budget"],
            "stop_reason": state["stop_reason"],
        }
    )


def create_service(root: Path, fixture: dict, **kwargs) -> TraceService:
    return TraceService.initialize(
        root, cache=Path(fixture["cache"]), labels=Path(fixture["labels"]), **kwargs
    )


def trace_value_rows(state: dict, endpoint: str, *, split: str) -> list[dict]:
    """Targets use the completed trace's observed directed graph, never input features."""
    if state["status"] != "completed":
        raise ValueError("Value labels require a completed reviewed trace")
    retained = {c["claim_id"] for c in state["critic"] if c["retained"]}
    reverse = {}
    for claim in state["claims"]:
        if claim["kind"] == "transfer" and claim["claim_id"] in retained:
            source, destination = claim["addresses"]
            reverse.setdefault(destination, set()).add(source)
    distances, queue = {endpoint: 0}, deque([endpoint])
    while queue:
        destination = queue.popleft()
        for source in sorted(reverse.get(destination, ())):
            if source not in distances:
                distances[source] = distances[destination] + 1
                queue.append(source)
    completed_at = int(time.time())
    return [
        {
            "case_id": state["case_id"],
            "features": value_features(row),
            "remaining_calls": distances.get(row["address"], 25),
            "completed_at": completed_at,
            "split": split,
            "address": row["address"],
            "evidence_kind": "synthetic",
            "label_kind": "distance_in_completed_observed_graph_or_censored_penalty_25",
        }
        for row in state["trace"]
        if "heuristic" in row and "hops" in row
    ]


def train_value_policy(root: Path):
    """Fit only separate synthetic variants; held-out variant and fixed tasks never fit."""
    import numpy as np
    from sklearn.metrics import mean_absolute_error
    from follow_the_money.models import DistributionGuard, fit_trace_value

    rows, graph_hashes = [], []
    for variant in (1, 2, 3, 4):
        fixture = build_fixtures(root / f"world-{variant}", variant=variant)
        service = create_service(root / f"case-{variant}", fixture)
        view = service.start_case(
            TraceRequest(
                chain="bitcoin",
                seed=fixture["seed"],
                goal="bounded_exploration",
                max_calls=24,
                max_hops=5,
                strategy="bfs",
                request_id=str(uuid4()),
            ),
            actor="synthetic-evaluator",
        )
        view = service.submit_approval(
            view["case_id"],
            Approval(
                request_id=str(uuid4()),
                evidence_sha256=view["state"]["evidence_sha256"],
                decision="approve",
                note="Simulated fixture review for value-model training; not a real analyst decision",
            ),
            actor="synthetic-evaluator",
        )
        rows.extend(
            trace_value_rows(
                view["state"],
                fixture["endpoint"],
                split="test" if variant == 4 else "train",
            )
        )
        graph_hashes.append(fixture["graph_sha256"])
    train_rows = [r for r in rows if r["split"] == "train"]
    test_rows = [r for r in rows if r["split"] == "test"]
    train_end = max(r["completed_at"] for r in train_rows)
    model = fit_trace_value(rows, train_end=train_end)
    x = np.asarray([r["features"] for r in train_rows])
    guard = DistributionGuard.fit(x, chain="synthetic", feature_names=VALUE_FEATURES)
    prediction = model.predict([r["features"] for r in test_rows])
    report = {
        "evidence_kind": "synthetic",
        "model": "HistGradientBoostingRegressor",
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "train_cases": sorted({r["case_id"] for r in train_rows}),
        "test_cases": sorted({r["case_id"] for r in test_rows}),
        "heldout_mae_calls": float(
            mean_absolute_error([r["remaining_calls"] for r in test_rows], prediction)
        ),
        "features": VALUE_FEATURES,
        "train_end": train_end,
        "graph_hashes": graph_hashes,
        "ood_threshold": guard.threshold,
        "mean": guard.mean.tolist(),
        "scale": guard.scale.tolist(),
        "notice": "Distinct addresses/txids, same authored graph family. Censored branches use a penalty of 25, not an observed endpoint distance. No real-world accuracy claim.",
    }
    (root / "trace-value-rows.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    (root / "trace-value-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    def score(item, chain):
        if chain != "bitcoin" or not item["address"].startswith("syn_"):
            return {
                "score": item["heuristic"],
                "ood": True,
                "method": "heuristic_fallback",
                "reason": "synthetic_only_model",
            }
        values = value_features(item)
        check = guard.inspect(values, chain="synthetic", feature_names=VALUE_FEATURES)
        if check["ood"]:
            return {**check, "score": item["heuristic"], "method": "heuristic_fallback"}
        remaining = max(0, float(model.predict([values])[0]))
        return {
            **check,
            "score": 1 / (1 + remaining),
            "method": "learned_trace_value",
            "calibrated": False,
        }

    return score, report


def critic_metrics(state: dict) -> dict:
    retained = [
        challenge(c, state["evidence"], state["labels"])["retained"]
        for c in state["claims"]
    ]
    false_claims = []
    for claim in state["claims"]:
        if claim["kind"] == "transfer":
            false_claims.append(
                make_claim(
                    "transfer",
                    claim["chain"],
                    tuple(claim["txids"]),
                    tuple(claim["addresses"]),
                    amount=claim["amount"] + 1,
                    output_index=claim["output_index"],
                    confidence=0.6,
                )
            )
    withdrawn = sum(
        not challenge(c, state["evidence"], state["labels"])["retained"]
        for c in false_claims
    )
    return {
        "supported_fixture_claims": len(retained),
        "supported_claims_withdrawn": len(retained) - sum(retained),
        "planted_false_claims": len(false_claims),
        "false_claims_withdrawn": withdrawn,
        "false_withdrawal_rate": (len(retained) - sum(retained))
        / max(1, len(retained)),
        "false_claim_detection_rate": withdrawn / max(1, len(false_claims)),
        "notice": "Constructed exact-amount contradictions, not a general adversarial benchmark.",
    }


def memory_metrics(root: Path, fixture: dict) -> dict:
    service = create_service(root, fixture)
    view = service.start_case(
        TraceRequest(chain="bitcoin", seed="syn_seed_a", request_id=str(uuid4())),
        actor="synthetic-evaluator",
    )
    service.submit_approval(
        view["case_id"],
        Approval(
            request_id=str(uuid4()),
            evidence_sha256=view["state"]["evidence_sha256"],
            decision="approve",
        ),
        actor="simulated-fixture-reviewer",
    )
    from follow_the_money.memory import CaseMemory

    queries = [
        (service.memory, "syn_partner", True),
        (service.memory, "syn_noise_0", False),
        (service.memory, "syn_exchange", False),
        (CaseMemory(service.root / "memory", "other-scope"), "syn_partner", False),
    ]
    tp = fp = fn = tn = 0
    for memory, address, expected in queries:
        actual = bool(memory.query_case_memory("bitcoin", [address])["links"])
        tp += actual and expected
        fp += actual and not expected
        fn += not actual and expected
        tn += not actual and not expected
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "evidence_kind": "synthetic",
        "review": "Explicitly simulated fixture review; no human decision is claimed.",
    }


def evaluate(*, output: Path, repeats: int = 3, include_value: bool = True) -> dict:
    if not 1 <= repeats <= 5:
        raise ValueError("repeats must be 1..5")
    output.mkdir(parents=True, exist_ok=True)
    fixture = build_fixtures(output / "fixed-world")
    score, value_report = (
        train_value_policy(output / "value-training")
        if include_value
        else (None, {"status": "not_run"})
    )
    strategies = ["bfs", "heuristic"] + (
        ["learned_trace_value"] if include_value else []
    )
    runs, sample = [], None
    for strategy in strategies:
        for task in TASKS:
            for repeat in range(repeats):
                service = create_service(
                    output / f"{strategy}-{task['id']}-{repeat}",
                    fixture,
                    score=score if strategy == "learned_trace_value" else None,
                )
                request = TraceRequest(
                    chain=task["chain"],
                    seed=task["seed"],
                    max_calls=task["max_calls"],
                    max_hops=task["max_hops"],
                    strategy="bfs" if strategy == "bfs" else "priority",
                    request_id=str(uuid4()),
                )
                start = time.perf_counter()
                view = service.start_case(request, actor="synthetic-evaluator")
                latency = time.perf_counter() - start
                state = view["state"]
                events = service.audit(view["case_id"])["events"]
                calls = [e for e in events if e["kind"] == "tool_reserved"]
                valid = sum(
                    e["payload"]["query"]["tool"]
                    in {"get_address_txs", "get_trc20_transfers", "get_freeze_events"}
                    and e["payload"]["query"]["chain"] == task["chain"]
                    for e in calls
                )
                found = success(state, task)
                runs.append(
                    {
                        "task": task["id"],
                        "strategy": strategy,
                        "repeat": repeat,
                        "success": found,
                        "calls": state["budget"]["calls"],
                        "calls_to_endpoint": state["budget"]["calls"]
                        if found and "endpoint" in task
                        else None,
                        "network_calls": state["budget"]["network_calls"],
                        "tool_calls": len(calls),
                        "valid_tool_calls": valid,
                        "latency_seconds": latency,
                        "external_cost_usd": 0,
                        "stop_reason": state["stop_reason"],
                        "behavior_sha256": behavior_hash(state),
                        "evidence_kind": "synthetic",
                        "case_status": view["status"],
                    }
                )
                if (
                    strategy == "heuristic"
                    and task["id"] == "branching-service"
                    and sample is None
                ):
                    sample = state
    summaries = []
    for strategy in strategies:
        selected = [r for r in runs if r["strategy"] == strategy]
        task_groups = [
            [r for r in selected if r["task"] == task["id"]] for task in TASKS
        ]
        summaries.append(
            {
                "strategy": strategy,
                "success_rate": sum(r["success"] for r in selected) / len(selected),
                "pass_k": sum(all(r["success"] for r in group) for group in task_groups)
                / len(task_groups),
                "k": repeats,
                "consistent_tasks": sum(
                    len({r["behavior_sha256"] for r in group}) == 1
                    for group in task_groups
                ),
                "task_count": len(task_groups),
                "mean_calls": statistics.mean(r["calls"] for r in selected),
                "median_latency_seconds": statistics.median(
                    r["latency_seconds"] for r in selected
                ),
                "tool_call_accuracy": sum(r["valid_tool_calls"] for r in selected)
                / max(1, sum(r["tool_calls"] for r in selected)),
            }
        )
    report = {
        "schema": "ftm-evaluation-v1",
        "evidence_kind": "synthetic",
        "fixed_graph_sha256": fixture["graph_sha256"],
        "task_contract_sha256": digest(TASKS),
        "runs": runs,
        "summaries": summaries,
        "critic": critic_metrics(sample),
        "memory": memory_metrics(output / "memory-evaluation", fixture),
        "value_model": value_report,
        "notice": "Three deliberately small authored tasks. Failed endpoint runs are censored at their budgets; no speedup is inferred from missing endpoints. Warm disk caches affect latency.",
        "llm_ablation": {
            "status": "not_run",
            "reason": "No approved provider/key; deterministic fallback and injected override tests only.",
        },
    }
    (output / "results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("data/follow_the_money/evaluation")
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--without-value", action="store_true")
    args = parser.parse_args()
    report = evaluate(
        output=args.output, repeats=args.repeats, include_value=not args.without_value
    )
    print(
        json.dumps(
            {
                "summaries": report["summaries"],
                "critic": report["critic"],
                "memory": report["memory"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
