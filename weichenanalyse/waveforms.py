"""Vereinheitlichte, per-Weiche normierte Wellenform-Matrix für das 1D-CNN.

Jede Weiche misst Strom (A) ODER Leistung (W). Pro Umlauf wird die Rohkurve
offset-korrigiert, auf eine feste Länge resampelt und dann PER WEICHE × RICHTUNG
gegen die Eigen-Baseline normiert (Abweichung von der eigenen Normalform):

    norm = (kurve − Baseline-Mittelkurve) / Baseline-Skala

Damit sieht das CNN einheiten-agnostische Form-Abweichungen vom Normalzustand der
jeweiligen Weiche — gleiches per-Weiche-relatives Prinzip wie bei den Features.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from weichenanalyse.data import DEFAULT_META, load_meta, load_signals
from weichenanalyse.preprocess import correct_offset, resample_curve

GROUP_KEYS = ["object_id", "position"]


def waveform_matrix(
    meta_path: Path | str = DEFAULT_META, n_points: int = 200, baseline_turns: int = 50
) -> tuple[pd.DataFrame, np.ndarray]:
    """Returns (keys_df[object_id,position,time,dt], X[n_turns, n_points])."""
    signals = load_signals(meta_path)
    meta = load_meta(Path(meta_path)).drop_duplicates(GROUP_KEYS + ["time"])

    keys_parts, mat_parts = [], []
    for (oid, pos), g in meta.groupby(GROUP_KEYS):
        g = g.sort_values("time")
        curves = np.vstack([
            resample_curve(correct_offset(signals.get((oid, t, pos), (np.array([]), ""))[0]), n_points)
            for t in g["time"]
        ])
        base = curves[:baseline_turns]
        base_mean = np.nanmean(base, axis=0)
        scale = float(np.nanstd(base)) or 1.0
        norm = (curves - base_mean) / scale
        mat_parts.append(np.nan_to_num(norm))
        keys_parts.append(g[["object_id", "position", "time"]])

    keys = pd.concat(keys_parts, ignore_index=True)
    keys["dt"] = pd.to_datetime(keys["time"], unit="ms")
    X = np.vstack(mat_parts).astype("float32")
    return keys, X
