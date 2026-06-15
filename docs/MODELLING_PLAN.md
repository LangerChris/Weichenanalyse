# Modelling-Plan — Weichenanalyse

Stand: 2026-06-15. Lebendes Dokument; wird mit dem Projekt fortgeschrieben.

## Ziele

**Primärziel (Start):** ein **generelles Fehlschlagen des Umlaufs** pro Weiche aus deren eigener
Historie vorhersagen/erkennen — ein Score "weicht dieser Umlauf von der Normalhistorie dieser Weiche ab?".
Später: feinere schwache Labels (DIANA-Diagnosen oder manuell gemeldete Störungsgründe) als zusätzliche
Validierung/Verfeinerung.

Dahinter weiterhin:
1. **Unüberwachte Anomalieerkennung** auf Motorstrom-Umläufen (pro Umlauf ein Anomalie-Score).
2. **Predictive Maintenance / Trend** pro Weiche über die Zeit (Degradations-Indikator).

Methodischer Anspruch: **breiter, systematischer Vergleich** klassischer und Deep-Learning-Verfahren
auf identischer Datenbasis und Evaluation. Alles **konfigurierbar** halten (Fenster, Schwellen, Modelle),
damit Varianten ausprobiert werden können.

## Unsicherheit & adaptive Warngrenze

Politik: **lieber zu früh warnen als zu spät** (asymmetrisch). Das Modell schätzt zu jedem Score eine
**Unsicherheit** (z. B. Residuenstreuung der Eigenhistorie) und leitet daraus eine **selbst adaptierende
Warngrenze** ab (Baseline ± k·σ, k über die Zeit/Streuung angepasst). So passt sich die Schwelle je Weiche
eigenständig an deren Rauschniveau an, statt einer festen globalen Grenze.

## Leitprinzip: pro Weiche, nicht zwischen Weichen

**Absolute Kennwerte (Peak-Strom, Umlaufzeit) dürfen NIE zwischen Weichen verglichen werden.** Jede Weiche
hat ihr eigenes legitimes Niveau. Anomalie = Abweichung einer Weiche von ihrer **eigenen Historie/Baseline**.
Konsequenzen:
- Baseline pro Weiche **und** Richtung (L/R) aus deren eigener Historie lernen; Scores auf weichen-relativen Residuen.
- Deskriptive „Peak je Weiche"-Tabellen sind kein Anomalie-Kriterium.
- Alles muss **vollautomatisch pro Weiche** laufen (Skalierung bis **2260 Weichen** über die DIANA-API; kein manuelles Tuning je Weiche).
- Leave-one-switch-out ist nur für die Generalisierbarkeit der *Methode* relevant, nicht das eigentliche Ziel.

## Datenbasis (siehe CLAUDE.md für Details)

3200 Umläufe, 4 Weichen, ~18 Monate. Pro Umlauf: 1 Motorstromkurve (116–1262 Samples, 50 Hz),
`turn_time`, `position` (L/R), `temperature_air`, `isMaintenance`, schwache Labels via `error_ids`.
Quelle: `data/pointturn_data.parquet` (Meta) + `data/pointturn_data_currents.json` (Rohströme).

## Pipeline-Architektur (Paket `weichenanalyse/`)

```
weichenanalyse/
├── data.py         # Laden + Join Meta/Rohströme → einheitliches Dataset
├── preprocess.py   # Offset-Korrektur, Maintenance-Filter, L/R-Split, Resampling, Referenzbezug
├── features.py     # phasenbasierte Feature-Extraktion pro Kurve
├── temperature.py  # Temperatur-Korrektur des Health-Indikators
├── models.py       # einheitliches Detector-Interface (fit/score) für klassisch + DL
├── evaluate.py     # AUC/PR, per-Weiche-Metriken, Plots
└── benchmark.py    # Harness: alle Modelle × Konfigurationen → Ergebnistabelle
```

Reproduzierbar als Skripte/`python -m` ausführbar; Notebooks importieren dieselben Module
(keine Logik-Duplikation im Notebook).

## Vorverarbeitungs-Entscheidungen

- **L/R strikt trennen** (eigene Referenzkurven, andere Form).
- **Offset-Korrektur:** Stromkurven beginnen mit negativem Sensor-Offset → Baseline subtrahieren.
- **Variable Länge:** zwei Repräsentationen parallel
  - Feature-Vektor pro Umlauf (für klassische Detektoren),
  - auf festes Raster resampelt, z. B. 200 Punkte (für PCA/Autoencoder).
- **Temperatur** (−8…+38 °C) herausrechnen, damit Trend ≠ Saisonalität.
- **`isMaintenance`-Umläufe** aus dem „Normal"-Pool ausschließen.
- **Normalisierung pro Weiche/Richtung**, dann globales Modell auf Residuen (generalisiert auf neue Weichen).

