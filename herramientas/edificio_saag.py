"""Edificio blanco del SAAG (el cuerpo de adelante, hacia la vía), según las fotos tomadas desde la vía
(fotos/5145405563058459129..134).

Se usa en dos lugares:
  - herramientas/escena_edificio.py: escena aparte, solo con el SAAG (poca memoria, para trabajarlo).
  - herramientas/mejoras_blender.py (mejorar_edificios): el mismo edificio dentro del render principal.
Necesita las funciones de mejoras_blender.py (nodos, rampa, ruido, mezclar, mat_simple, mat_lamina_techo, caja_bm, uv_metros, nodos).

En la imagen satelital (referencia_satelital.webp) el SAAG tiene dos cuerpos:
  - Atrás, hacia la plataforma, el del techo rojo (el "saag" del plano, 33 x 15 m). Ese es el galpón abierto
    de los stands y lo trabaja la otra PC: aquí NO se arma.
  - Adelante, hacia la vía, un cuerpo de dos plantas con techo plano gris (lo que el plano llamaba
    "saag_anexo"). Es el de este archivo y el que sale en las fotos: fachada blanca con pretil recto,
    zócalo y franja vertical de piedra gris, marquesina de concreto con columnas de piedra sobre la entrada,
    puerta de vidrio verde, emblema circular amarillo, ventanas con rejas blancas y reflectores en lo alto.
Los lados y la cara de atrás no salen en las fotos: son supuestos.

Medidas locales: origen en el centro del cuerpo del techo rojo, a nivel del piso. El frente (hacia la vía)
mira a -Y; visto desde la vía, -X es la izquierda (marquesina de entrada) y +X la derecha.
"""
import math

import bmesh
import bpy
from mathutils import Matrix

SAAG = dict(
    L=33.0, W=15.0,               # planta del cuerpo del techo rojo (m): solo como referencia de posición
    fondo_frente=12.5,            # fondo del cuerpo de adelante (techo plano), hasta la fachada de las fotos
    alero=6.6,                    # cuerpo de adelante: altura de las paredes hasta el techo plano
    pretil=7.5,                   # cuerpo de adelante: borde superior del pretil (lo que se ve desde la vía)
    muro=(0.88, 0.88, 0.86),      # blanco de la fachada
    piedra_x=0.58,                # posición de la franja de piedra (fracción del largo, desde la izquierda)
    marquesina=(-0.06, 0.27),     # marquesina de entrada: desde/hasta (fracción del largo; <0 sale del edificio)
    puerta_x=0.17, emblema_x=0.10,
    ventanas_pb=(0.35, 0.44, 0.52, 0.66, 0.74, 0.82, 0.91),   # planta baja, frente
    ventanas_pa=(0.36, 0.80),                                         # planta alta, frente
    reflectores=(0.30, 0.50, 0.75),
)


