@echo off
rem Abre el render 3D de la feria. Necesita Python instalado e internet (para la libreria 3D).
cd /d "%~dp0"
start "Servidor del render (no cerrar)" python -m http.server 8765 --bind 127.0.0.1
timeout /t 2 /nobreak >nul
start "" http://localhost:8765/
