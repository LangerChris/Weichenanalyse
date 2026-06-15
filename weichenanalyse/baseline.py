"""Baseline-Anomalie-Detektor: Abweichung von der EIGENEN Historie je Weiche.

Prinzip (siehe docs/MODELLING_PLAN.md, "pro Weiche, nicht zwischen Weichen"):
Für jede Gruppe (Weiche × Richtung L/R) wird aus den Trainings-Umläufen ein
Schwerpunkt (Mittelwert) und die Streuung (Std) der Features gelernt — rein
unüberwacht, ganz ohne Labels. Der Anomalie-Score eines Umlaufs ist seine
standardisierte Distanz (RMS der z-Werte) zu diesem weichen-eigenen Schwerpunkt.

Dadurch ist der Score in "Sigma der Eigenhistorie" ausgedrückt und damit über
Weichen hinweg vergleichbar, OHNE absolute Kennwerte zwischen Weichen zu vergleichen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from weichenanalyse.features import FEATURE_COLUMNS

GROUP_KEYS = ["object_id", "position"]


@dataclass
class PerSwitchBaseline:
    """Schwerpunkt-Baseline je (Weiche, Richtung)."""

    feature_columns: list[str] = field(default_factory=lambda: list(FEATURE_COLUMNS))
    min_train: int = 10          # Mindestzahl Umläufe, um eine Baseline zu lernen
    eps: float = 1e-9
    groups_: dict = field(default_factory=dict)  # (object_id, position) -> (mean, std)

    def fit(self, feats_train: pd.DataFrame) -> "PerSwitchBaseline":
        self.groups_ = {}
        for key, g in feats_train.groupby(GROUP_KEYS):
            X = g[self.feature_columns].to_numpy(dtype=float)
            if len(X) < self.min_train:
                continue
            mean = np.nanmean(X, axis=0)
            std = np.nanstd(X, axis=0)
            std = np.where(std < self.eps, self.eps, std)
            self.groups_[tuple(key)] = (mean, std)
        return self

    def score(self, feats: pd.DataFrame) -> np.ndarray:
        """RMS-z-Distanz je Umlauf. NaN, wenn die Gruppe nicht gelernt wurde."""
        scores = np.full(len(feats), np.nan)
        X_all = feats[self.feature_columns].to_numpy(dtype=float)
        keys = list(zip(*[feats[k] for k in GROUP_KEYS]))
        for i, key in enumerate(keys):
            params = self.groups_.get(key)
            if params is None:
                continue
            mean, std = params
            z = (X_all[i] - mean) / std
            scores[i] = np.sqrt(np.nanmean(z ** 2))
        return scores

    def thresholds(self, feats_train_scored: pd.DataFrame, score_col: str = "score",
                   k: float = 3.0) -> dict:
        """Adaptive Warngrenze je Gruppe: mean + k*std der Trainings-Scores.

        Früh-Warn-Politik: kleineres k senkt die Schwelle (warnt früher).
        """
        out = {}
        for key, g in feats_train_scored.dropna(subset=[score_col]).groupby(GROUP_KEYS):
            s = g[score_col].to_numpy()
            out[tuple(key)] = float(np.mean(s) + k * np.std(s))
        return out
