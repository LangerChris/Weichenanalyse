"""Form-Merkmale pro Umlauf aus der vereinheitlichten Wellenform (Strom A oder Leistung W).

Diese Merkmale liefern zusätzliche Vorboten für das Warner-Ensemble — nicht nur die
Amplitude (Mittelwert/Peak), sondern die FORM der Kurve: Steigung der Laufphase,
Energie, Lage der Spitze, Reststrom am Ende. Alle einheiten-agnostisch (funktionieren
auf Strom wie Leistung), da die Warner ohnehin per-Weiche-relativ arbeiten.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from weichenanalyse.data import DEFAULT_META, load_meta, load_signals
from weichenanalyse.features import extract_features

# Aus extract_features übernommene, form-beschreibende Größen (unit-agnostisch).
_BASE_COLS = ["run_slope", "energy", "peak_time_s", "settle_current", "run_std"]
SHAPE_COLS = [f"shape_{c}" for c in _BASE_COLS]


def shape_features(meta_path: Path | str = DEFAULT_META) -> pd.DataFrame:
    """Form-Merkmale je Umlauf, Schlüssel (object_id, time, position)."""
    signals = load_signals(meta_path)
    meta = load_meta(Path(meta_path))
    rows = []
    for row in meta.itertuples(index=False):
        wave, _unit = signals.get((row.object_id, row.time, row.position),
                                  (np.array([]), ""))
        f = extract_features(wave, row.sampling_interval) if wave.size else {}
        rec = {"object_id": row.object_id, "time": row.time, "position": row.position}
        for base, col in zip(_BASE_COLS, SHAPE_COLS):
            rec[col] = f.get(base, np.nan)
        rows.append(rec)
    return pd.DataFrame(rows)


def attach_shape_features(meta: pd.DataFrame, meta_path: Path | str = DEFAULT_META) -> pd.DataFrame:
    """Form-Merkmale an eine Meta-Tabelle anfügen (Merge über object_id/time/position)."""
    sf = shape_features(meta_path)
    return meta.merge(sf, on=["object_id", "time", "position"], how="left")
