"""Edificio blanco del SAAG (el cuerpo de adelante, hacia la vía), según las fotos tomadas desde la vía
(fotos/5145405563058459129..134) y las del 10-11-2026 de frente, de lado y de atrás.

Se usa en dos lugares:
  - herramientas/escena_edificio.py: escena aparte, solo con el SAAG (poca memoria, para trabajarlo).
  - herramientas/mejoras_blender.py (mejorar_edificios): el mismo edificio dentro del render principal.
Necesita las funciones de mejoras_blender.py (nodos, rampa, ruido, mezclar, mat_simple, mat_lamina_techo, caja_bm, uv_metros, nodos).

En la imagen satelital (referencia_satelital.webp) el SAAG tiene dos cuerpos:
  - Atrás, hacia la plataforma, el del techo rojo (el "saag" del plano, 33 x 15 m). Ese es el galpón abierto
    de los stands y lo trabaja la otra PC: aquí NO se arma.
  - Adelante, hacia la vía, un cuerpo de dos plantas con techo plano (lo que el plano llamaba "saag_anexo").
    Es el de este archivo: fachada blanca con losa y alero gris, dos franjas grises, zócalo y franja vertical
    de piedra laja, marquesina con columnas de piedra que sale de la esquina izquierda, puerta de vidrio con
    paños de reja, emblema del SAAGBA, ventanas con rejas blancas, reflectores LED y el muro manchado de la
    unión con el galpón. construir_entorno_saag() pone lo del lado izquierdo: poste con transformadores,
    planta eléctrica, tanque de agua y pulmón de aire.
El lado derecho no tiene ventanas; la cara de atrás no se ve (pega con el galpón).

Medidas locales: origen en el centro del cuerpo del techo rojo, a nivel del piso. El frente (hacia la vía)
mira a -Y; visto desde la vía, -X es la izquierda (marquesina de entrada) y +X la derecha.
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

SAAG = dict(
    L=33.0, W=15.0,               # planta del galpón del techo rojo (m): referencia de posición, aquí no se arma
    fondo=12.5,                   # fondo del edificio blanco, desde el galpón hasta la fachada de las fotos
    alero=7.3,                    # altura de las paredes; encima va la losa gris con alero (fotos del 10-11-2026)
    vuelo_alero=0.35,             # cuánto sale la losa del techo
    muro_atras=7.9,               # muro manchado de la unión con el galpón (sobresale del techo)
    muro=(0.88, 0.88, 0.86),      # blanco de la fachada
    franjas=(2.7, 4.75),          # alturas de las dos franjas grises horizontales
    zocalo=1.0,                   # alto del zócalo de piedra
    piedra_x=0.593,               # centro de la franja vertical de piedra (fracción del largo desde la izquierda)
    marquesina=(-0.06, 0.2),      # marquesina de entrada: desde/hasta (fracción del largo; <0 sale del edificio)
    vuelo_marquesina=2.6, alto_marquesina=3.5,
    puerta_x=0.125, emblema_x=0.038,
    ventana_pb=(1.85, 1.4, 1.45), ventana_pa=(5.55, 1.4, 1.3),   # (altura del centro, ancho, alto)
    ventanas_pb=(0.335, 0.44, 0.535, 0.66, 0.74, 0.82, 0.91),    # planta baja, frente
    ventanas_pa=(0.335, 0.80),                                    # planta alta, frente
    izq_pb=(3.0,), izq_pa=(3.0, 8.5),                             # lado izquierdo (m desde la fachada)
    reflectores=(0.14, 0.46, 0.75),
    # al lado izquierdo, visto desde la vía (m desde la esquina: x hacia afuera es negativo)
    poste=(-3.5, 5.0),            # desde la fachada
    planta=(-1.4, 2.2),           # desde la cara de atrás (contra la pared del galpón)
    tanque=(-1.5, 5.2), pulmon=(-0.9, 6.8),
)


def oclusion(nt, col, fuerza=0.55, dist=0.5):
    """Oscurece rincones, uniones y lo que queda debajo de los salientes (oclusión ambiental): da contacto y peso."""
    ao = nt.nodes.new('ShaderNodeAmbientOcclusion'); ao.samples = 8
    ao.inputs['Distance'].default_value = dist
    oscuro = mezclar(nt, (1, 1, 1, 1), ao.outputs['AO'], fuerza)
    return mezclar(nt, col, oscuro, 1.0, 'MULTIPLY')


def chorreado(nt, col, fuerza=0.12, escala=1.0, eje='Z'):
    """Chorreados de lluvia y polvo: manchas alargadas en la dirección 'eje' (Z en paredes, X en techos)."""
    tc = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    mp = nt.nodes.new('ShaderNodeMapping')
    largo = {'X': (0.25, 3.0, 3.0), 'Y': (3.0, 0.25, 3.0), 'Z': (3.0, 3.0, 0.25)}[eje]
    mp.inputs['Scale'].default_value = tuple(v * escala for v in largo)
    nt.links.new(tc, mp.inputs['Vector'])
    n = nt.nodes.new('ShaderNodeTexNoise'); n.inputs['Scale'].default_value = 1.0; n.inputs['Detail'].default_value = 6
    nt.links.new(mp.outputs['Vector'], n.inputs['Vector'])
    r = rampa(nt, n.outputs['Fac'], [(0.45, (1, 1, 1, 1)), (0.75, (1 - fuerza, 1 - fuerza * 1.05, 1 - fuerza * 1.2, 1))])
    return mezclar(nt, col, r, 1.0, 'MULTIPLY')


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
    lad.inputs['Color1'].default_value = (0.24, 0.26, 0.28, 1); lad.inputs['Color2'].default_value = (0.44, 0.45, 0.46, 1)
    lad.inputs['Mortar'].default_value = (0.12, 0.12, 0.12, 1)
    nt.links.new(uv, lad.inputs['Vector'])
    vet = nt.nodes.new('ShaderNodeTexNoise'); vet.inputs['Scale'].default_value = 9.0; vet.inputs['Detail'].default_value = 8
    nt.links.new(uv, vet.inputs['Vector'])
    col = mezclar(nt, lad.outputs['Color'], rampa(nt, vet.outputs['Fac'], [(0.35, (0.75, 0.75, 0.74, 1)), (0.7, (1.15, 1.13, 1.1, 1))]), 1.0, 'MULTIPLY')
    nt.links.new(oclusion(nt, chorreado(nt, col, 0.1)), bsdf.inputs['Base Color'])
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
    nt.links.new(oclusion(nt, chorreado(nt, col, 0.1)), bsdf.inputs['Base Color'])
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


def mat_manchado():
    """Concreto con manchas de humedad (muro alto de la unión con el galpón)."""
    m = bpy.data.materials.get('Concreto manchado')
    if m:
        return m
    m = bpy.data.materials.new('Concreto manchado')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    obj = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    col = rampa(nt, ruido(nt, obj, 1.2, 10), [(0.3, (0.32, 0.32, 0.3, 1)), (0.55, (0.55, 0.55, 0.52, 1)), (0.75, (0.75, 0.75, 0.72, 1))])
    nt.links.new(oclusion(nt, chorreado(nt, col, 0.1)), bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.92
    return m


def construir_saag(nombre='saag_anexo', coleccion=None):
    """Arma el edificio blanco del SAAG en coordenadas locales (frente a -Y) y devuelve el objeto."""
    d = SAAG
    L, W, ha = d['L'], d['W'], d['alero']
    x0 = -L / 2                                   # extremo izquierdo visto desde la vía
    fy = -W / 2 - d['fondo']                      # plano de la fachada principal
    yb = -W / 2                                   # cara de atrás: pega con el galpón del techo rojo
    yc, fondo = (fy + yb) / 2, yb - fy
    gris = mat_simple('Gris franjas SAAG', (0.5, 0.51, 0.52), 0.8)
    mats = [mat_pintura(d['muro']),                                            # 0 paredes
            mat_piedra(),                                                      # 1 piedra
            mat_simple('Vidrio ventana', (0.02, 0.03, 0.035), rug=0.05, metal=0.2),   # 2 vidrio
            mat_simple('Aluminio blanco', (0.8, 0.8, 0.79), 0.4, 0.3),         # 3 marcos
            mat_simple('Reja blanca', (0.82, 0.82, 0.8), 0.45, 0.3),            # 4 rejas
            mat_simple('Vidrio afiche', (0.1, 0.28, 0.16), rug=0.15, metal=0.1),  # 5 puerta con afiche verde
            gris,                                                              # 6 alero, franjas, marquesina
            mat_manchado(),                                                    # 7 muro alto de atrás
            mat_simple('Emblema amarillo', (0.85, 0.6, 0.03), 0.4),            # 8
            mat_simple('Emblema oscuro', (0.03, 0.04, 0.07), 0.4),             # 9
            mat_simple('Carcasa reflector', (0.03, 0.03, 0.035), 0.4, 0.5),    # 10
            mat_emision('Luz reflector', (1.0, 0.95, 0.85), 12.0),             # 11
            mat_simple('Piso entrada', (0.55, 0.53, 0.5), 0.7),                # 12
            mat_simple('Tubo PVC', (0.78, 0.78, 0.76), 0.5),                   # 13
            mat_simple('Techo plano', (0.42, 0.43, 0.43), 0.9),                # 14 impermeabilizante gris
            mat_simple('Aire acondicionado', (0.75, 0.75, 0.73), 0.5, 0.2),    # 15
            mat_simple('Tanque azul', (0.02, 0.12, 0.45), 0.45)]               # 16
    bm = bmesh.new()
    caja = lambda cx, cy, cz, sx, sy, sz, i: caja_bm(bm, cx, cy, cz, sx, sy, sz, i)

    def cilindro(cx, cy, z0, radio, alto, i, lados=24):
        c = bmesh.ops.create_cone(bm, cap_ends=True, segments=lados, radius1=radio, radius2=radio, depth=alto)
        bmesh.ops.translate(bm, verts=c['verts'], vec=(cx, cy, z0 + alto / 2))
        for f in {f for v in c['verts'] for f in v.link_faces}:
            f.material_index = i

    # ------------------------------------------------ cuerpo, losa con alero y muro alto de atrás
    caja(0, yc, ha / 2, L, fondo, ha, 0)
    v = d['vuelo_alero']
    caja(0, yc - v / 2, ha + 0.1, L + 2 * v, fondo + v, 0.2, 6)               # losa con alero gris
    caja(0, yc, ha + 0.21, L - 0.2, fondo - 0.4, 0.02, 14)                     # impermeabilizante
    z_m = 7.0                                                                  # por debajo queda el galpón
    caja(0, yb + 0.15, (z_m + d['muro_atras']) / 2, L + 2 * v + 0.2, 0.3, d['muro_atras'] - z_m, 7)
    for k in range(4):                                                         # aires en el techo
        caja(x0 + 5 + k * 6.5, yb - 2.2, ha + 0.6, 1.0, 0.8, 0.8, 15)
    tanque_techo = (L / 2 - 3.5, yb - 2.0, ha + 1.2)                          # tanque de agua sobre su base
    if not hay_modelo_tanque():
        cilindro(*tanque_techo, 0.9, 1.7, 16)
    caja(L / 2 - 3.5, yb - 2.0, ha + 0.7, 2.0, 2.0, 1.0, 13)
    for s in (-0.2, 0.2):                                                      # antena
        caja(L / 2 - 1.0 + s, yb - 0.5, d['muro_atras'] + 1.4, 0.04, 0.04, 2.8, 13)

    # ------------------------------------------------ franjas grises, zócalo y franja de piedra
    for z in d['franjas']:
        caja(0, yc - 0.0075, z, L + 0.03, fondo + 0.015, 0.07, 6)        # no asoman dentro del galpón
    caja(0, yc - 0.015, d['zocalo'] / 2, L + 0.06, fondo + 0.03, d['zocalo'], 1)
    caja(x0 + d['piedra_x'] * L, fy - 0.1, ha / 2, 1.65, 0.22, ha, 1)

    # ------------------------------------------------ ventanas con rejas blancas
    def ventana(u, z, ancho, alto, eje, plano, signo):
        """Ventana en la pared y=plano (eje 'y') o x=plano (eje 'x'), mirando hacia 'signo'."""
        def p(du, dz, su, sz, grosor, sale, i):
            if eje == 'y':
                caja(u + du, plano + signo * sale, z + dz, su, grosor, sz, i)
            else:
                caja(plano + signo * sale, u + du, z + dz, grosor, su, sz, i)
        p(0, 0, ancho + 0.12, alto + 0.12, 0.05, 0.0, 3)
        p(0, 0, ancho, alto, 0.03, 0.02, 2)
        n = max(4, round(ancho / 0.2))
        for k in range(n + 1):
            p(-ancho / 2 + k * ancho / n, 0, 0.03, alto, 0.03, 0.07, 4)
        for k in range(4):
            p(0, -alto / 2 + k * alto / 3, ancho, 0.03, 0.03, 0.07, 4)

    zb, za = d['ventana_pb'], d['ventana_pa']
    for f in d['ventanas_pb']:
        ventana(x0 + f * L, zb[0], zb[1], zb[2], 'y', fy, -1)
    for f in d['ventanas_pa']:
        ventana(x0 + f * L, za[0], za[1], za[2], 'y', fy, -1)
    for u in d['izq_pb']:                                                      # lado izquierdo
        ventana(fy + u, zb[0], zb[1], zb[2], 'x', x0, -1)
    for u in d['izq_pa']:
        ventana(fy + u, za[0], za[1], za[2], 'x', x0, -1)

    # ------------------------------------------------ entrada: marquesina, columnas, puertas y emblema
    m0, m1 = x0 + d['marquesina'][0] * L, x0 + d['marquesina'][1] * L
    vuelo, zm = d['vuelo_marquesina'], d['alto_marquesina']
    caja((m0 + m1) / 2, fy - vuelo / 2, zm + 0.15, m1 - m0, vuelo, 0.3, 6)        # losa
    caja((m0 + m1) / 2, fy - vuelo / 2, zm - 0.01, m1 - m0 - 0.1, vuelo - 0.1, 0.02, 0)   # plafón blanco
    for cx in (m0 + 0.3, m1 - 0.3):
        caja(cx, fy - vuelo + 0.3, zm / 2, 0.5, 0.5, zm, 1)                        # columnas de piedra
    caja((m0 + m1) / 2, fy - vuelo / 2, 0.075, m1 - m0, vuelo, 0.15, 12)         # piso de la entrada
    ux = x0 + d['puerta_x'] * L
    caja(ux, fy - 0.03, 1.3, 3.75, 0.08, 2.6, 3)                                   # marco de todo el conjunto
    caja(ux, fy - 0.06, 1.25, 1.1, 0.04, 2.45, 5)                                  # puerta de vidrio con afiche
    for s in (-1, 1):                                                              # paños con reja a los lados
        cx = ux + s * 1.2
        caja(cx, fy - 0.06, 1.25, 1.15, 0.04, 2.45, 2)
        for k in range(7):
            caja(cx - 0.5 + k * 1.0 / 6, fy - 0.1, 1.25, 0.035, 0.035, 2.45, 4)
        for z in (0.35, 0.9, 1.6, 2.3):
            caja(cx, fy - 0.1, z, 1.1, 0.035, 0.035, 4)
        caja(ux + s * 0.58, fy - 0.08, 1.25, 0.08, 0.08, 2.5, 3)                   # parales
    caja(ux, fy - 0.03, 0.04, 1.3, 0.3, 0.08, 12)                                  # escalón
    # emblema SAAGBA: escudo redondo con alas amarillas
    ex, ez = x0 + d['emblema_x'] * L, 2.1
    for radio, prof, i in ((0.36, 0.05, 9), (0.3, 0.07, 8), (0.18, 0.09, 9)):
        c = bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=radio, radius2=radio, depth=prof)
        bmesh.ops.rotate(bm, verts=c['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
        bmesh.ops.translate(bm, verts=c['verts'], vec=(ex, fy - prof / 2, ez))
        for cara in {f for vv in c['verts'] for f in vv.link_faces}:
            cara.material_index = i
    for s in (-1, 1):
        for k, (largo, alto) in enumerate(((0.55, 0.1), (0.45, 0.08), (0.32, 0.07))):
            caja(ex + s * (0.3 + largo / 2), fy - 0.03, ez + 0.06 - k * 0.11, largo, 0.04, alto, 8)

    # ------------------------------------------------ reflectores LED cuadrados bajo el alero
    def reflector(x, y, sx, sy):
        caja(x, y, ha - 0.55, sx * 0.45 + sy * 0.12, sy * 0.45 + sx * 0.12, 0.38, 10)
        caja(x + sy * 0.0, y, ha - 0.55, sx * 0.36 + sy * 0.13, sy * 0.36 + sx * 0.13, 0.3, 11)
    for f in d['reflectores']:
        reflector(x0 + f * L, fy - 0.07, 1, 0)
    reflector(x0 - 0.07, fy + 6.0, 0, 1)
    reflector(L / 2 + 0.07, fy + 3.5, 0, 1)

    # ------------------------------------------------ tubos: conducto en la fachada y bajantes a los lados
    caja(x0 + 0.22 * L, fy - 0.04, (3.9 + ha) / 2, 0.05, 0.05, ha - 3.9, 13)
    for x in (x0 - 0.07, L / 2 + 0.07):
        caja(x, yb - 0.35, ha / 2, 0.11, 0.11, ha, 13)

    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    uv_metros(me)
    ob = bpy.data.objects.new(nombre, me)
    (coleccion or bpy.context.scene.collection).objects.link(ob)
    if hay_modelo_tanque():                       # tanque real (modelo pintado de azul), hijo del edificio
        t = bpy.data.objects.new('Tanque de agua techo', None)
        t.instance_type = 'COLLECTION'; t.instance_collection = prototipo_tanque()
        t.location = tanque_techo; t.scale = (escala_tanque(),) * 3
        (coleccion or bpy.context.scene.collection).objects.link(t); t.parent = ob
    return ob


# ----------------------------------------------------------------------------- tanque de agua (modelo real)
MODELO_TANQUE = ('assets', 'tanque', 'tanque_agua_azul.glb')
DIAMETRO_TANQUE = 1.8                             # m: el del techo (como el de las fotos, de unos 2000 L)


def hay_modelo_tanque():
    return os.path.exists(os.path.join(RAIZ, *MODELO_TANQUE))


def prototipo_tanque():
    """Importa el tanque una vez y lo deja como colección oculta, con el origen en el centro de la base."""
    c = bpy.data.collections.get('Prototipo tanque')
    if c:
        return c
    c = bpy.data.collections.new('Prototipo tanque'); bpy.context.scene.collection.children.link(c)
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(RAIZ, *MODELO_TANQUE))
    nuevos = [o for o in bpy.data.objects if o not in antes]
    for o in nuevos:
        for cc in list(o.users_collection):
            cc.objects.unlink(o)
        c.objects.link(o)
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(v) for o in nuevos if o.type == 'MESH' for v in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c.instance_offset = ((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z)
    c['ancho'] = max(mx.x - mn.x, mx.y - mn.y)
    bpy.context.view_layer.layer_collection.children[c.name].exclude = True
    return c


def escala_tanque():
    return DIAMETRO_TANQUE / max(0.01, prototipo_tanque()['ancho'])


def construir_entorno_saag(nombre='saag_entorno', coleccion=None):
    """Lo que está al lado izquierdo del edificio visto desde la vía (fotos del 10-11-2026):
    poste de luz con tres transformadores, planta eléctrica bajo un techito de lámina roja,
    tanque de agua azul y pulmón de aire verde, contra la pared del galpón."""
    d = SAAG
    L, W = d['L'], d['W']
    x0, fy, yb = -L / 2, -W / 2 - d['fondo'], -W / 2
    mats = [mat_simple('Concreto base', (0.5, 0.49, 0.47), 0.9),               # 0
            mat_simple('Metal galvanizado', (0.6, 0.62, 0.63), 0.35, 1.0),     # 1
            mat_simple('Pintura negra', (0.03, 0.03, 0.03), 0.5),              # 2
            mat_simple('Transformador', (0.75, 0.76, 0.76), 0.45, 0.4),        # 3
            mat_simple('Planta electrica', (0.82, 0.82, 0.8), 0.4, 0.2),       # 4
            mat_lamina_techo((0.45, 0.12, 0.08)),                              # 5
            mat_simple('Tanque azul', (0.02, 0.12, 0.45), 0.45),               # 6
            mat_simple('Pulmon verde', (0.2, 0.27, 0.2), 0.5, 0.4),            # 7
            mat_simple('Rejilla', (0.1, 0.1, 0.1), 0.5)]                       # 8
    bm = bmesh.new()
    caja = lambda cx, cy, cz, sx, sy, sz, i: caja_bm(bm, cx, cy, cz, sx, sy, sz, i)

    def cilindro(cx, cy, z0, radio, alto, i, lados=24):
        c = bmesh.ops.create_cone(bm, cap_ends=True, segments=lados, radius1=radio, radius2=radio, depth=alto)
        bmesh.ops.translate(bm, verts=c['verts'], vec=(cx, cy, z0 + alto / 2))
        for f in {f for v in c['verts'] for f in v.link_faces}:
            f.material_index = i

    # poste: abajo pintado de negro, arriba galvanizado, cruceta y tres transformadores
    px_, py_ = x0 + d['poste'][0], fy + d['poste'][1]
    cilindro(px_, py_, 0, 0.13, 1.6, 2, 16)
    cilindro(px_, py_, 1.6, 0.12, 9.4, 1, 16)
    caja(px_, py_, 10.4, 2.4, 0.1, 0.1, 1)
    caja(px_, py_, 9.0, 0.1, 1.6, 0.1, 1)
    for k, (dx, dy) in enumerate(((0.45, 0.0), (-0.3, 0.35), (-0.3, -0.35))):
        cilindro(px_ + dx, py_ + dy, 7.4, 0.28, 0.85, 3, 16)
        caja(px_ + dx * 0.5, py_ + dy * 0.5, 7.8, abs(dx) + 0.1, abs(dy) + 0.1, 0.08, 1)
    # planta eléctrica sobre su base, con techito de lámina roja
    gx, gy = x0 + d['planta'][0], yb + d['planta'][1]
    caja(gx, gy, 0.12, 1.7, 3.6, 0.24, 0)
    caja(gx, gy, 0.5, 1.3, 3.2, 0.5, 2)
    caja(gx, gy, 1.35, 1.3, 3.2, 1.2, 4)
    for dy in (-0.9, 0.3):
        caja(gx - 0.66, gy + dy, 1.6, 0.02, 0.7, 0.3, 8)
    for dy in (-0.75, 0.75):
        for dx in (-0.8, 0.8):
            caja(gx + dx, gy + dy * 2, 1.25, 0.06, 0.06, 2.5, 1)
    techito = bm.verts.new((gx - 1.0, gy - 2.0, 2.35)), bm.verts.new((gx - 1.0, gy + 2.0, 2.35)), \
        bm.verts.new((gx + 1.0, gy + 2.0, 2.6)), bm.verts.new((gx + 1.0, gy - 2.0, 2.6))
    f = bm.faces.new(techito); f.material_index = 5
    bmesh.ops.solidify(bm, geom=[f], thickness=0.03)
    # tanque azul y pulmón de aire
    tx, ty = x0 + d['tanque'][0], yb + d['tanque'][1]
    caja(tx, ty, 0.08, 2.2, 2.2, 0.16, 0)
    cilindro(tx, ty, 0.16, 0.95, 1.75, 6, 32)
    cilindro(tx, ty, 1.91, 0.75, 0.15, 6, 32)
    ax, ay = x0 + d['pulmon'][0], yb + d['pulmon'][1]
    cilindro(ax, ay, 0.15, 0.32, 1.35, 7, 20)
    for k in range(3):
        caja(ax + 0.25 * math.cos(k * 2.1), ay + 0.25 * math.sin(k * 2.1), 0.08, 0.05, 0.05, 0.16, 2)

    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    uv_metros(me)
    ob = bpy.data.objects.new(nombre, me)
    (coleccion or bpy.context.scene.collection).objects.link(ob)
    return ob
