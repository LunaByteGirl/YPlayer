#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== [1/4] Vorbereitung & Werkzeuge ==="
VENV_DIR="${HOME}/.local/share/yplayer/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Erstelle Python Venv..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r requirements.txt pyinstaller
fi

if ! "$VENV_DIR/bin/python3" -c "import PyInstaller" 2>/dev/null; then
    echo "Installiere PyInstaller..."
    "$VENV_DIR/bin/pip" install pyinstaller
fi

APPIMAGETOOL="${HOME}/.local/bin/appimagetool"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Lade appimagetool herunter..."
    mkdir -p "${HOME}/.local/bin"
    curl -sL https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -o "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

echo "=== [2/4] PyInstaller Build ==="
rm -rf build/ dist/
"$VENV_DIR/bin/pyinstaller" \
  --noconfirm \
  --onedir \
  --windowed \
  --name YPlayer \
  --collect-all yt_dlp \
  --collect-all ytmusicapi \
  --collect-all pypresence \
  --collect-all certifi \
  YPlayer

echo "=== [3/4] AppDir erstellen ==="
APPDIR="build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -r dist/YPlayer/* "$APPDIR/usr/bin/"
cp yplayer.png "$APPDIR/yplayer.png"
cp yplayer.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/yplayer.png"
cp yplayer.svg "$APPDIR/yplayer.svg"
cp yplayer.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/yplayer.svg"

cat << 'EOF' > "$APPDIR/YPlayer.desktop"
[Desktop Entry]
Type=Application
Name=YPlayer
GenericName=YouTube Music Player
Comment=Minimalistischer nativer YouTube Music Player
Exec=YPlayer %U
Icon=yplayer
Categories=AudioVideo;Audio;Player;Qt;
Terminal=false
StartupWMClass=YPlayer
StartupNotify=true
EOF

cp "$APPDIR/YPlayer.desktop" "$APPDIR/usr/share/applications/YPlayer.desktop"

cat << 'EOF' > "$APPDIR/AppRun"
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${HERE}/usr/bin/_internal:${LD_LIBRARY_PATH}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS}"
exec "${HERE}/usr/bin/YPlayer" "$@"
EOF

chmod +x "$APPDIR/AppRun"

echo "=== [4/4] AppImage generieren ==="
export ARCH=x86_64
"$APPIMAGETOOL" "$APPDIR" YPlayer-x86_64.AppImage

echo "=== Fertig: YPlayer-x86_64.AppImage erfolgreich erstellt! ==="
