@echo off
rem Busca blender.exe y lo deja en la variable BLENDER.
rem Orden: variable BLENDER ya definida, Blender portable en Documentos\Blender, Blender instalado, PATH.
if defined BLENDER if exist "%BLENDER%" exit /b 0
set "BLENDER="
for /d %%D in ("%USERPROFILE%\Documents\Blender\blender-*") do if exist "%%D\blender.exe" set "BLENDER=%%D\blender.exe"
if defined BLENDER exit /b 0
for /d %%D in ("%ProgramFiles%\Blender Foundation\Blender *") do if exist "%%D\blender.exe" set "BLENDER=%%D\blender.exe"
if defined BLENDER exit /b 0
for %%E in (blender.exe) do if not "%%~$PATH:E"=="" set "BLENDER=%%~$PATH:E"
if defined BLENDER exit /b 0
echo.
echo No encontre Blender. Instale Blender 4.5 LTS desde https://www.blender.org/download/lts/
echo o escriba antes:  set BLENDER=C:\ruta\a\blender.exe
echo.
pause
exit /b 1
