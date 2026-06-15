"""Erster Testdurchlauf: Per-Weiche-Baseline auf einem zufälligen Test-Subset.

Pipeline: HAR-Extrakt laden -> Wartung filtern -> Features -> zufälliger Train/Test-Split
-> Baseline (Abweichung von der Eigenhistorie) lernen -> Test scoren -> AUC/PR
gegen die schwachen Labels (DIANA error_ids).

Usage:
    python scripts/run_baseline.py
    python scripts/run_baseline.py --test-frac 0.3 --seed 0 --k 3.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Repo-Wurzel in den Importpfad, damit das Skript aus scripts/ heraus läuft.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from weichenanalyse.baseline import PerSwitchBaseline
from weichenanalyse.data import load_dataset
from weichenanalyse.evaluate import evaluate_scores, random_split
from weichenanalyse.features import features_dataframe
from weichenanalyse import preprocess as pp


def main():
    ap = argparse.ArgumentParser(description="Baseline-Testdurchlauf (per Weiche)")
    ap.add_argument("--meta", default=None, help="Pfad zur *.parquet (Default: data/pointturn_data.parquet)")
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--min-train", type=int, default=10, help="Min. Umläufe je Gruppe für eine Baseline")
    ap.add_argument("--k", type=float, default=3.0, help="Warngrenze = mean + k*std (kleiner = früher warnen)")
    args = ap.parse_args()

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)

    # 1. Laden + Vorverarbeitung
    meta, currents = load_dataset() if args.meta is None else load_dataset(args.meta)
    meta, currents = pp.filter_maintenance(meta, currents)
    feats = features_dataframe(meta, currents)
    print(f"Umläufe (ohne Wartung): {len(feats)}  |  Fehlerquote: {feats['has_error'].mean():.2f}")

    # 2. Zufälliger Train/Test-Split
    train, test = random_split(feats, test_frac=args.test_frac, seed=args.seed)
    print(f"Split: train={len(train)}  test={len(test)}  (seed={args.seed})")

    # 3. Baseline lernen (unüberwacht, nur auf Train)
    model = PerSwitchBaseline(min_train=args.min_train).fit(train)
    print(f"Gelernte Gruppen (Weiche×Richtung): {len(model.groups_)}")

    # 4. Scoren
    train = train.assign(score=model.score(train))
    test = test.assign(score=model.score(test))

    # 5. Evaluation auf dem Test-Subset
    report = evaluate_scores(test, score_col="score", label_col="has_error")
    print("\n=== AUC / PR auf Test-Subset (Score vs. schwache Labels) ===")
    print(report.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    # 6. Score-Verteilung normal vs. Fehler (Test)
    valid = test.dropna(subset=["score"])
    print("\n=== Score-Verteilung Test (RMS-z zur Eigenhistorie) ===")
    print(valid.groupby("has_error")["score"].describe()[["count", "mean", "50%", "max"]]
          .round(2).to_string())

    # 7. Adaptive Warngrenze demonstrieren
    thr = model.thresholds(train, score_col="score", k=args.k)
    valid = valid.copy()
    valid["thr"] = [thr.get((o, p), np.nan) for o, p in zip(valid["object_id"], valid["position"])]
    flagged = valid["score"] > valid["thr"]
    tp = int((flagged & valid["has_error"]).sum())
    fp = int((flagged & ~valid["has_error"]).sum())
    fn = int((~flagged & valid["has_error"]).sum())
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    print(f"\n=== Warngrenze mean+{args.k}*std (früh-warn) ===")
    print(f"  geflaggt: {int(flagged.sum())}/{len(valid)}  |  Precision={prec:.2f}  Recall={rec:.2f}")


if __name__ == "__main__":
    main()