def mat_piedra():
    """Piedra laja gris en hiladas irregulares (franja vertical, columnas y zócalo)."""
    m = bpy.data.materials.get('Piedra laja')
    if m:
        return m
    m = bpy.data.materials.new('Piedra laja')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    uv = nt.nodes.new('ShaderNodeTexCoord').outputs['UV']
    lad = nt.nodes.new('ShaderNodeTexBrick')
    lad.offset = 0.37; lad.offset_frequency = 1; lad.squash = 1.0
    lad.inputs['Scale'].default_value = 1.0
    lad.inputs['Brick Width'].default_value = 0.38; lad.inputs['Row Height'].default_value = 0.11
    lad.inputs['Mortar Size'].default_value = 0.008; lad.inputs['Bias'].default_value = 0.0
    lad.inputs['Color1'].default_value = (0.30, 0.30, 0.29, 1); lad.inputs['Color2'].default_value = (0.46, 0.45, 0.43, 1)
    lad.inputs['Mortar'].default_value = (0.12, 0.12, 0.12, 1)
    nt.links.new(uv, lad.inputs['Vector'])
    vet = nt.nodes.new('ShaderNodeTexNoise'); vet.inputs['Scale'].default_value = 9.0; vet.inputs['Detail'].default_value = 8
    nt.links.new(uv, vet.inputs['Vector'])
    col = mezclar(nt, lad.outputs['Color'], rampa(nt, vet.outputs['Fac'], [(0.35, (0.75, 0.75, 0.74, 1)), (0.7, (1.15, 1.13, 1.1, 1))]), 1.0, 'MULTIPLY')
    nt.links.new(col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.85
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.6; bump.inputs['Distance'].default_value = 0.01
    alt = mezclar(nt, (1, 1, 1, 1), vet.outputs['Fac'], 0.4, 'MULTIPLY')
    hilada = nt.nodes.new('ShaderNodeMath'); hilada.operation = 'MULTIPLY'
    nt.links.new(lad.outputs['Fac'], hilada.inputs[0]); hilada.inputs[1].default_value = -1.0
    suma = nt.nodes.new('ShaderNodeMath'); suma.operation = 'ADD'
    nt.links.new(hilada.outputs[0], suma.inputs[0])
    gris = nt.nodes.new('ShaderNodeRGBToBW'); nt.links.new(alt, gris.inputs[0]); nt.links.new(gris.outputs[0], suma.inputs[1])
    nt.links.new(suma.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def mat_pintura(color):
    """Friso liso pintado de blanco (como en las fotos), con manchas suaves y la suciedad que sube del piso."""
    m = bpy.data.materials.get('Pintura SAAG')
    if m:
        return m
    m = bpy.data.materials.new('Pintura SAAG')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    obj = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(obj, sep.inputs[0])
    sucio = rampa(nt, sep.outputs['Z'], [(0.0, (0.72, 0.68, 0.62, 1)), (0.7, (1, 1, 1, 1))])
    manchas = rampa(nt, ruido(nt, obj, 0.35, 6), [(0.4, (1, 1, 1, 1)), (0.75, (0.93, 0.93, 0.91, 1))])
    col = mezclar(nt, mezclar(nt, color + (1,), sucio, 1.0, 'MULTIPLY'), manchas, 1.0, 'MULTIPLY')
    nt.links.new(col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.88
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.08; bump.inputs['Distance'].default_value = 0.002
    nt.links.new(ruido(nt, obj, 40.0, 4), bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def mat_emision(nombre, color, fuerza):
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = bpy.data.materials.new(nombre); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = color + (1,)
    b.inputs['Emission Color'].default_value = color + (1,); b.inputs['Emission Strength'].default_value = fuerza
    b.inputs['Roughness'].default_value = 0.2
    return m


def construir_saag(nombre='saag', coleccion=None):
    """Arma el edificio blanco del SAAG en coordenadas locales (frente a -Y) y devuelve el objeto."""
    d = SAAG
    L, W, ha, hp = d['L'], d['W'], d['alero'], d['pretil']
    x0 = -L / 2                                   # extremo izquierdo visto desde la vía
    fy = -W / 2 - d['fondo_frente']               # plano de la fachada principal
    mats = [mat_pintura(d['muro']),                                            # 0 paredes
            mat_piedra(),                                                      # 1 piedra
            mat_simple('Vidrio ventana', (0.02, 0.03, 0.035), rug=0.05, metal=0.2),   # 2 vidrio
            mat_simple('Aluminio', (0.78, 0.79, 0.8), 0.35, 0.8),              # 3 marcos
            mat_simple('Reja blanca', (0.82, 0.82, 0.8), 0.45, 0.3),            # 4 rejas
            mat_simple('Vidrio verde', (0.03, 0.16, 0.11), rug=0.05, metal=0.3),  # 5 puerta
            mat_simple('Concreto marquesina', (0.8, 0.8, 0.78), 0.8),          # 6 marquesina y pretil
            mat_simple('Concreto marquesina', (0.8, 0.8, 0.78), 0.8),          # 7 (libre)
            mat_simple('Emblema amarillo', (0.85, 0.6, 0.03), 0.4),            # 8
            mat_simple('Emblema oscuro', (0.03, 0.04, 0.07), 0.4),             # 9
            mat_simple('Reflector', (0.15, 0.15, 0.16), 0.4, 0.6),             # 10
            mat_emision('Luz reflector', (1.0, 0.95, 0.85), 40.0),             # 11
            mat_simple('Piso entrada', (0.55, 0.53, 0.5), 0.7),                # 12
            mat_simple('Bajante', (0.7, 0.7, 0.68), 0.5, 0.3),                 # 13
            mat_simple('Techo plano', (0.42, 0.43, 0.43), 0.9),                # 14 impermeabilizante gris
            mat_simple('Aire acondicionado', (0.75, 0.75, 0.73), 0.5, 0.2)]    # 15
    bm = bmesh.new()
    caja = lambda cx, cy, cz, sx, sy, sz, i: caja_bm(bm, cx, cy, cz, sx, sy, sz, i)

    # ------------------------------------------------ cuerpo de adelante: paredes, techo plano y pretil
    yb = -W / 2                                   # la cara de atrás pega con el galpón del techo rojo
    yc, fondo = (fy + yb) / 2, yb - fy
    caja(0, yc, ha / 2, L, fondo, ha, 0)
    caja(0, yc, ha + 0.03, L - 0.4, fondo - 0.4, 0.06, 14)
    e = 0.2                                       # espesor del pretil (las piezas no se solapan: caras
                                                  # coincidentes salen negras en Cycles)
    for (sx, sy, cx, cy) in ((L, e, 0, fy + e / 2), (L, e, 0, yb - e / 2),
                             (e, fondo - 2 * e, x0 + e / 2, yc), (e, fondo - 2 * e, L / 2 - e / 2, yc)):
        caja(cx, cy, (ha + hp) / 2, sx, sy, hp - ha, 0)
    for (sx, sy, cx, cy) in ((L + 0.06, 0.26, 0, fy - 0.01), (L + 0.06, 0.26, 0, yb + 0.01),
                             (0.26, fondo - 0.2, x0 - 0.01, yc), (0.26, fondo - 0.2, L / 2 + 0.01, yc)):
        caja(cx, cy, hp + 0.03, sx, sy, 0.06, 6)                               # remate del pretil
    for k in range(4):                                                         # aires en el techo plano
        caja(x0 + 6 + k * 7, yc + 1.5, ha + 0.45, 1.0, 0.8, 0.8, 15)

    # ------------------------------------------------ zócalo y franja de piedra
    caja(0, yc, 0.22, L + 0.06, fondo + 0.06, 0.44, 1)
    px_ = x0 + d['piedra_x'] * L
    caja(px_, fy - 0.12, (hp + 0.1) / 2, 1.65, 0.26, hp + 0.1, 1)

    # ------------------------------------------------ ventanas con rejas
    def ventana(u, z, ancho, alto, eje, plano, signo):
        """Ventana en la pared del plano y=plano (eje 'y') o x=plano (eje 'x'), mirando hacia 'signo'.
        u = posición a lo largo de la pared, z = centro. Marco, vidrio, alféizar y reja blanca cuadriculada."""
        def p(du, dz, su, sz, grosor, sale, i):
            if eje == 'y':
                caja(u + du, plano + signo * sale, z + dz, su, grosor, sz, i)
            else:
                caja(plano + signo * sale, u + du, z + dz, grosor, su, sz, i)
        p(0, 0, ancho + 0.12, alto + 0.12, 0.05, 0.0, 3)
        p(0, 0, ancho, alto, 0.03, 0.02, 2)
        p(0, -alto / 2 - 0.06, ancho + 0.2, 0.08, 0.16, 0.05, 6)
        n = max(3, round(ancho / 0.16))
        for k in range(n + 1):
            p(-ancho / 2 + k * ancho / n, 0, 0.022, alto, 0.022, 0.07, 4)
        for k in range(4):
            p(0, -alto / 2 + k * alto / 3, ancho, 0.022, 0.022, 0.07, 4)

    for f in d['ventanas_pb']:                                                 # fachada de las fotos
        ventana(x0 + f * L, 1.25, 1.6, 1.5, 'y', fy, -1)
    for f in d['ventanas_pa']:
        ventana(x0 + f * L, 5.35, 1.3, 1.5, 'y', fy, -1)
    for s in (-1, 1):                                                          # lados (supuestos)
        for u in (fy + 3.5, fy + 9.0):
            ventana(u, 1.25, 1.6, 1.5, 'x', s * L / 2, s)
            ventana(u, 5.35, 1.3, 1.5, 'x', s * L / 2, s)

    # ------------------------------------------------ entrada: marquesina, columnas, puerta y emblema
    m0, m1 = x0 + d['marquesina'][0] * L, x0 + d['marquesina'][1] * L
    vuelo = 2.6
    caja((m0 + m1) / 2, fy - vuelo / 2, 3.12, m1 - m0, vuelo, 0.28, 6)           # losa
    caja((m0 + m1) / 2, fy - vuelo + 0.02, 3.0, m1 - m0 + 0.04, 0.08, 0.5, 6)     # frente de la losa
    for cx in (m1 - 0.35, x0 + 0.3):
        caja(cx, fy - vuelo + 0.35, 1.5, 0.55, 0.55, 3.0, 1)                       # columnas de piedra
    caja(m0 + 0.1, fy - vuelo + 0.15, 1.5, 0.1, 0.1, 3.0, 3)                       # paral metálico del extremo
    caja((m0 + m1) / 2, fy - vuelo / 2, 0.075, m1 - m0, vuelo, 0.15, 12)          # piso de la entrada
    ux = x0 + d['puerta_x'] * L
    caja(ux, fy - 0.03, 1.3, 2.0, 0.08, 2.6, 3)                                    # marco
    caja(ux, fy - 0.06, 1.25, 1.8, 0.04, 2.4, 5)                                   # vidrio verde
    caja(ux, fy - 0.09, 1.25, 0.05, 0.03, 2.4, 3)                                  # junta de las dos hojas
    caja(ux, fy - 0.09, 1.1, 1.8, 0.03, 0.05, 3)
    for s in (-1, 1):
        caja(ux + s * 0.25, fy - 0.11, 1.15, 0.03, 0.04, 0.35, 3)                  # haladeras
    caja(ux + 1.55, fy - 0.03, 1.3, 0.9, 0.08, 2.6, 3)                             # paño fijo al lado
    caja(ux + 1.55, fy - 0.06, 1.3, 0.75, 0.04, 2.45, 5)
    ex = x0 + d['emblema_x'] * L
    for radio, prof, i in ((0.58, 0.04, 8), (0.48, 0.06, 9), (0.33, 0.08, 8), (0.16, 0.1, 9)):
        c = bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=radio, radius2=radio, depth=prof)
        bmesh.ops.rotate(bm, verts=c['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
        bmesh.ops.translate(bm, verts=c['verts'], vec=(ex, fy - prof / 2, 2.05))
        for cara in {f for vv in c['verts'] for f in vv.link_faces}:
            cara.material_index = i

    # ------------------------------------------------ reflectores en lo alto del frente
    for f in d['reflectores']:
        x = x0 + f * L
        caja(x, fy - 0.15, hp - 0.25, 0.08, 0.3, 0.08, 10)                        # brazo
        caja(x, fy - 0.35, hp - 0.35, 0.36, 0.14, 0.26, 10)                       # carcasa
        caja(x, fy - 0.43, hp - 0.35, 0.3, 0.02, 0.2, 11)                         # vidrio encendido

    # ------------------------------------------------ bajantes de agua en las esquinas del frente
    for x in (x0 + 0.35, L / 2 - 0.35):
        caja(x, fy - 0.08, ha / 2, 0.1, 0.1, ha, 13)

    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    uv_metros(me)
    ob = bpy.data.objects.new(nombre, me)
    (coleccion or bpy.context.scene.collection).objects.link(ob)
    return ob
