"""Feature-Assembly für das lernende Transfer-Modell (Endlage-Frühwarnung).

Grundsatz (siehe docs/MODELLING_PLAN.md):
- **dynamische** Merkmale werden PER WEICHE × Richtung normiert (z gegen die Eigen-Baseline
  aus den ersten Umläufen) → über Weichen vergleichbar, ermöglicht Transfer.
- **Persistenz**-Merkmale (wie lange schon erhöht, geglätteter Trend) bilden ab, dass ein
  Fehler eine Weile anhalten muss — vereinzelte Blips bleiben unauffällig.
- **statische** Metadaten (Antriebszahl, Heizung, Signaltyp) als Transfer-Kontext.

Per-Weiche-Baseline ist selbst-referenziell → kein Leakage über Weichen (LOSO-tauglich).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from weichenanalyse.data import DEFAULT_META
from weichenanalyse.labels import load_labeled_dataset
from weichenanalyse.shape import SHAPE_COLS, attach_shape_features

GROUP_KEYS = ["object_id", "position"]
_MAD_TO_STD = 1.4826

# Dynamische Roh-Merkmale, die per Weiche normiert werden.
DYN_FEATURES = ["mean_amp", "peak_amp", "turn_time", *SHAPE_COLS]
# Resultierende Modell-Spalten.
Z_COLS = [f"z_{f}" for f in DYN_FEATURES]
# Persistenz/Trend — Schwerpunkt auf der Umlaufzeit (laut Feature-Importance das Signal).
PERSIST_COLS = [
    "run_len_amp", "roll_z_amp", "roll_z_energy",
    "roll_z_tt", "run_len_tt", "frac_short_tt",
]
# Statische Metadaten bewusst WEGGELASSEN: bei ~48 Weichen Scheinkorrelation/Identitäts-Leakage.
FEATURE_COLS = Z_COLS + PERSIST_COLS


def _per_switch_z(g: pd.DataFrame, feature: str, baseline_turns: int) -> np.ndarray:
    base = g[feature].to_numpy(dtype=float)[:baseline_turns]
    base = base[~np.isnan(base)]
    if base.size == 0:
        return np.full(len(g), np.nan)
    med = float(np.median(base))
    mad = float(np.median(np.abs(base - med))) * _MAD_TO_STD
    scale = max(mad, 0.02 * abs(med), 1e-9)
    return (g[feature].to_numpy(dtype=float) - med) / scale


def assemble_features(meta_path: Path | str = DEFAULT_META, baseline_turns: int = 50) -> pd.DataFrame:
    """Per-Umlauf-Feature-Tabelle für das Modell (inkl. Schlüssel und statischer Metadaten)."""
    meta = attach_shape_features(load_labeled_dataset(meta_path, horizon=0))
    # Überlappende HARs derselben Weiche können Umläufe doppeln → eindeutig je Schlüssel.
    meta = meta.drop_duplicates(GROUP_KEYS + ["time"]).reset_index(drop=True)
    meta["dt"] = pd.to_datetime(meta["time"], unit="ms")
    meta["signal_W"] = (meta["signal_unit"] == "W").astype(int)
    meta["has_heater"] = meta["has_heater"].astype(int)

    parts = []
    for _, g in meta.groupby(GROUP_KEYS):
        g = g.sort_values("time").copy()
        for f, zc in zip(DYN_FEATURES, Z_COLS):
            g[zc] = _per_switch_z(g, f, baseline_turns)
        # Persistenz: Lauflänge erhöhter Amplitude (z>1) + geglättete Trends
        elevated = (g["z_mean_amp"] > 1.0).to_numpy()
        run = np.zeros(len(g), dtype=int)
        c = 0
        for i, e in enumerate(elevated):
            c = c + 1 if e else 0
            run[i] = c
        g["run_len_amp"] = run
        g["roll_z_amp"] = g["z_mean_amp"].rolling(5, min_periods=1).mean().to_numpy()
        g["roll_z_energy"] = g["z_shape_energy"].rolling(5, min_periods=1).mean().to_numpy()

        # Umlaufzeit-Dynamik (dominantes Signal): geglätteter Trend, Lauflänge auffälliger
        # Umlaufzeit und Anteil VERKÜRZTER Umläufe ("Umlaufzeit zu kurz" = Endlage-nah).
        ztt = g["z_turn_time"]
        g["roll_z_tt"] = ztt.rolling(5, min_periods=1).mean().to_numpy()
        tt_dev = (ztt.abs() > 1.0).to_numpy()
        run_tt = np.zeros(len(g), dtype=int)
        c = 0
        for i, e in enumerate(tt_dev):
            c = c + 1 if e else 0
            run_tt[i] = c
        g["run_len_tt"] = run_tt
        g["frac_short_tt"] = (ztt < -1.0).rolling(10, min_periods=1).mean().to_numpy()
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    keep = GROUP_KEYS + ["time", "dt"] + FEATURE_COLS  # n_drives ist Teil von FEATURE_COLS
    return out[keep]
