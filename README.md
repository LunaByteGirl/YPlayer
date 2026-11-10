# YPlayer

Ein minimalistischer, nativer Desktop-Musikplayer für Linux & Windows mit Google-/YouTube-Music-Integration und Discord Rich Presence.

## Funktionen

- **Nativ auf dem Desktop:** Schnelle PyQt6-Oberfläche für Linux (Wayland & X11) und Windows.
- **Home-Bildschirm:** Startseite mit Schnellzugriff auf Favoriten, Playlists und Entdecken-Kategorien.
- **Lokales Audio-Caching:** Stabiles Abspielen ohne Verbindungsabbrüche mit automatischer Vorpufferung des nächsten Titels.
- **Google-Konto-Verbindung:** Zugriff auf persönliche Playlists, Alben und Lieblingslieder.
- **Discord-Konto & Rich Presence:**
  - Nativer Login über lokalen Discord-IPC-Socket (Linux Unix-Sockets & Windows Named Pipes).
  - Zeigt Avatar, Anzeigename und `@handle` an.
  - Synchronisiert aktuellen Titel, Interpreten, Cover und Laufzeit in Echtzeit zu Discord.
  - Direkter Button „Auf YouTube anhören“ im Discord-Status.
- **Vektor-Design:** Dunkles Studio-Design mit 100 % QtSvg-Vektorsymbolen (keine Emojis auf Buttons).

## Voraussetzungen

- **Linux:** Python 3.10+, `ffmpeg`
- **Windows:** Python 3.10+ (im PATH aktiviert)

## Installation & Downloads

### Fertige Builds (Releases)

Lade die passende Version direkt von den [GitHub Releases](https://github.com/LunaByteGirl/YPlayer/releases/latest) herunter:

- **Windows Installer:** [`YPlayer-Setup-x64.exe`](https://github.com/LunaByteGirl/YPlayer/releases/download/v1.0.0/YPlayer-Setup-x64.exe) – Setup-Assistent mit Startmenü- und Desktop-Icon sowie Deinstallationsprogramm.
- **Windows Portable:** [`YPlayer-Windows-Portable-x64.zip`](https://github.com/LunaByteGirl/YPlayer/releases/download/v1.0.0/YPlayer-Windows-Portable-x64.zip) – Entpacken und sofort `YPlayer.exe` ohne Installation starten.
- **Linux AppImage:** [`YPlayer-x86_64.AppImage`](https://github.com/LunaByteGirl/YPlayer/releases/download/v1.0.0/YPlayer-x86_64.AppImage) – Standalone-AppImage für alle gängigen Distributionen (Arch, Ubuntu, Debian, Fedora, openSUSE etc.).

---

### Aus dem Quellcode starten

#### Windows: 1-Klick Startdatei

1. Repository klonen oder als ZIP entpacken:
   ```cmd
   git clone https://github.com/LunaByteGirl/YPlayer.git
   cd YPlayer
   ```

2. **Doppelklicke auf `YPlayer.bat`:**
   - Prüft Python, erstellt die virtuelle Umgebung und installiert Abhängigkeiten automatisch.
   - Startet YPlayer ohne störendes Konsolenfenster (`pythonw`).

Alternativ kann `YPlayer.pyw` direkt per Doppelklick gestartet werden.

#### Linux: Standalone AppImage oder Quellcode

1. **Als AppImage:**
   ```bash
   chmod +x YPlayer-x86_64.AppImage
   ./YPlayer-x86_64.AppImage
   ```
   *(Kann jederzeit neu gebaut werden mit `./build_appimage.sh`)*

2. **Aus dem Quellcode:**

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
