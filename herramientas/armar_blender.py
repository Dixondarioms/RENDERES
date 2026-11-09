"""Arma la escena del render en Blender a partir de la exportación del visor 3D.

Uso (desde la carpeta del proyecto):
  blender.exe -b -P herramientas/armar_blender.py -- [--previas]

Lee blender/escena.glb y blender/escena.json, configura cielo, sol, materiales, cámaras y
render, y guarda blender/feria.blend. Con --previas genera imágenes rápidas de cada vista.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DIR_B = os.path.join(RAIZ, 'blender')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
DATOS = json.load(open(os.path.join(DIR_B, 'escena.json'), encoding='utf-8'))


def a_blender(v):
    """three.js (Y arriba) -> Blender (Z arriba)."""
    x, y, z = v
    return Vector((x, -z, y))


# ---------------------------------------------------------------- escena limpia + importación
bpy.ops.wm.read_factory_settings(use_empty=True)
escena = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=os.path.join(DIR_B, 'escena.glb'))
print('Objetos importados:', len(bpy.data.objects))

# Quitar las luces importadas (las pone el visor); las reemplazamos por sol + cielo reales
for ob in list(bpy.data.objects):
    if ob.type == 'LIGHT' and ob.data.type in ('SUN', 'AREA'):
        bpy.data.objects.remove(ob, do_unlink=True)
for ob in bpy.data.objects:   # luces interiores del hangar más suaves
    if ob.type == 'LIGHT':
        ob.data.energy = min(ob.data.energy, 800)

# ---------------------------------------------------------------- colores por vértice (terreno)
for ob in bpy.data.objects:
    if ob.type != 'MESH' or not ob.data.color_attributes:
        continue
    nombre_attr = ob.data.color_attributes[0].name
    for ranura in ob.material_slots:
        m = ranura.material
        if not m or not m.use_nodes:
            continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf or any(n.type in ('VERTEX_COLOR', 'ATTRIBUTE') for n in m.node_tree.nodes):
            continue
        nt = m.node_tree
        attr = nt.nodes.new('ShaderNodeVertexColor'); attr.layer_name = nombre_attr
        mezcla = nt.nodes.new('ShaderNodeMix'); mezcla.data_type = 'RGBA'; mezcla.blend_type = 'MULTIPLY'
        mezcla.inputs['Factor'].default_value = 1.0
        entrada = bsdf.inputs['Base Color']
        if entrada.links:
            nt.links.new(entrada.links[0].from_socket, mezcla.inputs['A'])
        else:
            mezcla.inputs['A'].default_value = entrada.default_value
        nt.links.new(attr.outputs['Color'], mezcla.inputs['B'])
        nt.links.new(mezcla.outputs['Result'], entrada)

# ---------------------------------------------------------------- mejoras de pisos, edificios y árboles
exec(open(os.path.join(RAIZ, 'herramientas', 'mejoras_blender.py'), encoding='utf-8').read())
aplicar_todo()

# ---------------------------------------------------------------- sol
sol_dir = a_blender(DATOS['sol']).normalized()
datos_sol = bpy.data.lights.new('Sol', 'SUN')
datos_sol.energy = 4.0
datos_sol.angle = math.radians(0.6)
datos_sol.color = (1.0, 0.96, 0.9)
sol = bpy.data.objects.new('Sol', datos_sol)
escena.collection.objects.link(sol)
sol.rotation_euler = (-sol_dir).to_track_quat('-Z', 'Y').to_euler()

# ---------------------------------------------------------------- cielo HDR alineado con el sol
mundo = bpy.data.worlds.new('Cielo'); escena.world = mundo; mundo.use_nodes = True
nt = mundo.node_tree; nt.nodes.clear()
coord = nt.nodes.new('ShaderNodeTexCoord'); mapeo = nt.nodes.new('ShaderNodeMapping')
amb = nt.nodes.new('ShaderNodeTexEnvironment'); fondo = nt.nodes.new('ShaderNodeBackground'); salida = nt.nodes.new('ShaderNodeOutputWorld')
amb.image = bpy.data.images.load(os.path.join(RAIZ, 'assets', 'cielo', 'cielo_2k.hdr'))
nt.links.new(coord.outputs['Generated'], mapeo.inputs['Vector'])
nt.links.new(mapeo.outputs['Vector'], amb.inputs['Vector'])
nt.links.new(amb.outputs['Color'], fondo.inputs['Color'])
nt.links.new(fondo.outputs['Background'], salida.inputs['Surface'])
fondo.inputs['Strength'].default_value = 1.0

# columna del sol en el HDR -> giro sobre Z para que el sol del cielo coincida con la luz
img = amb.image
w, h = img.size
px = np.empty(w * h * 4, dtype=np.float32); img.pixels.foreach_get(px)
lum = px.reshape(h, w, 4)[..., :3].sum(axis=2)
fila, col = np.unravel_index(np.argmax(lum), lum.shape)
u = (col + 0.5) / w
phi_cielo = (0.5 - u) * 2 * math.pi            # convención equirectangular de Blender
phi_sol = math.atan2(sol_dir.y, sol_dir.x)


def prueba_giro(alfa):
    """Renderiza el cielo con una cámara apuntando al sol y mide qué tan centrado queda el brillo."""
    mapeo.inputs['Rotation'].default_value = (0, 0, alfa)
    cam_d = bpy.data.cameras.new('prueba'); cam_d.angle = math.radians(70)
    cam = bpy.data.objects.new('prueba', cam_d); escena.collection.objects.link(cam)
    cam.rotation_euler = sol_dir.to_track_quat('-Z', 'Y').to_euler(); cam.location = (0, 0, 0)
    escena.camera = cam
    ocultos = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render]
    for o in ocultos: o.hide_render = True
    sol.hide_render = True
    r = escena.render; r.engine = 'CYCLES'; escena.cycles.samples = 1; escena.cycles.use_denoising = False
    r.resolution_x, r.resolution_y, r.resolution_percentage = 48, 48, 100
    ruta = os.path.join(DIR_B, '_prueba_cielo.exr'); r.image_settings.file_format = 'OPEN_EXR'; r.filepath = ruta
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(ruta); p = np.empty(48 * 48 * 4, dtype=np.float32); im.pixels.foreach_get(p)
    l = p.reshape(48, 48, 4)[..., :3].sum(axis=2); y, x = np.unravel_index(np.argmax(l), l.shape)
    bpy.data.images.remove(im); os.remove(ruta)
    for o in ocultos: o.hide_render = False
    sol.hide_render = False
    bpy.data.objects.remove(cam, do_unlink=True)
    return math.hypot(x - 23.5, y - 23.5)


candidatos = [phi_cielo - phi_sol, phi_sol - phi_cielo, phi_cielo - phi_sol + math.pi, phi_sol - phi_cielo + math.pi]
mejor = min(candidatos, key=prueba_giro)
mapeo.inputs['Rotation'].default_value = (0, 0, mejor)
print('Giro del cielo:', round(math.degrees(mejor), 1), 'grados')


# ---------------------------------------------------------------- sol físico: se saca del HDR y se pasa a la lámpara
# El HDR de Poly Haven trae el sol sin recortar (≈75 000 en 8k). Con la lámpara encima había DOS soles.
# Se mide la irradiancia del disco solar del HDR, se le da esa misma fuerza y color a la lámpara y se borra
# el sol del HDR de iluminación. Así la relación sol/cielo (lo oscuras y azules que salen las sombras) es la real.
def separar_sol(img):
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32); img.pixels.foreach_get(px)
    p = px.reshape(h, w, 4)
    lum = p[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    umbral = max(40.0, float(np.percentile(lum, 99.9)) * 4)
    sol_px = lum > umbral
    filas = np.nonzero(sol_px)[0]
    lat = (filas + 0.5) / h * math.pi - math.pi / 2            # filas de Blender van de abajo (−90°) hacia arriba
    omega = (2 * math.pi / w) * (math.pi / h) * np.cos(lat)    # ángulo sólido de cada píxel
    E = (p[..., :3][sol_px] * omega[:, None]).sum(axis=0)      # irradiancia del sol (W/m², RGB)
    # se reemplaza el disco por el cielo de alrededor (anillo justo afuera del umbral)
    yy, xx = np.nonzero(sol_px)
    cy, cx = int(yy.mean()), int(xx.mean()); r = int(max(np.ptp(yy), np.ptp(xx)) / 2) + 3
    anillo = p[max(0, cy - 2 * r):cy + 2 * r + 1, max(0, cx - 2 * r):cx + 2 * r + 1, :3].reshape(-1, 3)
    al = anillo @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    relleno = np.median(anillo[al < umbral], axis=0)
    p[..., :3][sol_px] = relleno
    limpio = bpy.data.images.new('Cielo iluminacion', w, h, float_buffer=True, alpha=False)
    limpio.pixels.foreach_set(p.ravel())
    ruta = os.path.join(DIR_B, '_cielo_iluminacion.exr')
    limpio.filepath_raw = ruta; limpio.file_format = 'OPEN_EXR'; limpio.save()
    limpio.source = 'FILE'; limpio.reload()
    lum_E = float(E @ np.array([0.2126, 0.7152, 0.0722]))
    print(f'Sol del HDR: {sol_px.sum()} px, irradiancia {lum_E:.1f} W/m², color {tuple(round(float(c / lum_E), 3) for c in E)}')
    return limpio, lum_E, tuple(float(c / max(E)) for c in E)


cielo_luz, irradiancia, color_sol = separar_sol(amb.image)
amb.image = cielo_luz
datos_sol.energy = irradiancia
datos_sol.color = color_sol
datos_sol.angle = math.radians(0.53)          # diámetro real del disco solar
amb.interpolation = 'Smart'

# Fondo de cámara: el mismo cielo en 8k (el 2k se ve borroso en la panorámica). Solo para rayos de cámara,
# así no cambia la iluminación ni aparece un segundo sol en los reflejos.
ruta_8k = os.path.join(RAIZ, 'assets', 'cielo', 'cielo_8k_fondo.exr')
if os.path.exists(ruta_8k):
    amb8 = nt.nodes.new('ShaderNodeTexEnvironment'); amb8.image = bpy.data.images.load(ruta_8k); amb8.interpolation = 'Smart'
    nt.links.new(mapeo.outputs['Vector'], amb8.inputs['Vector'])
    camino = nt.nodes.new('ShaderNodeLightPath')
    mezcla_cielo = nt.nodes.new('ShaderNodeMix'); mezcla_cielo.data_type = 'RGBA'
    nt.links.new(camino.outputs['Is Camera Ray'], mezcla_cielo.inputs['Factor'])
    nt.links.new(amb.outputs['Color'], mezcla_cielo.inputs['A']); nt.links.new(amb8.outputs['Color'], mezcla_cielo.inputs['B'])
    nt.links.new(mezcla_cielo.outputs['Result'], fondo.inputs['Color'])
mundo.cycles.sampling_method = 'MANUAL'; mundo.cycles.sample_map_resolution = 2048

# ---------------------------------------------------------------- cámaras de las vistas
coleccion = bpy.data.collections.new('Camaras'); escena.collection.children.link(coleccion)
for nombre, v in DATOS['vistas'].items():
    cd = bpy.data.cameras.new(nombre); cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(DATOS.get('fov', 45))
    cd.clip_start = 0.3; cd.clip_end = 60000
    cam = bpy.data.objects.new('Cam_' + nombre, cd); coleccion.objects.link(cam)
    pos, mira = a_blender(v['pos']), a_blender(v['mira'])
    cam.location = pos
    cam.rotation_euler = (mira - pos).to_track_quat('-Z', 'Y').to_euler()
escena.camera = bpy.data.objects.get('Cam_hangar') or bpy.data.objects[0]

# ---------------------------------------------------------------- realismo: terreno, bruma, vegetación, luces, cámara
exec(open(os.path.join(RAIZ, 'herramientas', 'realismo_blender.py'), encoding='utf-8').read())
exec(open(os.path.join(RAIZ, 'herramientas', 'acto_blender.py'), encoding='utf-8').read())
aplicar_realismo()

# ---------------------------------------------------------------- personas y sillas
# La tribuna, las gradas, sus sillas y las personas del visor web se reemplazan en acto_blender.py
# (tarima protocolar con toldo, autoridades sentadas y la parada con uniforme verde pixelado).

# ---------------------------------------------------------------- render
r = escena.render
r.engine = 'CYCLES'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usar_gpu import activar_gpu   # noqa: E402
activar_gpu(escena)
c = escena.cycles
c.samples = 512
c.use_adaptive_sampling = True
c.adaptive_threshold = 0.015
c.use_denoising = True
c.denoiser = 'OPENIMAGEDENOISE'
c.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
c.denoising_prefilter = 'ACCURATE'
c.max_bounces = 12
c.diffuse_bounces = 5
c.glossy_bounces = 6
c.transmission_bounces = 10
c.volume_bounces = 0
c.transparent_max_bounces = 48           # hojas con recorte alfa: con pocos rebotes se ven manchas negras
c.sample_clamp_indirect = 12             # quita "luciérnagas" sin apagar los reflejos
c.blur_glossy = 0.5
c.caustics_reflective = False
c.caustics_refractive = False
c.use_light_tree = True
r.film_transparent = False
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
r.image_settings.file_format = 'PNG'
r.image_settings.color_depth = '16'
escena.view_settings.view_transform = 'AgX'
escena.view_settings.look = 'AgX - Medium High Contrast'
escena.view_settings.exposure = EXPOSICION_BASE
postproceso(escena)
os.makedirs(os.path.join(DIR_B, 'renders'), exist_ok=True)
r.filepath = os.path.join(DIR_B, 'renders', 'render_')

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(DIR_B, 'feria.blend'))
print('Guardado', os.path.join(DIR_B, 'feria.blend'))

# ---------------------------------------------------------------- imágenes rápidas de prueba
if '--previas' in ARGS:
    escena.cycles.samples = 24
    escena.cycles.adaptive_threshold = 0.1
    r.resolution_percentage = 50
    for nombre in ['hangar', 'feria', 'acto', 'tucanos', 'hercules']:
        cam = bpy.data.objects.get('Cam_' + nombre)
        if not cam:
            continue
        escena.camera = cam
        escena.view_settings.exposure = EXPOSICION_BASE + cam.get('exposicion', 0.0)
        r.filepath = os.path.join(DIR_B, 'renders', f'previa_{nombre}.png')
        bpy.ops.render.render(write_still=True)
        print('Previa', nombre, 'lista')
