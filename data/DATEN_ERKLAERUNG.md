# Erklärung des DIANA-Weichendatensatzes

## Was ist DIANA?

DIANA ist eine Web-Plattform der DB InfraGO AG zur Überwachung von Eisenbahn-Infrastruktur. Über DIANA kann man sich unter anderem die Umläufe (Stellvorgänge) von Weichen anschauen — also wie sich der Antriebsmotor einer Weiche bei jedem Umstellen verhält.

Die Daten, die wir hier betrachten, stammen von der Weiche **WE265** am **Bf Frankfurt(Main) Höchst**.

## Was ist ein "Umlauf"?

Ein Umlauf ist ein einzelner Stellvorgang einer Weiche: Der Motor läuft an, bewegt die Weichenzunge von einer Endlage in die andere, und stoppt wieder. Das dauert bei dieser Weiche ca. 4 Sekunden.

Jeder Umlauf hat eine **Richtung**:
- **L** = die Weiche wurde in die linke Endlage gestellt
- **R** = die Weiche wurde in die rechte Endlage gestellt

## Was wird gemessen?

Während jedes Umlaufs wird der **Motorstrom** (in Ampere) mit 50 Messungen pro Sekunde aufgezeichnet. Das ergibt eine Kurve, die den typischen Verlauf des Stellvorgangs zeigt:

1. **Anlaufspitze** — kurzer hoher Strom beim Start des Motors (~2.3 A)
2. **Laufphase** — gleichmäßiger Strom während die Zunge bewegt wird (~0.8–1.2 A)
3. **Abschaltung** — der Motor stoppt, Strom fällt auf 0

Diese Stromkurve ist wie ein "Fingerabdruck" des Stellvorgangs. Wenn sich die Kurve verändert (z.B. höherer Strom, längere Dauer), kann das auf mechanische Probleme hinweisen.

Zusätzlich zum Stromverlauf wird bei jedem Umlauf gespeichert:
- **Zeitpunkt** des Umlaufs
- **Außentemperatur** (in Kelvin — um in Celsius umzurechnen: Wert minus 273.15)
- **Wartungsmodus** — ob der Umlauf im Rahmen einer Wartung durchgeführt wurde
- **Fehlerzustände** — ob bei diesem Umlauf Diagnosen/Fehler erkannt wurden

## Referenzkurve

Für jede Richtung (L und R) gibt es eine **Referenzkurve**. Das ist ein gemittelter "normaler" Stromverlauf. Einzelne Umläufe werden mit dieser Referenz verglichen, um Abweichungen zu erkennen.

---

## Wie kommt man an die Daten?

Es gibt zwei Wege:

### Weg 1: HAR-Datei aus dem Browser exportieren

Das ist der Weg, den wir bisher genutzt haben. Eine HAR-Datei ist eine Aufzeichnung aller Netzwerkanfragen, die der Browser beim Besuch einer Webseite macht.

**Schritt für Schritt:**

1. DIANA im Browser öffnen und die gewünschte Weiche aufrufen
2. Entwicklertools öffnen (F12 oder Rechtsklick → "Untersuchen")
3. Auf den Tab **"Netzwerk"** klicken
4. Die gewünschte Ansicht in DIANA laden (z.B. Umläufe-Ansicht)
5. Im Netzwerk-Tab: Rechtsklick → **"Alles als HAR mit Inhalt speichern"**

**Problem:** Die HAR-Datei enthält sehr viel Ballast — von den 159 Einträgen in unserer Datei sind nur 2 tatsächlich relevant für die Umlaufdaten. Der Rest sind Bilder, Stylesheets, Schriftarten und andere Website-Dateien.

Die relevanten Daten stecken in den Antworten dieser beiden API-Aufrufe:

| API-Endpunkt | Was er liefert |
|---|---|
| `/im/api/v1/wk/pointturnlist/` | Die letzten 50 Umläufe mit allen Details + Referenzkurven |
| `/im/api/v1/events/pointturn/` | Nur ein einzelner Umlauf (nur Stromkurve, ohne Zusatzinfos) |

Für die Analyse ist der **pointturnlist**-Endpunkt der wichtige — er enthält alles.

