"""Video del recorrido por los stands de la AMB en 2K (2560 x 1440, 30 cuadros por segundo).

Uso (desde la carpeta del proyecto):
  blender.exe -b blender/feria.blend -P herramientas/recorrido.py -- [--muestras N] [--desde F] [--hasta F] [--escala P]

Los cuadros quedan en blender/renders/recorrido/cuadro_0001.png ... y al final se arma
blender/renders/recorrido_stands_2K.mp4 con ffmpeg (si está instalado).
Se puede cortar y volver a correr: los cuadros ya hechos se saltan (sigue desde donde quedó).
"""
import os
import shutil
import subprocess
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usar_gpu import activar_gpu   # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
opc = {'--muestras': 96, '--desde': None, '--hasta': None, '--escala': 100}
i = 0
while i < len(ARGS):
    if ARGS[i] in opc:
        opc[ARGS[i]] = int(ARGS[i + 1]); i += 2
    else:
        i += 1

escena = bpy.context.scene
r, c = escena.render, escena.cycles
cam = bpy.data.objects.get('Recorrido stands')
if not cam:
    sys.exit('No está la cámara "Recorrido stands": vuelva a armar la escena con Armar_escena.bat')
activar_gpu(escena)
escena.camera = cam
r.resolution_x, r.resolution_y = tuple(cam.get('resolucion', (2560, 1440)))
r.resolution_percentage = opc['--escala']
escena.view_settings.exposure = escena.get('exposicion_base', 0.0) + cam.get('exposicion', 0.0)
# Video de interior: muestras fijas (sin adaptativo, que en interiores deja manchas) + denoiser en la CPU.
c.samples = opc['--muestras']
c.use_adaptive_sampling = False
c.use_denoising = True
c.denoising_use_gpu = False
# La escena (BVH, texturas) queda en la tarjeta entre cuadros: sin esto cada cuadro la vuelve a preparar.
r.use_persistent_data = True
# Desde adentro del hangar no se ve el exterior: se oculta (libera memoria de la tarjeta).
for n in ('Arboleda de fondo', 'Grama 3D', 'relieve', 'lago'):
    o = bpy.data.objects.get(n)
    if o:
        o.hide_render = True
for nc in ('Arboles', 'Palmas'):
    col = bpy.data.collections.get(nc)
    for o in (col.all_objects if col else []):
        if o:                                       # la lista puede traer huecos de objetos ya borrados
            o.hide_render = True
if opc['--desde']:
    escena.frame_start = opc['--desde']
if opc['--hasta']:
    escena.frame_end = opc['--hasta']
carpeta = os.path.join(os.path.dirname(bpy.data.filepath), 'renders', 'recorrido')
os.makedirs(carpeta, exist_ok=True)
# Si una corrida anterior se cortó, el cuadro que estaba haciendo quedó como archivo vacío (marcador): se borra
# para que se vuelva a hacer (si no, Blender lo daría por terminado).
for nombre in os.listdir(carpeta):
    ruta = os.path.join(carpeta, nombre)
    if nombre.startswith('cuadro_') and os.path.getsize(ruta) == 0:
        os.remove(ruta)
r.filepath = os.path.join(carpeta, 'cuadro_')
r.image_settings.file_format = 'PNG'; r.image_settings.color_depth = '8'
r.use_file_extension = True
r.use_overwrite = False          # los cuadros ya hechos no se repiten
r.use_placeholder = True         # marca el cuadro en curso (permite varias PCs a la vez sobre la misma carpeta)
print(f'Recorrido: cuadros {escena.frame_start}-{escena.frame_end}, {r.resolution_x}x{r.resolution_y} '
      f'al {r.resolution_percentage} %, {c.samples} muestras')
bpy.ops.render.render(animation=True)

# Video MP4 (H.264) con ffmpeg, solo si están todos los cuadros
faltan = [f for f in range(1, escena.frame_end + 1) if not os.path.exists(os.path.join(carpeta, f'cuadro_{f:04d}.png'))
          or os.path.getsize(os.path.join(carpeta, f'cuadro_{f:04d}.png')) == 0]
ffmpeg = shutil.which('ffmpeg')
salida = os.path.join(os.path.dirname(carpeta), 'recorrido_stands_2K.mp4')
if faltan:
    print('Faltan', len(faltan), 'cuadros; vuelva a correr el recorrido para completarlos.')
elif not ffmpeg:
    print('No se encontró ffmpeg: los cuadros están en', carpeta, '(se pueden unir con cualquier editor de video).')
else:
    subprocess.run([ffmpeg, '-y', '-framerate', str(escena.render.fps), '-i', os.path.join(carpeta, 'cuadro_%04d.png'),
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', salida],
                   check=True)
    print('Video listo:', salida)
