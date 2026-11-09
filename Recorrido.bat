@echo off
rem Video del recorrido por los stands de la AMB (2K, 30 cuadros por segundo).
rem Se puede cortar y volver a correr: sigue desde el ultimo cuadro hecho.
rem Ejemplos:
rem   Recorrido.bat                  -> video completo (96 muestras por cuadro)
rem   Recorrido.bat --muestras 64    -> mas rapido, un poco mas de ruido
cd /d "%~dp0"
call herramientas\buscar_blender.bat || exit /b 1
if not exist "blender\feria.blend" (
  echo Falta blender\feria.blend. Ejecute primero Armar_escena.bat
  pause
  exit /b 1
)
"%BLENDER%" -b blender\feria.blend -P herramientas\recorrido.py -- %*
echo.
echo Listo: blender\renders\recorrido_stands_2K.mp4
pause