### Weg 2: Direkte API-Abfrage (empfohlen)

Statt den Umweg über den Browser zu gehen, kann man die DIANA-API auch direkt abfragen. Das ist besser, weil man gezielt nur die Daten bekommt, die man braucht, und weil man den Vorgang automatisieren kann.

#### Welches Werkzeug benutzen?

Um API-Anfragen zu schicken, braucht man ein Werkzeug. Für Einsteiger empfehlen wir **Postman** — ein kostenloses Programm mit grafischer Oberfläche, bei dem man nichts programmieren muss.

**Postman installieren:**
1. Auf https://www.postman.com/downloads/ gehen
2. Herunterladen und installieren
3. Man kann ohne Account starten (auf "Skip and go to the app" klicken)

Alternativ kann man auch **curl** verwenden — ein Kommandozeilen-Programm, das auf Mac und Linux schon vorinstalliert ist. Die Beispiele unten zeigen beide Wege.

#### Schritt 1: Anmeldung (Token holen)

Die API ist passwortgeschützt. Um sie zu nutzen, braucht man einen sogenannten **Token** — eine Art digitalen Ausweis, der 15 Minuten gültig ist.

**In Postman:**

1. Neuen Tab öffnen ("+"-Button oben)
2. Oben links **POST** auswählen (statt GET)
3. In die Adresszeile eingeben:
   ```
   https://diana-server.tech.db.de/auth/realms/dbnetze/protocol/openid-connect/token
   ```
4. Darunter auf den Tab **"Body"** klicken
5. Die Option **"x-www-form-urlencoded"** auswählen
6. Folgende Schlüssel-Wert-Paare eintragen (jede Zeile ist ein eigenes Feld):

   | KEY | VALUE |
   |---|---|
   | `grant_type` | `password` |
   | `client_id` | `detailplugins` |
   | `username` | *eigener DB-Benutzername (z.B. `d0001013815`)* |
   | `password` | *eigenes Passwort* |

7. Auf den blauen **"Send"**-Button klicken

**Mit curl (Kommandozeile):**

```bash
curl -X POST "https://diana-server.tech.db.de/auth/realms/dbnetze/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=detailplugins" \
  -d "username=DEIN_BENUTZERNAME" \
  -d "password=DEIN_PASSWORT"
```

**Die Antwort** sieht ungefähr so aus (gekürzt):

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6...(langer Text)...",
  "expires_in": 900,
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "token_type": "Bearer"
}
```

Den Wert von `access_token` kopieren — das ist der Token, den man für die nächsten **15 Minuten** verwenden kann. (Nach Ablauf einfach Schritt 1 wiederholen.)

> **Wichtig:** Es ist möglich, dass die direkte Passwort-Anmeldung nicht freigeschaltet ist. In dem Fall muss man den IT-Verantwortlichen für DIANA kontaktieren und fragen, ob "Direct Access Grants" für den Keycloak-Client aktiviert werden können, oder ob es einen Service-Account gibt.

#### Schritt 2: Daten abfragen

**In Postman:**

1. Neuen Tab öffnen
2. Oben links **GET** auswählen
3. In die Adresszeile eingeben:
   ```
   https://diana-server.tech.db.de/im/api/v1/wk/pointturnlist/
   ```
4. Darunter auf den Tab **"Params"** klicken und folgende Schlüssel-Wert-Paare eintragen:

   | KEY | VALUE |
   |---|---|
   | `objectId` | `FHOE---WK----265~~~~~` |
   | `position` | `L,R` |
   | `limit` | `50` |
   | `before` | `2026-04-28T22:00:00.000Z` |

5. Auf den Tab **"Authorization"** (oder "Auth") klicken
6. Bei "Type" **"Bearer Token"** auswählen
7. Den kopierten `access_token` aus Schritt 1 ins Token-Feld einfügen
8. Auf **"Send"** klicken

Die Antwort enthält die Umlaufdaten als JSON. Man kann sie über den "Save Response"-Button rechts unten als Datei speichern.

**Mit curl (Kommandozeile):**

```bash
curl "https://diana-server.tech.db.de/im/api/v1/wk/pointturnlist/?objectId=FHOE---WK----265~~~~~&position=L,R&limit=50&before=2026-04-28T22:00:00.000Z" \
  -H "Authorization: Bearer HIER_DEN_ACCESS_TOKEN_EINFUEGEN" \
  -o umlaufdaten.json
