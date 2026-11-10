"""Escena aparte con un solo edificio (por ahora el edificio blanco del SAAG, hacia la vía), para trabajarlo
sin cargar todo el render. El galpón del techo rojo (stands) va detrás y lo trabaja la otra PC.
Usa muy poca memoria: solo el edificio, un piso de grama, la acera, la vía, el sol y el cielo.

Uso (desde la carpeta del proyecto):
  blender.exe -b -P herramientas/escena_edificio.py -- [vista ...] [--muestras N] [--escala P] [--sin-render]

Guarda blender/edificio_saag.blend y las imágenes en blender/renders/saag_<vista>.png.
Vistas: via (como las fotos desde la vía), entrada, izquierda, esquina, techo, y del hangar:
hangar, hangar_centro, hangar_canasta, hangar_lavamanos, hangar_afuera, stands; y las de cada stand (stand_<clave>, frente_<clave>,
lateral_<clave>, detalle_<clave>; clave = igla, juego, mecanismo, ultraligero). --sin-stands: el hangar vacío. Sin vistas, todas.
Por defecto son imágenes rápidas (32 muestras al 50 %); para la final: --muestras 512 --escala 100.
El mismo edificio (herramientas/edificio_saag.py) es el que usa el render principal.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_B = os.path.join(RAIZ, 'blender')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
muestras, escala, vistas, renderizar = 32, 50, [], True
i = 0
while i < len(ARGS):
    if ARGS[i] == '--muestras':
        muestras = int(ARGS[i + 1]); i += 2
    elif ARGS[i] == '--escala':
        escala = int(ARGS[i + 1]); i += 2
    elif ARGS[i] == '--sin-render':
        renderizar = False; i += 1
    elif ARGS[i] == '--sin-stands':
        i += 1
    else:
        vistas.append(ARGS[i]); i += 1

bpy.ops.wm.read_factory_settings(use_empty=True)
escena = bpy.context.scene
DATOS = json.load(open(os.path.join(DIR_B, 'escena.json'), encoding='utf-8'))


def a_blender(v):
    x, y, z = v
    return Vector((x, -z, y))


exec(open(os.path.join(RAIZ, 'herramientas', 'mejoras_blender.py'), encoding='utf-8').read())
exec(open(os.path.join(RAIZ, 'herramientas', 'edificio_saag.py'), encoding='utf-8').read())
exec(open(os.path.join(RAIZ, 'herramientas', 'galpon_saag.py'), encoding='utf-8').read())

# giro del SAAG en el plano (EDIFICIOS de mejoras_blender): la escena se arma con el edificio derecho
# y se gira el sol al revés, así la luz cae igual que en el render principal.
datos_saag = next(d for d in EDIFICIOS if d['id'] == 'saag')
giro = -math.radians(datos_saag['ang'])

# ---------------------------------------------------------------- edificio
col = bpy.data.collections.new('Edificio'); escena.collection.children.link(col)
construir_saag('saag_anexo', col)
construir_entorno_saag('saag_entorno', col)
construir_galpon('saag_galpon', col)
# stands de la AMB con su decoración: se arman con el código del render principal (realismo_blender.py),
# cargado en un espacio aparte para que sus funciones no reemplacen las de esta escena
ns = dict(globals())
exec(open(os.path.join(RAIZ, 'herramientas', 'realismo_blender.py'), encoding='utf-8').read(), ns)
if '--sin-stands' not in ARGS:
    exec(open(os.path.join(RAIZ, 'herramientas', 'stands_saag.py'), encoding='utf-8').read(), ns)
    col_st = bpy.data.collections.new('Stands AMB SAAG'); escena.collection.children.link(col_st)
    ns['colocar_stands_saag'](col_st)

# ---------------------------------------------------------------- piso: grama, acera, caminería y la vía
def losa(nombre, x0, x1, y0, y1, z, mat):
    me = bpy.data.meshes.new(nombre)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    me.materials.append(mat)
    ob = bpy.data.objects.new(nombre, me); escena.collection.objects.link(ob)
    return ob


L, W = SAAG['L'], SAAG['W']
losa('Grama', -150, 150, -150, 150, 0.0, mat_grama())
fy = -W / 2 - SAAG['fondo']                         # fachada de las fotos
losa('Acera', -L / 2 - 8, L / 2 + 3, fy - 3, W / 2 + 3, 0.02, mat_simple('Acera', (0.6, 0.58, 0.55), 0.85))
x_puerta = -L / 2 + SAAG['puerta_x'] * L
losa('Caminería', x_puerta - 0.9, x_puerta + 0.9, -40, fy - 3, 0.025, mat_simple('Acera', (0.6, 0.58, 0.55), 0.85))
losa('Estacionamiento', -60, 60, -46, -40, 0.03, mat_asfalto())
losa('Via', -150, 150, -54, -46, 0.03, mat_asfalto())
losa('Plataforma', -60, 60, -W / 2, 60, 0.025, mat_concreto())
# paisaje: grama realista, mangos y setos (solo en esta escena; el render principal tiene el suyo)
exec(open(os.path.join(RAIZ, 'herramientas', 'entorno_escena_saag.py'), encoding='utf-8').read())
paisaje_saag(ns)

# ---------------------------------------------------------------- sol y cielo (igual que armar_blender.py)
sol_dir = (Matrix.Rotation(-giro, 3, 'Z') @ a_blender(DATOS['sol'])).normalized()
datos_sol = bpy.data.lights.new('Sol', 'SUN')
sol = bpy.data.objects.new('Sol', datos_sol); escena.collection.objects.link(sol)
sol.rotation_euler = (-sol_dir).to_track_quat('-Z', 'Y').to_euler()

mundo = bpy.data.worlds.new('Cielo'); escena.world = mundo; mundo.use_nodes = True
nt = mundo.node_tree; nt.nodes.clear()
amb = nt.nodes.new('ShaderNodeTexEnvironment'); fondo = nt.nodes.new('ShaderNodeBackground')
salida = nt.nodes.new('ShaderNodeOutputWorld')
amb.image = bpy.data.images.load(os.path.join(RAIZ, 'assets', 'cielo', 'cielo_2k.hdr'))
nt.links.new(amb.outputs['Color'], fondo.inputs['Color']); nt.links.new(fondo.outputs['Background'], salida.inputs['Surface'])


def separar_sol(img):
    """Mide el sol del HDR (irradiancia y color), lo pasa a la lámpara y lo borra del cielo."""
    w, h = img.size
    p = np.empty(w * h * 4, dtype=np.float32); img.pixels.foreach_get(p); p = p.reshape(h, w, 4)
    luma = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    lum = p[..., :3] @ luma
    umbral = max(40.0, float(np.percentile(lum, 99.9)) * 4)
    sol_px = lum > umbral
    filas = np.nonzero(sol_px)[0]
    lat = (filas + 0.5) / h * math.pi - math.pi / 2
    omega = (2 * math.pi / w) * (math.pi / h) * np.cos(lat)
    E = (p[..., :3][sol_px] * omega[:, None]).sum(axis=0)
    yy, xx = np.nonzero(sol_px)
    cy, cx = int(yy.mean()), int(xx.mean()); r = int(max(np.ptp(yy), np.ptp(xx)) / 2) + 3
    anillo = p[max(0, cy - 2 * r):cy + 2 * r + 1, max(0, cx - 2 * r):cx + 2 * r + 1, :3].reshape(-1, 3)
    p[..., :3][sol_px] = np.median(anillo[(anillo @ luma) < umbral], axis=0)
    limpio = bpy.data.images.new('Cielo iluminacion', w, h, float_buffer=True, alpha=False)
    limpio.pixels.foreach_set(p.ravel()); limpio.pack()
    lum_E = float(E @ luma)
    return limpio, lum_E, tuple(float(c / max(E)) for c in E)


amb.image, irradiancia, color_sol = separar_sol(amb.image)
datos_sol.energy, datos_sol.color, datos_sol.angle = irradiancia, color_sol, math.radians(0.53)
# misma exposición que el render principal (realismo_blender.calibrar_exposicion)
exposicion = round(math.log2(0.36 / (0.35 * irradiancia * 0.79 * 1.3 / math.pi)), 2)

# ---------------------------------------------------------------- cámaras
CAMARAS = {
    'via':     ((-6, -50, 1.6), (-3, -15, 3.6), 62),    # como las fotos desde el carro (la vía está a ~46 m)
    'entrada': ((-27, -32, 1.7), (-11, -20, 2.4), 55),
    'esquina': ((40, -60, 18), (0, -13, 3), 45),
    'izquierda': ((-30, -16, 2.0), (-16, -10, 3.5), 70),   # poste, planta y tanque
    'techo':   ((0, -55, 60), (0, -13, 2), 50),
    # hangar (galpón del techo rojo): +EV porque adentro hay mucha menos luz
    # (visto desde la pista, la izquierda del hangar es +X y la derecha -X)
    'hangar':           ((14.5, 7.0, 1.7), (-3, -7, 3.6), 95, 2.5),    # desde la esquina izquierda, lado de la pista
    'hangar_centro':    ((3.5, 10.5, 1.7), (1.5, -7.5, 3.8), 85, 2.3),
    'hangar_canasta':   ((8.25, 1.6, 1.6), (15.0, 2.5, 3.1), 75, 2.5),  # pared izquierda: canasta de baloncesto
    'hangar_lavamanos': ((-6.0, 1.8, 2.2), (-16.5, -0.6, 1.4), 80, 2.5),  # pared derecha: lavamanos y ducha
    'canasta':          ((11.0, 2.9, 2.6), (14.6, 2.5, 3.1), 50, 2.5),   # la canasta de cerca
    'extintores':       ((-2.4, 5.6, 1.6), (0.0, 2.5, 0.9), 45, 2.5),   # extintores de la columna del medio
    'hangar_afuera':  ((22, 42, 7), (0, 0, 3.5), 55, 0.0),            # desde la plataforma
    'stands':         ((0.0, 26, 4.5), (0, -2, 2.0), 70, 1.2),       # los 4 stands desde la plataforma
}
for nombre, (pos, mira, fov, *ev) in CAMARAS.items():
    cd = bpy.data.cameras.new('Cam_' + nombre); cd.sensor_fit = 'HORIZONTAL'; cd.angle_x = math.radians(fov)
    cd.clip_start = 0.1; cd.clip_end = 2000
    cam = bpy.data.objects.new('Cam_' + nombre, cd); escena.collection.objects.link(cam)
    cam.location = pos
    cam.rotation_euler = (Vector(mira) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
    cam['exposicion'] = ev[0] if ev else 0.0
escena.camera = bpy.data.objects['Cam_via']

# ---------------------------------------------------------------- render
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usar_gpu import activar_gpu   # noqa: E402
r = escena.render; r.engine = 'CYCLES'
activar_gpu(escena)
c = escena.cycles
c.samples = muestras; c.use_adaptive_sampling = True; c.adaptive_threshold = 0.015 if muestras >= 256 else 0.05
c.use_denoising = True; c.denoiser = 'OPENIMAGEDENOISE'
c.max_bounces = 12; c.diffuse_bounces = 5; c.glossy_bounces = 6; c.sample_clamp_indirect = 12
c.caustics_reflective = False; c.caustics_refractive = False
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, escala
r.image_settings.file_format = 'PNG'
escena.view_settings.view_transform = 'AgX'
escena.view_settings.look = 'AgX - Medium High Contrast'
escena.view_settings.exposure = exposicion
escena['exposicion_base'] = exposicion
ns['postproceso'](escena)        # composición de lente del render principal: brillo suave, aberración leve y viñeta
os.makedirs(os.path.join(DIR_B, 'renders'), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(DIR_B, 'edificio_saag.blend'))
print('Guardado', os.path.join(DIR_B, 'edificio_saag.blend'))

if renderizar:
    for nombre in (vistas or CAMARAS):
        cam = bpy.data.objects.get('Cam_' + nombre)
        if not cam:
            print('No existe la vista', nombre); continue
        escena.camera = cam
        escena.view_settings.exposure = exposicion + cam.get('exposicion', 0.0)
        r.filepath = os.path.join(DIR_B, 'renders', f'saag_{nombre}.png')
        bpy.ops.render.render(write_still=True)
        print('Lista la vista', nombre)
