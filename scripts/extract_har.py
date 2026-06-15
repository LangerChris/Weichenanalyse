"""
Extract point turn list data and error/diagnosis info from DIANA HAR files.

Usage:
    python extract_har.py data/Umlaeufe/test_data.har
    python extract_har.py data/Umlaeufe/*.har              # multiple files
    python extract_har.py data/Umlaeufe/ --output out.parquet  # custom output
"""

import json
import argparse
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone


def build_switches(records: list, har_file: str) -> list:
    """Aus den masterdata-Komponenten je Weiche eine statische Feature-Zeile bauen.

    Liefert Standort/Hierarchie, Weichentyp (aus Beschreibung), Antriebs-Konfiguration
    (SAT01/SATCD ...) und Heizung (EEH) — Transfer-Features für die Vorhersage.
    """
    by_oid = defaultdict(list)
    for r in records:
        if r.get("objectId"):
            by_oid[r["objectId"]].append(r)

    out = []
    for oid, recs in by_oid.items():
        comp2000 = next((r for r in recs if r.get("componentId") == 2000), {})
        org = next((r["indices"]["org"] for r in recs
                    if (r.get("indices") or {}).get("org")), {})
        discs = sorted({r.get("componentDiscriminator") for r in recs
                        if r.get("componentDiscriminator")})
        drives = [d for d in discs if d.startswith("SAT")]
        tracks = sorted({t for r in recs for t in (r.get("tracks") or [])})
        out.append({
            "object_id": oid,
            "har_file": har_file,
            "label": comp2000.get("label") or (recs[0].get("label", "")),
            "description": comp2000.get("description", ""),
            "district": next((r.get("district") for r in recs if r.get("district")), ""),
            "region": org.get("h1", {}).get("name", ""),
            "area": org.get("h2", {}).get("name", ""),
            "subarea": org.get("h3", {}).get("name", ""),
            "station": org.get("h4", {}).get("name", ""),
            "tracks": ",".join(map(str, tracks)),
            "drives": ",".join(drives),
            "n_drives": len(drives),
            "has_heater": any(d.startswith("EEH") for d in discs),
        })
    return out


