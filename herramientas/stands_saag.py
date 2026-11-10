"""Los 4 stands de los proyectos de la AMB dentro del hangar del SAAG (escena aparte), con su decoración.

Los stands se arman con el mismo código del render principal (realismo_blender.stands_amb, sin cambiarlo): aquí solo
se le dan los puestos donde va cada uno. Dos stands por nave, contra el fondo (el edificio blanco) y abiertos hacia
la plataforma:
    nave izquierda: aeronave ultraligera ULV (afuera) y Cóndor (al medio)
    nave derecha:   disparo automatizado Igla-S (al medio) y simulador Igla-S (afuera)
Decoración: alfombra roja en T por nave, tótems azul marino "AMB" a la entrada, letrero colgante
"PROYECTOS TECNOLÓGICOS AMB" sobre cada nave, letrero principal
"PROYECTOS TECNOLÓGICOS AMB" colgado de la viga del frente y plantas ornamentales reales de Poly Haven (CC0):
árbol del dinero (pachira) en matero negro, planta de hojas anchas en matero de barro y anturios en matero blanco.

Se ejecuta en un espacio aparte donde ya se cargaron mejoras_blender.py, edificio_saag.py, galpon_saag.py y
realismo_blender.py (escena_edificio.py lo hace).
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

STANDS_SAAG = dict(
    # (x del punto de referencia en la entrada, y del centro de los stands, [(stand, x del centro), ...]).
    # La pared de fondo de cada stand queda 2,45 m detrás del centro, delante del edificio blanco; en la nave
    # izquierda van un poco más adelante para no tapar la escalera del hangar.
    naves=[
        (8.6, -4.45, [('igla', 11.6), ('mecanismo', 4.5)]),
        (-8.6, -3.7, [('ultraligero', -10.5), ('juego', -4.2)]),
    ],
    ev_camaras=3.0,               # exposición extra de las vistas de los stands (adentro hay menos luz)
    titulo='PROYECTOS TECNOLÓGICOS AMB',            # letreros colgantes de cada nave
    letrero='PROYECTOS TECNOLÓGICOS AMB',           # letrero principal colgado de la viga del frente
)


def _barra(bm, p1, p2, ancho, alto, i, arriba=(0, 0, 1)):
    p1, p2 = Vector(p1), Vector(p2)
    dv = p2 - p1
    r = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(dv.length, ancho, alto), verts=r['verts'])
    bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=dv.normalized().to_track_quat('X', 'Z').to_matrix())
    bmesh.ops.translate(bm, vec=(p1 + p2) / 2, verts=r['verts'])
    for f in {f for v in r['verts'] for f in v.link_faces}:
        f.material_index = i


def _objeto(nombre, bm, mats, col):
    me = bpy.data.meshes.new(nombre)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(nombre, me)
    col.objects.link(ob)
    return ob


def _puestos(y, puestos, col):
    """Piso y pared de fondo falsos, como los del visor, para que stands_amb() sepa dónde y hacia dónde va cada stand."""
    m158 = bpy.data.materials.get('Material_158') or bpy.data.materials.new('Material_158')
    m158.use_nodes = True
    for _, x in puestos:
        C = Vector((x, y, 0.0))
        bm = bmesh.new(); caja_bm(bm, 0, 0, 0, 5.8, 5.0, 0.02, 0)
        piso = _objeto('Puesto', bm, [m158], col); piso.location = C
        bm = bmesh.new(); caja_bm(bm, 0, 0, 0, 5.8, 0.08, 2.5, 0)
        fondo = _objeto('Fondo puesto', bm, [mat_simple('Fondo puesto', (0.5, 0.5, 0.5))], col); fondo.location = C + Vector((0, -2.45, 1.25))
    bpy.context.view_layer.update()


def colocar_stands_saag(col):
    originales = list(PROYECTOS_AMB)
    por_clave = {p['clave']: p for p in originales}
    for x_ref, y, puestos in STANDS_SAAG['naves']:
        _puestos(y, puestos, col)
        # el punto de referencia (la "cámara de la entrada" de stands_amb) decide el orden y de qué lado va la
        # pared lateral de cada stand: del lado de afuera de la nave, así los dos quedan abiertos hacia la alfombra
        cd = bpy.data.cameras.new('ref'); ref = bpy.data.objects.new('Cam_proyectos', cd)
        escena.collection.objects.link(ref); ref.location = (x_ref, 14.0, 1.7)
        bpy.context.view_layer.update()
        claves = [c for c, _ in puestos]
        PROYECTOS_AMB[:] = [por_clave[c] for c in claves] + [p for p in originales if p['clave'] not in claves]
        stands_amb()
        bpy.data.objects.remove(ref, do_unlink=True)
    PROYECTOS_AMB[:] = originales
    # vistas que stands_amb() arma para el pasillo del render principal: aquí no sirven
    for o in list(bpy.data.objects):
        if o.name.startswith(('Cam_stands', 'Recorrido')) or (o.type == 'CAMERA' and '.0' in o.name):
            bpy.data.objects.remove(o, do_unlink=True)
    for o in bpy.data.objects:
        if o.type == 'CAMERA' and o.name.startswith(('Cam_stand_', 'Cam_frente_', 'Cam_lateral_', 'Cam_detalle_')):
            o['exposicion'] = STANDS_SAAG['ev_camaras']
    decoracion(col)
    camara_recorrido_saag()


# ----------------------------------------------------------------------------- video del recorrido por los stands
RECORRIDO_SAAG_FPS = 24
# (segundo, posición de la cámara, punto al que mira). Entra desde la plataforma por la alfombra de la nave derecha
# (Igla-S y disparo automatizado), cruza entre las columnas del medio a la nave izquierda (Cóndor y ULV) y sale
# hacia atrás para la vista general con el letrero. Las posiciones evitan columnas, tótems, plantas y materos.
RECORRIDO_SAAG = [
    (0.0, (0.0, 24.0, 5.0), (0.0, 0.0, 2.6)),
    (4.0, (8.25, 12.0, 2.2), (8.25, -2.0, 1.8)),
    (8.0, (8.8, 3.0, 1.65), (11.6, -4.0, 1.4)),
    (11.0, (7.6, 1.0, 1.65), (4.5, -4.0, 1.4)),
    (14.5, (2.5, 0.6, 1.7), (-3.0, -2.0, 1.5)),
    (17.5, (-5.0, 1.8, 1.65), (-4.2, -3.5, 1.4)),
    (20.5, (-8.5, 1.5, 1.65), (-10.5, -3.0, 1.1)),
    (23.5, (-8.25, 6.0, 2.6), (-6.0, -3.0, 1.2)),
    (28.0, (0.0, 20.0, 5.5), (0.0, -1.0, 2.0)),
]
EV_AFUERA, EV_ADENTRO = 1.0, 2.5                  # exposición extra afuera y adentro del hangar


def camara_recorrido_saag():
    """Cámara animada 'Recorrido SAAG' (sin el prefijo Cam_: no entra en las vistas fijas), con la mira en un Empty
    (restricción Track To). La exposición (más alta adentro del hangar) la anima recorrido_saag.py al renderizar,
    para no tocar las vistas fijas."""
    cd = bpy.data.cameras.new('Recorrido SAAG'); cd.sensor_fit = 'HORIZONTAL'; cd.lens = 18
    cd.clip_start = 0.05; cd.clip_end = 3000
    cam = bpy.data.objects.new('Recorrido SAAG', cd); escena.collection.objects.link(cam)
    mira = bpy.data.objects.new('Recorrido SAAG mira', None); escena.collection.objects.link(mira)
    tr = cam.constraints.new('TRACK_TO'); tr.target = mira; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
    claves_ev = []
    for seg, pos, apunta in RECORRIDO_SAAG:
        f = 1 + round(seg * RECORRIDO_SAAG_FPS)
        cam.location = pos; cam.keyframe_insert('location', frame=f)
        mira.location = apunta; mira.keyframe_insert('location', frame=f)
        adentro = -7.5 < pos[1] < 7.0
        claves_ev.append((f, EV_ADENTRO if adentro else EV_AFUERA))
    for ob in (cam, mira):
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'; kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    cam['resolucion'] = (1920, 1080)
    cam['ev_claves'] = [v for c in claves_ev for v in c]      # (cuadro, EV extra) en pares: recorrido_saag.py los anima
    escena.render.fps = RECORRIDO_SAAG_FPS
    escena.frame_start, escena.frame_end = 1, 1 + round(RECORRIDO_SAAG[-1][0] * RECORRIDO_SAAG_FPS)
    print('Recorrido SAAG:', escena.frame_end, 'cuadros a', RECORRIDO_SAAG_FPS, 'cuadros por segundo')


# ----------------------------------------------------------------------------- decoración
def _mat_alfombra():
    m = bpy.data.materials.get('Alfombra roja')
    if m:
        return m
    m = bpy.data.materials.new('Alfombra roja')
    nt, b, out = nodos(m); nt.links.new(b.outputs[0], out.inputs[0])
    tc = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    nt.links.new(rampa(nt, ruido(nt, tc, 3.0, 6), [(0.3, (0.3, 0.012, 0.018, 1)), (0.7, (0.42, 0.02, 0.028, 1))]), b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.95
    bu = nt.nodes.new('ShaderNodeBump'); bu.inputs['Strength'].default_value = 0.25
    nt.links.new(ruido(nt, tc, 150.0, 2), bu.inputs['Height']); nt.links.new(bu.outputs[0], b.inputs['Normal'])
    return m


def decoracion(col):
    L, W = SAAG['L'], SAAG['W']
    yF = W / 2
    navy = mat_simple('Letrero azul marino', (0.006, 0.013, 0.035), 0.45)
    dorado = mat_simple('Dorado letrero', (0.62, 0.4, 0.06), 0.35, 0.3)
    blanco = mat_simple('Texto blanco stand', (0.85, 0.85, 0.85), 0.4)
    negro = mat_simple('Matero negro', (0.02, 0.02, 0.022), 0.4)
    blanco_m = mat_simple('Matero blanco', (0.8, 0.8, 0.78), 0.35)
    tierra = mat_simple('Tierra matero', (0.08, 0.05, 0.03), 0.95)
    hoja = mat_simple('Hoja palma', (0.045, 0.16, 0.035), 0.55)
    arbusto = mat_simple('Arbusto', (0.05, 0.18, 0.03), 0.8)
    cable = mat_simple('Cable acero', (0.5, 0.5, 0.5), 0.4, 0.9)
    alfombra = _mat_alfombra()
    condensada = _fuente_archivo('AGENCYB.TTF')
    negrita = _fuente_archivo('arialbd.ttf')
    deco = Stand('Decoracion AMB', Matrix.Identity(4), 1, col)
    for x_ref, y_centro, puestos in STANDS_SAAG['naves']:
        y_stands = y_centro + 2.5                         # frente de los stands
        c = math.copysign(L / 4, x_ref)                   # centro de la nave
        xs = [x for _, x in puestos]
        # alfombra roja en T: pasillo desde la plataforma y franja a lo largo del frente de los stands
        deco.caja('Alfombra pasillo', (2.4, yF + 2.0 - y_stands, 0.015), (c, (yF + 2.0 + y_stands) / 2, 0.035), alfombra, bisel=0)
        deco.caja('Alfombra frente', (max(xs) - min(xs) + 5.8, 1.5, 0.015), ((max(xs) + min(xs)) / 2, y_stands + 0.75, 0.034),
                  alfombra, bisel=0)
        # tótems AMB a los dos lados de la entrada
        for s in (-1, 1):
            x = c + s * 1.9
            deco.caja('Totem', (0.62, 0.62, 2.3), (x, yF - 1.2, 1.17), navy)
            for cara, dy in (('+Y', 0.316), ('-Y', -0.316)):
                deco.texto('AMB', 0.3, (x, yF - 1.2 + dy, 1.95), cara, blanco, condensada)
                deco.caja('Linea totem', (0.4, 0.004, 0.008), (x, yF - 1.2 + dy * 1.003, 1.78), dorado, bisel=0)
                deco.texto('PROYECTOS\nTECNOLÓGICOS', 0.075, (x, yF - 1.2 + dy, 1.6), cara, dorado, negrita)
        # letrero colgante sobre la nave, con texto por los dos lados
        yl, zl = yF - 0.8, 4.35
        deco.caja('Letrero nave', (6.6, 0.06, 0.85), (c, yl, zl), navy, bisel=0.004)
        for cara, dy in (('+Y', 0.032), ('-Y', -0.032)):
            deco.texto(STANDS_SAAG['titulo'], 0.36, (c, yl + dy, zl + 0.1), cara, blanco, condensada)
            deco.caja('Linea dorada letrero', (4.2, 0.004, 0.012), (c, yl + dy * 1.05, zl - 0.17), dorado, bisel=0)
            deco.texto(UNIDAD_LETRERO, 0.075, (c, yl + dy, zl - 0.28), cara, dorado, negrita, espacio=1.25)
        for s in (-1, 1):
            x = c + s * 3.0
            z_techo = GALPON['alero'] + (GALPON['cumbre'] - GALPON['alero']) * (1 - abs(x - c) / (L / 4))
            deco.tubo('Cable letrero', (x, yl, zl + 0.42), (x, yl, z_techo - 0.1), 0.006, cable)
        # plantas ornamentales reales (Poly Haven, CC0); si faltan los modelos, palmas y arbustos hechos por código
        plantas = cargar_plantas()
        entrada = ((c - 3.1, yF - 1.0), (c + 3.1, yF - 1.0))
        puntas = ((min(xs) - 2.6, y_stands + 0.9), (max(xs) + 2.6, y_stands + 0.9))
        pasillo = [(c + s * 1.65, y) for s in (-1, 1) for y in (yF - 4.0, yF - 7.0)]
        if plantas:
            for k, (x, y) in enumerate(entrada):                 # árbol del dinero en matero negro alto
                matero(col, (x, y), 0.3, 0.62, negro, tierra, redondo=True)
                planta(col, plantas['pachira'], (x, y, 0.65), giro=1.3 + k * 2.1)
            for k, (x, y) in enumerate(puntas):                  # planta de hojas anchas con su matero de barro
                planta(col, plantas['matero_barro'], (x, y, 0.03), giro=0.7 + k * 1.9, escala=1.15)
            for k, (x, y) in enumerate(pasillo):                 # anturios en materos blancos
                matero(col, (x, y), 0.29, 0.5, blanco_m, tierra)
                planta(col, plantas['anturio'], (x, y, 0.52), giro=k * 1.57, escala=0.85)
        else:
            for (x, y) in entrada + puntas:
                palma(col, (x, y), negro, tierra, hoja)
            for (x, y) in pasillo:
                bm = bmesh.new()
                caja_bm(bm, 0, 0, 0.25, 0.5, 0.5, 0.5, 0)
                r = bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.34)
                bmesh.ops.translate(bm, vec=(0, 0, 0.82), verts=r['verts'])
                for f in {f for v in r['verts'] for f in v.link_faces}:
                    f.material_index = 1
                ob = _objeto('Arbusto en matero', bm, [blanco_m, arbusto], col)
                ob.location = (x, y, 0.03)
    # letrero principal colgado de la viga carril del frente (debajo de la línea del techo), entre las dos naves y
    # delante de la columna del medio, mirando a la plataforma
    yc = yF + 0.75                                            # viga carril de los portones (galpon_saag.py)
    ancho, alto, zt = 8.0, 1.1, 5.4                           # zt: borde de arriba = cara de abajo de la viga
    zc_ = zt - alto / 2
    yl = yc + 0.25                                            # delante del paral del medio de la viga
    deco.caja('Marco letrero principal', (ancho + 0.1, 0.06, alto + 0.1), (0, yl - 0.07, zc_), dorado, bisel=0.003)
    deco.caja('Letrero principal', (ancho, 0.1, alto), (0, yl, zc_), navy, bisel=0.005)
    deco.texto(STANDS_SAAG['letrero'], 0.5, (0, yl + 0.055, zc_ + 0.14), '+Y', blanco, condensada)
    deco.caja('Linea letrero principal', (5.6, 0.004, 0.016), (0, yl + 0.053, zc_ - 0.2), dorado, bisel=0)
    deco.texto(UNIDAD_LETRERO, 0.1, (0, yl + 0.055, zc_ - 0.36), '+Y', dorado, negrita, espacio=1.3)
    acero = mat_simple('Acero blanco', (0.85, 0.85, 0.83), 0.5, 0.2)
    for x in (-3.2, 3.2):                                     # pletinas que lo sujetan a la viga
        deco.caja('Pletina letrero', (0.08, 0.3, 0.06), (x, yc + 0.1, zt + 0.03), acero, bisel=0)
        deco.caja('Pletina letrero', (0.08, 0.04, 0.3), (x, yl - 0.07, zt - 0.1), acero, bisel=0)


# ----------------------------------------------------------------------------- plantas ornamentales reales
PLANTAS = {   # prototipo: (archivo en assets/plantas, objetos del modelo que forman la planta)
    'matero_barro': ('potted_plant_01', ('potted_plant_01_leaves', 'potted_plant_01_pebbles', 'potted_plant_01_pot',
                                         'potted_plant_01_stem')),
    'pachira': ('pachira_aquatica_01', ('pachira_aquatica_01_bark_d', 'pachira_aquatica_01_leaves_d')),
    'anturio': ('anthurium_botany_01', ('anthurium_botany_01_b',)),
}


def cargar_plantas():
    """Importa los modelos una sola vez y deja cada planta como colección oculta (se pone con instancias)."""
    if bpy.data.collections.get('Planta anturio'):
        return {k: bpy.data.collections['Planta ' + k] for k in PLANTAS}
    raiz = bpy.data.collections.new('Prototipos plantas'); escena.collection.children.link(raiz)
    protos = {}
    for clave, (archivo, nombres) in PLANTAS.items():
        ruta = os.path.join(RAIZ, 'assets', 'plantas', archivo, archivo + '_2k.gltf')
        if not os.path.exists(ruta):
            print('Falta el modelo', ruta)
            return None
        antes = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=ruta)
        nuevos = [o for o in bpy.data.objects if o not in antes]
        c = bpy.data.collections.new('Planta ' + clave); raiz.children.link(c)
        usar = [o for o in nuevos if o.name.split('.')[0] in nombres]
        for o in nuevos:
            for cc in list(o.users_collection):
                cc.objects.unlink(o)
            if o in usar:
                c.objects.link(o)
        for o in [o for o in nuevos if o not in usar]:
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(v) for o in usar if o.type == 'MESH' for v in o.bound_box]
        c.instance_offset = (sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts), min(p.z for p in pts))
        protos[clave] = c
    bpy.context.view_layer.layer_collection.children[raiz.name].exclude = True
    return protos


def planta(col, proto, pos, giro=0.0, escala=1.0):
    ob = bpy.data.objects.new('Planta ' + proto.name[7:], None)
    ob.instance_type = 'COLLECTION'; ob.instance_collection = proto
    ob.location = pos; ob.rotation_euler.z = giro; ob.scale = (escala,) * 3
    col.objects.link(ob)
    return ob


def matero(col, pos, radio, alto, mat, mat_tierra, redondo=False):
    """Matero moderno (cilindro un poco cónico o cubo) con la tierra arriba."""
    bm = bmesh.new()
    if redondo:
        r = bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=radio * 0.8, radius2=radio, depth=alto)
        bmesh.ops.translate(bm, vec=(0, 0, alto / 2), verts=r['verts'])
    else:
        caja_bm(bm, 0, 0, alto / 2, radio * 2, radio * 2, alto, 0)
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=radio * 0.92, radius2=radio * 0.92, depth=0.02)
    bmesh.ops.translate(bm, vec=(0, 0, alto - 0.03), verts=r['verts'])
    for f in {f for v in r['verts'] for f in v.link_faces}:
        f.material_index = 1
    ob = _objeto('Matero', bm, [mat, mat_tierra], col)
    ob.location = (pos[0], pos[1], 0.03)
    for p in ob.data.polygons:
        p.use_smooth = redondo and p.material_index == 0
    return ob


def palma(col, pos, mat_matero, mat_tierra, mat_hoja, n=9):
    """Palma de interior en matero: tallos que suben y se doblan, con la hoja ancha en la punta."""
    bm = bmesh.new()
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.2, radius2=0.27, depth=0.55)
    bmesh.ops.translate(bm, vec=(0, 0, 0.275), verts=r['verts'])
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.25, radius2=0.25, depth=0.02)
    bmesh.ops.translate(bm, vec=(0, 0, 0.53), verts=r['verts'])
    for f in {f for v in r['verts'] for f in v.link_faces}:
        f.material_index = 1
    for k in range(n):
        a = k * 2 * math.pi / n + (k % 2) * 0.3
        d = Vector((math.cos(a), math.sin(a), 0))
        alto = 0.9 + 0.35 * ((k * 7) % 3) / 2
        p0 = Vector((0, 0, 0.55))
        p1 = p0 + d * 0.15 + Vector((0, 0, alto))
        p2 = p1 + d * 0.45 + Vector((0, 0, 0.15))
        p3 = p2 + d * 0.4 - Vector((0, 0, 0.3))
        _barra(bm, p0, p1, 0.015, 0.015, 2)                  # tallo
        _barra(bm, p1, p2, 0.012, 0.012, 2)                  # nervio de la hoja
        _barra(bm, p2, p3, 0.01, 0.01, 2)
        lado = Vector((-d.y, d.x, 0))
        for j in range(1, 11):                               # hojuelas a los dos lados del nervio
            t = j / 11
            q = p1.lerp(p2, t * 2) if t < 0.5 else p2.lerp(p3, (t - 0.5) * 2)
            largo = 0.32 * math.sin(math.pi * (0.15 + 0.8 * t))
            for sl in (-1, 1):
                punta = q + lado * sl * largo + d * 0.06 - Vector((0, 0, 0.12 * largo))
                _barra(bm, q, punta, 0.05, 0.006, 2)
    ob = _objeto('Palma en matero', bm, [mat_matero, mat_tierra, mat_hoja], col)
    ob.location = (pos[0], pos[1], 0.03)
    return ob
