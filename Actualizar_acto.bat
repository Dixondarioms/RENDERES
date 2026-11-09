@echo off
rem Rehace solo el acto (tarima con toldo, autoridades sentadas y la parada) dentro de blender\feria.blend,
rem sin volver a armar toda la escena. Sirve si la PC no tiene memoria para Armar_escena.bat
rem o para probar cambios de herramientas\acto_blender.py.
cd /d "%~dp0"
call herramientas\buscar_blender.bat || exit /b 1
if not exist "blender\feria.blend" (
  echo Falta blender\feria.blend. Ejecute primero Armar_escena.bat
  pause
  exit /b 1
)
"%BLENDER%" -b blender\feria.blend -P herramientas\actualizar_acto.py
echo.
echo Listo. Para las imagenes:  Renderizar.bat tribuna toldo autoridades parada formacion acto
pause
