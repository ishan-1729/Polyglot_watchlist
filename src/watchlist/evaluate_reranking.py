"""E5-only paired reranking of frozen Phase 4 shortlists; no training."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import time

from watchlist.compare_retrieval import multilingual_benchmark, phase3_benchmark
from watchlist.embeddings import file_hash
from watchlist.evaluate import latency_summary, metric
from watchlist.evaluation_data import fingerprint
from watchlist.reranking import MiniLMScorer, PairScorer, peak_memory_bytes, rerank

DATASETS = {
    "fictional": "eval/results/phase04/fictional",
    "public-small": "data/evaluation/phase04/public-small",
    "multilingual": "eval/results/phase04/multilingual",
}


def frozen_benchmark(dataset: str, expected_hash: str) -> tuple[dict, list[dict], dict]:
    """Verify the original artifact, query labels and complete alias-view fingerprints."""
    path = Path(DATASETS[dataset]) / "results.json"
    if file_hash(path) != expected_hash:
        raise ValueError("saved Phase 4 result checksum changed")
    old = json.loads(path.read_text())
    views, queries, _ = multilingual_benchmark() if dataset == "multilingual" else phase3_benchmark(dataset)
    if fingerprint(queries) != old["query_fingerprint"]:
        raise ValueError("frozen query fingerprint changed")
    e5_config = json.loads(Path("eval/configs/embeddings.json").read_text())["model"]
    if old["model"]["config"] != e5_config:
        raise ValueError("E5 model configuration changed")
    for view, entities in views.items():
        manifest = {"version": "alias-cache-v1", "encoder": old["model"],
                    "entities": [asdict(e) for e in entities]}
        if fingerprint(manifest) != old["reference_cache"][view]["key"]:
            raise ValueError("frozen reference alias view changed")
    saved = old["methods"]["e5_small"]["queries"]
    if len(queries) != len(saved):
        raise ValueError("frozen query count changed")
    for q, row in zip(queries, saved):
        if any(row.get(key) != value for key, value in q.items()):
            raise ValueError("frozen query labels or order changed")
        entities = {e.entity_id: e for e in views[q["view"]]}
        ids = [c["entity_id"] for c in row["candidates"]]
        if len(ids) != len(set(ids)) or set(ids) != set(entities):
            raise ValueError("E5 candidate universe invalid")
        for c in row["candidates"]:
            e = entities[c["entity_id"]]
            if (c["matched_alias_id"], c["matched_alias"]) not in {(a.alias_id, a.name) for a in e.aliases}:
                raise ValueError("saved candidate alias not in view")
    return views, queries, old


def summarize(rows: list[dict], k: int, method: str) -> dict:
    """Separate retrieval eligibility, conditional accuracy and truncated ranking."""
    positive = [r for r in rows if r["status"] == "positive"]
    n = len(positive)
    retrieved = [r for r in positive if r["baseline_rank"] is not None]
    rank_key = "baseline_rank" if method == "e5" else "reranked_rank"
    hits = sum(r[rank_key] == 1 for r in positive)
    informative = [r for r in positive if r["index_entity_count"] > k]
    coverage = sum(r["baseline_rank"] is not None for r in informative)
    reciprocal = sum(1 / r[rank_key] if r[rank_key] is not None else 0 for r in positive)
    return {
        "query_count": len(rows), "positive_queries": n, "excluded_queries": len(rows)-n,
        "target_groups": len({r["group_id"] for r in positive}),
        "retrieval_recall_at_k": metric(coverage/len(informative) if informative else None,
                                        coverage if informative else None, len(informative),
                                        None if informative else "K covers index or no eligible positives"),
        "retrieved_target_count": len(retrieved),
        "uninformative_coverage_queries": n-len(informative),
        "recall_at_1": metric(hits/n if n else None, hits if n else None, n, None if n else "no eligible positives"),
        "conditional_reranking_accuracy": metric(hits/len(retrieved) if retrieved else None,
                                                 hits if retrieved else None, len(retrieved),
                                                 None if retrieved else "no retrieved positive targets"),
        "mrr_at_k": metric(reciprocal/n if n else None, reciprocal if n else None, n, None if n else "no eligible positives"),
    }


def aggregate(rows: list[dict], k: int) -> list[dict]:
    """Keep familiar challenge/sanity suites and overlapping diagnostic slices explicit."""
    output = []
    for partition in ("development", "test", "ambiguity", "absent"):
        part = [r for r in rows if r["partition"] == partition]
        selections = {"all": part,
                      "challenge": [r for r in part if r["status"] == "positive" and r["kind"] not in {"exact", "formatting"}],
                      "known_alias_exact": [r for r in part if r["kind"] == "exact"],
                      "heldout_alias": [r for r in part if r["kind"] == "heldout_alias"],
                      "typos": [r for r in part if r["kind"] in {"deletion", "adjacent_swap"}],
                      "word_order": [r for r in part if r["kind"] == "word_order"],
                      "cross_script": [r for r in part if r.get("cross_script_only")]}
        for script in sorted({r["script"] for r in part}):
            selections["script:"+script] = [r for r in part if r["script"] == script]
        cross = selections["cross_script"]
        for direction in sorted({r["script"]+"→"+"+".join(r.get("reference_scripts", [])) for r in cross}):
            selections[direction] = [r for r in cross if r["script"]+"→"+"+".join(r.get("reference_scripts", [])) == direction]
        for label in sorted({r.get("pair_type", "source-alias") for r in cross}):
            selections["cross_script:"+label] = [r for r in cross if r.get("pair_type", "source-alias") == label]
        for label, subset in selections.items():
            output.append({"partition": partition, "slice": label,
                           **{m: summarize(subset, k, m) for m in ("e5", "e5_cross_encoder")}})
    return output


def failure_reason(status: str, rank: int | None, candidates: list[dict]) -> str | None:
    """Describe observed rank failures, without inventing a linguistic cause."""
    if status != "positive" or rank == 1:
        return None
    if rank is None:
        return "target absent from E5 shortlist; reranker cannot recover it"
    if candidates[0]["raw_logit"] == candidates[rank-1]["raw_logit"]:
        return "top logit tied; stable entity-ID ordering puts target later"
    return "another shortlisted record has a higher cross-encoder logit"


def evaluate(views: dict, queries: list[dict], old: dict, scorer: PairScorer,
             k: int, repetitions: int) -> dict:
    """Rerank each frozen shortlist; time fresh pair scoring, not cached scores."""
    if type(k) is not int or k not in {5, 10} or type(repetitions) is not int or repetitions < 1:
        raise ValueError("approved K and positive repetitions required")
    if len(queries) != len(old["methods"]["e5_small"]["queries"]):
        raise ValueError("query and baseline counts differ")
    rows = []
    error = None
    historical = {t["query_id"]: t for t in old["methods"]["e5_small"]["timing"]["per_query"]}
    for query, baseline in zip(queries, old["methods"]["e5_small"]["queries"]):
        entities = views[query["view"]]
        candidates = baseline["candidates"][:k]
        ids = [c["entity_id"] for c in candidates]
        try:
            ranked = rerank(query["text"], ids, entities, scorer)  # untimed warm-up
            samples = []
            for _ in range(repetitions):
                start = time.perf_counter_ns()
                repeated = rerank(query["text"], ids, entities, scorer)
                samples.append((time.perf_counter_ns()-start)/1e6)
                if repeated != ranked:
                    raise ValueError("repeated reranking differs in the same process")
        except (TimeoutError, MemoryError) as exc:
            error = {"query_id": query["query_id"], "type": type(exc).__name__, "message": str(exc)}
            break
        reranked_ids = [c["entity_id"] for c in ranked]
        if len(reranked_ids) != len(ids) or set(reranked_ids) != set(ids):
            raise ValueError("reranking changed candidate membership")
        target = query["target_id"]
        before = ids.index(target)+1 if target in ids else None
        after = reranked_ids.index(target)+1 if target in reranked_ids else None
        rows.append({**query, "cross_script_only": baseline["cross_script_only"],
                     "index_entity_count": len(entities), "returned_candidate_count": len(ids),
                     "baseline_rank": before, "reranked_rank": after,
                     "original_e5_candidates": candidates, "reranked_candidates": ranked,
                     "pair_count": sum(len(c["available_aliases"]) for c in ranked),
                     "change": "unchanged" if before == after else "improved" if after < before else "worse",
                     "failure": failure_reason(query["status"], after, ranked),
                     "reranking_latency": {"samples_ms": samples, **latency_summary(samples)},
                     "historical_e5_latency": latency_summary(historical[query["query_id"]]["samples_ms"])})
        if len(rows) % 25 == 0:
            print(f"K={k}: {len(rows)}/{len(queries)} queries", flush=True)
    return {"k": k, "complete": error is None, "error": error, "expected_queries": len(queries),
            "queries": rows, "aggregates": aggregate(rows, k),
            "latency_scope": "fresh reranking: normalization, pair tokenization, model inference, best-alias grouping and sorting; excludes retrieval/model load/file checks",
            "timing_repetitions": repetitions,
            "latency": latency_summary([v for r in rows for v in r["reranking_latency"]["samples_ms"]])}


def render_report(result: dict) -> str:
    """Derive readable paired tables and failure gallery from saved numbers."""
    def show(m: dict) -> str:
        return "N/A" if m["value"] is None else f"{m['value']:.4f} (n={m['denominator']})"
    lines = ["# Phase 5A E5-only reranking", "", f"Dataset: {result['dataset']}", "",
             "Raw cross-encoder logits and E5 cosine scores are not identity probabilities. Existing benchmarks are exploratory diagnostics."]
    for experiment in result["experiments"].values():
        lines += ["", f"## K={experiment['k']} — complete: {experiment['complete']}", "",
                  "| Partition / slice | Method | Positives / groups | Retrieval R@K | R@1 | Conditional accuracy | MRR@K |",
                  "|---|---|---:|---|---|---|---|"]
        for a in experiment["aggregates"]:
            if not a["e5"]["query_count"]:
                continue
            for method in ("e5", "e5_cross_encoder"):
                d = a[method]
                lines.append(f"| {a['partition']} / {a['slice']} | {method} | {d['positive_queries']} / {d['target_groups']} | " +
                             " | ".join(show(d[m]) for m in ("retrieval_recall_at_k", "recall_at_1", "conditional_reranking_accuracy", "mrr_at_k")) + " |")
        t = experiment["latency"]
        lines += ["", f"Reranking latency: median {t['median_ms']} ms; p95 {t['p95_ms']} ms; {t['observations']} observations.",
                  experiment["latency_scope"], "", "Saved E5 timing is historical, not a concurrently measured total pipeline time."]
        for change in ("improved", "unchanged", "worse"):
            cases = [q for q in experiment["queries"] if q["partition"] == "test" and q["status"] == "positive" and q["change"] == change]
            lines += ["", f"### Test positives: {change} ({len(cases)})", ""]
            for q in cases[:10]:
                lines.append(f"- {json.dumps(q['text'], ensure_ascii=False)}: `{q['target_id']}`, {q['kind']}, rank {q['baseline_rank']} → {q['reranked_rank']}. {q['failure'] or ''}")
        lines += ["", "All queries, evidence, timings and failures remain in JSON. N/A coverage means K spans the index or no eligible queries; conditional accuracy excludes retrieval misses. Slice rows overlap; do not add their denominators."]
        if experiment["error"]:
            lines += ["", "INCOMPLETE RUN: " + json.dumps(experiment["error"])]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dataset", choices=list(DATASETS))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config["primary_k"] != 5 or config["sensitivity_k"] != 10 or config["max_runtime_seconds"] != 1800:
        parser.error("configuration differs from approved scope")
    started = time.perf_counter()
    scorer = MiniLMScorer(config["model"], deadline=started+config["max_runtime_seconds"])
    for dataset in ([args.dataset] if args.dataset else config["datasets"]):
        views, queries, old = frozen_benchmark(dataset, config["phase4_result_sha256"][dataset])
        experiments = {}
        for k in (config["primary_k"], config["sensitivity_k"]):
            experiments[str(k)] = evaluate(views, queries, old, scorer, k, config["timing_repetitions"])
            if not experiments[str(k)]["complete"]:
                break
        result = {"dataset": dataset, "config": config, "model": scorer.metadata,
                  "phase4_sha256": config["phase4_result_sha256"][dataset],
                  "query_fingerprint": fingerprint(queries), "experiments": experiments,
                  "model_load_seconds": scorer.load_seconds, "process_peak_rss_bytes": peak_memory_bytes(),
                  "elapsed_seconds_since_run_start": time.perf_counter()-started,
                  "environment": {"python": platform.python_version(), "platform": platform.platform()}}
        root = Path("data/evaluation/phase05/reranking/public-small" if dataset == "public-small"
                    else f"eval/results/phase05/reranking/{dataset}")
        root.mkdir(parents=True, exist_ok=True)
        (root/"results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        (root/"report.md").write_text(render_report(result))
        print(f"Saved {root}", flush=True)
        if not all(e["complete"] for e in experiments.values()):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
