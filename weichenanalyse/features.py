"""Phasenbasierte Feature-Extraktion pro Umlauf.

Der Stromverlauf eines Stellvorgangs hat drei Phasen (siehe DATEN_ERKLAERUNG.md):
  1. Anlaufspitze  — kurzer Strompeak beim Motorstart
  2. Laufphase     — gleichmäßiger Strom während die Zunge bewegt wird
  3. Abschaltung   — Strom fällt auf 0

Die Features fassen jede Kurve zu einem interpretierbaren Vektor zusammen, der die
klassischen Anomalie-Detektoren speist.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from weichenanalyse.preprocess import correct_offset

# Anteil der Anlaufphase an der Gesamtdauer (für die Phasen-Trennung).
_STARTUP_FRACTION = 0.2


def extract_features(current: np.ndarray, sampling_interval: float = 0.02) -> dict[str, float]:
    """Feature-Vektor für eine einzelne Stromkurve berechnen."""
    c = correct_offset(np.asarray(current, dtype=float))
    n = c.size
    if n == 0:
        return {}

    dt = sampling_interval
    duration = n * dt
    startup_end = max(1, int(n * _STARTUP_FRACTION))

    startup = c[:startup_end]
    run = c[startup_end:] if n > startup_end else c

    peak = float(np.max(c))
    return {
        "duration_s": float(duration),
        "n_samples": float(n),
        "peak_current": peak,
        "peak_time_s": float(np.argmax(c) * dt),
        "mean_current": float(np.mean(c)),
        "std_current": float(np.std(c)),
        "energy": float(np.sum(c) * dt),  # ∫ I dt
        "startup_peak": float(np.max(startup)),
        "run_mean": float(np.mean(run)),
        "run_std": float(np.std(run)),
        "run_slope": _slope(run, dt),
        "settle_current": float(np.mean(c[-startup_end:])),  # Reststrom am Ende
    }


def features_dataframe(
    meta: pd.DataFrame, currents: list[np.ndarray]
) -> pd.DataFrame:
    """Feature-Tabelle für alle Umläufe; behält die Metadaten-Schlüssel bei."""
    rows = []
    for row, curve in zip(meta.itertuples(index=False), currents):
        feats = extract_features(curve, row.sampling_interval)
        feats.update(
            object_id=row.object_id,
            time=row.time,
            position=row.position,
            temperature_c=(row.temperature_air - 273.15)
            if row.temperature_air is not None
            else np.nan,
            has_error=len(row.error_ids) > 0,
        )
        rows.append(feats)
    return pd.DataFrame(rows)


FEATURE_COLUMNS = [
    "duration_s", "n_samples", "peak_current", "peak_time_s", "mean_current",
    "std_current", "energy", "startup_peak", "run_mean", "run_std",
    "run_slope", "settle_current",
]


def _slope(y: np.ndarray, dt: float) -> float:
    """Lineare Steigung (A/s) der Laufphase via Least-Squares."""
    if y.size < 2:
        return 0.0
    x = np.arange(y.size) * dt
    return float(np.polyfit(x, y, 1)[0])
