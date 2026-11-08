@echo off
rem Abre la escena del render en Blender. Si todavia no existe, primero ejecute Armar_escena.bat
cd /d "%~dp0"
call herramientas\buscar_blender.bat || exit /b 1
if not exist "blender\feria.blend" (
  echo Falta blender\feria.blend. Ejecute primero Armar_escena.bat
  pause
  exit /b 1
)
start "" "%BLENDER%" "%~dp0blender\feria.blend"
