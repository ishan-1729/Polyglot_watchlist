"""Temporal GNNs, training-distribution checks and optional trace value model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import torch
from torch import nn
from torch_geometric.nn import GATConv, SAGEConv

from follow_the_money.contracts import FtmError


class PriorityGNN(nn.Module):
    """Two causal message-passing layers; never symmetrize temporal edges."""

    def __init__(self, width: int, kind: str = "sage", hidden: int = 16):
        super().__init__()
        if kind not in {"sage", "gat"}:
            raise ValueError("kind must be sage or gat")
        layer = SAGEConv if kind == "sage" else GATConv
        self.first = layer(width, hidden)
        self.second = layer(hidden, 1)

    def forward(self, features: torch.Tensor, edges: torch.Tensor) -> torch.Tensor:
        return self.second(torch.relu(self.first(features, edges)), edges).squeeze(-1)


@dataclass
class DistributionGuard:
    mean: np.ndarray
    scale: np.ndarray
    threshold: float
    chain: str
    feature_names: tuple[str, ...]

    @classmethod
    def fit(
        cls, values: np.ndarray, *, chain: str, feature_names: Sequence[str]
    ) -> DistributionGuard:
        if len(values) < 2 or not np.isfinite(values).all():
            raise FtmError("invalid_training", "OOD fit requires finite training rows")
        mean = values.mean(axis=0)
        scale = np.maximum(values.std(axis=0), 1e-6)
        distances = np.sqrt(np.mean(((values - mean) / scale) ** 2, axis=1))
        return cls(
            mean,
            scale,
            float(max(1.0, np.quantile(distances, 0.99) * 1.25)),
            chain,
            tuple(feature_names),
        )

    def inspect(
        self, values: Sequence[float], *, chain: str, feature_names: Sequence[str]
    ) -> dict[str, Any]:
        x = np.asarray(values, dtype=float)
        mismatch = (
            chain != self.chain
            or tuple(feature_names) != self.feature_names
            or x.shape != self.mean.shape
            or not np.isfinite(x).all()
        )
        distance = (
            None
            if mismatch
            else float(np.sqrt(np.mean(((x - self.mean) / self.scale) ** 2)))
        )
        return {
            "ood": mismatch or distance > self.threshold,
            "distance": distance,
            "threshold": self.threshold,
            "reason": "schema_or_chain_mismatch" if mismatch else "training_distance",
        }


def score_address(
    values: Sequence[float],
    *,
    guard: DistributionGuard | None,
    predict: Any = None,
    chain: str,
    feature_names: Sequence[str],
    heuristic: float,
) -> dict[str, Any]:
    """Fail closed to a bounded heuristic when no suitable trained model exists."""
    if not np.isfinite(heuristic) or not 0 <= heuristic <= 1:
        raise ValueError("heuristic must be finite in [0, 1]")
    check = (
        {"ood": True, "reason": "model_unavailable"}
        if guard is None
        else guard.inspect(values, chain=chain, feature_names=feature_names)
    )
    if check["ood"] or predict is None:
        return {
            **check,
            "score": heuristic,
            "method": "heuristic_fallback",
            "calibrated": False,
        }
    try:
        score = float(predict(np.asarray(values, dtype=float).reshape(1, -1))[0])
    except (ValueError, TypeError, RuntimeError, IndexError, KeyError):
        return {
            "ood": True,
            "reason": "model_error",
            "score": heuristic,
            "method": "heuristic_fallback",
            "calibrated": False,
        }
    if not np.isfinite(score) or not 0 <= score <= 1:
        return {
            "ood": True,
            "reason": "invalid_model_output",
            "score": heuristic,
            "method": "heuristic_fallback",
            "calibrated": False,
        }
    return {**check, "score": score, "method": "priority_model", "calibrated": False}


def fit_trace_value(rows: Sequence[dict[str, Any]], *, train_end: int):
    """Fit remaining-calls value from completed own traces, respecting time.

    Requires independent cases; never train on the task being evaluated. The
    caller must split by case and use completion time, not just seed time.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    selected = [
        r for r in rows if r["completed_at"] <= train_end and r["split"] == "train"
    ]
    if len({r["case_id"] for r in selected}) < 3:
        raise FtmError(
            "insufficient_traces", "At least three completed training cases required"
        )
    x = np.asarray([r["features"] for r in selected], dtype=float)
    y = np.asarray([r["remaining_calls"] for r in selected], dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all() or (y < 0).any():
        raise FtmError("invalid_training", "Invalid trace value examples")
    return HistGradientBoostingRegressor(
        max_iter=30, max_leaf_nodes=7, min_samples_leaf=2, random_state=47
    ).fit(x, y)
