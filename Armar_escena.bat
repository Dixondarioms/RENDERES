@echo off
rem Arma blender\feria.blend desde blender\escena.glb con todas las mejoras (aviones, edificios, arboles, pisos)
rem y genera imagenes de prueba en blender\renders\previa_*.png
cd /d "%~dp0"
call herramientas\buscar_blender.bat || exit /b 1
echo Usando %BLENDER%
"%BLENDER%" -b -P herramientas\armar_blender.py -- --previas
echo.
echo Listo: blender\feria.blend y blender\renders\previa_*.png
pause
