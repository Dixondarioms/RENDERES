"""Hangar del SAAG (el galpón del techo rojo, detrás del edificio blanco), según las fotos de adentro del 10-11-2026.

Solo las instalaciones, sin helicópteros, vehículos ni equipos:
  - Dos naves a dos aguas (cada una para un helicóptero), pórticos de acero blanco con cartelas, fila de columnas
    en el medio con el rayado amarillo y rojo, canal entre las naves con el tubo grande de desagüe.
  - Techo de lámina (gris por dentro, roja por fuera) con correas blancas, cruces de cable y claraboyas translúcidas;
    lámparas colgantes.
  - Paredes laterales de bloque pintado de blanco con franja de bloque calado, abertura bajo el techo, extractores
    y cruces blancas por fuera.
  - Fondo: la cara de atrás del edificio blanco (ventanas, puerta de madera, ventanas altas, panel azul marino,
    tubería eléctrica, escalera con el cuartico debajo y escalera de gato).
  - Visto desde la plataforma: a la izquierda (+X) la canasta de baloncesto; en el medio extintores en la columna;
    a la derecha (-X) lavamanos de baldosa
    gris, ducha de emergencia y tablero eléctrico. Extintores en gabinete rojo en las dos paredes.
  - Frente hacia la plataforma: portones de malla colgados de una viga carril que sale a los lados (abiertos).

Usa las funciones de mejoras_blender.py y edificio_saag.py (SAAG, mat_simple, caja_bm, uv_metros, nodos, rampa,
ruido, mezclar). Mismas coordenadas locales que edificio_saag.py: el galpón ocupa x = ±L/2, y = -W/2 (pared del
edificio blanco) hasta +W/2 (frente abierto hacia la plataforma).
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

GALPON = dict(
    alero=5.1,                    # altura del techo en las paredes laterales y en la canal del medio
    cumbre=7.0,                   # altura de la cumbrera de cada nave
    porticos=(-7.3, -2.5, 2.5, 7.3),   # y de los pórticos (el primero va pegado al edificio blanco)
    pared=3.3, calado=(3.3, 4.0), remate=4.15,   # pared de bloque, franja de bloque calado y remate
    portones_abiertos=True,
)


# ----------------------------------------------------------------------------- materiales
def mat_bloque():
    m = bpy.data.materials.get('Bloque pintado')
    if m:
        return m
    m = bpy.data.materials.new('Bloque pintado')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    uv = nt.nodes.new('ShaderNodeTexCoord').outputs['UV']
    lad = nt.nodes.new('ShaderNodeTexBrick')
    lad.offset = 0.5; lad.squash = 1.0
    lad.inputs['Scale'].default_value = 1.0
    lad.inputs['Brick Width'].default_value = 0.4; lad.inputs['Row Height'].default_value = 0.2
    lad.inputs['Mortar Size'].default_value = 0.006
    lad.inputs['Color1'].default_value = (0.86, 0.86, 0.84, 1); lad.inputs['Color2'].default_value = (0.83, 0.83, 0.81, 1)
    lad.inputs['Mortar'].default_value = (0.7, 0.7, 0.68, 1)
    nt.links.new(uv, lad.inputs['Vector'])
    # suciedad que sube del piso (salpicaduras), chorreados bajo el bloque calado y oclusión en rincones
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(nt.nodes.new('ShaderNodeTexCoord').outputs['Object'], sep.inputs[0])
    sucio = rampa(nt, sep.outputs['Z'], [(0.0, (0.62, 0.58, 0.52, 1)), (0.45, (0.93, 0.92, 0.9, 1)), (0.9, (1, 1, 1, 1))])
    col = mezclar(nt, lad.outputs['Color'], sucio, 1.0, 'MULTIPLY')
    nt.links.new(oclusion(nt, chorreado(nt, col, 0.16, 1.3), 0.6, 0.6), bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.88
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.35; bump.inputs['Distance'].default_value = 0.005
    nt.links.new(lad.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def mat_lamina_galpon():
    """Lámina acanalada: roja por fuera, galvanizada por dentro (una sola cara, según de qué lado se mire)."""
    m = bpy.data.materials.get('Lamina galpon')
    if m:
        return m
    m = bpy.data.materials.new('Lamina galpon')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    uv = nt.nodes.new('ShaderNodeTexCoord').outputs['UV']
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    col = mezclar(nt, (0.45, 0.13, 0.08, 1), (0.6, 0.62, 0.63, 1), geo.outputs['Backfacing'])
    manchas = rampa(nt, ruido(nt, uv, 0.4, 6), [(0.4, (1, 1, 1, 1)), (0.75, (0.82, 0.8, 0.76, 1))])
    col = chorreado(nt, mezclar(nt, col, manchas, 1.0, 'MULTIPLY'), 0.2, 1.0, eje='X')   # chorreados en la pendiente
    nt.links.new(oclusion(nt, col, 0.45, 0.8), bsdf.inputs['Base Color'])
    rug = nt.nodes.new('ShaderNodeMapRange'); rug.inputs['To Min'].default_value = 0.38; rug.inputs['To Max'].default_value = 0.7
    nt.links.new(ruido(nt, uv, 1.5, 4), rug.inputs['Value']); nt.links.new(rug.outputs['Result'], bsdf.inputs['Roughness'])
    bsdf.inputs['Metallic'].default_value = 0.45
    onda = nt.nodes.new('ShaderNodeTexWave'); onda.wave_type = 'BANDS'; onda.bands_direction = 'Y'
    onda.inputs['Scale'].default_value = 1.6; onda.inputs['Distortion'].default_value = 0.0
    nt.links.new(uv, onda.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.6; bump.inputs['Distance'].default_value = 0.02
    nt.links.new(onda.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def mat_claraboya():
    """Lámina translúcida de fibra (amarillenta): deja pasar la luz."""
    m = bpy.data.materials.get('Claraboya')
    if m:
        return m
    m = bpy.data.materials.new('Claraboya')
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent'); tr.inputs['Color'].default_value = (0.95, 0.85, 0.6, 1)
    tp = nt.nodes.new('ShaderNodeBsdfTransparent'); tp.inputs['Color'].default_value = (0.95, 0.9, 0.75, 1)
    mx = nt.nodes.new('ShaderNodeMixShader'); mx.inputs['Fac'].default_value = 0.08
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(tp.outputs[0], mx.inputs[2]); nt.links.new(mx.outputs[0], out.inputs[0])
    return m


def mat_baldosa(nombre, color, tam):
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = bpy.data.materials.new(nombre)
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    uv = nt.nodes.new('ShaderNodeTexCoord').outputs['UV']
    lad = nt.nodes.new('ShaderNodeTexBrick'); lad.offset = 0.0; lad.squash = 1.0
    lad.inputs['Scale'].default_value = 1.0
    lad.inputs['Brick Width'].default_value = tam; lad.inputs['Row Height'].default_value = tam
    lad.inputs['Mortar Size'].default_value = 0.004
    lad.inputs['Color1'].default_value = color + (1,); lad.inputs['Color2'].default_value = tuple(c * 1.15 for c in color) + (1,)
    lad.inputs['Mortar'].default_value = (0.35, 0.35, 0.35, 1)
    nt.links.new(uv, lad.inputs['Vector'])
    nt.links.new(lad.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.35
    return m


def mat_vidrio_claro(nombre):
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = bpy.data.materials.new(nombre); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.9, 0.95, 0.95, 1)
    b.inputs['Transmission Weight'].default_value = 1.0; b.inputs['Roughness'].default_value = 0.05
    b.inputs['IOR'].default_value = 1.05
    return m


def mat_acero_pintado():
    """Acero pintado de blanco con polvo, manchas y oclusión en las uniones."""
    m = bpy.data.materials.get('Acero blanco pintado')
    if m:
        return m
    m = bpy.data.materials.new('Acero blanco pintado')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    tc = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    polvo = rampa(nt, ruido(nt, tc, 2.5, 8), [(0.4, (1, 1, 1, 1)), (0.72, (0.86, 0.84, 0.8, 1))])
    col = mezclar(nt, (0.84, 0.84, 0.82, 1), polvo, 1.0, 'MULTIPLY')
    nt.links.new(oclusion(nt, col, 0.5, 0.35), bsdf.inputs['Base Color'])
    rug = nt.nodes.new('ShaderNodeMapRange'); rug.inputs['To Min'].default_value = 0.35; rug.inputs['To Max'].default_value = 0.6
    nt.links.new(ruido(nt, tc, 6.0, 3), rug.inputs['Value']); nt.links.new(rug.outputs['Result'], bsdf.inputs['Roughness'])
    bsdf.inputs['Metallic'].default_value = 0.15
    return m


def mat_pintura_gastada(nombre, color):
    """Pintura de seguridad (rayado de las columnas) con desgaste y roces abajo, donde la tocan."""
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = bpy.data.materials.new(nombre)
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    tc = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc, sep.inputs[0])
    gasto = rampa(nt, ruido(nt, tc, 9.0, 10), [(0.55, (0, 0, 0, 1)), (0.68, (1, 1, 1, 1))])
    abajo = rampa(nt, sep.outputs['Z'], [(0.0, (1, 1, 1, 1)), (0.6, (0.25, 0.25, 0.25, 1))])
    fac = mezclar(nt, gasto, abajo, 1.0, 'MULTIPLY')
    col = mezclar(nt, color + (1,), (0.32, 0.31, 0.29, 1), fac)
    nt.links.new(oclusion(nt, col, 0.45, 0.3), bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.5
    return m


def mat_piso_hangar():
    """Piso de concreto del hangar: textura real, losas de 5 m con juntas, manchas de aceite (más brillantes) y
    oclusión junto a paredes y objetos."""
    m = bpy.data.materials.get('Piso hangar SAAG')
    if m:
        return m
    m = bpy.data.materials.new('Piso hangar SAAG')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    tc = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    t = tex_pbr(nt, tc, 'piso_hangar', 2.5)
    base = mezclar(nt, (0.56, 0.55, 0.53, 1), t['col'], 0.8, 'MULTIPLY')
    losas = nt.nodes.new('ShaderNodeTexBrick'); losas.offset = 0.0; losas.squash = 1.0
    losas.inputs['Scale'].default_value = 1.0; losas.inputs['Brick Width'].default_value = 5.0
    losas.inputs['Row Height'].default_value = 5.0; losas.inputs['Mortar Size'].default_value = 0.012
    losas.inputs['Color1'].default_value = (1, 1, 1, 1); losas.inputs['Color2'].default_value = (0.93, 0.93, 0.92, 1)
    losas.inputs['Mortar'].default_value = (0.35, 0.35, 0.35, 1)
    nt.links.new(tc, losas.inputs['Vector'])
    base = mezclar(nt, base, losas.outputs['Color'], 1.0, 'MULTIPLY')
    aceite = rampa(nt, ruido(nt, tc, 0.45, 7), [(0.6, (0, 0, 0, 1)), (0.7, (1, 1, 1, 1))])
    gotas = rampa(nt, ruido(nt, tc, 3.0, 4), [(0.66, (0, 0, 0, 1)), (0.72, (0.8, 0.8, 0.8, 1))])
    fac = mezclar(nt, aceite, gotas, 1.0, 'LIGHTEN')
    col = mezclar(nt, base, (0.17, 0.16, 0.15, 1), fac)
    nt.links.new(oclusion(nt, col, 0.55, 0.6), bsdf.inputs['Base Color'])
    rug = mezclar(nt, t['rug'], (0.3, 0.3, 0.3, 1), fac)
    gris = nt.nodes.new('ShaderNodeRGBToBW'); nt.links.new(rug, gris.inputs[0]); nt.links.new(gris.outputs[0], bsdf.inputs['Roughness'])
    nt.links.new(t['normal'], bsdf.inputs['Normal'])
    return m


# ----------------------------------------------------------------------------- galpón
def construir_galpon(nombre='saag_galpon', coleccion=None):
    d, g = SAAG, GALPON
    L, W = d['L'], d['W']
    xL, xR, yB, yF = -L / 2, L / 2, -W / 2, W / 2
    h_alero, h_cumbre = g['alero'], g['cumbre']
    naves = (-L / 4, L / 4)                       # centro de cada nave
    media = L / 4

    def z_techo(x):
        """Altura de la cara de abajo de la lámina en x."""
        c = naves[0] if x < 0 else naves[1]
        return h_alero + (h_cumbre - h_alero) * max(0.0, 1 - abs(x - c) / media)

    M = {}
    lista = []

    def mat(clave, crear):
        if clave not in M:
            M[clave] = len(lista); lista.append(crear())
        return M[clave]

    acero = mat('acero', mat_acero_pintado)
    piso = mat('piso', mat_piso_hangar)
    bloque = mat('bloque', mat_bloque)
    lamina = mat('lamina', mat_lamina_galpon)
    clara = mat('clara', mat_claraboya)
    gris_canal = mat('canal', lambda: mat_simple('Canal galvanizada', (0.45, 0.46, 0.47), 0.45, 0.8))
    tubo = mat('tubo', lambda: mat_simple('Tubo PVC', (0.78, 0.78, 0.76), 0.5))
    amarillo = mat('amarillo', lambda: mat_pintura_gastada('Pintura amarilla gastada', (0.85, 0.6, 0.02)))
    rojo = mat('rojo', lambda: mat_simple('Rojo extintor', (0.6, 0.02, 0.02), 0.4))
    rojo_rayado = mat('rojo_rayado', lambda: mat_pintura_gastada('Pintura roja gastada', (0.55, 0.02, 0.02)))
    negro = mat('negro', lambda: mat_simple('Pintura negra', (0.03, 0.03, 0.03), 0.5))
    pared_fondo = mat('fondo', lambda: mat_pintura(d['muro']))
    vidrio = mat('vidrio', lambda: mat_simple('Vidrio ventana', (0.02, 0.03, 0.035), rug=0.05, metal=0.2))
    marco = mat('marco', lambda: mat_simple('Aluminio blanco', (0.8, 0.8, 0.79), 0.4, 0.3))
    madera = mat('madera', lambda: mat_simple('Puerta de madera', (0.33, 0.19, 0.11), 0.55))
    azul = mat('azul', lambda: mat_simple('Azul marino pared', (0.012, 0.022, 0.07), 0.6))
    gris_baldosa = mat('baldosa', lambda: mat_baldosa('Baldosa gris oscura', (0.11, 0.11, 0.12), 0.3))
    concreto = mat('concreto', lambda: mat_simple('Concreto gris', (0.5, 0.5, 0.48), 0.85))
    verde = mat('verde', lambda: mat_simple('Tubo verde ducha', (0.04, 0.3, 0.15), 0.4, 0.3))
    letrero_verde = mat('lverde', lambda: mat_simple('Letrero verde', (0.0, 0.4, 0.15), 0.4))
    letrero_rojo = mat('lrojo', lambda: mat_simple('Letrero rojo', (0.65, 0.03, 0.03), 0.4))
    tablero = mat('tablero', lambda: mat_simple('Tablero electrico', (0.55, 0.56, 0.57), 0.4, 0.5))
    acrilico = mat('acrilico', lambda: mat_vidrio_claro('Acrilico tablero'))
    naranja = mat('naranja', lambda: mat_simple('Aro naranja', (0.75, 0.12, 0.02), 0.4, 0.3))
    red = mat('red', lambda: mat_simple('Red blanca', (0.9, 0.9, 0.88), 0.7))
    pantalla = mat('pantalla', lambda: mat_simple('Pantalla lampara', (0.85, 0.83, 0.75), 0.3))
    malla = mat('malla', lambda: mat_simple('Malla porton', (0.88, 0.88, 0.86), 0.45, 0.3))
    loza = mat('loza', lambda: mat_simple('Loza blanca', (0.9, 0.9, 0.9), 0.15))

    bm = bmesh.new()

    def caja(cx, cy, cz, sx, sy, sz, i):
        caja_bm(bm, cx, cy, cz, sx, sy, sz, i)

    def viga(p1, p2, ancho, alto, i, arriba=(0, 0, 1)):
        """Barra de sección ancho x alto entre dos puntos."""
        p1, p2 = Vector(p1), Vector(p2)
        dv = p2 - p1
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(dv.length, ancho, alto), verts=r['verts'])
        q = dv.normalized().to_track_quat('X', 'Z')
        bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=q.to_matrix())
        bmesh.ops.translate(bm, vec=(p1 + p2) / 2, verts=r['verts'])
        for f in {f for v in r['verts'] for f in v.link_faces}:
            f.material_index = i

    def cilindro(c, radio, alto, i, eje='Z', lados=20, r2=None):
        r = bmesh.ops.create_cone(bm, cap_ends=True, segments=lados, radius1=radio, radius2=radio if r2 is None else r2, depth=alto)
        if eje == 'X':
            bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
        elif eje == 'Y':
            bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
        bmesh.ops.translate(bm, vec=c, verts=r['verts'])
        for f in {f for v in r['verts'] for f in v.link_faces}:
            f.material_index = i

    # ================================================= piso de concreto del hangar
    caja(0, 0, 0.02, L - 0.4, W - 0.05, 0.02, piso)

    # ================================================= techo: lámina por paños y claraboyas
    voladizo_lado, voladizo_frente = 0.45, 0.6
    for n, c in enumerate(naves):
        for lado in (0, 1):                                       # 0: faldón izquierdo de la nave, 1: derecho
            x_borde = c - media if lado == 0 else c + media
            if (n == 0 and lado == 0) or (n == 1 and lado == 1):
                x_borde += -voladizo_lado if lado == 0 else voladizo_lado
            franjas, panos = 4, 10
            for f_ in range(franjas):
                xa = x_borde + (c - x_borde) * f_ / franjas
                xb = x_borde + (c - x_borde) * (f_ + 1) / franjas
                for p_ in range(panos):
                    ya = yB + (yF + voladizo_frente - yB) * p_ / panos
                    yb_ = yB + (yF + voladizo_frente - yB) * (p_ + 1) / panos
                    za, zb = z_techo(min(max(xa, xL), xR)) + 0.02, z_techo(min(max(xb, xL), xR)) + 0.02
                    if xa < xL or xa > xR:
                        za = h_alero + 0.02 - (h_cumbre - h_alero) / media * voladizo_lado
                    vs = [bm.verts.new(v) for v in ((xa, ya, za), (xb, ya, zb), (xb, yb_, zb), (xa, yb_, za))]
                    cara = bm.faces.new(vs)
                    es_clara = f_ in (1, 2) and p_ in (1, 4, 7) and (f_ + p_ // 3 + n + lado) % 2 == 0
                    cara.material_index = clara if es_clara else lamina
                    cara.normal_update()
                    if cara.normal.z < 0:
                        cara.normal_flip()

    # ================================================= pórticos: columnas, vigas, cartelas y correas
    sv, hv = 0.22, 0.42                                  # sección de las vigas
    for y in g['porticos']:
        for c in naves:
            for s in (-1, 1):
                xe = c + s * media
                viga((xe, y, z_techo(xe) - hv / 2), (c, y, h_cumbre - hv / 2), sv, hv, acero)
        if y == g['porticos'][0]:
            continue                                     # el de atrás va pegado al edificio blanco, sin columnas
        for x in (xL + 0.2, 0.0, xR - 0.2):
            zc = z_techo(x) - hv
            caja(x, y, zc / 2, 0.3, 0.3, zc, acero)
            for s in (-1, 1):                            # cartelas (forman la "Y" arriba de cada columna)
                if (x < -1 and s < 0) or (x > 1 and s > 0):
                    continue
                xb = x + s * 1.6
                viga((x, y, zc - 1.0), (xb, y, z_techo(xb) - hv * 0.9), 0.15, 0.2, acero)
        # rayado de la columna del medio: amarillo abajo y franja roja
        caja(0, y, 0.95, 0.32, 0.32, 1.9, amarillo)
        caja(0, y, 2.0, 0.32, 0.32, 0.2, rojo_rayado)
    # correas a lo largo (de atrás hacia el frente) y cruces de cable en el techo
    for c in naves:
        for k in range(-7, 8):
            x = c + k * media / 7.5
            viga((x, yB, z_techo(x) - 0.08), (x, yF + 0.3, z_techo(x) - 0.08), 0.06, 0.14, acero)
        ys = g['porticos']
        for a, b in zip(ys[:-1], ys[1:]):
            for s in (-1, 1):
                x1, x2 = c - media * 0.9, c - media * 0.1
                if s > 0:
                    x1, x2 = c + media * 0.1, c + media * 0.9
                viga((x1, a, z_techo(x1) - 0.18), (x2, b, z_techo(x2) - 0.18), 0.012, 0.012, acero)
                viga((x1, b, z_techo(x1) - 0.18), (x2, a, z_techo(x2) - 0.18), 0.012, 0.012, acero)
    # canal del medio y tubo grande de desagüe; vigas de borde en las paredes
    caja(0, (yB + yF) / 2 + 0.3, h_alero - 0.08, 0.6, W + 0.6, 0.18, gris_canal)
    cilindro((0.25, (yB + yF) / 2 + 0.2, h_alero - 0.55), 0.13, W + 0.4, tubo, eje='Y')
    cilindro((0.25, yF + 0.45, (h_alero - 0.55) / 2), 0.11, h_alero - 0.55, tubo)
    for x in (xL + 0.15, xR - 0.15):
        caja(x, (yB + yF) / 2, h_alero - 0.25, 0.2, W, 0.3, acero)
    # lámparas colgantes
    for c in naves:
        for dx in (-3.5, 3.5):
            for y in (-4.5, 0.0, 4.5):
                x = c + dx
                zt = z_techo(x)
                caja(x, y, zt - 0.55, 0.015, 0.015, 1.1, negro)
                cilindro((x, y, zt - 1.2), 0.13, 0.25, negro)
                cilindro((x, y, zt - 1.55), 0.12, 0.45, pantalla, r2=0.3)

    # ================================================= paredes laterales: bloque, calado, abertura y cruces
    e = 0.2
    for s, xw in ((-1, xL), (1, xR)):
        xc = xw - s * e / 2
        caja(xc, 0, g['pared'] / 2, e, W, g['pared'], bloque)
        z0, z1 = g['calado']
        caja(xc, 0, z1 + (g['remate'] - z1) / 2, e, W, g['remate'] - z1, bloque)
        n = int(W / 0.32)
        for k in range(n + 1):                                         # bloque calado: tabiques y huecos
            caja(xc, yB + k * W / n, (z0 + z1) / 2, e, 0.07, z1 - z0, bloque)
        caja(xc, 0, (z0 + z1) / 2, e - 0.02, W, 0.06, bloque)
        for y in (yB + 0.2, -2.5, 2.5, yF - 0.2):                      # machones
            caja(xw - s * 0.25, y, g['remate'] / 2, 0.3, 0.35, g['remate'], bloque)
        # cruces blancas por fuera en cada tramo
        for a, b in ((yB + 0.4, -2.7), (-2.3, 2.3), (2.7, yF - 0.4)):
            viga((xw + s * 0.03, a, 0.35), (xw + s * 0.03, b, g['pared'] - 0.1), 0.04, 0.1, acero, )
            viga((xw + s * 0.03, b, 0.35), (xw + s * 0.03, a, g['pared'] - 0.1), 0.04, 0.1, acero)
        # canal y bajantes por fuera
        caja(xw + s * 0.25, (yB + yF) / 2 + 0.3, h_alero - 0.1, 0.25, W + 0.6, 0.2, gris_canal)
        for y in (-2.5, 2.5):
            caja(xw + s * 0.15, y + 0.4, (h_alero - 0.2) / 2, 0.11, 0.11, h_alero - 0.2, tubo)

    # extractores (cuadro negro con aspas) en la franja de bloque calado
    extractores = []                            # (posición, giro) para el modelo real del ventilador

    def extractor(xw, s, y):
        xi = xw - s * (e + 0.03)
        zc = sum(g['calado']) / 2
        if hay_modelo_extractor():
            extractores.append(((xw - s * e, y, zc), 0.0 if s > 0 else math.pi))
            return
        caja(xi, y, zc, 0.12, 0.85, 0.85, negro)
        cilindro((xi - s * 0.065, y, zc), 0.38, 0.02, gris_canal, eje='X', lados=24)
        cilindro((xi - s * 0.08, y, zc), 0.35, 0.02, negro, eje='X', lados=24)
        cilindro((xi - s * 0.1, y, zc), 0.08, 0.06, gris_canal, eje='X')
        for k in range(3):
            a = k * 2 * math.pi / 3
            viga((xi - s * 0.1, y, zc), (xi - s * 0.1, y + 0.32 * math.cos(a), zc + 0.32 * math.sin(a)), 0.02, 0.14, gris_canal)
    for y in (-4.5, 1.0, 5.0):
        extractor(xR, 1, y)
    for y in (-1.0, 4.8):
        extractor(xL, -1, y)

    # ================================================= fondo: cara de atrás del edificio blanco
    yp = yB + 0.02
    caja(0, yB, h_cumbre / 2, L - 0.4, 0.04, h_cumbre, pared_fondo)   # repello del fondo (dentro del galpón)

    def ventana_fondo(x, z, ancho, alto, rejas=False):
        caja(x, yp + 0.02, z, ancho + 0.1, 0.05, alto + 0.1, marco)
        caja(x, yp + 0.04, z, ancho, 0.04, alto, vidrio)
        if rejas:
            for k in range(7):
                caja(x - ancho / 2 + k * ancho / 6, yp + 0.08, z, 0.025, 0.025, alto, marco)
    for x in (-7.5, -5.0, -2.6, 3.4, 5.8, 8.2, 10.6):
        ventana_fondo(x, 1.75, 1.2, 1.0)
    ventana_fondo(2.4, 1.85, 0.55, 0.55, rejas=True)
    caja(1.2, yp + 0.03, 1.07, 1.0, 0.06, 2.1, madera)                  # puerta de madera
    caja(1.2, yp + 0.02, 1.1, 1.15, 0.04, 2.2, marco)
    for c in naves:                                                    # ventanas altas bajo cada cumbrera
        for dx, z in ((-3.6, 5.0), (0.0, 5.9), (3.6, 5.0)):
            ventana_fondo(c + dx, z, 1.0, 0.85)
    caja(13.9, yp + 0.02, 2.5, 2.6, 0.03, 5.0, azul)                   # panel azul marino
    for z in (2.6, 3.2):                                               # tubería eléctrica a lo largo
        caja(0, yp + 0.05, z, L - 1.0, 0.04, 0.04, tubo)
    for x in (-4.0, 0.6, 7.0, 12.0):
        caja(x, yp + 0.05, (3.2 + 6.0) / 2, 0.04, 0.04, 2.8, tubo)
    # escalera de concreto con el cuartico debajo y escalera de gato
    caja(xL + 1.6, yB + 1.3, 1.4, 2.8, 2.6, 2.8, bloque)                # cuartico de bloque
    caja(xL + 2.2, yB + 2.62, 1.05, 0.9, 0.04, 2.1, negro)              # puerta negra
    escalones, x_base, x_tope = 16, -8.9, xL + 3.0
    for k in range(escalones):
        x = x_base + (x_tope - x_base) * (k + 0.5) / escalones
        alto = 2.8 * (k + 1) / escalones
        caja(x, yB + 0.65, alto / 2, abs(x_tope - x_base) / escalones + 0.01, 1.2, alto, concreto)
    viga((x_base, yB + 1.22, 1.0), (x_tope, yB + 1.22, 3.8), 0.05, 0.05, acero)      # pasamanos
    for k in range(5):
        x = x_base + (x_tope - x_base) * k / 4
        caja(x, yB + 1.22, 2.8 * k / 4 + 0.5, 0.04, 0.04, 1.0, acero)
    viga((xL + 0.3, yB + 2.55, 3.8), (x_tope, yB + 2.55, 3.8), 0.05, 0.05, acero)     # baranda del descanso
    for z in range(13):                                                 # escalera de gato hasta la ventana alta
        caja(xL + 3.9, yp + 0.25, 3.0 + z * 0.3, 0.45, 0.03, 0.03, negro)
    for dx in (-0.22, 0.22):
        caja(xL + 3.9 + dx, yp + 0.25, 4.8, 0.04, 0.04, 3.7, negro)

    # Lados vistos desde la plataforma (mirando hacia el edificio blanco): la izquierda es +X y la derecha -X.
    # ================================================= canasta de baloncesto (pared de +X) y extintores
    xi, sd = xR - e, -1                         # cara de adentro de la pared y hacia dónde sale lo que se cuelga
    yc_ = 2.5
    viga((xi + sd * 0.05, yc_, 2.2), (xi + sd * 1.45, yc_, 3.9), 0.16, 0.16, negro)            # brazo diagonal
    viga((xi + sd * 0.95, yc_, 3.3), (xi + sd * 1.65, yc_, 3.3), 0.1, 0.1, negro)              # brazo al tablero
    caja(xi + sd * 1.68, yc_, 3.42, 0.03, 1.8, 1.05, acrilico)                                  # tablero de acrílico
    for (sy, sz, dy, dz) in ((1.84, 0.04, 0, 0.525), (1.84, 0.04, 0, -0.525), (0.04, 1.05, 0.9, 0), (0.04, 1.05, -0.9, 0)):
        caja(xi + sd * 1.68, yc_ + dy, 3.42 + dz, 0.05, sy, sz, marco)
    for (sy, sz, dy, dz) in ((0.59, 0.05, 0, 0.2), (0.59, 0.05, 0, -0.2), (0.05, 0.45, 0.27, 0), (0.05, 0.45, -0.27, 0)):
        caja(xi + sd * 1.7, yc_ + dy, 3.15 + dz, 0.035, sy, sz, marco)                         # recuadro blanco (solo el borde)
    canasta = None
    if hay_modelo_red():                                                                        # aro y red reales
        canasta = ((xi + sd * 1.695, yc_, 3.05), math.pi / 2 if sd < 0 else -math.pi / 2)
    else:
        aro_c = Vector((xi + sd * (1.7 + 0.15 + 0.23), yc_, 3.05))
        for k in range(16):                                                                     # aro y red
            a1, a2 = k * 2 * math.pi / 16, (k + 1) * 2 * math.pi / 16
            p1 = aro_c + Vector((0.23 * math.cos(a1), 0.23 * math.sin(a1), 0))
            p2 = aro_c + Vector((0.23 * math.cos(a2), 0.23 * math.sin(a2), 0))
            viga(p1, p2, 0.018, 0.018, naranja)
            viga(p1, aro_c + Vector((0.14 * math.cos(a1 + 0.4), 0.14 * math.sin(a1 + 0.4), -0.42)), 0.008, 0.008, red)
        caja(xi + sd * 1.78, yc_, 3.08, 0.15, 0.2, 0.08, naranja)

    extintores = []                             # (posición de la base, giro) para el modelo real del extintor
    modelo_ext = hay_modelo_extintor()

    def gabinete(x, y, s):
        """Gabinete rojo abierto con el extintor adentro y el letrero arriba, en la pared x (s: hacia dónde mira)."""
        if modelo_ext:
            caja(x + s * 0.01, y, 1.35, 0.02, 0.5, 0.8, rojo)                  # fondo
            for dy in (-0.24, 0.24):
                caja(x + s * 0.13, y + dy, 1.35, 0.26, 0.02, 0.8, rojo)        # lados
            for dz in (-0.39, 0.39):
                caja(x + s * 0.13, y, 1.35 + dz, 0.26, 0.5, 0.02, rojo)        # arriba y abajo
            extintores.append(((x + s * 0.11, y, 0.98), math.pi / 2 if s > 0 else -math.pi / 2))
        else:
            caja(x + s * 0.06, y, 1.35, 0.1, 0.45, 0.75, rojo)
            cilindro((x + s * 0.13, y, 1.3), 0.09, 0.5, rojo)
        caja(x + s * 0.02, y, 2.05, 0.02, 0.28, 0.32, letrero_rojo)
    gabinete(xR - e, 5.2, -1)
    gabinete(xL + e, -1.0, 1)

    # ================================================= medio: extintores colgados en la columna
    for s in (-1, 1):
        if modelo_ext:
            caja(s * 0.19, 2.5, 1.12, 0.06, 0.04, 0.12, negro)                 # gancho
            extintores.append(((s * 0.26, 2.5, 0.5), math.pi / 2 if s > 0 else -math.pi / 2))
        else:
            cilindro((s * 0.27, 2.5, 0.75), 0.1, 0.62, rojo)
            cilindro((s * 0.27, 2.5, 1.12), 0.03, 0.12, negro)

    # ================================================= lavamanos, ducha de emergencia y tablero (pared de -X)
    xd, sl = xL + e, 1
    yl = -3.6                                                                        # lavamanos de baldosa gris
    caja(xd + sl * 0.33, yl, 0.45, 0.66, 2.0, 0.9, gris_baldosa)
    for fila in range(2):
        for col in range(3):
            caja(xd + sl * 0.67, yl - 0.66 + col * 0.66, 0.22 + fila * 0.4, 0.04, 0.55, 0.32, negro)
    caja(xd + sl * 0.33, yl, 0.92, 0.7, 2.05, 0.05, gris_baldosa)
    caja(xd + sl * 0.02, yl, 1.2, 0.04, 2.05, 0.6, gris_baldosa)
    caja(xd + sl * 0.33, yl + 0.4, 0.93, 0.42, 0.5, 0.04, loza)
    cilindro((xd + sl * 0.12, yl + 0.4, 1.05), 0.02, 0.22, marco)
    yd = 2.6                                                                         # ducha de emergencia
    caja(xd + sl * 0.02, yd, 1.4, 0.04, 2.0, 2.8, gris_baldosa)
    caja(xd + sl * 0.5, yd, 0.06, 0.95, 0.95, 0.12, concreto)
    cilindro((xd + sl * 0.15, yd + 0.6, 1.25), 0.03, 2.5, verde)
    viga((xd + sl * 0.15, yd + 0.6, 2.45), (xd + sl * 0.15, yd, 2.45), 0.05, 0.05, verde)
    cilindro((xd + sl * 0.15, yd, 2.3), 0.04, 0.18, verde, r2=0.15)
    caja(xd + sl * 0.35, yd - 0.2, 1.95, 0.02, 0.02, 0.6, verde)                     # tirador con triángulo
    viga((xd + sl * 0.35, yd - 0.32, 1.62), (xd + sl * 0.35, yd - 0.08, 1.62), 0.02, 0.02, verde)
    cilindro((xd + sl * 0.35, yd + 0.6, 1.0), 0.14, 0.08, verde)                     # lavaojos
    caja(xd + sl * 0.02, yd + 0.6, 2.75, 0.03, 0.32, 0.26, letrero_verde)
    for k, y in enumerate((-1.95, -1.3)):                                            # tableros eléctricos
        caja(xd + sl * 0.12, y, 1.6, 0.2, 0.55, 0.8 - k * 0.2, tablero)
    caja(xd + sl * 0.05, -1.62, 3.0, 0.05, 0.05, 2.2, tubo)

    # ================================================= frente: viga carril con portones de malla
    largo_carril = L + 2 * 12.0
    yc = yF + 0.75
    for zc in (5.45, 5.95):
        caja(0, yc, zc, largo_carril, 0.12, 0.1, acero)
    n = int(largo_carril / 0.6)
    for k in range(n):
        x1 = -largo_carril / 2 + k * largo_carril / n
        viga((x1, yc, 5.45), (x1 + largo_carril / n, yc, 5.95), 0.05, 0.05, acero)
    for x in (-largo_carril / 2 + 0.2, xL - 0.3, 0.0, xR + 0.3, largo_carril / 2 - 0.2):
        caja(x, yc, 3.0, 0.3, 0.3, 6.0, acero)
    ancho_p, alto_p, n_p = L / 6, 5.1, 6

    def porton(x, y):
        x0_, z0_ = x - ancho_p / 2, 0.15
        for (cx, cz, sx, sz) in ((x, z0_, ancho_p, 0.08), (x, z0_ + alto_p, ancho_p, 0.08),
                                 (x0_, z0_ + alto_p / 2, 0.08, alto_p), (x0_ + ancho_p, z0_ + alto_p / 2, 0.08, alto_p),
                                 (x, z0_ + alto_p / 2, ancho_p, 0.06)):
            caja(cx, y, cz, sx, 0.06, sz, malla)
        nb = int(ancho_p / 0.12)
        for k in range(1, nb):
            caja(x0_ + k * ancho_p / nb, y, z0_ + alto_p / 2, 0.018, 0.018, alto_p, malla)
        for k in range(1, 5):
            caja(x, y, z0_ + k * alto_p / 5, ancho_p, 0.012, 0.012, malla)
        caja(x - ancho_p / 4, y, z0_ + alto_p + 0.25, 0.08, 0.04, 0.5, acero)       # colgadores
        caja(x + ancho_p / 4, y, z0_ + alto_p + 0.25, 0.08, 0.04, 0.5, acero)
    for k in range(n_p):
        if g['portones_abiertos']:                                    # corridos a los dos lados, apilados
            lado = -1 if k < n_p // 2 else 1
            j = k % (n_p // 2)
            x = lado * (L / 2 + 0.6 + ancho_p / 2)
            y = yc - 0.25 - j * 0.14
        else:
            x = xL + ancho_p * (k + 0.5)
            y = yc - 0.25
        porton(x, y)

    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for m in lista:
        me.materials.append(m)
    uv_metros(me)
    ob = bpy.data.objects.new(nombre, me)
    (coleccion or bpy.context.scene.collection).objects.link(ob)
    if canasta:
        proto_r = prototipo_red()
        ob_r = bpy.data.objects.new('Aro y red', None)
        ob_r.instance_type = 'COLLECTION'; ob_r.instance_collection = proto_r
        ob_r.location = canasta[0]; ob_r.rotation_euler.z = canasta[1]; ob_r.scale = (proto_r['escala'],) * 3
        (coleccion or bpy.context.scene.collection).objects.link(ob_r)
    if extintores:
        proto_e = prototipo_extintor()
        for k, (pos, giro) in enumerate(extintores):
            ex = bpy.data.objects.new(f'Extintor {k + 1}', None)
            ex.instance_type = 'COLLECTION'; ex.instance_collection = proto_e
            ex.location = pos; ex.rotation_euler.z = giro
            (coleccion or bpy.context.scene.collection).objects.link(ex)
    if extractores:
        proto = prototipo_extractor()
        for k, (pos, giro) in enumerate(extractores):
            ex = bpy.data.objects.new(f'Extractor {k + 1}', None)
            ex.instance_type = 'COLLECTION'; ex.instance_collection = proto
            ex.location = pos; ex.rotation_euler.z = giro; ex.scale = (ESCALA_EXTRACTOR,) * 3
            (coleccion or bpy.context.scene.collection).objects.link(ex)
    return ob


# ----------------------------------------------------------------------------- aro y red (modelo de TurboSquid)
# "Basketball net" (TurboSquid 624665, gratis, licencia estándar de TurboSquid): aro rojo con ganchos, red de tela
# y soporte, en OBJ (assets/canasta/red_baloncesto.obj). Va montado en el tablero de la canasta (aro a 3,05 m).
MODELO_RED = ('assets', 'canasta', 'red_baloncesto.obj')
DIAMETRO_ARO = 0.48                               # m, por fuera (el reglamentario es 45 cm por dentro)


def hay_modelo_red():
    return os.path.exists(os.path.join(RAIZ, *MODELO_RED))


def prototipo_red():
    """Importa el OBJ una vez: origen en la cara del soporte que va contra el tablero, a la altura de la parte de
    arriba del aro; el lado del tablero queda hacia -Y del modelo."""
    c = bpy.data.collections.get('Prototipo red')
    if c:
        return c
    c = bpy.data.collections.new('Prototipo red'); bpy.context.scene.collection.children.link(c)
    antes = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=os.path.join(RAIZ, *MODELO_RED))
    nuevos = [o for o in bpy.data.objects if o not in antes]
    aro = mat_simple('Aro rojo', (0.7, 0.06, 0.02), 0.35, 0.6)
    tela = bpy.data.materials.get('Red de tela') or bpy.data.materials.new('Red de tela')
    tela.use_nodes = True
    b = tela.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.85, 0.85, 0.83, 1); b.inputs['Roughness'].default_value = 0.85
    b.inputs['Subsurface Weight'].default_value = 0.15
    metal = mat_simple('Metal pulido', (0.6, 0.62, 0.64), 0.25, 1.0)
    cambio = {'Metal_red': aro, 'Fabric___Gray': tela, 'Metal_Polished_Blue': metal}
    xs, ys, zs = [], [], []
    for o in nuevos:
        for cc in list(o.users_collection):
            cc.objects.unlink(o)
        c.objects.link(o)
        for sl in o.material_slots:
            if sl.material:
                sl.material = cambio.get(sl.material.name.split('.')[0], sl.material)
        if o.name.startswith('Basketball'):                       # aro: lo que no es tela, para medir el diámetro
            me = o.data
            i_aro = [i for i, sl in enumerate(o.material_slots) if sl.material is aro]
            vs = {v for p in me.polygons if p.material_index in i_aro for v in p.vertices}
            pts = [o.matrix_world @ me.vertices[v].co for v in vs]
            xs += [p.x for p in pts]; zs += [p.z for p in pts]
        if o.name.startswith('holder'):
            pts = [o.matrix_world @ v.co for v in o.data.vertices]
            ys += [p.y for p in pts]
        for pol in o.data.polygons:
            pol.use_smooth = True
    ancho = max(xs) - min(xs)
    c.instance_offset = ((max(xs) + min(xs)) / 2, min(ys), max(zs))
    c['escala'] = DIAMETRO_ARO / ancho
    bpy.context.view_layer.layer_collection.children[c.name].exclude = True
    return c


# ----------------------------------------------------------------------------- extintores (modelo de TurboSquid)
# "Fire Extinguisher 3D" de 3Domingas (TurboSquid 1968407, gratis, licencia Royalty Free de TurboSquid), limpiado en
# assets/extintor/extintor.blend: 60 cm de alto, base en el origen, materiales con sus texturas (assets/extintor/textures).
MODELO_EXTINTOR = ('assets', 'extintor', 'extintor.blend')


def hay_modelo_extintor():
    return os.path.exists(os.path.join(RAIZ, *MODELO_EXTINTOR))


def prototipo_extintor():
    c = bpy.data.collections.get('Prototipo extintor')
    if c:
        return c
    c = bpy.data.collections.new('Prototipo extintor'); bpy.context.scene.collection.children.link(c)
    with bpy.data.libraries.load(os.path.join(RAIZ, *MODELO_EXTINTOR), link=False) as (desde, hacia):
        hacia.objects = [n for n in desde.objects if n == 'Extintor']
    for o in hacia.objects:
        c.objects.link(o)
    bpy.context.view_layer.layer_collection.children[c.name].exclude = True
    return c


# ----------------------------------------------------------------------------- extractores (modelo del usuario)
# Ventilador de 120 mm (STEP de FreeCAD que mandó el usuario, convertido a assets/extractor/ventilador_120mm.glb),
# agrandado al tamaño de los extractores del hangar: marco cuadrado de unos 84 cm.
MODELO_EXTRACTOR = ('assets', 'extractor', 'ventilador_120mm.glb')
ESCALA_EXTRACTOR = 7.0


def hay_modelo_extractor():
    return os.path.exists(os.path.join(RAIZ, *MODELO_EXTRACTOR))


def prototipo_extractor():
    c = bpy.data.collections.get('Prototipo extractor')
    if c:
        return c
    c = bpy.data.collections.new('Prototipo extractor'); bpy.context.scene.collection.children.link(c)
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(RAIZ, *MODELO_EXTRACTOR))
    nuevos = [o for o in bpy.data.objects if o not in antes]
    m = bpy.data.materials.get('Extractor negro') or bpy.data.materials.new('Extractor negro')
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.025, 0.025, 0.027, 1); b.inputs['Roughness'].default_value = 0.45
    b.inputs['Metallic'].default_value = 0.3
    for o in nuevos:
        for cc in list(o.users_collection):
            cc.objects.unlink(o)
        c.objects.link(o)
        if o.type == 'MESH':
            o.data.materials.clear(); o.data.materials.append(m)
    c.instance_offset = (0, 0, 0)                 # el modelo ya viene centrado
    bpy.context.view_layer.layer_collection.children[c.name].exclude = True
    return c
