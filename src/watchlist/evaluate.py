"""Evaluate the unchanged RapidFuzz baseline offline, with explicit denominators."""

import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import sqlite3
import statistics
import time

from watchlist.database import load_database, connect_database
from watchlist.entities import load_entities
from watchlist.evaluation_data import (audit_queries, build_benchmark, build_legacy_benchmark,
                                      fingerprint, query_labels)
from watchlist.evaluation_metrics import METRIC_PROTOCOL, metric, ranking_fields, summarize
from watchlist.matching import Candidate, rank_candidates, SCORER_NAME


def latency_summary(samples: list[float]) -> dict:
    """Milliseconds; p95 uses the nearest-rank convention, not interpolation."""
    ordered = sorted(samples)
    return {"observations": len(samples), "median_ms": statistics.median(ordered) if ordered else None,
            "p95_ms": ordered[math.ceil(.95 * len(ordered))-1] if ordered else None,
            "p95_method": "nearest-rank"}


def ranking_failure(status: str, target_rank: int | None, candidates: list,
                    method: str = "normalized edit similarity") -> str | None:
    """Describe ranking evidence without assuming every method uses edit distance."""
    if status != "positive" or target_rank == 1:
        return None
    if target_rank is None:
        return "target absent from ranking"
    if candidates[0].similarity_score == candidates[target_rank - 1].similarity_score:
        return "top score tied; stable entity-ID ordering puts target later"
    return f"another record has higher {method}"


def _verify_alias_view(candidates: list[Candidate], entities: tuple) -> None:
    """A returned match must cite an alias visible to this retrieval call."""
    allowed = {entity.entity_id: {(alias.alias_id, alias.name) for alias in entity.aliases}
               for entity in entities}
    for candidate in candidates:
        if (not isinstance(candidate, Candidate) or candidate.entity_id not in allowed
                or (candidate.matched_alias_id, candidate.matched_alias) not in allowed[candidate.entity_id]):
            raise ValueError('candidate entity/alias is outside the approved reference view')


def evaluate_queries(views: dict, queries: list[dict], repetitions: int, *,
                     requested_k: int | None = None, regression_only: bool = False) -> tuple[list[dict], dict]:
    """Audit the complete benchmark before sending only text/aliases to search.

    One untimed call warms each query. Timed calls use the same immutable alias
    tuple and must reproduce the saved ranking. Gold labels stay in this scoring
    layer; the retriever never receives the benchmark context or a query object.
    """
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("timing repetitions must be a positive integer")
    if requested_k is not None and (type(requested_k) is not int or requested_k < 1):
        raise ValueError('requested_k must be a positive integer or null for the complete index')
    audit_queries(queries, views, regression_only=regression_only)
    rows, timings = [], []
    for query in queries:
        entities = views[query["view"]]
        if not entities:
            raise ValueError("empty evaluation reference")
        requested = len(entities) if requested_k is None else requested_k
        labelled = {**query, **query_labels(query, regression_only=regression_only)}
        candidates = rank_candidates(query["text"], entities, top_k=requested)
        fields = ranking_fields(labelled, candidates, index_entity_count=len(entities), requested_k=requested)
        _verify_alias_view(candidates, entities)
        durations = []
        for _ in range(repetitions):
            start = time.perf_counter_ns()
            repeated = rank_candidates(query["text"], entities, top_k=requested)
            durations.append((time.perf_counter_ns() - start) / 1_000_000)
            if repeated != candidates:
                raise ValueError('repeated ranking differs from the saved untimed ranking')
        failure = ranking_failure(labelled['status'], fields['target_rank'], candidates)
        rows.append({**labelled, **fields, 'regression_only': regression_only,
                     "failure": failure, "candidates": [asdict(c) for c in candidates]})
        timings.append({"query_id": query["query_id"], "partition": query["partition"],
                        "kind": query["kind"], "script": query["script"], "samples_ms": durations,
                        **latency_summary(durations)})
    return rows, {"warmup": "one untimed call per query", "repetitions": repetitions,
                  'requested_k': requested_k,
                  "scope": "rank_candidates including normalization, scoring and requested ranking; excludes audit, DB loading and serialization",
                  "query_count": len(queries), "per_query": timings,
                  **latency_summary([t for row in timings for t in row["samples_ms"]])}


