"""Testlauf der persistenz-basierten Vorwarnung gegen die Endlage-Ereignisse.

Warnung = Stromstärke über `min_consecutive` Umläufe in Folge erhöht (relativ zur
Eigen-Baseline der Weiche). Bewertung: wird vor der Endlage-Störung (2723/2724)
gewarnt, und wie viel Vorwarnzeit (in Umläufen)?

Usage:
    python scripts/run_warning.py
    python scripts/run_warning.py --feature motor_0_mean_current --z 2.0 --min-consecutive 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from weichenanalyse.labels import load_labeled_dataset
from weichenanalyse.warning import PersistenceWarning, evaluate_warnings


def main():
    ap = argparse.ArgumentParser(description="Persistenz-Vorwarnung testen")
    ap.add_argument("--feature", default="motor_0_mean_current")
    ap.add_argument("--baseline-turns", type=int, default=50)
    ap.add_argument("--z", type=float, default=2.0)
    ap.add_argument("--min-consecutive", type=int, default=10)
    args = ap.parse_args()

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 30)

    meta = load_labeled_dataset(horizon=0)  # is_target reicht für die Bewertung
    model = PersistenceWarning(
        feature=args.feature,
        baseline_turns=args.baseline_turns,
        z_thresh=args.z,
        min_consecutive=args.min_consecutive,
    ).fit(meta)
    pred = model.predict(meta)

    print(f"Konfiguration: feature={args.feature}  z>{args.z}  min_consecutive={args.min_consecutive}  "
          f"baseline_turns={args.baseline_turns}")

    rep = evaluate_warnings(pred, target_col="is_target")
    tgt = rep[rep.has_target]
    notgt = rep[~rep.has_target]

    # Recall: Anteil Ziel-Weichen, die VOR dem ersten Ziel-Event gewarnt wurden
    warned_before = tgt[(tgt.lead_turns.notna()) & (tgt.lead_turns > 0)]
    print(f"\nZiel-Weichen: {len(tgt)}  |  davon rechtzeitig gewarnt (Warnung vor 1. Ereignis): "
          f"{len(warned_before)}  ({100*len(warned_before)/max(len(tgt),1):.0f}%)")
    if len(warned_before):
        print(f"  Vorwarnzeit (Umläufe)  Median={warned_before.lead_turns.median():.0f}  "
              f"Min={warned_before.lead_turns.min():.0f}  Max={warned_before.lead_turns.max():.0f}")
    # Fehlalarm: Weichen OHNE Ziel-Event, die trotzdem warnen
    fa = notgt[notgt.warned]
    print(f"Weichen ohne Ziel-Event: {len(notgt)}  |  davon mit Warnung (Fehlalarm-Kandidaten): {len(fa)}")

    print("\n=== Je Weiche (mit Ziel-Event) ===")
    show = tgt.merge(meta[["object_id"]].drop_duplicates(), on="object_id")
    print(rep[rep.has_target][["object_id", "turns", "warned", "first_warn_idx",
          "first_target_idx", "lead_turns"]].to_string(index=False))


if __name__ == "__main__":
    main()
