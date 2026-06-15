# CLAUDE.md — Weichenanalyse

Kontext für Claude Code zu diesem Projekt. (Diese Datei ist über `.gitignore` ausgeschlossen — sie bleibt lokal.)

## Worum geht es?

Masterarbeit zur **Zustandsüberwachung von Eisenbahn-Weichen** anhand des Motorstroms beim Stellvorgang.
Datenquelle ist **DIANA**, die Monitoring-Plattform der DB InfraGO AG. Jeder Stellvorgang einer Weiche
(„Umlauf" / Point Turn Event, PTE) wird als Stromkurve aufgezeichnet (50 Hz, ~4 s).

**Analyseziel (vom Betreuer/Autor bestätigt):**
1. **Unüberwachte Anomalieerkennung** — Abweichungen vom Normalverhalten in den Stromkurven finden, ohne
   vorab gelabelte Fehler.
2. **Predictive Maintenance / Trendanalyse** — Verschleiß über die Zeit modellieren und Auffälligkeiten
   erkennen, bevor sie zum Ausfall führen.

→ Der Ansatz ist also primär **unsupervised / semi-supervised**, nicht reine Fehlerklassifikation. Die
`errorConditionMetaIds` und Diagnose-Feedbacks sind nützliche (aber wahrscheinlich spärliche/unvollständige)
schwache Labels zur Validierung, nicht die primäre Trainingsgrundlage.

Beispiel-Weiche: **WE265** am Bf Frankfurt(Main) Höchst, objectId `FHOE---WK----265~~~~~`.

Ausführliche Domänen-Erklärung (Datenherkunft, API-Zugriff, JSON-Struktur, Glossar): siehe
[data/DATEN_ERKLAERUNG.md](data/DATEN_ERKLAERUNG.md).

## Aktueller Stand (Stand 2026-06-15)

- **Datenexploration läuft.** Hauptarbeit aktuell im Notebook [notebooks/explore_data.ipynb](notebooks/explore_data.ipynb):
  HAR-Struktur verstehen, `pointturnlist` extrahieren, Stromverläufe je Richtung (L/R) gegen die Referenzkurve plotten,
  einzelne Umläufe inspizieren.
- **Extraktionsskript** [scripts/extract_har.py](scripts/extract_har.py): liest eine oder mehrere HAR-Dateien,
  zieht Umlauf-Metadaten + Motorströme + Diagnose-Feedback heraus und schreibt
  Metadaten als Parquet/CSV, Rohströme als JSON, Diagnosen als CSV. (Neu via GitHub gepullt.)
- **Extraktion über alle 4 HARs gelaufen** (2026-06-15) → `data/pointturn_data.parquet` (+ `_currents.json`, `_diagnoses.csv`).
  Dabei zwei Windows-Encoding-Bugs in `extract_har.py` gefixt (HAR-Lesen + stdout auf UTF-8).
- **Pipeline-Paket `weichenanalyse/`** angelegt: `data.py` (Laden+Join), `preprocess.py` (Offset/Filter/L-R-Split/Resampling),
  `features.py` (phasenbasierte Features). Smoke-getestet, Features trennen Fehler/Normal klar.
- Modelling-Plan & Roadmap: [docs/MODELLING_PLAN.md](docs/MODELLING_PLAN.md). Ziel: breiter Vergleich klassisch vs. Deep Learning.
- **Noch kein Detektor/Modell** trainiert — nächster Schritt: Evaluation-Harness + Baseline.

## Datensatz-Fakten (Extraktion 2026-06-15, alle 4 HARs)

3200 Umläufe, 4 Weichen, Zeitraum **Nov 2024 – Mai 2026** (~18 Monate). Output in `data/pointturn_data*`.

| Weiche (objectId) | HAR | Umläufe | Fehlerquote | Wartung |
|---|---|---|---|---|
| FH-----WK----153 | WE153 | 1050 | **1.00** (quasi durchgehend defekt) | 4 |
| FSTK---WK-----25 | WE25 | 1050 | 0.44 | 11 |
| FFA----WK----438 | WE438 | 1050 | 0.23 | 24 |
| FHOE---WK----265 | WE265 (test_data) | 50 | 0.52 | 1 |

- **Kurvenlänge variabel:** 116–1262 Samples (Median 204), `turn_time` 2.3–25 s (Median 4.1). → Alignment/Resampling oder phasenbasierte Features nötig.
- **Peak-Strom** stark gespreizt (Median 3.2 A, 75 %-Quantil 10.1 A) — L/R unterscheiden sich deutlich.
- **Temperatur** −8 bis +38 °C → relevante Kovariate (Strom ist temperaturabhängig).
- Schwache Labels: `errorConditionMetaIds` pro Umlauf (häufigste IDs 2640/2647/2646/2639); 31 Diagnosen (switch-level) im `*_diagnoses.csv`.
- Skript erfasst nur **motor_0** in der Metadaten-Tabelle (Rohströme aller Motoren liegen im `*_currents.json`).

## Daten

- `data/Umlaeufe/*.har` — Browser-Export (HAR) der DIANA-Netzwerkanfragen. **Gitignored** (`*.har`), groß (~22–27 MB je Datei).
  Vorhanden: `WE153.har`, `WE25.har`, `WE438.har`, `test_data.har` (WE265).
  **Noch ungelabelt:** Es ist (Stand jetzt) nicht bekannt, welche dieser Weichen auffällig/defekt sind —
  das herauszufinden ist Teil der Analyse.
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