def aggregate(rows: list[dict]) -> list[dict]:
    """Keep partitions and sanity/challenge suites separate; expose empty scripts."""
    results = []
    partitions = ['development', 'test']
    partitions += sorted({row['partition'] for row in rows} - set(partitions))
    for partition in partitions:
        subset = [r for r in rows if r["partition"] == partition]
        for suite in ("sanity", "challenge", "diagnostic", "absent"):
            selected = [r for r in subset if (
                "diagnostic" if r["status"] == "diagnostic" else
                "absent" if r["status"] == "absent" else
                "sanity" if r["kind"] in {"exact", "formatting"} else "challenge") == suite]
            results.append({"partition": partition, "suite": suite, "slice": "all", **summarize(selected)})
            if not selected:
                continue
            for field in ("kind", "script"):
                categories = sorted({r[field] for r in selected} | ({"LATIN", "ARABIC", "CYRILLIC"} if field == "script" else set()))
                for value in categories:
                    results.append({"partition": partition, "suite": suite, "slice": f"{field}:{value}",
                                    **summarize([r for r in selected if r[field] == value])})
    return results


def run(config: dict) -> tuple[dict, list[dict]]:
    """Bind configuration, source and splits before any search; never fetch data."""
    if not isinstance(config, dict):
        raise ValueError('evaluation config must be an object')
    mode = config.get('benchmark_mode', 'evaluation-v2')
    if not isinstance(mode, str) or mode not in {'evaluation-v2', 'regression_only_legacy'}:
        raise ValueError('benchmark_mode must explicitly select evaluation-v2 or regression_only_legacy')
    legacy = mode == 'regression_only_legacy'
    if config["dataset"] == "fictional":
        entities = load_entities()
        assignments = json.loads(Path(config["partitions"]).read_text())
    elif config["dataset"] == "public-small":
        entities, provenance, synthetic = load_database(Path(config["database"]))
        manifest = json.loads(Path(config["partitions"]).read_text())
        if synthetic or manifest["snapshot_id"] != provenance.snapshot_id or manifest["raw_sha256"] != provenance.raw_sha256:
            raise ValueError("split manifest does not match public snapshot")
        assignments = manifest["assignments"]
        connection = connect_database(Path(config["database"]), readonly=True)
        try:
            groups = dict(connection.execute('SELECT entity_id, group_id FROM entities'))
        finally:
            connection.close()
        if any(assignments.get(key, {}).get("group_id") != group for key, group in groups.items()):
            raise ValueError("split group differs from stored provider group")
    else:
        raise ValueError("unknown evaluation dataset")
    absent = json.loads(Path(config["absent_queries"]).read_text()) if config.get("absent_queries") else []
    builder = build_legacy_benchmark if legacy else build_benchmark
    views, queries, audit = builder(entities, assignments, seed=config["seed"], absent=absent)
    rows, timing = evaluate_queries(views, queries, config["timing_repetitions"],
                                   requested_k=config.get('requested_k'), regression_only=legacy)
    # Both supported source datasets were exposed in earlier project work.
    # A newer validation contract does not make them independent test evidence.
    for row in rows:
        row['regression_only'] = True
    result = {"protocol_version": "baseline-evaluation-v2", 'metric_protocol_version': METRIC_PROTOCOL,
              'benchmark_protocol_version': views.protocol_version, 'benchmark_mode': mode,
              'regression_only': True, "scorer": SCORER_NAME,
              "config": config, "config_fingerprint": fingerprint(config),
              "queries_fingerprint": fingerprint(queries), "audit": audit,
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "machine": platform.machine(), "processor": platform.processor() or "unreported",
                              "rapidfuzz": version("rapidfuzz")},
              "corpus": {"entities": len(entities), "aliases": sum(len(e.aliases) for e in entities)},
              "aggregates": aggregate(rows), "queries": rows, "timing": timing,
              "limitations": ["Previously exposed project datasets are regression-only, not independent generalization evidence.",
                              "Small selected corpus; synthetic perturbations are not real user traffic.",
                              "Source IDs and aliases are working record labels, not verified identities.",
                              "No confidence intervals or operational guarantees; correlated queries share entities.",
                              "Reserved training/calibration groups are not evaluated or fitted.",
                              "Unknown upstream duplicates may remain. Scores are not probabilities."]}
    return result, queries