```

(Die Option `-o umlaufdaten.json` speichert die Antwort direkt in eine Datei.)

**Die Parameter der Abfrage:**

| Parameter | Bedeutung | Beispiel |
|---|---|---|
| `objectId` | Die ID der Weiche | `FHOE---WK----265~~~~~` |
| `position` | Welche Richtungen | `L,R` (beide) oder `L` oder `R` |
| `limit` | Wie viele Umläufe maximal | `50` |
| `before` | Nur Umläufe vor diesem Zeitpunkt | `2026-04-28T22:00:00.000Z` |

> **Tipp:** Um ältere Daten zu bekommen, einfach den `before`-Parameter weiter in die Vergangenheit setzen. Um die nächsten 50 Umläufe davor zu holen, den Zeitstempel des ältesten Umlaufs aus der vorherigen Antwort verwenden.

#### Wie findet man die objectId einer anderen Weiche?

Die objectId setzt sich zusammen aus einem Betriebsstellen-Kürzel und einer Nummer. In unserem Beispiel:
- `FHOE` = Frankfurt(Main) Höchst
- `WK` = Weiche (Objekttyp)
- `265` = Weichennummer

Um herauszufinden, welche Weichen verfügbar sind, kann man diesen Endpunkt abfragen:

```
GET https://diana-server.tech.db.de/im/api/v1/masterdata/<objectId>
```

Oder sich die Rechte-Übersicht holen, die alle verfügbaren Objekt-IDs auflistet:

```
POST https://diana-server.tech.db.de/im/api/v1/permissions/rights
```

---

## Struktur der Antwort von pointturnlist

Die API liefert ein JSON-Objekt mit folgender Struktur:

```
pointturnlist
├── ptes              ← Liste der Umläufe (Point Turn Events)
│   └── Jeder Umlauf enthält:
│       ├── position          "L" oder "R"
│       ├── turnTime          Dauer in Sekunden (z.B. 4.2)
│       ├── samplingInterval  Abstand zwischen Messungen (0.02 = 50 Hz)
│       ├── time              Zeitpunkt (Unix-Zeitstempel in Millisekunden)
│       ├── temperatureAir    Außentemperatur in Kelvin
│       ├── isMaintenance     true/false — Wartungsmodus
│       ├── objectId          ID der Weiche
│       ├── errorConditionMetaIds  Fehlerzustände (leer = kein Fehler)
│       └── motorTurnData     Liste der Motordaten
│           └── Jeder Motor enthält:
│               ├── idSub1    Motor-Kennung (z.B. "SAT01")
│               ├── current   Liste der Stromwerte (in Ampere)
│               └── power     Liste der Leistungswerte (oft leer)
│
└── configs           ← Referenzkurven
    └── Pro Richtung (L und R) eine Referenz mit:
        ├── position
        ├── turnTime
        └── motorTurnData (gleiche Struktur wie oben)
```

## Glossar

| Begriff | Erklärung |
|---|---|
| **Umlauf / PTE** | Ein einzelner Stellvorgang der Weiche |
| **HAR-Datei** | HTTP Archive — Aufzeichnung aller Browser-Netzwerkanfragen |
| **API** | Programmierschnittstelle — ermöglicht direkten Datenabruf ohne Browser |
| **Token** | Digitaler Ausweis für die API-Authentifizierung (15 Min. gültig) |
| **JSON** | Textformat für strukturierte Daten (von der API zurückgeliefert) |
| **Keycloak** | Die Anmelde-Software, die DIANA verwendet |
| **objectId** | Eindeutige Kennung einer Weiche im DIANA-System |
| **Referenzkurve** | Gemittelter "Normal"-Stromverlauf zum Vergleich |
| **samplingInterval** | Zeitabstand zwischen zwei Messpunkten (0.02s = alle 20ms) |
