@echo off
title YPlayer
cd /d "%~dp0"

echo ====================================================
echo  YPlayer - Native YouTube & YouTube Music Player
echo ====================================================

:: 1. Python-Pruefung
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [FEHLER] Python wurde auf diesem System nicht gefunden!
    echo Bitte lade Python herunter: https://www.python.org/downloads/
    echo WICHTIG: Setze bei der Installation das Haekchen bei "Add Python to PATH"!
    echo.
    pause
    exit /b 1
)

:: 2. Virtuelle Umgebung einrichten (falls nicht vorhanden)
if not exist "venv\Scripts\python.exe" (
    echo.
    echo [1/2] Richte virtuelle Umgebung fuer Windows ein...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [2/2] Installiere Abhaengigkeiten (PyQt6, yt-dlp, ytmusicapi, pypresence)...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    echo.
    echo Installation erfolgreich abgeschlossen!
) else (
    call venv\Scripts\activate.bat
)

:: 3. YPlayer starten (ohne Terminalfenster via pythonw)
echo Starte YPlayer...
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" YPlayer.py
) else (
    start "" python YPlayer.py
)