def render_report(result: dict) -> str:
    """Generate readable numbers from machine results, never hand-entered metrics."""
    def show(m: dict) -> str:
        return f"{m['value']:.4f} (n={m['denominator']})" if m['value'] is not None else f"N/A ({m['reason']})"
    lines = ["# Existing RapidFuzz baseline evaluation", "", f"Dataset: `{result['config']['dataset']}`; protocol: {result['protocol_version']}.",
             f"Metric contract: {result['metric_protocol_version']}; regression-only: {result['regression_only']}.",
             f"Corpus: {result['corpus']['entities']} records, {result['corpus']['aliases']} aliases.", "",
             "These are record-retrieval experiments, not identity or wrongdoing findings.", "",
             "Positive metrics exclude absent, ambiguous and unlabelable queries. Absent suggestions have a separate denominator.",
             "Recall@K excludes cutoffs covering the index and queries evaluated below K. Full MRR requires complete rankings; MRR@K uses only observed ranks at its stated cutoff.", "",
             "| Partition / suite / slice | Queries | Positive groups | Recall@1 | Recall@10 | Recall@50 | Full MRR | MRR@K |",
             "|---|---:|---:|---|---|---|---|---|"]
    for row in result["aggregates"]:
        truncated = '; '.join(f"K={value['k']} (requested {value['requested_k']}): {show(value)}"
                              for value in row['mrr_by_depth'].values()) or show(row['mrr_at_k'])
        lines.append(f"| {row['partition']} / {row['suite']} / {row['slice']} | {row['query_count']} | {row['group_count']} | " +
                     " | ".join(show(row[k]) for k in ("recall_at_1", "recall_at_10", "recall_at_50", "mrr")) + f" | {truncated} |")
    lines += ["", "## Timing", "", f"{result['timing']['query_count']} queries; {result['timing']['observations']} observations. "
              f"Median {result['timing']['median_ms']} ms; p95 {result['timing']['p95_ms']} ms (nearest rank).",
              result['timing']['scope'], "", "## Exclusions and failures", "",
              f"Skipped transformations: {len(result['audit']['skipped'])}. Diagnostics: "
              f"{sum(q['status']=='diagnostic' for q in result['queries'])}. Full reasons and rankings are in results.json."]
    failures = [q for q in result["queries"] if q["failure"]]
    lines += [f"Top-1 failures among eligible positives: {len(failures)}. Up to 20 shown below.", ""]
    for q in sorted(failures, key=lambda q: (-(q['target_rank'] or 100000), q['query_id']))[:20]:
        lines.append(f"- {json.dumps(q['text'], ensure_ascii=False)} → target `{q['target_id']}`, rank {q['target_rank']}; {q['kind']}; {q['failure']}.")
    lines += ["", "## Absent-target behavior", ""]
    for row in result['aggregates']:
        if row['suite']=='absent' and row['slice']=='all' and row['query_count']:
            lines.append(f"{row['partition']} suggestion rate: " + show(row['absent_suggestion_rate']) + ". Threshold FPR: N/A; no threshold exists.")
    lines += ["", "## Limits", "", *["- " + x for x in result['limitations']], ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        if not isinstance(config, dict):
            raise ValueError('evaluation config must be an object')
        if not isinstance(config.get('output'), str) or not config['output'].strip():
            raise ValueError('output must be a nonblank directory path')
        output = Path(config["output"])
        if output.exists() or output.is_symlink():
            raise ValueError('output already exists; select a new directory to preserve historical evidence')
        result, queries = run(config)
        artifacts = {
            'queries.jsonl': ''.join(json.dumps(query, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n' for query in queries),
            'results.json': json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            'report.md': render_report(result),
        }
        output.mkdir(parents=True, mode=0o700, exist_ok=False)
        for name, content in artifacts.items():
            with (output / name).open('x', encoding='utf-8') as stream:
                stream.write(content)
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(output), "queries": len(queries), "skipped": len(result['audit']['skipped']),
                      "test_challenge": next(r for r in result['aggregates'] if r['partition']=='test' and r['suite']=='challenge' and r['slice']=='all')}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
