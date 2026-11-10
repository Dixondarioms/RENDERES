"""Los 4 stands de los proyectos de la AMB dentro del hangar del SAAG (escena aparte), con su decoración.

Los stands se arman con el mismo código del render principal (realismo_blender.stands_amb, sin cambiarlo): aquí solo
se le dan los puestos donde va cada uno. Dos stands por nave, contra el fondo (el edificio blanco) y abiertos hacia
la plataforma:
    nave izquierda: aeronave ultraligera ULV (afuera) y Cóndor (al medio)
    nave derecha:   disparo automatizado Igla-S (al medio) y simulador Igla-S (afuera)
Decoración: alfombra roja en T por nave, tótems azul marino "AMB" a la entrada, letrero colgante
"PROYECTOS TECNOLÓGICOS DE LA AMB" sobre cada nave, palmas en matero y bolas de arbusto en materos blancos.

Se ejecuta en un espacio aparte donde ya se cargaron mejoras_blender.py, edificio_saag.py, galpon_saag.py y
realismo_blender.py (escena_edificio.py lo hace).
"""
import math

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
    titulo='PROYECTOS TECNOLÓGICOS DE LA AMB',
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
        # palmas en matero negro a la entrada y en las puntas del frente de los stands
        for (x, y) in ((c - 3.1, yF - 1.0), (c + 3.1, yF - 1.0), (min(xs) - 2.6, y_stands + 0.9), (max(xs) + 2.6, y_stands + 0.9)):
            palma(col, (x, y), negro, tierra, hoja)
        # bolas de arbusto en materos blancos a lo largo del pasillo
        for s in (-1, 1):
            for y in (yF - 4.0, yF - 7.0):
                bm = bmesh.new()
                caja_bm(bm, 0, 0, 0.25, 0.5, 0.5, 0.5, 0)
                r = bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.34)
                bmesh.ops.translate(bm, vec=(0, 0, 0.82), verts=r['verts'])
                for f in {f for v in r['verts'] for f in v.link_faces}:
                    f.material_index = 1
                ob = _objeto('Arbusto en matero', bm, [blanco_m, arbusto], col)
                ob.location = (c + s * 1.65, y, 0.03)
                for p in ob.data.polygons:
                    p.use_smooth = p.material_index == 1


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
