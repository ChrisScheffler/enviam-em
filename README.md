# enviaM Energy Monitor

Eine benutzerdefinierte Home-Assistant-Integration, die den Live-Energiefluss
des enviaM Energy Monitor (Kiwigrid HEMS) ausliest und als Leistungssensoren
bereitstellt.

## Bereitgestellte Sensoren

| Sensor | Quellfeld | Beschreibung |
| --- | --- | --- |
| PV Production | `pv.out` | Aktuelle PV-Erzeugung |
| Grid Import | `grid.in` | Leistung, die aus dem Netz bezogen wird |
| Grid Export | `grid.out` | Leistung, die ins Netz eingespeist wird |
| Home Consumption | `consumption.in` | Gesamtverbrauch des Haushalts |
| EV Charging | `ev.in` | Ladeleistung des Elektroautos |
| EV Discharging | `ev.out` | Rückspeisung aus dem Elektroauto (bidirektionale Anlagen) |

Alle Leistungssensoren werden in Watt angegeben und verwenden die
Geräteklasse `power` mit der Zustandsklasse `measurement`.

### Tagesenergie-Sensoren

Diese Sensoren basieren auf
`https://hems.kiwigrid.com/v11/analytics/overview?type=WORK` für den jeweils
aktuellen Tag (lokale Mitternacht bis 23:59:59) und werden alle 60 Sekunden
abgefragt. Die Energiesensoren werden in Kilowattstunden angegeben und
verwenden die Geräteklasse `energy` mit der Zustandsklasse `total`, sodass sie
direkt im Energie-Dashboard von Home Assistant genutzt werden können.

| Sensor | Quellserie | Beschreibung |
| --- | --- | --- |
| Energy Consumed Today | `WorkConsumed` | Gesamtverbrauch des heutigen Tages |
| Energy From Grid Today | `WorkIn` | Heute aus dem Netz bezogene Energie |
| Energy Self Consumed Today | `WorkConsumedFromProducers` | Heute durch eigene Erzeugung gedeckte Energie |
| Energy Produced Today | `WorkProduced` | Heute erzeugte Energie |
| Energy To Grid Today | `WorkOut` | Heute ins Netz eingespeiste Energie |
| Self Sufficiency Today | abgeleitet | Anteil des Verbrauchs, der ohne Netzbezug gedeckt wurde |
| Self Consumption Ratio Today | abgeleitet | Anteil der Erzeugung, der selbst verbraucht wurde |

Der Overview-Endpunkt liefert die aggregierten Werte der Gesamtanlage direkt,
sodass nichts mehr abgeleitet werden muss. Jeder Energiesensor stellt
zusätzlich die Aufteilung pro Intervall als Attribut `hourly` bereit, zusammen
mit `resolution`, `time_zone`, `source_series` und `source_unit`. Intervalle,
die als `null` gemeldet werden (noch keine Daten), werden übersprungen.

Die beiden Verhältnissensoren werden aus den Werten oben berechnet
(`Autarkiegrad = Eigenverbrauch / Verbrauch`,
`Eigenverbrauchsanteil = Eigenverbrauch / Erzeugung`) und in Prozent
angegeben. Sie sind auf 0–100 % begrenzt und bleiben nicht verfügbar, wenn die
zugrunde liegenden Werte fehlen.

## Installation (HACS)

1. **HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories**
2. URL `https://github.com/ChrisScheffler/enviam-em`, Kategorie **Integration**
3. **enviaM Energy Monitor** installieren
4. Home Assistant neu starten
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → **enviaM Energy Monitor**
6. Benutzername und Passwort eingeben

Updates erscheinen in HACS, sobald ein neues Release mit erhöhter `version` in
`custom_components/enviam_em/manifest.json` veröffentlicht wurde.

## Installation (manuell)

Kopiere den Ordner `custom_components/enviam_em` in das Verzeichnis
`custom_components` deiner Home-Assistant-Konfiguration und starte Home
Assistant neu.

## Konfiguration

Die Integration authentifiziert sich über die enviaM-Übersichtsseite
(Keycloak), ruft einen Access-Token vom Context-Endpunkt ab und fragt
`https://hems.kiwigrid.com/v11/energy-flow` alle 10 Sekunden ab. Die
Tagesenergiewerte werden alle 60 Sekunden von
`https://hems.kiwigrid.com/v11/analytics/overview` gelesen. Beide Endpunkte
verwenden denselben Bearer-Token.

Wenn sich die Zugangsdaten ändern, startet Home Assistant eine
Reauthentifizierung und fragt nach einem neuen Passwort; der bestehende
Konfigurationseintrag wird dabei direkt aktualisiert.

## Fehlersuche

Aktiviere das Debug-Logging in der `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.enviam_em: debug
```
