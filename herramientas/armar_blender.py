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

# ---------------------------------------------------------------- personas y sillas
def lineal(hexa):
    """Color sRGB '#rrggbb' -> RGBA lineal (para el color de objeto)."""
    c = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c) + (1.0,)


def nodo(nt, tipo, **kw):
    n = nt.nodes.new(tipo)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def matematica(nt, op, a, b=None, clamp=False):
    n = nodo(nt, 'ShaderNodeMath', operation=op, use_clamp=clamp)
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def material_persona(m, tela):
    """tela=True: la ropa toma el color del objeto (uniforme). tela=False: civil, se tiñe suave y se respeta la piel."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = bsdf.inputs['Base Color'].links[0].from_socket if bsdf.inputs['Base Color'].links else None
    info = nodo(nt, 'ShaderNodeObjectInfo')
    if tex is None:
        nt.links.new(info.outputs['Color'], bsdf.inputs['Base Color']); return
    if tela:
        bw = nodo(nt, 'ShaderNodeRGBToBW'); nt.links.new(tex, bw.inputs['Color'])
        f = matematica(nt, 'MULTIPLY_ADD', bw.outputs[0], 1.6); f.node.inputs[2].default_value = 0.4
        mul = nodo(nt, 'ShaderNodeVectorMath', operation='SCALE')
        nt.links.new(info.outputs['Color'], mul.inputs[0]); nt.links.new(f, mul.inputs['Scale'])
        nt.links.new(mul.outputs[0], bsdf.inputs['Base Color'])
    else:
        sep = nodo(nt, 'ShaderNodeSeparateColor'); nt.links.new(tex, sep.inputs['Color'])
        R, G, B = sep.outputs[0], sep.outputs[1], sep.outputs[2]
        a = matematica(nt, 'MULTIPLY', matematica(nt, 'SUBTRACT', matematica(nt, 'SUBTRACT', R, G), 0.04), 20, clamp=True)
        b = matematica(nt, 'MULTIPLY', matematica(nt, 'SUBTRACT', matematica(nt, 'SUBTRACT', G, B), 0.015), 28, clamp=True)
        c = matematica(nt, 'SUBTRACT', 1.0, matematica(nt, 'MULTIPLY', matematica(nt, 'SUBTRACT', matematica(nt, 'SUBTRACT', R, B), 0.3), 10, clamp=True))
        piel = matematica(nt, 'MULTIPLY', matematica(nt, 'MULTIPLY', a, b), c)
        suave = nodo(nt, 'ShaderNodeMix', data_type='RGBA'); suave.inputs['Factor'].default_value = 0.55
        nt.links.new(info.outputs['Color'], suave.inputs['A']); suave.inputs['B'].default_value = (1, 1, 1, 1)
        teñido = nodo(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY'); teñido.inputs['Factor'].default_value = 1
        nt.links.new(tex, teñido.inputs['A']); nt.links.new(suave.outputs['Result'], teñido.inputs['B'])
        final = nodo(nt, 'ShaderNodeMix', data_type='RGBA'); nt.links.new(piel, final.inputs['Factor'])
        nt.links.new(teñido.outputs['Result'], final.inputs['A']); nt.links.new(tex, final.inputs['B'])
        nt.links.new(final.outputs['Result'], bsdf.inputs['Base Color'])


ruta_pers = os.path.join(DIR_B, 'personas.json')
if os.path.exists(ruta_pers):
    PD = json.load(open(ruta_pers, encoding='utf-8'))
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(DIR_B, 'personas_modelos.glb'))
    modelos = {}
    for ob in set(bpy.data.objects) - antes:
        if ob.type == 'MESH' and ob.name.split('.')[0] in ('soldado', 'soldadoS', 'civil', 'civilS'):
            modelos[ob.name.split('.')[0]] = ob.data
            for ranura in ob.material_slots:
                material_persona(ranura.material, ob.name.startswith('soldado'))
        bpy.data.objects.remove(ob, do_unlink=True)
    col_p = bpy.data.collections.new('Personas'); escena.collection.children.link(col_p)
    for i, d in enumerate(PD['personas'] if '--personas' in ARGS else []):
        civil = d['civ'] and d['s']
        clave = ('civil' if civil else 'soldado') + ('S' if d['s'] else '')
        ob = bpy.data.objects.new(f'Persona_{i:04d}', modelos[clave]); col_p.objects.link(ob)
        ob.location = a_blender(d['p'])
        ob.rotation_euler = (0, 0, math.atan2(-d['d'][1], d['d'][0]))
        ob.color = lineal(d['c'])

    # Silla plástica con respaldo (se tiñe con el color de cada una)
    import bmesh
    bm = bmesh.new()
    def bloque(cx, cy, cz, sx, sy, sz):
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=r['verts'])
        bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=r['verts'])
    bloque(0, 0, 0.44, 0.44, 0.44, 0.04)                 # asiento
    bloque(-0.2, 0, 0.68, 0.04, 0.44, 0.44)              # respaldo
    for x in (-0.19, 0.19):
        for y in (-0.19, 0.19):
            bloque(x, y, 0.21, 0.03, 0.03, 0.42)         # patas
    malla_silla = bpy.data.meshes.new('silla'); bm.to_mesh(malla_silla); bm.free()
    ms = bpy.data.materials.new('silla'); ms.use_nodes = True
    b = ms.node_tree.nodes['Principled BSDF']; b.inputs['Roughness'].default_value = 0.45
    info = ms.node_tree.nodes.new('ShaderNodeObjectInfo'); ms.node_tree.links.new(info.outputs['Color'], b.inputs['Base Color'])
    malla_silla.materials.append(ms)
    col_s = bpy.data.collections.new('Sillas'); escena.collection.children.link(col_s)
    for i, d in enumerate(PD['sillas']):
        ob = bpy.data.objects.new(f'Silla_{i:04d}', malla_silla); col_s.objects.link(ob)
        ob.location = a_blender(d['p'])
        ob.rotation_euler = (0, 0, math.atan2(-d['d'][1], d['d'][0]))
        ob.color = lineal(d['c'])
    print('Personas:', len(PD['personas']), ' Sillas:', len(PD['sillas']))

# ---------------------------------------------------------------- render
r = escena.render
r.engine = 'CYCLES'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usar_gpu import activar_gpu   # noqa: E402
activar_gpu(escena)
escena.cycles.samples = 256
escena.cycles.use_adaptive_sampling = True
escena.cycles.adaptive_threshold = 0.02
escena.cycles.use_denoising = True
escena.cycles.max_bounces = 6
escena.cycles.transparent_max_bounces = 16
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
r.image_settings.file_format = 'PNG'
escena.view_settings.view_transform = 'AgX'
escena.view_settings.look = 'AgX - Medium High Contrast'
escena.view_settings.exposure = -0.7
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
        r.filepath = os.path.join(DIR_B, 'renders', f'previa_{nombre}.png')
        bpy.ops.render.render(write_still=True)
        print('Previa', nombre, 'lista')
