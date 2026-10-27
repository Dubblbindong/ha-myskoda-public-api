<img src="https://raw.githubusercontent.com/Dubblbindong/ha-myskoda-public-api/main/custom_components/myskoda_public_api/brand/icon.png" alt="" width="96" align="right">

# MyŠkoda Public API für Home Assistant

Bindet deinen Škoda über die **offizielle
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs)** in
Home Assistant ein. Die Anmeldung läuft über einen API-Schlüssel aus der
MyŠkoda-App. Es wird kein Konto-Passwort in Home Assistant gespeichert,
Schnittstelle und Limits sind von Škoda dokumentiert.

> **Nur für den persönlichen Gebrauch.** Škoda stellt die Public API für
> private Endnutzer bereit. Dieses Projekt steht in keiner Verbindung zu
> Škoda Auto. Škoda und MyŠkoda sind Marken der Škoda Auto a.s.

English documentation: [README.md](README.md)

## Was du bekommst

Es werden nur Entitäten angelegt, die dein Fahrzeug tatsächlich meldet.

- **Batterie und Laden:** Ladezustand, elektrische Reichweite, Ladestatus,
  AC/DC, Ladeleistung und -geschwindigkeit, Restzeit, voll geladen um,
  Stecker angeschlossen und verriegelt, Ladeschalter, Ladelimit-Regler
  (50 bis 100 %), Lademodus, Batterieschonmodus, maximaler Ladestrom,
  aktuelles Ladeprofil
- **Verbrenner:** Tankfüllstand, Gesamtreichweite, Reichweite je Antrieb,
  AdBlue-Reichweite, Antriebsart
- **Status:** Verriegelung, Türen, Fenster, Licht, Kofferraum, Motorhaube,
  Schiebedach, Kilometerstand
- **Position:** Standort-Tracker mit letzter Parkposition und aufgelöster
  Adresse, Parkstatus
- **Klima:** Klima-Entität mit Zieltemperatur, Klimatisierungsstatus,
  Scheibenheizung vorn und hinten, Schalter für Standheizung und
  Standlüftung
- **Fahrzeug:** Fahrzeugbild, Kennzeichen
- **Diagnose:** verbleibende API-Anfragen, Zeitpunkt des Limit-Resets,
  Ablauf des API-Schlüssels, Zeitstempel der Daten, Aktualisieren-Button

**Fernbefehle:** Laden starten und stoppen, Ladelimit setzen, Lademodus
wechseln, Klimatisierung, Standheizung und Standlüftung starten und stoppen.

## Voraussetzungen

- Ein Škoda mit Škoda Connect / MyŠkoda und ein aktives MyŠkoda-Konto.
- Ein API-Schlüssel aus der **MyŠkoda-App**. Öffne https://go.skoda.eu/api-keys
  auf dem Handy, erstelle einen Schlüssel und wähle das Fahrzeug aus.
  Schlüssel laufen ab; die Integration warnt eine Woche vorher und fragt bei
  Bedarf nach einem neuen.
- Home Assistant 2025.1 oder neuer.

## Installation

**HACS**

1. HACS → Integrationen → Menü (⋮) → *Benutzerdefinierte Repositories*
2. Repository `Dubblbindong/ha-myskoda-public-api`, Kategorie *Integration*
3. *MyŠkoda Public API* installieren und Home Assistant neu starten.

**Manuell**

Den Ordner `custom_components/myskoda_public_api` in den Ordner
`custom_components` deiner Konfiguration kopieren und Home Assistant neu
starten.

## Einrichtung

1. Einstellungen → Geräte & Dienste → *Integration hinzufügen* →
   *MyŠkoda Public API*
2. API-Schlüssel und FIN (VIN) des Fahrzeugs eingeben. Der Schlüssel wird
   mit einer einzigen API-Anfrage geprüft.

Ein Eintrag ist ein Fahrzeug. Für ein zweites Auto die Integration erneut
hinzufügen; derselbe Schlüssel geht, wenn er beide Fahrzeuge abdeckt.

