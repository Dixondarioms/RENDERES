"""Paisaje alrededor del SAAG en la escena aparte (escena_edificio.py), para que las vistas de afuera se vean reales:
grama realista del render principal, mangos frente al edificio (como en las fotos desde la vía) y setos bajos en el
jardín del frente. El render principal tiene su propia vegetación: esto es solo para la escena aparte.

Se ejecuta en el espacio de escena_edificio.py (usa SAAG, mezclar, rampa, ruido, nodos, cargar_modelo_arbol) y
recibe ns, el espacio donde está cargado realismo_blender.py.
"""
import math
import random

import bmesh
import bpy

MANGOS = [  # (x, y, ancho de copa, giro): entre el edificio y la vía, dejando ver la fachada como en las fotos
    (-23.0, -34.0, 13.0, 0.3),
    (1.0, -37.5, 14.5, 2.0),
    (22.0, -33.5, 12.0, 4.1),
    (36.0, -12.0, 11.0, 1.1),
]


def mat_seto():
    m = bpy.data.materials.get('Seto')
    if m:
        return m
    m = bpy.data.materials.new('Seto')
    nt, b, out = nodos(m); nt.links.new(b.outputs[0], out.inputs[0])
    tc = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    vor = nt.nodes.new('ShaderNodeTexVoronoi'); vor.inputs['Scale'].default_value = 28.0
    nt.links.new(tc, vor.inputs['Vector'])
    hojas = rampa(nt, vor.outputs['Distance'], [(0.0, (0.06, 0.16, 0.03, 1)), (0.5, (0.035, 0.1, 0.02, 1)), (0.9, (0.012, 0.03, 0.01, 1))])
    manchas = rampa(nt, ruido(nt, tc, 1.2, 5), [(0.35, (0.85, 0.9, 0.8, 1)), (0.7, (1.15, 1.1, 0.9, 1))])
    nt.links.new(mezclar(nt, hojas, manchas, 1.0, 'MULTIPLY'), b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.6
    b.inputs['Subsurface Weight'].default_value = 0.1
    bu = nt.nodes.new('ShaderNodeBump'); bu.inputs['Strength'].default_value = 0.9; bu.inputs['Distance'].default_value = 0.03
    nt.links.new(vor.outputs['Distance'], bu.inputs['Height']); nt.links.new(bu.outputs[0], b.inputs['Normal'])
    return m


def seto(nombre, x0, x1, y, alto=0.85, fondo=0.8):
    """Seto podado: bolas de follaje encimadas y deformadas con ruido, para que el borde no quede recto."""
    random.seed(hash(nombre) % 1000)
    bm = bmesh.new()
    n = max(2, int((x1 - x0) / 0.55))
    for k in range(n + 1):
        x = x0 + (x1 - x0) * k / n
        r = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
        bmesh.ops.scale(bm, vec=(0.75 + random.random() * 0.2, fondo / 1.0, alto / 0.95), verts=r['verts'])
        bmesh.ops.translate(bm, vec=(x, y + (random.random() - 0.5) * 0.08, alto * 0.48), verts=r['verts'])
        for v in r['verts']:
            v.co += v.normal * (random.random() - 0.5) * 0.08
    me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free()
    me.materials.append(mat_seto())
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(nombre, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def paisaje_saag(ns):
    ns['mat_grama_realista']()                                       # grama del render principal
    arbol = cargar_modelo_arbol('island_tree_01')
    if arbol:
        col_arb, ancho, alto = arbol
        bpy.context.view_layer.layer_collection.children[col_arb.name].exclude = True
        for x, y, copa, giro in MANGOS:
            e = bpy.data.objects.new('Mango', None)
            e.instance_type = 'COLLECTION'; e.instance_collection = col_arb
            k = copa / ancho
            e.location = (x, y, 0.0); e.rotation_euler.z = giro; e.scale = (k, k, k * 0.95)
            bpy.context.scene.collection.objects.link(e)
    # setos del jardín del frente, a los dos lados de la caminería de la entrada
    L, W = SAAG['L'], SAAG['W']
    fy = -W / 2 - SAAG['fondo']
    xp = -L / 2 + SAAG['puerta_x'] * L
    y_seto = fy - 5.5
    seto('Seto izquierdo', -L / 2 - 2.0, xp - 1.4, y_seto)
    seto('Seto derecho', xp + 1.4, L / 2 + 1.0, y_seto)
