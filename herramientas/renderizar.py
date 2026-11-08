"""Renders finales en alta calidad desde blender/feria.blend, usando la tarjeta gráfica si hay.

Uso (desde la carpeta del proyecto):
  blender.exe -b blender/feria.blend -P herramientas/renderizar.py -- [vista ...] [--muestras N] [--escala P]

Vistas: los nombres de las cámaras sin 'Cam_' (panoramica, aerea, feria, acto, tribuna, hangar, tucanos,
hercules, carretera, porton, proyectos, planta). Sin vistas, renderiza todas.
Las imágenes quedan en blender/renders/render_<vista>.png
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usar_gpu import activar_gpu   # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
muestras, escala, vistas = 256, 100, []
i = 0
while i < len(ARGS):
    if ARGS[i] == '--muestras':
        muestras = int(ARGS[i + 1]); i += 2
    elif ARGS[i] == '--escala':
        escala = int(ARGS[i + 1]); i += 2
    else:
        vistas.append(ARGS[i]); i += 1

escena = bpy.context.scene
r = escena.render
activar_gpu(escena)
escena.cycles.samples = muestras
escena.cycles.adaptive_threshold = 0.02
r.resolution_percentage = escala
camaras = sorted((o for o in bpy.data.objects if o.type == 'CAMERA' and o.name.startswith('Cam_')), key=lambda o: o.name)
if vistas:
    camaras = [c for c in camaras if c.name[4:] in vistas]
    faltan = set(vistas) - {c.name[4:] for c in camaras}
    if faltan:
        print('No existen estas vistas:', ', '.join(sorted(faltan)))
carpeta = os.path.join(os.path.dirname(bpy.data.filepath), 'renders')
os.makedirs(carpeta, exist_ok=True)
for cam in camaras:
    nombre = cam.name[4:]
    r.resolution_x, r.resolution_y = tuple(cam.get('resolucion', (1920, 1080)))
    escena.camera = cam
    r.filepath = os.path.join(carpeta, f'render_{nombre}.png')
    print('Renderizando', nombre, f'{r.resolution_x}x{r.resolution_y}', muestras, 'muestras')
    bpy.ops.render.render(write_still=True)
print('Listo. Imágenes en', carpeta)