def parse_har(har_path: Path) -> dict:
    """Parse a single HAR file and return pointturn + diagnosis data."""
    # HAR exports are UTF-8; Windows would otherwise default to cp1252 and crash.
    try:
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)
    except UnicodeDecodeError:
        with open(har_path, encoding="utf-8-sig") as f:
            har = json.load(f)

    turns = []
    diagnoses = []
    masterdata_records = []

    for entry in har["log"]["entries"]:
        url = entry["request"]["url"]
        resp_text = entry["response"]["content"].get("text", "")
        if not resp_text:
            continue

        # --- Point turn list data ---
        if "pointturnlist" in url:
            try:
                data = json.loads(resp_text)
            except json.JSONDecodeError:
                continue

            configs = {
                c["position"]: c for c in (data.get("configs") or [])
            }

            for p in data.get("ptes", []):
                # Extract motor current stats (summary, not raw array)
                motor_data = p.get("motorTurnData") or []
                motor_summary = {}
                for i, m in enumerate(motor_data):
                    curr = m.get("current", [])
                    if curr:
                        motor_summary[f"motor_{i}_id"] = m.get("idSub1", "")
                        motor_summary[f"motor_{i}_peak_current"] = max(curr)
                        motor_summary[f"motor_{i}_mean_current"] = sum(curr) / len(curr)
                        motor_summary[f"motor_{i}_samples"] = len(curr)
                        motor_summary[f"motor_{i}_delay_start"] = m.get("delayStartTime")
                    # Store raw current for model training
                    motor_summary[f"motor_{i}_current_raw"] = curr
                    motor_summary[f"motor_{i}_power_raw"] = m.get("power", [])

                # Error codes from this turn event
                error_meta = p.get("errorConditionMetaIds") or {}
                error_ids = sorted(set(
                    val for vals in error_meta.values() for val in vals
                ))

                # Reference turn time for comparison
                pos = p.get("position", "")
                ref_config = configs.get(pos, {})
                ref = ref_config.get("reference", {})

                row = {
                    "har_file": har_path.name,
                    "object_id": p.get("objectId", data.get("objectId", "")),
                    "time": p.get("time"),
                    "timestamp": datetime.fromtimestamp(
                        p["time"] / 1000, tz=timezone.utc
                    ).isoformat() if p.get("time") else None,
                    "position": pos,
                    "turn_time": p.get("turnTime"),
                    "ref_turn_time": ref.get("turnTime"),
                    "reference_time": ref.get("time"),       # wann Referenz gesetzt wurde
                    "config_time": ref_config.get("configTime"),  # wann Config zuletzt geändert
                    "sampling_interval": p.get("samplingInterval"),
                    "is_maintenance": p.get("isMaintenance", False),
                    "temperature_air": p.get("temperatureAir"),
                    "error_ids": error_ids,
                    "error_components": list(error_meta.keys()),
                    "has_error": len(error_ids) > 0,
                    **motor_summary,
                }
                turns.append(row)

        # --- Diagnosis feedback ---
        elif "diagnosesfeedback/view/stack" in url:
            try:
                data = json.loads(resp_text)
            except json.JSONDecodeError:
                continue
            for d in data:
                diagnoses.append({
                    "object_id": d.get("objectId", ""),
                    "diagnosis_id": d.get("diagnosisId"),
                    "diagnosis_text": d.get("diagnosisTranslation", ""),
                    "component": d.get("component", ""),
                    "component_text": d.get("componentTranslation", ""),
                    "status": d.get("diagnosisStatus", ""),
                    "time": d.get("time"),
                })

        # --- Master data (static switch metadata) ---
        elif "/masterdata/" in url:
            try:
                data = json.loads(resp_text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                masterdata_records.extend(data)

    switches = build_switches(masterdata_records, har_path.name)
    return {"turns": turns, "diagnoses": diagnoses, "switches": switches}


def print_summary(all_turns: list, all_diagnoses: list, har_files: list):
    """Print a concise overview."""
    print(f"\n{'='*60}")
    print(f"  HAR Extraction Summary")
    print(f"{'='*60}")
    print(f"  Files processed:  {len(har_files)}")
    print(f"  Turn events:      {len(all_turns)}")
    print(f"  Diagnoses:        {len(all_diagnoses)}")

    if all_turns:
        # Per-switch summary
        switches = {}
        for t in all_turns:
            oid = t["object_id"]
            if oid not in switches:
                switches[oid] = {"count": 0, "errors": 0, "positions": set()}
            switches[oid]["count"] += 1
            switches[oid]["positions"].add(t["position"])
            if t["has_error"]:
                switches[oid]["errors"] += 1

        print(f"\n  {'Weiche':<30} {'Turns':>6} {'Errors':>7} {'Pos':>5}")
        print(f"  {'-'*30} {'-'*6} {'-'*7} {'-'*5}")
        for oid, info in sorted(switches.items()):
            pos = ",".join(sorted(info["positions"]))
            print(f"  {oid:<30} {info['count']:>6} {info['errors']:>7} {pos:>5}")

    if all_diagnoses:
        print(f"\n  Active diagnoses:")
        seen = set()
        for d in all_diagnoses:
            key = (d["object_id"], d["diagnosis_id"])
            if key not in seen:
                seen.add(key)
                print(f"    [{d['diagnosis_id']}] {d['diagnosis_text']}")
                print(f"         → {d['object_id']} ({d['status']})")

    print(f"{'='*60}\n")


def main():
    # Windows consoles default to cp1252 and choke on non-latin1 output (e.g. "→").
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Extract DIANA point turn data from HAR files")
    parser.add_argument("paths", nargs="+", help="HAR file(s) or directory containing them")
    parser.add_argument("--output", "-o", default="pointturn_data.parquet",
                        help="Output file (.parquet or .csv)")
    parser.add_argument("--csv", action="store_true", help="Force CSV output")
    args = parser.parse_args()

    # Collect HAR files
    har_files = []
    for p in args.paths:
        path = Path(p)
        if path.is_dir():
            har_files.extend(sorted(path.glob("*.har")))
        elif path.suffix == ".har":
            har_files.append(path)

    if not har_files:
        print("No HAR files found.", file=sys.stderr)
        sys.exit(1)

    # Extract
    all_turns = []
    all_diagnoses = []
    all_switches = []
    for hf in har_files:
        result = parse_har(hf)
        all_turns.extend(result["turns"])
        all_diagnoses.extend(result["diagnoses"])
        all_switches.extend(result["switches"])

    # Summary
    print_summary(all_turns, all_diagnoses, har_files)

    if not all_turns:
        print("No point turn data found.", file=sys.stderr)
        sys.exit(1)

    # Save — try parquet first, fall back to CSV
    output_path = Path(args.output)
    use_csv = args.csv or output_path.suffix == ".csv"

    try:
        import pandas as pd
    except ImportError:
        print("pandas not installed. Run: uv add pandas", file=sys.stderr)
        sys.exit(1)

    # Separate raw current arrays from the tabular metadata
    meta_cols = [c for c in all_turns[0] if not c.endswith("_raw")]
    raw_cols = [c for c in all_turns[0] if c.endswith("_raw")]

    df_meta = pd.DataFrame([{k: v for k, v in t.items() if k in meta_cols} for t in all_turns])
    # Convert list columns to strings for tabular formats
    df_meta["error_ids"] = df_meta["error_ids"].apply(lambda x: ",".join(map(str, x)) if x else "")
    df_meta["error_components"] = df_meta["error_components"].apply(lambda x: ",".join(x) if x else "")

    # Save metadata table
    if use_csv or output_path.suffix == ".csv":
        output_path = output_path.with_suffix(".csv")
        df_meta.to_csv(output_path, index=False)
    else:
        try:
            df_meta.to_parquet(output_path, index=False)
        except Exception:
            output_path = output_path.with_suffix(".csv")
            df_meta.to_csv(output_path, index=False)
            print(f"  (parquet unavailable, saved as CSV)")

    print(f"  Metadata saved to: {output_path}")
    print(f"  Columns: {list(df_meta.columns)}")
    print(f"  Shape: {df_meta.shape}")

    # Save raw current arrays as separate JSON (for time-series model training)
    raw_path = output_path.with_name(output_path.stem + "_currents.json")
    raw_data = []
    for t in all_turns:
        raw_data.append({
            "object_id": t["object_id"],
            "time": t["time"],
            "position": t["position"],
            "error_ids": t["error_ids"],
            **{k: t[k] for k in raw_cols},
        })
    with open(raw_path, "w") as f:
        json.dump(raw_data, f)
    print(f"  Raw currents saved to: {raw_path}")

    # Diagnoses table
    if all_diagnoses:
        diag_path = output_path.with_name(output_path.stem + "_diagnoses.csv")
        pd.DataFrame(all_diagnoses).to_csv(diag_path, index=False)
        print(f"  Diagnoses saved to: {diag_path}")

    # Static switch metadata table (one row per switch)
    if all_switches:
        sw_path = output_path.with_name(output_path.stem + "_switches.csv")
        df_sw = pd.DataFrame(all_switches).drop_duplicates("object_id")
        df_sw.to_csv(sw_path, index=False)
        print(f"  Switch metadata saved to: {sw_path}")
        print(f"  Switches: {df_sw.shape[0]}  Columns: {list(df_sw.columns)}")


if __name__ == "__main__":
    main()
