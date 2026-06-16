"""Persistenz-basierte Vorwarnung.

Idee (vom Autor vorgegeben): nicht auf einzelne Ausreißer reagieren, sondern warnen,
wenn das Ankündigungsmerkmal — erhöhte Stromstärke gegenüber der EIGENEN Baseline der
Weiche — über mehr als `min_consecutive` Umläufe in Folge anhält. Das bildet einen
anlaufenden Verschleiß ab, nicht Rauschen.

Ablauf je Weiche × Richtung (zeitlich sortiert):
  1. Baseline aus den ersten `baseline_turns` Umläufen (robust: Median + MAD) — angenommen gesund.
  2. Pro Umlauf: Abweichung z = (Wert − Median) / MAD; "erhöht", wenn z > `z_thresh`.
  3. Warnung, sobald `min_consecutive` aufeinanderfolgende Umläufe "erhöht" sind.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

GROUP_KEYS = ["object_id", "position"]
_MAD_TO_STD = 1.4826


@dataclass
class PersistenceWarning:
    feature: str = "mean_amp"              # Amplituden-Merkmal (Strom A oder Leistung W).
    # Empirisch: der MITTELwert kündigt Endlage-Störungen an, der Peak nicht.
    baseline_turns: int = 50               # erste N Umläufe je Gruppe = gesunde Referenz
    z_thresh: float = 2.0                  # ab wann ein Umlauf "erhöht" zählt
    min_consecutive: int = 10              # so viele erhöhte Umläufe in Folge -> Warnung
    min_scale_frac: float = 0.02           # MAD-Untergrenze als Anteil von |Median|
    eps: float = 1e-9
    groups_: dict = field(default_factory=dict)  # (oid,pos) -> (median, scale)

    def _scale(self, med: float, mad: float) -> float:
        # Floor verhindert explodierende z-Werte bei fast konstanten Merkmalen (z.B. Umlaufzeit).
        return max(mad, self.min_scale_frac * abs(med), self.eps)

    def fit(self, meta: pd.DataFrame) -> "PersistenceWarning":
        self.groups_ = {}
        for key, g in meta.groupby(GROUP_KEYS):
            g = g.sort_values("time")
            n_base = min(self.baseline_turns, max(5, len(g) // 2))
            base = g[self.feature].to_numpy(dtype=float)[:n_base]
            base = base[~np.isnan(base)]
            if base.size == 0:
                continue
            med = float(np.median(base))
            mad = float(np.median(np.abs(base - med))) * _MAD_TO_STD
            self.groups_[tuple(key)] = (med, self._scale(med, mad))
        return self

    def predict(self, meta: pd.DataFrame) -> pd.DataFrame:
        """Pro Umlauf: z-Abweichung, 'erhöht', Lauflänge und Warn-Flag (zeitlich kausal)."""
        out = meta.copy()
        out["z_dev"] = np.nan
        out["elevated"] = False
        out["run_len"] = 0
        out["warn"] = False

        for key, idx in out.groupby(GROUP_KEYS).groups.items():
            params = self.groups_.get(tuple(key) if not isinstance(key, tuple) else key)
            if params is None:
                continue
            med, mad = params
            g = out.loc[idx].sort_values("time")
            order = g.index.to_numpy()
            vals = g[self.feature].to_numpy(dtype=float)
            z = (vals - med) / mad
            elevated = z > self.z_thresh

            run = np.zeros(len(g), dtype=int)
            c = 0
            for i, e in enumerate(elevated):
                c = c + 1 if e else 0
                run[i] = c
            warn = run >= self.min_consecutive

            out.loc[order, "z_dev"] = z
            out.loc[order, "elevated"] = elevated
            out.loc[order, "run_len"] = run
            out.loc[order, "warn"] = warn
        return out


@dataclass
class EnsembleWarning:
    """Mehrere Persistenz-Warner ODER-verknüpft (maximale Trefferquote).

    Politik "lieber einmal zu viel warnen": gewarnt wird, sobald IRGENDEIN Warner
    anschlägt. Jeder Warner ist per-Weiche-relativ; reine Leistungs-Weichen werden
    über `mean_amp`/`peak_amp` automatisch mit abgedeckt.
    """

    features: tuple[str, ...] = ("mean_amp", "peak_amp", "turn_time")
    baseline_turns: int = 50
    z_thresh: float = 2.0
    min_consecutive: int = 10
    warners_: dict = field(default_factory=dict)

    def fit(self, meta: pd.DataFrame) -> "EnsembleWarning":
        self.warners_ = {}
        for f in self.features:
            self.warners_[f] = PersistenceWarning(
                feature=f, baseline_turns=self.baseline_turns,
                z_thresh=self.z_thresh, min_consecutive=self.min_consecutive,
            ).fit(meta)
        return self

    def predict(self, meta: pd.DataFrame) -> pd.DataFrame:
        out = meta.copy()
        warn_any = np.zeros(len(out), dtype=bool)
        fired = [[] for _ in range(len(out))]
        for f, w in self.warners_.items():
            wf = w.predict(meta)["warn"].to_numpy()
            warn_any |= wf
            for i in np.where(wf)[0]:
                fired[i].append(f)
        out["warn"] = warn_any
        out["warn_by"] = [",".join(x) for x in fired]
        return out


def evaluate_warnings(
    pred: pd.DataFrame, target_col: str = "is_target"
) -> pd.DataFrame:
    """Je Weiche: erste Warnung vs. erstes Ziel-Event, Vorwarnzeit (in Umläufen)."""
    rows = []
    for oid, g in pred.groupby("object_id"):
        g = g.sort_values("time").reset_index(drop=True)
        has_target = g[target_col].any()
        warn_pos = np.where(g["warn"].to_numpy())[0]
        tgt_pos = np.where(g[target_col].to_numpy())[0]
        first_warn = int(warn_pos[0]) if warn_pos.size else None
        first_tgt = int(tgt_pos[0]) if tgt_pos.size else None
        lead = (first_tgt - first_warn) if (first_warn is not None and first_tgt is not None) else None
        rows.append({
            "object_id": oid,
            "turns": len(g),
            "has_target": bool(has_target),
            "warned": first_warn is not None,
            "first_warn_idx": first_warn,
            "first_target_idx": first_tgt,
            "lead_turns": lead,  # >0: Warnung VOR dem Ereignis
        })
    return pd.DataFrame(rows)