## Track 1 — Anomalieerkennung (Benchmark-Kandidaten)

| Klasse | Verfahren |
|---|---|
| Baseline | Abweichung von Referenzkurve (aligned L2 / DTW, Fläche, `turn_time`-Δ) |
| Klassisch (Feature) | Isolation Forest, LOF, One-Class SVM, Mahalanobis/RobustCov |
| Kurvenbasiert linear | (Functional) PCA → Rekonstruktionsfehler / Hotelling T² |
| Deep | 1D-Conv-Autoencoder, LSTM/Transformer-Autoencoder (Rekonstruktionsfehler) |

## Track 2 — Trend / Predictive Maintenance

1. Health-Indikator (HI) je Umlauf = Anomalie-Score oder gezielte Features (Laufphasen-Strom).
2. Temperaturkorrektur des HI.
3. Change-Point/Trend-Erkennung (rolling Mean, CUSUM, `ruptures`).
4. Schwellen-Forecast (exp. Glättung) zur Vorwarnung.

> Nur 4 Weichen → **kein** klassisches RUL-Regressionsmodell, sondern Degradations-Trend-Demonstration.

## Evaluation

- **Automatisiert, nicht manuell:** Test-/Bewertungs-Set wird aus den schwachen Labels (DIANAs eigene
  `error_ids` / Diagnosen) automatisch gebildet — das skaliert auf 2260 Weichen und ist reproduzierbar.
  Kein handverlesenes Test-Set für die allgemeine Evaluation.
- Metriken pro Weiche und Richtung: ROC-AUC, PR-AUC; Score = Abweichung von der eigenen Baseline.
- **Gold-Labels (manuell, partiell):** Störungen werden via Excel-Vorlage
  (`data/labels/stoerungen_template.xlsx`, erzeugt von `scripts/make_label_template.py`) geliefert.
  → **Partielle Positive (PU-Setting):** gemeldete Störungen sind sichere Treffer; ein fehlender Eintrag
  bedeutet NICHT "gesund" (es gibt unbekannte Störungen). Daher: gemeldete Labels nur als Positive werten,
  nicht-gemeldete Umläufe als "unlabeled", nicht als Negative. Optional bestätigte Gesund-Zeiträume als echte Negative.

## Daten- & Label-Logistik

- **Datenquelle:** manueller HAR-Export aus DIANA (kein API-Zugriff). HAR-Dateien nach `data/Umlaeufe/<Name>.har`.
- **Labels:** ausgefüllte `data/labels/stoerungen.xlsx` (Tab `Stoerungen` = Störungen, `Gesund_bestaetigt` = optionale echte Negative).
- `HAR_Datei`-Spalte verknüpft Labels mit HAR; die kryptische `objectId` wird automatisch aus der HAR zugeordnet.

## Fehlerarten in den Daten (DIANAs Diagnosen, = unsere schwachen Labels)

Quelle: `*_diagnoses.csv` (switch-level) + `errorConditionMetaIds` (pro Umlauf). Kategorien:
- Erhöhter / stark erhöhter **Strom/Leistung** — beim Umlauf, bei Ver-/Entriegelung (häufigste Klasse)
- **Störung Endlage** L/R
- **Stark verlängerte Umlaufzeit**
- **Abweichende Referenz** (L/R, Umlaufzeit)

Ziel: diese Abweichungen unüberwacht und *früher* als DIANAs Schwellwert-Diagnose erkennen.

## Roadmap / Status

- [x] HAR-Extraktion über alle 4 Weichen (`extract_har.py`, Windows-Bugs gefixt)
- [x] **Daten-Pipeline-Module** (data → preprocess → features) — lauffähig, Features diskriminativ
- [x] **Evaluation-Harness** (`evaluate.py`, random split, AUC/PR je Weiche)
- [x] **Baseline-Detektor** (`baseline.py`, Per-Weiche-Schwerpunkt) + Testdurchlauf (`scripts/run_baseline.py`)
      → erster Befund: Gesamt-AUC ~0.58 (schwach, erwartbar). Ursache: hohe Kontamination (56 % Fehler)
      verzerrt den Schwerpunkt; durchgehend defekte Weichen (WE153) haben keine saubere Eigen-Referenz.
- [ ] **Robustere Baseline** (Median/MAD statt Mittel; nur "frühe gesunde" Historie als Referenz) ← nächster Schritt
- [ ] Klassische Detektoren (Isolation Forest, PCA/T²)
- [ ] PCA/Autoencoder
- [ ] Benchmark-Vergleich
- [ ] Track 2: Trend/Predictive Maintenance
