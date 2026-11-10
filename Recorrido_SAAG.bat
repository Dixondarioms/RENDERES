@echo off
rem Video del recorrido por los stands del hangar del SAAG (28 s, 24 cuadros por segundo).
rem Antes hay que armar la escena con Edificio_SAAG.bat. Se puede cortar y volver a correr: sigue donde quedo.
rem Ejemplos:
rem   Recorrido_SAAG.bat                           -> 1920 x 1080, 64 muestras (con tarjeta grafica)
rem   Recorrido_SAAG.bat --escala 50 --muestras 16 -> borrador rapido (PC sin tarjeta grafica)
cd /d "%~dp0"
call herramientas\buscar_blender.bat || exit /b 1
if not exist "blender\edificio_saag.blend" (
  echo Falta blender\edificio_saag.blend. Ejecute primero Edificio_SAAG.bat --sin-render
  pause
  exit /b 1
)
"%BLENDER%" -b blender\edificio_saag.blend -P herramientas\recorrido_saag.py -- %*
echo.
echo Listo: blender\renders\recorrido_stands_saag.mp4
pause
