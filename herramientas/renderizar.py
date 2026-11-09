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
muestras, escala, vistas = 512, 100, []
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
escena.cycles.adaptive_threshold = 0.015
r.resolution_percentage = escala
base_ev = escena.get('exposicion_base', escena.view_settings.exposure)
camaras = sorted((o for o in bpy.data.objects if o.type == 'CAMERA' and o.name.startswith('Cam_')), key=lambda o: o.name)
if vistas:
    camaras = [c for c in camaras if c.name[4:] in vistas]
    faltan = set(vistas) - {c.name[4:] for c in camaras}
    if faltan:
        print('No existen estas vistas:', ', '.join(sorted(faltan)))
carpeta = os.path.join(os.path.dirname(bpy.data.filepath), 'renders')
os.makedirs(carpeta, exist_ok=True)
# El denoiser en la CPU: en la GPU compite por memoria con la escena (y con otros programas abiertos).
escena.cycles.denoising_use_gpu = False

# Desde adentro del hangar no se ve el exterior: en esas vistas se ocultan la arboleda de fondo, la grama 3D,
# los árboles, las palmas y el relieve (libera más de 1 GB de la tarjeta sin cambiar la imagen).
OCULTAR_ADENTRO = ('Arboleda de fondo', 'Grama 3D', 'relieve', 'lago')
COLECCIONES_AFUERA = ('Arboles', 'Palmas')


def exterior(visible):
    obs = [bpy.data.objects.get(n) for n in OCULTAR_ADENTRO]
    for c in COLECCIONES_AFUERA:
        col = bpy.data.collections.get(c)
        obs += list(col.all_objects) if col else []
    for o in obs:
        if o:
            o.hide_render = not visible


def renderizar():
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        if 'cannot save' in str(e):
            # la imagen ya está hecha, pero el archivo está abierto (p. ej. en el visor de Fotos de Windows)
            alterna = r.filepath.replace('.png', '_2.png')
            bpy.data.images['Render Result'].save_render(alterna)
            print('No se pudo escribir', r.filepath, '(¿abierta en otro programa?) -> guardada como', alterna)
            return
        # memoria de la GPU agotada u otro error del dispositivo: se repite en la CPU
        print('Falló en la tarjeta gráfica (', str(e)[:80], ') -> se repite con el procesador')
        dispositivo, n = escena.cycles.device, escena.cycles.samples
        escena.cycles.device = 'CPU'
        escena.cycles.samples = min(n, 256)            # en el procesador 512 muestras de interior tardan ~20 min
        bpy.ops.render.render(write_still=True)
        escena.cycles.device, escena.cycles.samples = dispositivo, n


def solo_stand(raiz):
    """Vista individual de un stand: oculta los otros stands de la AMB (raiz=None los muestra todos)."""
    col = bpy.data.collections.get('Stands AMB')
    for st in (col.objects if col else []):
        if st and st.name.startswith('Stand ') and st.parent is None:
            ver = raiz is None or st.name == raiz
            for o in [st] + list(st.children_recursive):
                o.hide_render = not ver


for cam in camaras:
    nombre = cam.name[4:]
    solo_stand(cam.get('stand'))
    r.resolution_x, r.resolution_y = tuple(cam.get('resolucion', (1920, 1080)))
    escena.camera = cam
    ev = cam.get('exposicion', 0.0)
    escena.view_settings.exposure = base_ev + ev   # p. ej. el interior del hangar va más abierto
    # El muestreo adaptativo mide el error ANTES de la exposición: en interiores (+4 EV) da por terminado el
    # píxel demasiado pronto y el ruido amplificado sale como manchas "de papel arrugado" tras el denoiser.
    escena.cycles.use_adaptive_sampling = ev <= 0.5
    exterior(ev <= 2.0)        # solo las vistas de interior (+4 EV) no ven el exterior
    r.filepath = os.path.join(carpeta, f'render_{nombre}.png')
    print('Renderizando', nombre, f'{r.resolution_x}x{r.resolution_y}', muestras, 'muestras')
    renderizar()
exterior(True)
solo_stand(None)
print('Listo. Imágenes en', carpeta)
