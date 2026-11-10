"""Video del recorrido por los stands del hangar del SAAG (escena aparte blender/edificio_saag.blend).

Uso (desde la carpeta del proyecto; antes hay que armar la escena con Edificio_SAAG.bat):
  blender.exe -b blender/edificio_saag.blend -P herramientas/recorrido_saag.py -- [--muestras N] [--escala P] [--desde F] [--hasta F]

Los cuadros quedan en blender/renders/recorrido_saag/cuadro_0001.png ... y al final se arma
blender/renders/recorrido_stands_saag.mp4 con ffmpeg. Se puede cortar y volver a correr: sigue donde quedó.
Por defecto: 1920 x 1080, 24 cuadros por segundo, 64 muestras. En una PC sin tarjeta gráfica conviene un borrador:
--escala 50 --muestras 16.
"""
import os
import shutil
import subprocess
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usar_gpu import activar_gpu   # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
opc = {'--muestras': 64, '--desde': None, '--hasta': None, '--escala': 100}
i = 0
while i < len(ARGS):
    if ARGS[i] in opc:
        opc[ARGS[i]] = int(ARGS[i + 1]); i += 2
    else:
        i += 1

escena = bpy.context.scene
r, c = escena.render, escena.cycles
cam = bpy.data.objects.get('Recorrido SAAG')
if not cam:
    sys.exit('No está la cámara "Recorrido SAAG": vuelva a armar la escena con Edificio_SAAG.bat')
activar_gpu(escena)
escena.camera = cam
r.resolution_x, r.resolution_y = tuple(cam.get('resolucion', (1920, 1080)))
r.resolution_percentage = opc['--escala']
# exposición animada: más alta adentro del hangar (claves guardadas en la cámara)
base = escena.get('exposicion_base', escena.view_settings.exposure)
claves = list(cam.get('ev_claves', []))
for k in range(0, len(claves), 2):
    escena.view_settings.exposure = base + claves[k + 1]
    escena.view_settings.keyframe_insert('exposure', frame=int(claves[k]))
# video: muestras fijas (sin adaptativo, que en interiores deja manchas que cambian de un cuadro a otro) + denoiser
c.samples = opc['--muestras']
c.use_adaptive_sampling = False
c.use_denoising = True
r.use_persistent_data = True                  # la escena queda preparada entre cuadros
if opc['--desde']:
    escena.frame_start = opc['--desde']
if opc['--hasta']:
    escena.frame_end = opc['--hasta']
carpeta = os.path.join(os.path.dirname(bpy.data.filepath), 'renders', 'recorrido_saag')
os.makedirs(carpeta, exist_ok=True)
for nombre in os.listdir(carpeta):           # cuadro que quedó a medias en una corrida cortada
    ruta = os.path.join(carpeta, nombre)
    if nombre.startswith('cuadro_') and os.path.getsize(ruta) == 0:
        os.remove(ruta)
r.filepath = os.path.join(carpeta, 'cuadro_')
r.image_settings.file_format = 'PNG'; r.image_settings.color_depth = '8'
r.use_file_extension = True
r.use_overwrite = False
r.use_placeholder = True
print(f'Recorrido SAAG: cuadros {escena.frame_start}-{escena.frame_end}, {r.resolution_x}x{r.resolution_y} '
      f'al {r.resolution_percentage} %, {c.samples} muestras')
bpy.ops.render.render(animation=True)

ultimo = escena.frame_end
faltan = [f for f in range(1, ultimo + 1) if not os.path.exists(os.path.join(carpeta, f'cuadro_{f:04d}.png'))
          or os.path.getsize(os.path.join(carpeta, f'cuadro_{f:04d}.png')) == 0]
ffmpeg = shutil.which('ffmpeg')
salida = os.path.join(os.path.dirname(carpeta), 'recorrido_stands_saag.mp4')
if faltan:
    print('Faltan', len(faltan), 'cuadros; vuelva a correr el recorrido para completarlos.')
elif not ffmpeg:
    print('No se encontró ffmpeg: los cuadros están en', carpeta)
else:
    subprocess.run([ffmpeg, '-y', '-framerate', str(escena.render.fps), '-i', os.path.join(carpeta, 'cuadro_%04d.png'),
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', salida],
                   check=True)
    print('Video listo:', salida)
