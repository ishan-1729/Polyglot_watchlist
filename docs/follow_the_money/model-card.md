# Priority models — synthetic pipeline verification

These models are research experiments, not classifiers of guilt, ownership or
operational risk. No real Elliptic model was trained. Elliptic++ dataset licence
verification is blocked; Elliptic2 exceeds the approved download limit.

The seeded generator creates 600 fictional nodes across 30 periods. Periods
1–18 train (360 nodes), 19–24 select epochs (120), and 25–30 test (120).
IDs do not cross splits. Directed messages flow from earlier to later nodes;
training removes later edges. Scaling uses training rows only. Perturbing test
features must leave saved weights and validation metrics identical.

GraphSAGE, GAT and XGBoost receive the same numeric features and temporal split;
the GNNs additionally receive graph edges. Six synthetic feature proxies include
one deliberately privileged signal. A second fit removes it. The five remaining
columns correspond to live-computable definitions in `features.py`, but their
synthetic values are generated, not measurements from public addresses.

Measured test average precision (seed 47, 40 GNN epochs maximum):

| Model | Full features | Five-feature subset | Drop |
|---|---:|---:|---:|
| GraphSAGE | 0.946293 | 0.699059 | 0.247234 |
| GAT | 0.572325 | 0.562924 | 0.009401 |
| XGBoost | 0.930949 | 0.711873 | 0.219076 |

All metrics, split counts, scalers, hashes and measured fit times are in
`config/follow_the_money/training-results.json`. They establish executable
experiments, not generalization. No confidence intervals or search over seeds
was performed. GAT's weak result is retained. Similarity/priority scores are
uncalibrated. The Brier metric does not itself establish calibration.

`DistributionGuard` checks feature schema, chain and standardized distance using
training statistics. Synthetic training provenance cannot pass as Bitcoin/TRON.
Missing, out-of-distribution or invalid model outputs fall back to a bounded
heuristic. A suitable real-data model requires licence review, mapped features,
new temporal evaluation and calibration before operational consideration.

The change classifier derives weak labels from later synthetic co-spends. It
trains only when the label was observed before the cutoff. Paired negatives are
assumptions, and collaborative transactions can invalidate the positive label.
The optional value regressor requires at least three independently completed
training cases. Its trace experiment follows in the evaluation phase.

PyG installs and runs on Linux Python 3.14; wheel resolution also succeeded for
Windows. Windows runtime was not tested. TorchScript and PyG annotation warnings
are upstream compatibility warnings, retained in test output. No TorchScript or
compiled PyG extension is used. Model weights remain under gitignored `data/`;
torch weights must be loaded with `weights_only=True`. Never load arbitrary
pickle models supplied by an LLM, source label or API client.

The final evaluation trains a separate trace-value model on three completed,
explicitly simulated fixture reviews (51 rows) and evaluates a fourth (17 rows).
It uses critic-retained observed edges and censored distance penalty 25. Its
three features are parent-value fraction, hop count and log incoming units.
Cases/identifiers are disjoint, but graphs share the same authored structure.
The reported MAE and search gains are toy-family diagnostics only. The optional
`demo --learned-synthetic` exercises this policy; real wallets and TRON trigger
fallback. See `evaluation-results.json` for final measured results.

The GNNs are not validated production frontier scorers. Their synthetic chain
provenance cannot be relabeled Bitcoin. A real deployment would require licensed
point-in-time training features, complete neighborhood/coverage semantics,
independent temporal evaluation, a search benchmark and calibration. The current
public gold replay correctly uses heuristics and reports no GNN benefit.
