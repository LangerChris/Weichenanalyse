"""Evaluation: zufälliger Train/Test-Split und AUC gegen schwache Labels.

Die schwachen Labels (`has_error`, aus DIANAs error_ids) dienen NUR zur Bewertung,
nicht zum Training. Score = Abweichung von der Eigenhistorie; eine Weiche mit
nur einer Klasse (z. B. durchgehend Fehler) hat keine definierte AUC.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def random_split(feats: pd.DataFrame, test_frac: float = 0.3, seed: int = 0):
    """Zufälliger Split in Train/Test (zeilenweise)."""
    rng = np.random.default_rng(seed)
    idx = np.arange(len(feats))
    rng.shuffle(idx)
    n_test = int(len(idx) * test_frac)
    test_idx = np.sort(idx[:n_test])
    train_idx = np.sort(idx[n_test:])
    return (
        feats.iloc[train_idx].reset_index(drop=True),
        feats.iloc[test_idx].reset_index(drop=True),
    )


def _metrics(df: pd.DataFrame, score_col: str, label_col: str):
    y = df[label_col].astype(int).to_numpy()
    s = df[score_col].to_numpy()
    n, n_pos = len(y), int(y.sum())
    if n_pos == 0 or n_pos == n:
        return n, n_pos, np.nan, np.nan
    return n, n_pos, roc_auc_score(y, s), average_precision_score(y, s)


def evaluate_scores(
    feats_scored: pd.DataFrame, score_col: str = "score", label_col: str = "has_error"
) -> pd.DataFrame:
    """AUC/PR gesamt und je Weiche (nur Zeilen mit gültigem Score)."""
    df = feats_scored.dropna(subset=[score_col])
    rows = [("GESAMT", *_metrics(df, score_col, label_col))]
    for key, g in df.groupby("object_id"):
        rows.append((key, *_metrics(g, score_col, label_col)))
    return pd.DataFrame(rows, columns=["gruppe", "n", "n_pos", "auc", "ap"])
