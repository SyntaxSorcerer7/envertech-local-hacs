# Envertech EVT Local – Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io/)

Lokale Home Assistant Integration für **Envertech EVT2000SE** Mikro-Wechselrichter – komplett ohne Cloud, direkt über das lokale TCP-Protokoll.

---

## Features

- **Rein lokal** – Keine Cloud-Abhängigkeit, keine Internetverbindung nötig
- **Live-Daten** aller 4 Mikroinverter-Kanäle (MI 0–3):
  - DC-Spannung (V)
  - AC-Leistung (W)
  - Gesamtenergie (kWh)
  - Temperatur (°C)
  - AC-Spannung (V)
  - Frequenz (Hz)
- **Gesamtwerte** über alle Kanäle (Gesamtleistung, Gesamtenergie)
- **Leistungsbegrenzung** setzen (600W – 2000W in festen Stufen)
- **Firmware-Version** auslesen
- **Persistente TCP-Verbindung** für maximale Zuverlässigkeit
- **Config Flow** – Einrichtung über die HA-Oberfläche
- **Übersetzungen** – Deutsch und Englisch

---

## Voraussetzungen

- Home Assistant 2024.1.0 oder neuer
- [HACS](https://hacs.xyz/) installiert
- Envertech EVT2000SE Wechselrichter im lokalen Netzwerk
- Bekannte IP-Adresse und Seriennummer des Wechselrichters

### Seriennummer herausfinden

Die Seriennummer steht auf dem Typenschild des Wechselrichters. In der Integration wird sie als **Hex-Wert** eingegeben. Beispiel:

- Dezimal: `2712847316` → Hex: `A1B2C3D4`
- Auf dem Typenschild steht möglicherweise die Hex-Darstellung direkt

Die Seriennummer kann auch über die EnverView-App oder das Envertech-Portal abgelesen werden.

---

## Installation

### Über HACS (empfohlen)

1. **HACS** öffnen → **Integrationen** → Menü (⋮) → **Benutzerdefinierte Repositories**
2. Repository-URL eingeben: `https://github.com/DEIN-USER/envertech-local`
3. Kategorie: **Integration**
4. **Hinzufügen** → **Envertech EVT Local** suchen → **Herunterladen**
5. Home Assistant **neu starten**

### Manuell

1. Den Ordner `custom_components/envertech_local/` in dein Home Assistant `config/custom_components/` Verzeichnis kopieren
2. Home Assistant **neu starten**

---

## Konfiguration

### Über die UI (Config Flow)

1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**
2. Nach **"Envertech EVT Local"** suchen
3. IP-Adresse des Wechselrichters eingeben
4. Seriennummer als Hex-Wert eingeben (z.B. `A1B2C3D4`)
5. Die Integration testet die Verbindung automatisch

### Parameter

| Parameter | Beschreibung | Beispiel |
|-----------|-------------|----------|
| IP-Adresse | Lokale IP des Wechselrichters | `192.168.1.100` |
| Seriennummer | Geräte-Serial als Hex | `A1B2C3D4` |

> **Tipp:** Vergib dem Wechselrichter eine feste IP-Adresse in deinem Router (DHCP-Reservierung), damit sich die IP nicht ändert.

---

## Entitäten

### Pro Mikroinverter-Kanal (MI 0–3)

Es werden **4 Geräte** angelegt (MI 0 bis MI 3), jeweils mit:

| Sensor | Einheit | Device Class | Beschreibung |
|--------|---------|-------------|--------------|
| DC-Spannung | V | `voltage` | Eingangsspannung vom Solarpanel |
| AC-Leistung | W | `power` | Aktuelle Einspeiseleistung |
| Gesamtenergie | kWh | `energy` | Kumulierte Energieproduktion |
| Temperatur | °C | `temperature` | Interne Temperatur des MI |
| AC-Spannung | V | `voltage` | Netzspannung |
| Frequenz | Hz | `frequency` | Netzfrequenz |

### Gesamtgerät

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| AC-Gesamtleistung | W | Summe aller 4 MI-Kanäle |
| Gesamtenergie | kWh | Summe aller 4 MI-Kanäle |
| Firmware-Version | – | z.B. "164.125" (standardmäßig deaktiviert) |

### Steuerung

| Entität | Typ | Beschreibung |
|---------|-----|--------------|
| Leistungsbegrenzung | `select` | Watt-Stufe wählen (600W–2000W) |

### Verfügbare Leistungsstufen (EVT2000SE)

| Stufe |
|-------|
| 600W |
| 800W |
| 1200W |
| 1400W |
| 1440W |
| 1600W |
| 1640W |
| 1800W |
| 2000W |

---

## Automationen & Dashboards

### Beispiel: Energy Dashboard

Die Sensoren mit `device_class: energy` und `state_class: total_increasing` sind automatisch für das **Home Assistant Energy Dashboard** kompatibel. Füge dort die Gesamtenergie oder die einzelnen MI-Energiesensoren hinzu.

### Beispiel: Leistungsbegrenzung per Automation

```yaml
automation:
  - alias: "Wechselrichter auf 800W begrenzen bei hohem Netzbezug"
    trigger:
      - platform: numeric_state
        entity_id: sensor.stromzaehler_leistung
        above: 3000
        for:
          minutes: 5
    action:
      - service: select.select_option
        target:
          entity_id: select.envertech_a1b2c3d4_power_limit
        data:
          option: "800W"
```

### Beispiel: Temperatur-Warnung

```yaml
automation:
  - alias: "Wechselrichter Übertemperatur-Warnung"
    trigger:
      - platform: numeric_state
        entity_id: sensor.envertech_mi_0_temperature
        above: 70
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Wechselrichter Warnung"
          message: "MI 0 Temperatur: {{ states('sensor.envertech_mi_0_temperature') }}°C"
```

### Beispiel: Lovelace Dashboard Card

```yaml
type: entities
title: Envertech EVT2000SE
entities:
  - entity: sensor.envertech_a1b2c3d4_total_ac_power
    name: Gesamtleistung
  - entity: sensor.envertech_a1b2c3d4_total_energy_all
    name: Gesamtenergie
  - entity: select.envertech_a1b2c3d4_power_limit
    name: Leistungsbegrenzung
  - type: divider
  - entity: sensor.envertech_mi_0_ac_power
    name: MI 0 Leistung
  - entity: sensor.envertech_mi_1_ac_power
    name: MI 1 Leistung
  - entity: sensor.envertech_mi_2_ac_power
    name: MI 2 Leistung
  - entity: sensor.envertech_mi_3_ac_power
    name: MI 3 Leistung
```

---

## Technische Details

### Kommunikationsprotokoll

Die Integration kommuniziert direkt über TCP Port `14889` mit dem Wechselrichter. Das Protokoll ist proprietär und wurde durch Reverse Engineering der EnverView-App dokumentiert (siehe `research/wechselrichter-api.md`).

| Eigenschaft | Wert |
|-------------|------|
| Transport | TCP |
| Port | 14889 |
| TX-Encoding | ASCII-HEX |
| RX-Encoding | Binär |
| Poll-Intervall | 120 Sekunden |
| Verbindung | Persistent (eine TCP-Session) |

### Verbindungsstrategie

Die Integration hält **eine persistente TCP-Verbindung** zum Wechselrichter. Dies ist notwendig, da der WR bei häufigem Neuverbinden instabil wird. Auf einer bestehenden Verbindung antwortet er zuverlässig – auch nach längerer Idle-Zeit.

### Retries & Fehlerbehandlung

| Operation | Max Retries | Delay | Timeout |
|-----------|------------|-------|---------|
| Live Data (0x1077) | 3 | 3s | 3s |
| Power Limit Read (0x1041) | 5 | 5s | 10s |
| TCP Connect | 1 | – | 5s |

### Geräte-Architektur

Der EVT2000SE enthält 4 logische Mikroinverter (MI 0–3) mit fortlaufenden UIDs. Jeder MI hat ein eigenes Solarpanel-Input und liefert unabhängige Messwerte. Die Integration erstellt für jeden MI ein eigenes HA-Gerät mit zugehörigen Sensoren.

---

## Fehlerbehebung

### "Cannot connect to inverter"

- Prüfe, ob der Wechselrichter eingeschaltet ist (produziert er gerade Strom?)
- Prüfe die IP-Adresse: `ping 192.168.1.100`
- Prüfe, ob Port 14889 erreichbar ist: `nc -zv 192.168.1.100 14889`
- Manche Wechselrichter sind nur tagsüber erreichbar (kein Standby-Modus)
- Stelle sicher, dass keine andere Anwendung (z.B. EnverView-App) gleichzeitig verbunden ist

### "No response from inverter"

- Der Wechselrichter braucht manchmal mehrere Sekunden zum Antworten
- Die Integration hat automatische Retries eingebaut
- Bei anhaltenden Problemen: HA neu starten, um die TCP-Verbindung zurückzusetzen

### Sensoren zeigen "Unavailable"

- Nachts liefern die Wechselrichter oft keine Daten (kein Strom = kein Netzwerk)
- Nach Sonnenaufgang sollten die Sensoren automatisch wieder verfügbar werden
- Prüfe die HA-Logs: **Einstellungen** → **System** → **Protokolle** → nach "envertech" filtern

### Falsche Seriennummer

- Die Seriennummer muss als **Hex-Wert** eingegeben werden
- Beispiel: Wenn auf dem Gerät `2712847316` steht → in Hex umrechnen: `A1B2C3D4`
- Python: `hex(2712847316)` → `0xA1B2C3D4`

### Leistungsbegrenzung funktioniert nicht

- Das Lesen der aktuellen Begrenzung ist unzuverlässig (~20% Erfolgsrate)
- Das **Setzen** funktioniert zuverlässig
- Nach dem Setzen wird der neue Wert direkt in der Integration aktualisiert
- Nur die definierten Stufen sind verfügbar (600, 800, 1200, 1400, 1440, 1600, 1640, 1800, 2000W)

---

## Entwicklung

### Projektstruktur

```
custom_components/envertech_local/
├── __init__.py          # Integration Setup & Entry Points
├── config_flow.py       # Konfigurationsdialog
├── const.py             # Konstanten
├── coordinator.py       # Daten-Coordinator (Polling)
├── manifest.json        # Integration Manifest
├── protocol.py          # TCP-Protokoll Implementierung
├── select.py            # Power Limit Select Entity
├── sensor.py            # Sensor Entities
├── strings.json         # UI-Strings (Basis)
└── translations/
    ├── de.json           # Deutsche Übersetzung
    └── en.json           # Englische Übersetzung
```

### Architektur

```
┌─────────────────────────────────────────────┐
│                Home Assistant               │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ sensor.py │  │ select.py│  │config_flow│  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │              │             │        │
│  ┌────▼──────────────▼─────────────▼─────┐  │
│  │         coordinator.py                │  │
│  │    (DataUpdateCoordinator, 120s)      │  │
│  └────────────────┬──────────────────────┘  │
│                   │                         │
│  ┌────────────────▼──────────────────────┐  │
│  │          protocol.py                  │  │
│  │   (EnvertechConnection, TCP, async)   │  │
│  └────────────────┬──────────────────────┘  │
└───────────────────┼─────────────────────────┘
                    │ TCP :14889
          ┌─────────▼──────────┐
          │  EVT2000SE (LAN)   │
          │  MI 0 │ MI 1       │
          │  MI 2 │ MI 3       │
          └────────────────────┘
```

### Protokoll-Referenz

Die vollständige Protokolldokumentation befindet sich in [`research/wechselrichter-api.md`](research/wechselrichter-api.md).

---

## Kompatibilität

| Gerät | Status |
|-------|--------|
| EVT2000SE | ✅ Voll unterstützt |
| EVT800 | ⚠️ Sollte funktionieren (ungetestet, ggf. andere Watt-Codes) |
| EVT1000 | ⚠️ Sollte funktionieren (ungetestet) |
| EVT400 | ⚠️ Sollte funktionieren (ungetestet, weniger MI-Kanäle) |
| Envertech Monitor/Gateway | ❌ Nicht unterstützt (anderer Kommunikationsablauf) |

---

## Lizenz

MIT License

---

## Danksagung

- Protokoll-Analyse basierend auf der decompilierten EnverView-App (v4.1.20)
- Live-Verifizierung gegen EVT2000SE (Firmware 164.125)
- PCAP-Mitschnitte mit PCAPdroid
