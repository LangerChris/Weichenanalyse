# Modelling-Plan — Weichenanalyse

Stand: 2026-06-15. Lebendes Dokument; wird mit dem Projekt fortgeschrieben.

## Ziele

**Vorhersageziel (festgelegt):** das **Auftreten einer Endlage-Störung** vorhersagen —
DIANA-Codes **2724 (Störung Endlage Links)** und **2723 (Störung Endlage Rechts)**.
Framing als **Frühwarnung mit Horizont**: Ziel = „innerhalb der nächsten X Umläufe/Tage tritt
eine Endlage-Störung auf" (X konfigurierbar). Damit Vorwarnzeit für die Instandhaltung.

**Prädiktoren (Eingang), NICHT Ziel:** die übrigen DIANA-Fehlercodes (erhöhter Strom etc.),
die Motorstrom-Kurvenmerkmale und statische Weichen-Metadaten. Beobachtung in den Daten:
Endlage-Störungen werden von erhöhten-Strom-Codes (2266, 2626, 2647, 2640) zeitlich angekündigt.

Methodischer Anspruch: **breiter, systematischer Vergleich** klassischer und Deep-Learning-Verfahren
auf identischer Datenbasis und Evaluation. Alles **konfigurierbar** halten (Horizont, Fenster, Modelle).

### Realität der Datenlage (Stand 4 HARs)

2723/2724 kommen **nur 5×** vor, **alle auf WE438**, geclustert am Historienende; die anderen 3 Weichen: null.
→ Überwachtes Training/Eval ist auf den aktuellen Daten nicht belastbar. **Strategie:** Framework jetzt bauen
(Features, Transfer, Leave-one-switch-out-Eval), echtes Training/Eval sobald gezielt HARs von Weichen
**mit** Endlage-Störungen vorliegen.

## Unsicherheit & adaptive Warngrenze

Politik: **lieber zu früh warnen als zu spät** (asymmetrisch). Das Modell schätzt zu jedem Score eine
**Unsicherheit** (z. B. Residuenstreuung der Eigenhistorie) und leitet daraus eine **selbst adaptierende
Warngrenze** ab (Baseline ± k·σ, k über die Zeit/Streuung angepasst). So passt sich die Schwelle je Weiche
eigenständig an deren Rauschniveau an, statt einer festen globalen Grenze.

## Leitprinzip: per-Weiche normieren, über Weichen lernen

Zwei scheinbar gegensätzliche Anforderungen, die zusammen gehören:

1. **Absolute Kennwerte (Peak-Strom, Umlaufzeit) NIE roh zwischen Weichen vergleichen.** Jede Weiche hat ihr
   eigenes legitimes Niveau. Deshalb: **dynamische Merkmale per-Weiche/Richtung normieren** (Abweichung von der
   Eigenhistorie, z. B. z-Wert/Residuum). So wird „2 σ über der Eigenhistorie" bei jeder Weiche dasselbe.
2. **Transfer erwünscht:** Wissen von vielen Weichen soll auf neue Weichen übertragen werden. Das geht, WEIL
   die dynamischen Merkmale per-Weiche normiert (und damit vergleichbar) sind — **plus statische Weichen-Metadaten**
   (Standort, Typ, Antrieb …), auf die das Modell konditionieren kann.

Daraus: **Modell über alle Weichen gepoolt** (auf normierten dynamischen + statischen Features), Bewertung per
**Leave-one-switch-out** → misst echten Transfer auf ungesehene Weichen. Vollautomatisch je Weiche, kein Hand-Tuning.

## Feature-Quellen

**Dynamisch (pro Umlauf, per-Weiche normiert):**
- Kurvenmerkmale (Peak, Laufphasen-Strom, Energie, Steigung, Umlaufzeit …) → als Residuum zur Eigenhistorie.
- Aktivität anderer Fehlercodes zuletzt (Rate/Anzahl im jüngsten Fenster) als Vorboten.
- Zeitlich: kumulative Umlaufzahl (Verschleiß-Proxy), Drift/Trend der Merkmale, Zeit seit letzter Referenzänderung.

**Statisch (pro Weiche, aus `masterdata`/`config` — für Transfer):**
- **Standort/Hierarchie:** Bezirk, Bahnhof, Gleis.
- **Weichentyp/Nutzung:** aus `description` (z. B. „ICE-Reinigungsanlage", „ZBA", „Stw").
- **Antriebs-Konfiguration:** Anzahl/Typ Antriebe (SAT01/SATCD), Heizstäbe (EEH01).
- **Referenz/Config:** Referenz-Umlaufzeit, Config-Alter (Zeit seit Referenz gesetzt).

> **Leakage-Vorsicht:** DIANAs eigene Schwellwert-Parameter (`configParameter`: 2303/2310/2311) NICHT als
> Feature verwenden — sie erzeugen die Labels mit.

> **Extraktion nötig:** `extract_har.py` muss um `masterdata` (statische Features) und die ungenutzten
> pte-/config-Felder (`delayStartTime`, `configTime`/Referenz-`time`) erweitert werden.

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

## Track 1 — Anomalieerkennung (jetzt als Vorboten-Feature)

> Rolle verschoben: Die Anomalie-Scores sind nicht mehr das Endziel, sondern ein **Vorboten-Feature**
> für die Endlage-Vorhersage (und weiter nützlich zur unüberwachten Exploration). Kandidaten:

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

- **Ziel-Label = 2724/2723 im Frühwarn-Horizont:** ein Umlauf ist positiv, wenn innerhalb der nächsten
  X Umläufe/Tage eine Endlage-Störung folgt (X konfigurierbar).
- **Negative = zuverlässig:** DIANA überwacht kontinuierlich → Fehlen des Codes gilt als „keine Endlage-Störung".
  Damit ist eine **überwachte** Bewertung möglich (anders als bei den manuellen Gold-Labels, die PU sind).
- **Leave-one-switch-out:** Modell auf allen Weichen außer einer trainieren, auf der ausgelassenen bewerten
  → misst Transfer auf ungesehene Weichen. Metriken: PR-AUC (wegen starkem Klassenungleichgewicht), ROC-AUC,
  Vorwarnzeit (wie früh vor dem Ereignis geschlagen wird).
- **Klassenungleichgewicht/Seltenheit** explizit behandeln (PR-AUC statt Accuracy; ggf. Resampling/Gewichte).
- **Gold-Labels (manuell, partiell):** zusätzlich; Störungen werden via Excel-Vorlage
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
- [x] **Datenanalyse Zielcodes 2723/2724** → nur 5 Positive (alle WE438), Vorboten = Strom-Codes
- [ ] **`extract_har.py` erweitern**: `masterdata` (statische Features) + ungenutzte pte/config-Felder ← nächster Schritt
- [ ] **Feature-Engineering**: dynamische (per-Weiche normierte) + statische Features, Frühwarn-Label mit Horizont
- [ ] **Transfer-Setup**: gepooltes Modell + Leave-one-switch-out-Evaluation (PR-AUC, Vorwarnzeit)
- [ ] Modellvergleich klassisch vs. Deep auf der Vorhersageaufgabe
- [ ] Echtes Training/Eval, sobald HARs von Weichen MIT Endlage-Störungen vorliegen
- [ ] (parallel) robustere unüberwachte Baseline als Vorboten-Feature
