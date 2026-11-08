@echo off
rem Renders finales en alta calidad (usa la tarjeta grafica si hay).
rem Ejemplos:
rem   Renderizar.bat                     -> todas las vistas
rem   Renderizar.bat panoramica acto     -> solo esas vistas
rem   Renderizar.bat panoramica --muestras 512
cd /d "%~dp0"
call herramientas\buscar_blender.bat || exit /b 1
if not exist "blender\feria.blend" (
  echo Falta blender\feria.blend. Ejecute primero Armar_escena.bat
  pause
  exit /b 1
)
"%BLENDER%" -b blender\feria.blend -P herramientas\renderizar.py -- %*
echo.
echo Listo: imagenes en blender\renders\render_*.png
pause
