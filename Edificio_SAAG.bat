@echo off
rem Escena aparte solo con el edificio del SAAG (usa poca memoria, unos 40 s para armarla).
rem Guarda blender\edificio_saag.blend y las imagenes en blender\renders\saag_<vista>.png
rem Vistas: via entrada esquina atras techo
rem Ejemplos:
rem   Edificio_SAAG.bat                              -> todas las vistas, rapidas (32 muestras al 50 %%)
rem   Edificio_SAAG.bat via --muestras 512 --escala 100   -> vista desde la via en alta calidad
rem   Edificio_SAAG.bat --sin-render                 -> solo arma la escena (para abrirla en Blender)
cd /d "%~dp0"
call herramientas\buscar_blender.bat || exit /b 1
"%BLENDER%" -b -P herramientas\escena_edificio.py -- %*
echo.
echo Listo: blender\edificio_saag.blend y blender\renders\saag_*.png
echo Para verla en Blender:  "%BLENDER%" blender\edificio_saag.blend
pause
