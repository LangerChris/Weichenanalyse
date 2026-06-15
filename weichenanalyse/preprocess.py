"""Vorverarbeitung der Stromkurven.

Schritte (siehe docs/MODELLING_PLAN.md):
  - Offset-Korrektur (Sensor-Baseline am Kurvenanfang entfernen)
  - Maintenance-Umläufe ausfiltern
  - Aufteilung nach Richtung L/R
  - Resampling auf ein festes Raster (für PCA/Autoencoder)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

def correct_offset(current: np.ndarray) -> np.ndarray:
    """Sensor-Offset abziehen.

    Der Motor läuft sofort an (die Anlaufspitze liegt schon bei Sample ~3-4), es gibt
    also keine ruhige Vorlaufphase. Strom ist physikalisch >= 0; die einzige Baseline
    ist das kleine Sensor-Rauschen (~-0.01 A). Daher das Minimum als Nulllinie nehmen,
    nicht die ersten Samples (die würden den Peak treffen).
    """
    if current.size == 0:
        return current
    return current - np.min(current)


def resample_curve(current: np.ndarray, n_points: int = 200) -> np.ndarray:
    """Kurve linear auf eine feste Länge interpolieren (Zeit normiert auf [0, 1])."""
    if current.size == 0:
        return np.full(n_points, np.nan)
    if current.size == 1:
        return np.full(n_points, current[0])
    src = np.linspace(0.0, 1.0, current.size)
    dst = np.linspace(0.0, 1.0, n_points)
    return np.interp(dst, src, current)


def filter_maintenance(meta: pd.DataFrame, currents: list[np.ndarray]):
    """Umläufe im Wartungsmodus entfernen (kein regulärer Betrieb)."""
    mask = ~meta["is_maintenance"].astype(bool).to_numpy()
    return _apply_mask(meta, currents, mask)


def split_by_position(meta: pd.DataFrame, currents: list[np.ndarray]) -> dict[str, tuple]:
    """In Richtungen L/R aufteilen. Returns {position: (meta_sub, currents_sub)}."""
    out: dict[str, tuple] = {}
    for pos in sorted(meta["position"].dropna().unique()):
        mask = (meta["position"] == pos).to_numpy()
        out[pos] = _apply_mask(meta, currents, mask)
    return out


def build_matrix(
    currents: list[np.ndarray],
    n_points: int = 200,
    offset: bool = True,
) -> np.ndarray:
    """Liste variabel langer Kurven -> (n_turns, n_points)-Matrix für Modelle."""
    rows = []
    for c in currents:
        if offset:
            c = correct_offset(c)
        rows.append(resample_curve(c, n_points))
    return np.vstack(rows) if rows else np.empty((0, n_points))


def _apply_mask(meta: pd.DataFrame, currents: list[np.ndarray], mask: np.ndarray):
    sub_meta = meta.loc[mask].reset_index(drop=True)
    sub_currents = [c for c, keep in zip(currents, mask) if keep]
    return sub_meta, sub_currents
