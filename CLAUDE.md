# CLAUDE.md — Weichenanalyse

Kontext für Claude Code zu diesem Projekt. (Diese Datei ist über `.gitignore` ausgeschlossen — sie bleibt lokal.)

## Worum geht es?

Masterarbeit zur **Zustandsüberwachung von Eisenbahn-Weichen** anhand des Motorstroms beim Stellvorgang.
Datenquelle ist **DIANA**, die Monitoring-Plattform der DB InfraGO AG. Jeder Stellvorgang einer Weiche
(„Umlauf" / Point Turn Event, PTE) wird als Stromkurve aufgezeichnet (50 Hz, ~4 s).

**Vorhersageziel (festgelegt):** die **Endlage-Störung** vorhersagen — DIANA-Codes **2724 (Endlage Links)**
und **2723 (Endlage Rechts)** — als **Frühwarnung mit Horizont** ("Endlage-Störung in den nächsten X Umläufen?").
Die übrigen Fehlercodes, Kurvenmerkmale und Weichen-Metadaten sind **Prädiktoren**, nicht das Ziel.
**Transfer** über Weichen hinweg ist erwünscht (gepoolt trainieren, Leave-one-switch-out evaluieren);
dynamische Merkmale dafür per-Weiche normieren, statische Metadaten als Transfer-Kontext.
Details/Begründung: [docs/MODELLING_PLAN.md](docs/MODELLING_PLAN.md).

Beispiel-Weiche: **WE265** am Bf Frankfurt(Main) Höchst, objectId `FHOE---WK----265~~~~~`.

Ausführliche Domänen-Erklärung (Datenherkunft, API-Zugriff, JSON-Struktur, Glossar): siehe
[data/DATEN_ERKLAERUNG.md](data/DATEN_ERKLAERUNG.md).

## Aktueller Stand (Stand 2026-06-15)

- **Extraktion über alle 24 HARs gelaufen** → `data/pointturn_data.parquet` (+ `_currents.json`, `_diagnoses.csv`, `_switches.csv`).
  `extract_har.py` zieht Umläufe, Motorströme, Diagnosen und statische `masterdata`-Features; Windows-Encoding-Bugs gefixt.
- **Pipeline-Paket `weichenanalyse/`**: `data.py` (Laden+Join), `preprocess.py` (Offset/Filter/L-R-Split/Resampling),
  `features.py` (phasenbasierte Features), `baseline.py` (Per-Weiche-Schwerpunkt), `evaluate.py` (Split+AUC),
  `labels.py` (Zielcodes 2723/2724, Frühwarn-Label mit Horizont, Switch-Metadaten, bestätigte Störungen).
- **Gold-Labels:** 12 bestätigte Störungen (`data/labels/stoerungen.xlsx`) + Fehlercode-Beschreibungen
  (`data/reference/error_codes.csv`) eingepflegt. Validierung: Endlage-nahe Störungen richten sich eng an 2723/2724 aus.
- Modelling-Plan & Roadmap: [docs/MODELLING_PLAN.md](docs/MODELLING_PLAN.md).
- **Nächster Schritt:** Feature-Engineering (dynamisch normiert + statisch) → Transfer-Modell mit Leave-one-switch-out.

## Datensatz-Fakten (Extraktion 2026-06-15, alle 24 HARs)

**12.500 Umläufe, 24 Weichen.** Output in `data/pointturn_data*` (alle gitignored, aus HAR regenerierbar).

- **Zielcode 2723/2724:** 86 Ziel-Umläufe auf **20 von 24 Weichen** (vorher mit 4 HARs nur 5 auf 1 Weiche).
  Frühwarn-Positive je Horizont: h=0 → 86 (0.7 %), h=10 → 625 (5.0 %), h=50 → 1961 (15.7 %).
- **Störfall-HARs sind kurze Fenster** um den Vorfall (100–500 Umläufe), Referenz-Weichen (WE438/WE521/WE153/WE25) lange Zeiträume.
- **Kurvenlänge variabel** (Median ~200 Samples, `turn_time` ~4 s); **Temperatur** −8…+38 °C (Kovariate).
- **L/R im Code kodiert:** Fehlercodes treten als L/R-Paare auf (z. B. 2724 Endlage L / 2723 Endlage R).
- Skript erfasst nur **motor_0** in der Metadaten-Tabelle (Rohströme im `*_currents.json`).
- Alle 24 Weichen sind **Einzelantrieb** (SAT01, `n_drives`=1); Mehrantrieb (SATCD) kommt im Fleet vor, hier nicht.

## Daten

- `data/Umlaeufe/*.har` — Browser-Export (HAR) der DIANA-Netzwerkanfragen. **Gitignored** (`*.har`).
  24 Dateien (Stand 2026-06-15); manche Dateinamen enthalten Leerzeichen + Fehlerhinweise (z. B. `WE28 Kupplung.har`).
  Manuell gelabelte Störfälle in `data/labels/stoerungen.xlsx`; weitere Weichen sind ungelabelt (es können unbekannte Störungen enthalten sein).
- In einer HAR-Datei sind nur 1–2 von ~159 Einträgen relevant:
  - `GET /im/api/v1/wk/pointturnlist/` → 50 Umläufe mit vollständigen `motorTurnData` + Referenzkurven (`configs`). **Der wichtige Endpunkt.**
  - `GET /im/api/v1/events/pointturn/` → einzelner Umlauf (nur current/power).
  - `diagnosesfeedback/view/stack` → Diagnose-/Fehler-Feedback (vom Skript ausgewertet).

### Wichtige Felder pro Umlauf (PTE)
`position` (L/R), `turnTime` (Dauer s), `samplingInterval` (0.02 = 50 Hz), `time` (Unix-ms),
`temperatureAir` (**Kelvin** — Celsius = Wert − 273.15), `isMaintenance`, `errorConditionMetaIds`,
`motorTurnData[].current` (Stromverlauf in A, die eigentliche Zeitreihe).

## Setup & Befehle

- Python **≥3.13**, Paketmanager **uv** (`pyproject.toml` + `uv.lock`). Virtualenv liegt in `.venv/`.
- Abhängigkeiten: `ipykernel`, `matplotlib`, `nbconvert`, `pandas`, `pyarrow`.
- **Firmen-Proxy / TLS:** `uv` schlägt im DB-Netz mit „invalid peer certificate: UnknownIssuer" fehl.
  Lösung: `uv`-Befehle mit `--native-tls` ausführen (z. B. `uv add --native-tls <pkg>`).
- Skript ausführen: `uv run python scripts/extract_har.py data/Umlaeufe/ -o pointturn_data.parquet`

## Umgebungs-Hinweise (Windows)

- Shell ist **PowerShell**. System-`python` ist nicht installiert (öffnet Microsoft-Store-Stub) — immer
  `.venv\Scripts\python.exe` bzw. `uv run` verwenden.
- HAR-Dateien als **UTF-8** öffnen (`encoding='utf-8'`), nicht den cp1252-Default. Beim Drucken von Notebook-Inhalten
  mit Sonderzeichen `PYTHONIOENCODING=utf-8` setzen.

## Git

- Remote: `https://github.com/LangerChris/Weichenanalyse.git`, Branch `main`.
- `.gitignore` schließt aus: `*.har`, `.DS_store`.
