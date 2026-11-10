# YPlayer (YTMusic Linux)

Ein minimalistischer, nativer Desktop-Musikplayer für Linux mit Google-/YouTube-Music-Integration und Discord Rich Presence.

## Funktionen

- **Nativ auf dem Desktop:** Schnelle PyQt6-Oberfläche optimiert für Wayland und X11.
- **Home-Bildschirm:** Startseite mit Schnellzugriff auf Favoriten, Playlists und Entdecken-Kategorien.
- **Lokales Audio-Caching:** Stabiles Abspielen ohne Verbindungsabbrüche mit automatischer Vorpufferung des nächsten Titels.
- **Google-Konto-Verbindung:** Zugriff auf persönliche Playlists, Alben und Lieblingslieder.
- **Discord-Konto & Rich Presence:**
  - Nativer Login über lokalen Discord-IPC-Socket.
  - Zeigt Avatar, Anzeigename und `@handle` an.
  - Synchronisiert aktuellen Titel, Interpreten, Cover und Laufzeit in Echtzeit zu Discord.
  - Direkter Button „Auf YouTube anhören“ im Discord-Status.
- **Vektor-Design:** Dunkles Studio-Design mit 100 % QtSvg-Vektorsymbolen (keine Emojis auf Buttons).

## Voraussetzungen

- Linux (z. B. Arch, CachyOS, Fedora, Ubuntu)
- Python 3.10+
- `ffmpeg` für Audiowiedergabe

## Installation & Start

### Option 1: Als AppImage (Empfohlen, portabel ohne Installation)

1. Mache das AppImage ausführbar:
   ```bash
   chmod +x YPlayer-x86_64.AppImage
   ```

2. Starte das Programm direkt per Doppelklick oder über das Terminal:
   ```bash
   ./YPlayer-x86_64.AppImage
   ```

*Hinweis: Ein neues AppImage kann jederzeit mit dem mitgelieferten Skript `./build_appimage.sh` gebaut werden.*

### Option 2: Aus dem Quellcode starten

1. Repository klonen:
   ```bash
   git clone https://github.com/LunaByteGirl/YTMusic-Linux.git
   cd YTMusic-Linux
   ```

2. Virtuelle Python-Umgebung erstellen und Abhängigkeiten installieren:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. YPlayer starten:
   ```bash
   ./YPlayer
   ```

## Tastatur-Shortcuts

- `Leertaste`: Wiedergabe / Pause
- `J` / `Links`: 5 Sekunden zurückspulen
- `L` / `Rechts`: 5 Sekunden vorspulen
- `N`: Nächster Titel
- `P`: Vorheriger Titel
- `M`: Stummschalten
- `S`: Zufallswiedergabe (Shuffle)
- `R`: Wiederholung umschalten (Aus / Alle / Einzeln)
- `F`: Aktuellen Titel zu Favoriten hinzufügen