**Optionen** (Konfigurieren auf der Integrationsseite)

- *Abfrageintervall:* standardmäßig 300 s, mindestens 240 s. Siehe
  Rate-Limit.
- *S-PIN:* nur zum Starten der Standheizung nötig.

## Rate-Limit

Die API erlaubt etwa **20 Anfragen pro Stunde und Fahrzeug**. Jede Abfrage,
jeder Fernbefehl und die Aktualisierung nach einem Befehl zählen. Die
Integration

- fragt standardmäßig alle 5 Minuten ab, also 12 Anfragen pro Stunde,
- liest die Limit-Header mit und bremst, sobald nur noch zwei Anfragen übrig
  sind,
- wartet nach einer 429-Antwort so lange, wie die API vorgibt,
- zeigt verbleibende Anfragen und Reset-Zeitpunkt als Diagnose-Sensoren.

Auch der *Aktualisieren*-Button und jeder Befehl verbrauchen Kontingent.
Automationen, die minütlich abfragen oder schalten, sind daher keine gute
Idee.

## Aktionen

**`myskoda_public_api.start_air_conditioning`**

- `device_id` (Pflicht): das Fahrzeug
- `temperature`: Ziel-Innenraumtemperatur in °C, 16 bis 30
- `without_external_power`: Klimatisierung auch ohne Ladekabel erlauben

**`myskoda_public_api.start_auxiliary_heating`**

- `device_id` (Pflicht): das Fahrzeug
- `duration`: Laufzeit in Minuten
- `start_mode`: `heating` oder `ventilation`
- `temperature`: Ziel-Innenraumtemperatur in °C
- `spin`: S-PIN, sonst wird die aus den Optionen verwendet

Für den Alltag reicht die Klima-Entität: Eine gesetzte Temperatur wird
gespeichert und beim nächsten *Einschalten* verwendet; läuft die
Klimatisierung bereits, wird sie mit dem neuen Ziel neu gestartet.

## Gut zu wissen

- **Befehle laufen asynchron.** Die API nimmt den Befehl an, das Fahrzeug
  führt ihn danach aus. Schalter zeigen sofort den erwarteten Zustand; die
  Integration holt den Stand nach 15 Sekunden neu und, nur falls das
  Fahrzeug bis dahin nichts gemeldet hat, noch einmal nach 60 Sekunden.
- **Teildaten sind normal.** Teile, die die API gerade nicht liefern kann,
  fehlen in der Antwort; die betroffenen Entitäten sind bis zur nächsten
  erfolgreichen Abfrage *nicht verfügbar*.
- **Position nur im Stand.** Während der Fahrt hat der Tracker keine
  Koordinaten.
- **Kein Ver- oder Entriegeln, kein Blinken oder Hupen.** Das bietet die API
  nicht an; der Verriegelungsstatus ist nur lesbar.
- **Ladeprofile** werden gelesen; das aktuelle ist ein Sensor. Bearbeiten
  ist nicht umgesetzt.

## Fehlersuche

- *API-Schlüssel abgelehnt:* abgelaufen, in der App gelöscht oder nicht für
  diese FIN freigegeben. In der MyŠkoda-App neu anlegen oder anpassen.
- *Limit ausgeschöpft:* auf den Reset warten (Diagnose-Sensor) und das
  Abfrageintervall erhöhen.
- Bei Problemmeldungen die Diagnosedatei von der Geräteseite anhängen;
  Schlüssel, FIN, Kennzeichen, Position und Adresse sind darin geschwärzt.
- Debug-Protokoll:

```yaml
logger:
  logs:
    custom_components.myskoda_public_api: debug
```

## Mitmachen und Sicherheit

Hinweise zum Mitarbeiten und zum Einsatz von KI-Werkzeugen stehen in
[CONTRIBUTING.md](CONTRIBUTING.md), Sicherheitslücken bitte vertraulich
gemäß [SECURITY.md](SECURITY.md) melden.

## Lizenz

[MIT](LICENSE)
