"""Laden und Zusammenführen der extrahierten Umlauf-Daten.

Quellen (erzeugt von scripts/extract_har.py):
  - <prefix>.parquet            Metadaten-Tabelle (eine Zeile je Umlauf)
  - <prefix>_currents.json      Rohe Stromkurven, gejoint über object_id+time+position

`load_dataset` liefert die Metadaten als DataFrame plus die ausgerichteten Stromkurven
als Liste von float-Arrays (gleiche Reihenfolge wie die DataFrame-Zeilen).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Repo-Wurzel relativ zu dieser Datei: weichenanalyse/ -> ..
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_META = REPO_ROOT / "data" / "pointturn_data.parquet"


@dataclass
class Turn:
    """Ein einzelner Umlauf: Metadaten + rohe Stromkurve."""

    object_id: str
    time: int
    position: str  # "L" oder "R"
    current: np.ndarray  # roher Motorstrom (A), 50 Hz
    sampling_interval: float
    turn_time: float | None
    temperature_air: float | None  # Kelvin
    is_maintenance: bool
    error_ids: list[int]

    @property
    def has_error(self) -> bool:
        return len(self.error_ids) > 0

    @property
    def temperature_c(self) -> float | None:
        return None if self.temperature_air is None else self.temperature_air - 273.15


def _currents_path(meta_path: Path) -> Path:
    """data/foo.parquet -> data/foo_currents.json"""
    return meta_path.with_name(meta_path.stem + "_currents.json")


def load_currents(meta_path: Path = DEFAULT_META, motor: int = 0) -> dict[tuple, np.ndarray]:
    """Rohströme als Mapping (object_id, time, position) -> current-Array."""
    path = _currents_path(meta_path)
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    key_col = f"motor_{motor}_current_raw"
    out: dict[tuple, np.ndarray] = {}
    for r in records:
        key = (r["object_id"], r["time"], r["position"])
        out[key] = np.asarray(r.get(key_col) or [], dtype=float)
    return out


def load_signals(meta_path: Path = DEFAULT_META, motor: int = 0) -> dict[tuple, tuple]:
    """Vereinheitlichte Wellenform je Umlauf: Strom (A) wo vorhanden, sonst Leistung (W).

    Returns Mapping (object_id, time, position) -> (array, unit), unit in {"A","W",""}.
    """
    path = _currents_path(Path(meta_path))
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    cur_col, pw_col = f"motor_{motor}_current_raw", f"motor_{motor}_power_raw"
    out: dict[tuple, tuple] = {}
    for r in records:
        key = (r["object_id"], r["time"], r["position"])
        c = r.get(cur_col) or []
        p = r.get(pw_col) or []
        if c:
            out[key] = (np.asarray(c, dtype=float), "A")
        elif p:
            out[key] = (np.asarray(p, dtype=float), "W")
        else:
            out[key] = (np.array([], dtype=float), "")
    return out


def load_meta(meta_path: Path = DEFAULT_META) -> pd.DataFrame:
    """Metadaten-Tabelle laden und error_ids zurück in Listen wandeln."""
    df = pd.read_parquet(meta_path)

    def parse_ids(v) -> list[int]:
        if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
            return []
        return [int(x) for x in str(v).split(",") if x != ""]

    df["error_ids"] = df["error_ids"].apply(parse_ids)
    return df


def load_dataset(
    meta_path: Path | str = DEFAULT_META, motor: int = 0
) -> tuple[pd.DataFrame, list[np.ndarray]]:
    """Metadaten + ausgerichtete Stromkurven laden.

    Returns:
        (meta_df, currents) — currents[i] gehört zu meta_df.iloc[i].
        meta_df bekommt eine Spalte ``n_samples`` mit der Kurvenlänge.
    """
    meta_path = Path(meta_path)
    meta = load_meta(meta_path)
    currents_map = load_currents(meta_path, motor=motor)

    currents: list[np.ndarray] = []
    missing = 0
    for row in meta.itertuples(index=False):
        key = (row.object_id, row.time, row.position)
        curve = currents_map.get(key)
        if curve is None:
            curve = np.array([], dtype=float)
            missing += 1
        currents.append(curve)

    meta = meta.copy()
    meta["n_samples"] = [len(c) for c in currents]
    if missing:
        print(f"Warnung: {missing} Umläufe ohne passende Stromkurve.")
    return meta, currents


def iter_turns(
    meta_path: Path | str = DEFAULT_META, motor: int = 0
) -> list[Turn]:
    """Bequeme Objekt-Sicht: Liste von Turn-Instanzen."""
    meta, currents = load_dataset(meta_path, motor=motor)
    turns: list[Turn] = []
    for row, curve in zip(meta.itertuples(index=False), currents):
        turns.append(
            Turn(
                object_id=row.object_id,
                time=row.time,
                position=row.position,
                current=curve,
                sampling_interval=row.sampling_interval,
                turn_time=row.turn_time,
                temperature_air=row.temperature_air,
                is_maintenance=bool(row.is_maintenance),
                error_ids=list(row.error_ids),
            )
        )
    return turns
