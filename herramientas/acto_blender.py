"""Acto central en Blender: tarima protocolar con toldo blanco y tres filas de sillas para las autoridades (en lugar
de la tribuna y las gradas del visor web), y la parada con militares venezolanos de uniforme verde pixelado.

Se ejecuta dentro de armar_blender.py (en el mismo espacio de nombres que realismo_blender.py); la función de
entrada es acto_protocolar(), que llama aplicar_realismo().

Marco local del acto = el del hangar en el visor three.js: +x hacia la vía (sureste); la parada mira hacia +x,
a la tarima. PL(X, Y) convierte un píxel del plano de distribución ampliado a (x, z) en metros.
"""
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

_ACTO_POS, _ACTO_GIRO = (-27.28, 11.16), -0.83601
RUMBO_ACTO = _ACTO_GIRO                      # ángulo en Blender de la dirección +x local (hacia la tarima)


def _A(x, z, h=0.0):
    """Coordenadas locales del acto (x, z, altura) -> Blender."""
    a = _ACTO_GIRO
    X = x * math.cos(a) + z * math.sin(a) + _ACTO_POS[0]
    Z = -x * math.sin(a) + z * math.cos(a) + _ACTO_POS[1]
    return Vector((X, -Z, h))


def _local(v):
    """Blender -> (x, z) locales del acto."""
    a = _ACTO_GIRO
    dx, dz = v.x - _ACTO_POS[0], -v.y - _ACTO_POS[1]
    return dx * math.cos(a) - dz * math.sin(a), dx * math.sin(a) + dz * math.cos(a)


def _PL(X, Y):
    return (Y - 588) * 0.245, -(X - 282) * 0.245


# ------------------------------------------------------------------------------------------------ parámetros
# Tarima: frente hacia la parada (-x). Medidas en metros.
TARIMA = dict(cx=-1.0, cz=-161.2, fondo=9.0, largo=40.0, alto=0.6)
TOLDO = dict(margen_x=1.0, margen_z=2.0, alero=4.2, cumbrera=6.0, modulo=5.5)
FILAS_SILLAS = 3
PASO_SILLAS = 0.78                 # de centro a centro en la fila
OCUPACION = 0.86                   # fracción de sillas con alguien sentado
ZONA_TRIBUNA_VIEJA = (-9.0, 10.5, -219.5, -102.0)   # x0, x1, z0, z1: piezas del visor que se quitan (no las astas)

# Colores (sRGB) del uniforme pixelado verde del Ejército venezolano: verde claro, oliva, verde oscuro, marrón, negro
CAMO_VE = ('#77784f', '#55603a', '#323d27', '#5a4834', '#1f201b')
TONOS_PIEL = ('#6b4329', '#8a5a3a', '#a26c47', '#c08a62', '#7a4b30', '#d3a07a')


def _lin(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c) + (1.0,)


# ------------------------------------------------------------------------------------------------ materiales
def _bsdf(nombre, color, rugosidad=0.6, metal=0.0, **extra):
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = bpy.data.materials.new(nombre); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = _lin(color) if isinstance(color, str) else color
    b.inputs['Roughness'].default_value = rugosidad
    b.inputs['Metallic'].default_value = metal
    for k, v in extra.items():
        b.inputs[k].default_value = v
    return m


def _n(nt, tipo, **kw):
    n = nt.nodes.new(tipo)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def _arrugas(nt, b, fuerza=0.25, escala=9.0):
    """Relieve de tela: arrugas grandes + trama fina."""
    tc = _n(nt, 'ShaderNodeTexCoord')
    n1 = _n(nt, 'ShaderNodeTexNoise'); n1.inputs['Scale'].default_value = escala; n1.inputs['Detail'].default_value = 4
    n2 = _n(nt, 'ShaderNodeTexNoise'); n2.inputs['Scale'].default_value = 420; n2.inputs['Detail'].default_value = 1
    nt.links.new(tc.outputs['Object'], n1.inputs['Vector']); nt.links.new(tc.outputs['Object'], n2.inputs['Vector'])
    s = _n(nt, 'ShaderNodeMath', operation='MULTIPLY_ADD')
    nt.links.new(n2.outputs['Fac'], s.inputs[0]); s.inputs[1].default_value = 0.35; nt.links.new(n1.outputs['Fac'], s.inputs[2])
    bump = _n(nt, 'ShaderNodeBump'); bump.inputs['Strength'].default_value = fuerza; bump.inputs['Distance'].default_value = 0.01
    nt.links.new(s.outputs[0], bump.inputs['Height']); nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])


def _tela(nombre, color, rugosidad=0.85, brillo_tela=0.25, fuerza=0.25):
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = _bsdf(nombre, color, rugosidad)
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Sheen Weight'].default_value = brillo_tela; b.inputs['Sheen Roughness'].default_value = 0.6
    _arrugas(m.node_tree, b, fuerza)
    return m


def mat_camuflaje(nombre='Uniforme pixelado VE', pixel=0.011, escala=8.5):
    """Camuflaje digital (pixelado) verde: cinco colores en celdas cúbicas de `pixel` metros, desplazado por persona."""
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = bpy.data.materials.new(nombre); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    b.inputs['Roughness'].default_value = 0.88
    b.inputs['Sheen Weight'].default_value = 0.2; b.inputs['Sheen Roughness'].default_value = 0.6
    nt.links.new(_nodos_camo(nt, pixel, escala), b.inputs['Base Color'])
    _arrugas(nt, b, 0.3)
    return m


def _nodos_camo(nt, pixel=0.011, escala=8.5):
    """Nodos del pixelado verde venezolano; devuelve la salida de color."""
    tc = _n(nt, 'ShaderNodeTexCoord'); info = _n(nt, 'ShaderNodeObjectInfo')
    off = _n(nt, 'ShaderNodeVectorMath', operation='SCALE'); off.inputs[0].default_value = (17.3, 9.1, 5.7)
    nt.links.new(info.outputs['Random'], off.inputs['Scale'])
    suma = _n(nt, 'ShaderNodeVectorMath', operation='ADD')
    nt.links.new(tc.outputs['Object'], suma.inputs[0]); nt.links.new(off.outputs['Vector'], suma.inputs[1])
    snap = _n(nt, 'ShaderNodeVectorMath', operation='SNAP'); snap.inputs[1].default_value = (pixel, pixel, pixel)
    nt.links.new(suma.outputs['Vector'], snap.inputs[0])

    def capa(esc, semilla):
        r = _n(nt, 'ShaderNodeTexNoise'); r.inputs['Scale'].default_value = esc; r.inputs['Detail'].default_value = 1.5
        r.inputs['Roughness'].default_value = 0.6
        sm = _n(nt, 'ShaderNodeVectorMath', operation='ADD'); sm.inputs[1].default_value = (semilla, semilla * 1.7, semilla * 0.3)
        nt.links.new(snap.outputs['Vector'], sm.inputs[0]); nt.links.new(sm.outputs['Vector'], r.inputs['Vector'])
        return r.outputs['Fac']

    def rampa(fac, pares):
        cr = _n(nt, 'ShaderNodeValToRGB'); cr.color_ramp.interpolation = 'CONSTANT'
        els = cr.color_ramp.elements
        els[0].position = 0.0; els[0].color = pares[0][1]
        els[1].position = pares[1][0]; els[1].color = pares[1][1]
        for pos, col in pares[2:]:
            e = els.new(pos); e.color = col
        nt.links.new(fac, cr.inputs['Fac'])
        return cr.outputs['Color']

    c = [_lin(h) for h in CAMO_VE]
    base = rampa(capa(escala, 0.0), [(0, c[0]), (0.47, c[1]), (0.56, c[2])])
    manchas = capa(escala * 1.3, 11.0); negras = capa(escala * 1.9, 23.0)
    mm = _n(nt, 'ShaderNodeMix', data_type='RGBA')
    gt = _n(nt, 'ShaderNodeMath', operation='GREATER_THAN'); gt.inputs[1].default_value = 0.6
    nt.links.new(manchas, gt.inputs[0]); nt.links.new(gt.outputs[0], mm.inputs['Factor'])
    nt.links.new(base, mm.inputs['A']); mm.inputs['B'].default_value = c[3]
    mn = _n(nt, 'ShaderNodeMix', data_type='RGBA')
    gn = _n(nt, 'ShaderNodeMath', operation='GREATER_THAN'); gn.inputs[1].default_value = 0.64
    nt.links.new(negras, gn.inputs[0]); nt.links.new(gn.outputs[0], mn.inputs['Factor'])
    nt.links.new(mm.outputs['Result'], mn.inputs['A']); mn.inputs['B'].default_value = c[4]
    return mn.outputs['Result']


def mat_piel():
    m = bpy.data.materials.get('Piel')
    if m:
        return m
    m = bpy.data.materials.new('Piel'); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    info = _n(nt, 'ShaderNodeObjectInfo')
    cr = _n(nt, 'ShaderNodeValToRGB'); els = cr.color_ramp.elements
    tonos = [_lin(h) for h in TONOS_PIEL]
    els[0].color = tonos[0]; els[1].position = 1.0; els[1].color = tonos[-1]
    for i, t in enumerate(tonos[1:-1]):
        e = els.new((i + 1) / (len(tonos) - 1)); e.color = t
    nt.links.new(info.outputs['Random'], cr.inputs['Fac'])
    nt.links.new(cr.outputs['Color'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.5
    b.inputs['Subsurface Weight'].default_value = 0.2
    b.inputs['Subsurface Radius'].default_value = (0.012, 0.005, 0.003)
    b.inputs['Subsurface Scale'].default_value = 1.0
    return m


def mat_pelo():
    m = bpy.data.materials.get('Pelo')
    if m:
        return m
    m = _bsdf('Pelo', '#16110d', 0.55)
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    info = _n(nt, 'ShaderNodeObjectInfo')
    cr = _n(nt, 'ShaderNodeValToRGB'); els = cr.color_ramp.elements
    els[0].color = _lin('#120e0b'); els[1].position = 0.88; els[1].color = _lin('#2a211a')
    e = els.new(0.9); e.color = _lin('#8d8a86')          # algunas canas
    cr.color_ramp.interpolation = 'CONSTANT'
    nt.links.new(info.outputs['Random'], cr.inputs['Fac']); nt.links.new(cr.outputs['Color'], b.inputs['Base Color'])
    _arrugas(nt, b, 0.6, 60)
    return m


# ------------------------------------------------------------------------------------------------ geometría
K_MB = 1.75          # radio del elemento de metaball / radio de la superficie (elemento aislado, umbral 0.6)


class Figura:
    """Arma una malla con varias partes: familias de metaballs (cuerpo, ropa) y piezas sólidas, cada una con su material."""

    def __init__(self, nombre):
        self.nombre = nombre
        self.familias = {}          # material -> objeto metaball
        self.piezas = []            # (bmesh, material)

    # metaballs: cada familia es una superficie aparte (no se funde con las otras)
    def _mb(self, mat):
        if mat not in self.familias:
            mb = bpy.data.metaballs.new(f'_mb_{self.nombre}_{mat.name}')
            mb.resolution = mb.render_resolution = 0.0105; mb.threshold = 0.6
            o = bpy.data.objects.new(f'_mb{len(bpy.data.objects)}x{len(self.familias)}', mb)
            bpy.context.scene.collection.objects.link(o)
            self.familias[mat] = o
        return self.familias[mat].data

    def cap(self, mat, a, b, r):
        a, b = Vector(a), Vector(b)
        d = b - a
        e = self._mb(mat).elements.new(type='CAPSULE')
        e.co = (a + b) / 2; e.size_x = max(d.length / 2, 1e-4); e.radius = r * K_MB
        if d.length > 1e-6:
            e.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())

    def eli(self, mat, c, sx, sy, sz, giro=None):
        e = self._mb(mat).elements.new(type='ELLIPSOID')
        e.co = Vector(c); e.radius = K_MB; e.size_x, e.size_y, e.size_z = sx, sy, sz
        if giro is not None:
            e.rotation = giro

    def bola(self, mat, c, r):
        e = self._mb(mat).elements.new(type='BALL'); e.co = Vector(c); e.radius = r * K_MB

    # piezas sólidas
    def pieza(self, mat):
        bm = bmesh.new(); self.piezas.append((bm, mat)); return bm

    def caja(self, mat, c, t, giro=None, bisel=0.0):
        bm = self.pieza(mat)
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=t, verts=r['verts'])
        if giro is not None:
            bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=giro.to_matrix() if hasattr(giro, 'to_matrix') else giro)
        bmesh.ops.translate(bm, vec=Vector(c), verts=r['verts'])
        if bisel:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bisel, segments=2, affect='EDGES')
        return bm

    def cil(self, mat, a, b, r1, r2=None, seg=16, tapas=True):
        a, b = Vector(a), Vector(b); d = b - a
        bm = self.pieza(mat)
        r = bmesh.ops.create_cone(bm, cap_ends=tapas, segments=seg, radius1=r1, radius2=r1 if r2 is None else r2, depth=d.length)
        q = Vector((0, 0, 1)).rotation_difference(d.normalized())
        bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=q.to_matrix())
        bmesh.ops.translate(bm, vec=(a + b) / 2, verts=r['verts'])
        for f in bm.faces:
            f.smooth = True
        return bm

    def esfera(self, mat, c, s, corte=None, seg=24):
        """Elipsoide de semiejes s; corte = altura relativa (-1..1) bajo la cual se quita (casco, gorra)."""
        bm = self.pieza(mat)
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
        if corte is not None:
            res = bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), plane_co=(0, 0, corte),
                                         plane_no=(0, 0, 1), clear_inner=True)
        bmesh.ops.scale(bm, vec=s, verts=list(bm.verts))
        bmesh.ops.translate(bm, vec=Vector(c), verts=list(bm.verts))
        for f in bm.faces:
            f.smooth = True
        return bm

    def malla(self):
        """Convierte todo a una sola malla con un material por parte."""
        dg = bpy.context.evaluated_depsgraph_get()
        partes = []
        for mat, o in self.familias.items():
            me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
            bm = bmesh.new(); bm.from_mesh(me); bpy.data.meshes.remove(me)
            for f in bm.faces:
                f.smooth = True
            partes.append((bm, mat))
        partes += self.piezas
        final = bmesh.new(); mats = []
        for bm, mat in partes:
            if mat not in mats:
                mats.append(mat)
            tmp = bpy.data.meshes.new('_tmp'); bm.to_mesh(tmp); bm.free()
            n0 = len(final.faces)
            final.from_mesh(tmp); bpy.data.meshes.remove(tmp)
            final.faces.ensure_lookup_table()
            for f in final.faces[n0:]:
                f.material_index = mats.index(mat)
        me = bpy.data.meshes.new(self.nombre)
        final.to_mesh(me); final.free()
        for mat in mats:
            me.materials.append(mat)
        for o in self.familias.values():
            mb = o.data; bpy.data.objects.remove(o); bpy.data.metaballs.remove(mb)
        return me


# ------------------------------------------------------------------------------------------------ poses
def _pose(tipo):
    """Articulaciones (m) con la persona mirando a +X, la izquierda en +Y y los pies en z = 0."""
    J = {}
    if tipo == 'sentado':
        # silla de 0.46 m; muslos horizontales, espalda casi recta
        for s, lado in ((1, 'I'), (-1, 'D')):
            J['cadera' + lado] = (0.0, 0.095 * s, 0.53)
            J['rodilla' + lado] = (0.45, 0.115 * s, 0.53)
            J['tobillo' + lado] = (0.47, 0.115 * s, 0.085)
            J['talon' + lado] = (0.43, 0.115 * s, 0.035)
            J['punta' + lado] = (0.64, 0.13 * s, 0.035)
            J['hombro' + lado] = (-0.06, 0.195 * s, 1.0)
            J['codo' + lado] = (-0.03, 0.235 * s, 0.72)
            J['muneca' + lado] = (0.2, 0.17 * s, 0.6)
            J['mano' + lado] = (0.29, 0.15 * s, 0.585)
        J.update(pelvis=(-0.03, 0, 0.58), abdomen=(-0.05, 0, 0.72), pecho=(-0.06, 0, 0.89),
                 cuello0=(-0.06, 0, 1.02), cuello1=(-0.045, 0, 1.13), cabeza=(-0.035, 0, 1.21))
        return J
    for s, lado in ((1, 'I'), (-1, 'D')):
        J['cadera' + lado] = (0.0, 0.092 * s, 0.9)
        J['rodilla' + lado] = (0.015, 0.075 * s, 0.5)
        J['tobillo' + lado] = (0.0, 0.055 * s, 0.085)
        J['talon' + lado] = (-0.045, 0.05 * s, 0.035)
        J['punta' + lado] = (0.19, 0.135 * s, 0.035)        # firmes: talones juntos, puntas abiertas
        J['hombro' + lado] = (0.0, 0.195 * s, 1.41)
        J['codo' + lado] = (-0.005, 0.235 * s, 1.13)
        J['muneca' + lado] = (0.015, 0.225 * s, 0.875)
        J['mano' + lado] = (0.025, 0.215 * s, 0.79)
    J.update(pelvis=(0.0, 0, 0.95), abdomen=(0.005, 0, 1.1), pecho=(0.012, 0, 1.28),
             cuello0=(0.0, 0, 1.43), cuello1=(0.012, 0, 1.54), cabeza=(0.022, 0, 1.62))
    if tipo == 'fusil':        # arma al pie: culata en el suelo junto al pie derecho, la mano en el guardamanos
        J['codoD'] = (0.02, -0.25, 1.13); J['munecaD'] = (0.1, -0.265, 0.9); J['manoD'] = (0.125, -0.27, 0.83)
    elif tipo == 'bandera':    # sostiene el asta delante del pecho con la derecha
        J['codoD'] = (0.12, -0.24, 1.12); J['munecaD'] = (0.3, -0.15, 1.15); J['manoD'] = (0.34, -0.12, 1.16)
    elif tipo == 'tambor':     # manos sobre el redoblante, a la altura de la cintura
        J['codoI'] = (0.04, 0.24, 1.12); J['munecaI'] = (0.25, 0.14, 1.0); J['manoI'] = (0.31, 0.1, 0.99)
        J['codoD'] = (0.04, -0.24, 1.12); J['munecaD'] = (0.25, -0.14, 1.0); J['manoD'] = (0.31, -0.1, 0.99)
    elif tipo == 'atril':      # manos sobre el atril
        J['codoI'] = (0.06, 0.24, 1.15); J['munecaI'] = (0.3, 0.17, 1.1); J['manoI'] = (0.37, 0.15, 1.1)
        J['codoD'] = (0.06, -0.24, 1.15); J['munecaD'] = (0.3, -0.17, 1.1); J['manoD'] = (0.37, -0.15, 1.1)
    return J


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _cuerpo(F, J, tela, piel, calzado, alto_bota=0.0, mat_pantalon=None, chaqueta=False, bolsillos=False):
    """Cuerpo y ropa. alto_bota: fracción de la pierna (tobillo->rodilla) que cubre la bota (0 = zapato)."""
    pant = mat_pantalon or tela
    # torso
    F.eli(tela, J['pelvis'], 0.118, 0.165, 0.1)
    F.eli(tela, J['abdomen'], 0.11, 0.152, 0.11)
    F.eli(tela, J['pecho'], 0.122, 0.185, 0.125)
    for l in 'ID':
        F.bola(tela, J['hombro' + l], 0.06)
        F.cap(tela, J['cuello0'], J['hombro' + l], 0.05)
        # brazos (manga hasta la muñeca)
        F.cap(tela, J['hombro' + l], J['codo' + l], 0.047)
        F.cap(tela, J['codo' + l], J['muneca' + l], 0.04)
        # piernas
        cad, rod, tob = J['cadera' + l], J['rodilla' + l], J['tobillo' + l]
        F.cap(pant, cad, _mix(cad, rod, 0.5), 0.078)
        F.cap(pant, _mix(cad, rod, 0.5), rod, 0.062)
        tope = _mix(tob, rod, alto_bota) if alto_bota else _mix(tob, rod, 0.06)
        F.cap(pant, rod, tope, 0.055)
        # calzado
        F.cap(calzado, tob, _mix(tob, rod, alto_bota + 0.04) if alto_bota else tob, 0.047)
        F.cap(calzado, J['talon' + l], J['punta' + l], 0.036)
        F.bola(calzado, _mix(J['talon' + l], J['punta' + l], 0.8), 0.038)
        # manos
        F.cap(piel, J['muneca' + l], J['mano' + l], 0.028)
        F.eli(piel, _mix(J['muneca' + l], J['mano' + l], 0.6), 0.03, 0.03, 0.03)
    if bolsillos:        # uniforme de campaña: cuello, bolsillos de pecho con tapa y bolsillos laterales del pantalón
        F.cil(tela, Vector(J['cuello0']) + Vector((0, 0, -0.02)), Vector(J['cuello0']) + Vector((0.008, 0, 0.035)), 0.078, 0.064,
              seg=20, tapas=False)
        pe = Vector(J['pecho'])
        for s in (1, -1):
            g = Matrix.Rotation(0.42 * s, 3, 'Z')
            F.caja(tela, pe + Vector((0.108, 0.088 * s, 0.03)), (0.026, 0.1, 0.12), g, bisel=0.008)
            F.caja(tela, pe + Vector((0.118, 0.09 * s, 0.085)), (0.014, 0.108, 0.035), g, bisel=0.005)
            l = 'I' if s > 0 else 'D'
            F.caja(pant, Vector(_mix(J['cadera' + l], J['rodilla' + l], 0.5)) + Vector((0.0, 0.07 * s, 0.0)), (0.13, 0.03, 0.15), bisel=0.01)
        F.eli(tela, Vector(_mix(J['pelvis'], J['abdomen'], 0.75)) + Vector((0, 0, 0.03)), 0.122, 0.16, 0.05)   # blusa sobre el cinturón
    if chaqueta:         # faldones de la chaqueta sobre la cadera
        F.eli(tela, _mix(J['pelvis'], J['abdomen'], 0.3), 0.125, 0.17, 0.09)
    # cuello y cabeza
    cab = Vector(J['cabeza'])
    F.cap(piel, J['cuello0'], J['cuello1'], 0.05)
    F.eli(piel, cab, 0.098, 0.079, 0.112)
    F.eli(piel, cab + Vector((0.03, 0, -0.055)), 0.068, 0.062, 0.05)            # mandíbula
    F.cap(piel, cab + Vector((0.092, 0, 0.012)), cab + Vector((0.108, 0, -0.022)), 0.013)   # nariz
    for s in (1, -1):
        F.eli(piel, cab + Vector((0.0, 0.079 * s, 0.0)), 0.018, 0.01, 0.03)  # orejas
    ojos = _bsdf('Ojos', '#1a120d', 0.2)
    for s in (1, -1):
        F.esfera(ojos, cab + Vector((0.083, 0.032 * s, 0.018)), (0.011, 0.013, 0.008), seg=10)
    cejas = mat_pelo()
    for s in (1, -1):
        F.cap(cejas, cab + Vector((0.091, 0.012 * s, 0.038)), cab + Vector((0.083, 0.05 * s, 0.04)), 0.007)
    return cab


def _casco(F, cab):
    cub = mat_camuflaje('Cubrecasco pixelado', pixel=0.012, escala=9.0)
    F.esfera(cub, cab + Vector((-0.004, 0, 0.03)), (0.136, 0.124, 0.122), corte=-0.28)
    F.cil(_bsdf('Barboquejo', '#1d1e19', 0.8), cab + Vector((0.0, 0.085, 0.0)), cab + Vector((0.035, 0.0, -0.105)), 0.006, seg=6)
    F.cil(_bsdf('Barboquejo', '#1d1e19', 0.8), cab + Vector((0.0, -0.085, 0.0)), cab + Vector((0.035, 0.0, -0.105)), 0.006, seg=6)


def _boina(F, cab, color='#141414'):
    m = _tela('Boina ' + color, color, 0.9, 0.4, 0.4)
    giro = Matrix.Rotation(math.radians(-14), 4, 'X').to_quaternion()
    F.eli(m, cab + Vector((-0.005, -0.02, 0.085)), 0.12, 0.112, 0.042, giro)
    F.cil(m, cab + Vector((-0.005, 0, 0.045)), cab + Vector((-0.005, 0, 0.07)), 0.098, 0.1, seg=24)
    F.esfera(_bsdf('Dorado', '#c9a43a', 0.3, 1.0), cab + Vector((0.075, 0.035, 0.085)), (0.012, 0.006, 0.016), seg=10)


def _gorra(F, cab, tela, banda='#111111'):
    """Gorra de plato de oficial: copa, banda y visera negra con charretera dorada."""
    F.cil(tela, cab + Vector((0.0, 0, 0.06)), cab + Vector((0.01, 0, 0.13)), 0.098, 0.13, seg=28)
    F.cil(_tela('Banda ' + banda, banda, 0.7), cab + Vector((0.0, 0, 0.055)), cab + Vector((0.002, 0, 0.09)), 0.1, 0.102, seg=28)
    vis = F.esfera(_bsdf('Visera charol', '#050505', 0.12), cab + Vector((0.09, 0, 0.06)), (0.065, 0.1, 0.012), corte=0.0, seg=20)
    F.cil(_bsdf('Dorado', '#c9a43a', 0.3, 1.0), cab + Vector((0.1, 0.07, 0.072)), cab + Vector((0.1, -0.07, 0.072)), 0.004, seg=6)
    F.esfera(_bsdf('Dorado', '#c9a43a', 0.3, 1.0), cab + Vector((0.112, 0, 0.11)), (0.006, 0.022, 0.02), seg=12)


def _pelo(F, cab, calvo=False):
    m = mat_pelo()
    F.esfera(m, cab + Vector((-0.012, 0, 0.022 if not calvo else -0.01)), (0.1, 0.084, 0.108), corte=0.05 if not calvo else 0.15)


def _cinturon(F, J, color='#1e2018'):
    m = _tela('Cinturón ' + color, color, 0.6, 0.0, 0.1)
    c = _mix(J['pelvis'], J['abdomen'], 0.62)
    pts = [Vector(c) + Vector((0.132 * math.cos(t), 0.172 * math.sin(t), 0)) for t in [i * 2 * math.pi / 16 for i in range(17)]]
    for a, b in zip(pts, pts[1:]):
        F.cil(m, a, b, 0.024, seg=8)
    F.caja(_bsdf('Hebilla', '#8d8a80', 0.35, 1.0), Vector(c) + Vector((0.135, 0, 0)), (0.012, 0.06, 0.04))


def _fusil(F, J):
    """AK-103 negro, vertical con la culata en el suelo (arma al pie)."""
    m = _bsdf('Fusil', '#121212', 0.42, 0.35)
    x, y = J['manoD'][0] + 0.02, J['manoD'][1] - 0.025
    F.caja(m, (x - 0.01, y, 0.13), (0.1, 0.035, 0.26))                  # culata
    F.caja(m, (x, y, 0.38), (0.06, 0.045, 0.24))                         # cajón de mecanismos
    F.caja(m, (x + 0.08, y, 0.3), (0.035, 0.03, 0.17), Matrix.Rotation(0.5, 3, 'Y'))     # cargador curvo
    F.caja(m, (x + 0.065, y, 0.43), (0.03, 0.03, 0.09), Matrix.Rotation(-0.35, 3, 'Y'))  # empuñadura
    F.caja(_bsdf('Guardamanos', '#1a1712', 0.6), (x, y, 0.59), (0.055, 0.042, 0.18), bisel=0.008)
    F.cil(m, (x - 0.015, y, 0.5), (x - 0.015, y, 0.74), 0.009, seg=8)   # tubo de gases
    F.cil(m, (x + 0.005, y, 0.5), (x + 0.005, y, 0.95), 0.0095, seg=10)  # cañón
    F.caja(m, (x - 0.006, y, 0.905), (0.025, 0.01, 0.03))                # alza delantera


def _redoblante(F, J):
    c = Vector(_mix(J['pelvis'], J['abdomen'], 0.5)) + Vector((0.24, 0, 0.0))
    F.cil(_bsdf('Caja tambor', '#c9a43a', 0.3, 1.0), c + Vector((0, 0, -0.08)), c + Vector((0, 0, 0.08)), 0.18, seg=32)
    F.cil(_bsdf('Parche', '#e9e5d8', 0.5), c + Vector((0, 0, 0.08)), c + Vector((0, 0, 0.085)), 0.181, seg=32)
    F.cil(_tela('Tahalí blanco', '#e8e6e0', 0.7), Vector(J['hombroI']) + Vector((0.03, 0, 0.02)), c + Vector((-0.1, -0.12, 0.05)), 0.02, seg=6)


# ------------------------------------------------------------------------------------------------ modelos 3D de personas
# Soldado: "soldier_full_tactical_gear" (con esqueleto; se congela en su pose de descanso y el uniforme se pinta con
# el pixelado verde). Autoridades: "captain" (sin esqueleto, en pose T; se sienta deformando la malla con huesos
# definidos aquí). Si faltan los archivos se usan las figuras hechas por código.
_RAIZ_ACTO = globals().get('RAIZ') or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
MODELO_SOLDADO = os.path.join(_RAIZ_ACTO, 'assets', 'personas', 'soldado_tactico.glb')
MODELO_AUTORIDAD = os.path.join(_RAIZ_ACTO, 'assets', 'personas', 'capitan.glb')
GIRO_MODELOS = math.pi / 2          # los modelos miran a -Y; en el acto las figuras miran a +X


def _importar(ruta):
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=ruta)
    return [o for o in bpy.data.objects if o not in antes]


def _borrar(objs):
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)


def _unir(nombre, partes):
    """[(malla, matriz)] -> una sola malla; cada parte conserva sus materiales."""
    final = bmesh.new(); mats = []
    for me, M in partes:
        me.transform(M)
        mapa = []
        for m in me.materials:
            if m not in mats:
                mats.append(m)
            mapa.append(mats.index(m))
        if mapa:
            me.polygons.foreach_set('material_index', [mapa[min(p.material_index, len(mapa) - 1)] for p in me.polygons])
        final.from_mesh(me)
    out = bpy.data.meshes.new(nombre); final.to_mesh(out); final.free()
    for m in mats:
        out.materials.append(m)
    return out


def _luminancia_media(img):
    px = np.empty(len(img.pixels), dtype=np.float32); img.pixels.foreach_get(px)
    rgb = px.reshape(-1, 4)[::7, :3] ** 2.2
    return float(max(0.02, (rgb @ np.array([0.2126, 0.7152, 0.0722])).mean()))


def _camuflar(mat):
    """Pone el pixelado verde sobre la tela del modelo, conservando costuras y arrugas de su textura."""
    if mat.get('camuflado'):
        return
    nt = mat.node_tree; b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    if not b.inputs['Base Color'].links:
        return
    l = b.inputs['Base Color'].links[0]
    img = l.from_node.image if l.from_node.type == 'TEX_IMAGE' else None
    media = _luminancia_media(img) if img else 0.2
    bw = _n(nt, 'ShaderNodeRGBToBW'); nt.links.new(l.from_socket, bw.inputs['Color'])
    f = _n(nt, 'ShaderNodeMath', operation='MULTIPLY_ADD')
    nt.links.new(bw.outputs['Val'], f.inputs[0]); f.inputs[1].default_value = 0.75 / media; f.inputs[2].default_value = 0.25
    esc = _n(nt, 'ShaderNodeVectorMath', operation='SCALE')
    nt.links.new(_nodos_camo(nt, 0.011, 8.5), esc.inputs[0]); nt.links.new(f.outputs[0], esc.inputs['Scale'])
    nt.links.new(esc.outputs['Vector'], b.inputs['Base Color'])
    mat['camuflado'] = True


def malla_soldado():
    """Soldado del modelo del usuario en su pose de descanso, mirando a +X, con los pies en z = 0."""
    me = bpy.data.meshes.get('Soldado (modelo)')
    if me:
        return me
    if not os.path.exists(MODELO_SOLDADO):
        return None
    objs = _importar(MODELO_SOLDADO)
    arm = next((o for o in objs if o.type == 'ARMATURE'), None)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    partes = []
    for o in objs:
        if o.type == 'MESH' and o.modifiers:                  # la Icosphere suelta no tiene esqueleto
            partes.append((bpy.data.meshes.new_from_object(o.evaluated_get(dg), depsgraph=dg), o.matrix_world.copy()))
    mano = Vector((0, 0, 0))
    if arm:
        pb = next((p for p in arm.pose.bones if 'R_Hand' in p.name), None)
        if pb:
            mano = arm.matrix_world @ pb.head
    me = _unir('Soldado (modelo)', partes)
    for m, _ in partes:
        bpy.data.meshes.remove(m)
    _borrar(objs)
    R = Matrix.Rotation(GIRO_MODELOS, 4, 'Z')
    me.transform(R); mano = R @ mano
    co = np.empty(len(me.vertices) * 3, dtype=np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    pies = co[co[:, 2] < co[:, 2].min() + 0.12]
    d = Vector((-(pies[:, 0].min() + pies[:, 0].max()) / 2, -(pies[:, 1].min() + pies[:, 1].max()) / 2, -co[:, 2].min()))
    me.transform(Matrix.Translation(d)); mano += d
    me['mano_d'] = mano[:]
    for m in me.materials:
        if m and any(k in m.name for k in ('Kitel', 'Pants')):
            _camuflar(m)
    print('Soldado (modelo):', len(me.polygons), 'caras, alto', round(float(co[:, 2].max() - co[:, 2].min()), 2), 'm')
    return me


def _accesorio(clave, mano):
    """Fusil o redoblante del soldado del modelo (objeto aparte, en la misma posición que el soldado)."""
    me = bpy.data.meshes.get('Accesorio ' + clave)
    if me:
        return me
    F = Figura('Accesorio ' + clave)
    if clave == 'fusil':
        _fusil(F, {'manoD': (mano[0], mano[1] - 0.005, mano[2])})
    else:
        _redoblante(F, {'pelvis': (0, 0, 0.95), 'abdomen': (0.02, 0, 1.1), 'hombroI': (0, 0.2, 1.42)})
    return F.malla()


# Esqueleto simple del modelo de autoridad en su pose T original: mira a -Y y su izquierda queda en +X
_REPOSO = {'cadera': (0.1, 0.03, 0.93), 'rodilla': (0.1, 0.03, 0.52), 'tobillo': (0.1, 0.03, 0.09), 'punta': (0.1, -0.17, 0.03),
           'hombro': (0.19, 0.05, 1.5), 'codo': (0.48, 0.05, 1.5), 'muneca': (0.76, 0.05, 1.5), 'mano': (0.93, 0.05, 1.5)}
_POSES_AUTORIDAD = {
    # sentado en una silla de 0.46 m: muslos al frente, manos sobre los muslos
    'sentado': dict(torso=(0, 0, -0.385), cadera=(0.1, 0.03, 0.545), rodilla=(0.11, -0.38, 0.545), tobillo=(0.11, -0.41, 0.115),
                    hombro=(0.19, 0.05, 1.115), codo=(0.23, 0.0, 0.835), muneca=(0.17, -0.265, 0.68)),
    # de pie con las manos sobre el atril
    'atril': dict(torso=(0, 0, 0), cadera=(0.1, 0.03, 0.93), rodilla=(0.1, 0.03, 0.52), tobillo=(0.1, 0.03, 0.09),
                  hombro=(0.19, 0.05, 1.5), codo=(0.215, 0.0, 1.22), muneca=(0.18, -0.26, 1.13)),
}


def _dist_seg(V, a, b):
    a, b = np.array(a, dtype=np.float64), np.array(b, dtype=np.float64)
    ab = b - a; t = np.clip(((V - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
    return np.linalg.norm(V - (a + t[:, None] * ab), axis=1)


def _suave(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def _posar(V, solo_piernas, pose):
    """Deforma los vértices de la pose T con huesos de peso por distancia: lo sienta o le pone las manos en el atril."""
    P = _POSES_AUTORIDAD[pose]
    x, z = V[:, 0], V[:, 2]
    huesos = []          # (peso sin normalizar, rotación 3x3, cabeza en reposo, cabeza en la pose)
    k_cuerpo = 0.0 if solo_piernas else 1.0

    def rot(a0, b0, a1, b1):
        d0 = Vector(b0) - Vector(a0); d1 = Vector(b1) - Vector(a1)
        return np.array(d0.normalized().rotation_difference(d1.normalized()).to_matrix())

    w = _suave((z - 0.8) / 0.12) / (np.minimum(_dist_seg(V, (0, 0.03, 0.85), (0, 0.03, 1.55)),
                                               _dist_seg(V, (0, 0.02, 1.55), (0, 0.02, 1.95))) ** 4 + 1e-7)
    huesos.append((w * k_cuerpo, np.eye(3), np.zeros(3), np.array(P['torso'], dtype=np.float64)))
    for s in (1, -1):
        lado = _suave((s * x + 0.03) / 0.06)
        S = np.array((s, 1, 1))
        R0 = {k: tuple(np.array(v) * S) for k, v in _REPOSO.items()}
        P1 = {k: tuple(np.array(v) * S) for k, v in P.items() if k != 'torso'}
        w = lado * _suave((0.99 - z) / 0.14) / (_dist_seg(V, R0['cadera'], R0['rodilla']) ** 4 + 1e-7)          # muslo
        huesos.append((w * k_cuerpo, rot(R0['cadera'], R0['rodilla'], P1['cadera'], P1['rodilla']),
                       np.array(R0['cadera']), np.array(P1['cadera'])))
        w = lado * _suave((0.78 - z) / 0.1) / (np.minimum(_dist_seg(V, R0['rodilla'], R0['tobillo']),                # pierna y pie
                                                          _dist_seg(V, R0['tobillo'], R0['punta'])) ** 4 + 1e-7)
        huesos.append((w, rot(R0['rodilla'], R0['tobillo'], P1['rodilla'], P1['tobillo']), np.array(R0['rodilla']), np.array(P1['rodilla'])))
        zona = lado * _suave((s * x - 0.15) / 0.07) * _suave((z - 1.28) / 0.1) * k_cuerpo
        w = zona / (_dist_seg(V, R0['hombro'], R0['codo']) ** 4 + 1e-7)                                          # brazo
        huesos.append((w, rot(R0['hombro'], R0['codo'], P1['hombro'], P1['codo']), np.array(R0['hombro']), np.array(P1['hombro'])))
        w = zona / (np.minimum(_dist_seg(V, R0['codo'], R0['muneca']), _dist_seg(V, R0['muneca'], R0['mano'])) ** 4 + 1e-7)
        huesos.append((w, rot(R0['codo'], R0['muneca'], P1['codo'], P1['muneca']), np.array(R0['codo']), np.array(P1['codo'])))
    W = np.stack([h[0] for h in huesos], axis=1)
    suma = W.sum(axis=1, keepdims=True)
    W = np.where(suma > 0, W / np.maximum(suma, 1e-30), np.eye(len(huesos))[0])
    nuevo = np.zeros_like(V)
    for k, (_, R, c0, c1) in enumerate(huesos):
        nuevo += W[:, k:k + 1] * ((V - c0) @ R.T + c1)
    return nuevo


def _verdear(mat):
    """Variante verde oliva del uniforme azul: cambia solo los píxeles azules (no la piel ni lo dorado)."""
    nt = mat.node_tree; b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    if not b.inputs['Base Color'].links:
        return
    src = b.inputs['Base Color'].links[0].from_socket
    sep = _n(nt, 'ShaderNodeSeparateColor', mode='HSV'); nt.links.new(src, sep.inputs['Color'])

    def op(nombre, a, v):
        m = _n(nt, 'ShaderNodeMath', operation=nombre); nt.links.new(a, m.inputs[0])
        if isinstance(v, float):
            m.inputs[1].default_value = v
        else:
            nt.links.new(v, m.inputs[1])
        return m.outputs[0]
    mask = op('MULTIPLY', op('MULTIPLY', op('GREATER_THAN', sep.outputs[0], 0.5), op('LESS_THAN', sep.outputs[0], 0.8)),
              op('GREATER_THAN', sep.outputs[1], 0.15))
    comb = _n(nt, 'ShaderNodeCombineColor', mode='HSV'); comb.inputs[0].default_value = 0.2
    nt.links.new(op('MULTIPLY', sep.outputs[1], 0.85), comb.inputs[1]); nt.links.new(op('MULTIPLY', sep.outputs[2], 1.2), comb.inputs[2])
    mx = _n(nt, 'ShaderNodeMix', data_type='RGBA'); nt.links.new(mask, mx.inputs['Factor'])
    nt.links.new(src, mx.inputs['A']); nt.links.new(comb.outputs['Color'], mx.inputs['B'])
    nt.links.new(mx.outputs['Result'], b.inputs['Base Color'])


def malla_autoridad(pose='sentado', color='azul'):
    """Modelo de autoridad del usuario sentado (o en el atril), mirando a +X; color del uniforme 'azul' o 'verde'."""
    nombre = f'Autoridad {pose} {color} (modelo)'
    me = bpy.data.meshes.get(nombre)
    if me:
        return me
    if not os.path.exists(MODELO_AUTORIDAD):
        return None
    objs = _importar(MODELO_AUTORIDAD)
    partes = []
    zapatos = _bsdf('Zapatos de charol', '#070707', 0.2)
    for o in objs:
        if o.type != 'MESH' or not o.data.polygons:
            continue
        m = o.data.copy(); m.transform(o.matrix_world)
        V = np.empty(len(m.vertices) * 3); m.vertices.foreach_get('co', V); V = V.reshape(-1, 3)
        es_zapato = V[:, 2].max() < 0.2                      # pieza de los zapatos (tenis en el modelo original)
        m.vertices.foreach_set('co', _posar(V, es_zapato, pose).ravel())
        m.update()
        if es_zapato:
            m.materials.clear(); m.materials.append(zapatos)
        elif color == 'verde':
            for i, mt in enumerate(m.materials):
                if mt:
                    c = bpy.data.materials.get(mt.name + ' verde')
                    if not c:
                        c = mt.copy(); c.name = mt.name + ' verde'; _verdear(c)
                    m.materials[i] = c
        partes.append((m, Matrix.Rotation(GIRO_MODELOS, 4, 'Z')))
    me = _unir(nombre, partes)
    for m, _ in partes:
        bpy.data.meshes.remove(m)
    _borrar(objs)
    return me


# ------------------------------------------------------------------------------------------------ personas
def _figura(clave):
    """Malla de cada tipo de persona (se reusa en todas sus copias)."""
    me = bpy.data.meshes.get('Persona ' + clave)
    if me:
        return me
    piel = mat_piel()
    F = Figura('Persona ' + clave)
    if clave in ('soldado', 'tambor', 'bandera', 'jefe'):
        pose = {'soldado': 'fusil', 'jefe': 'firmes'}.get(clave, clave)
        J = _pose(pose)
        cab = _cuerpo(F, J, mat_camuflaje(), piel, _bsdf('Botas de charol', '#080808', 0.18), alto_bota=0.42, bolsillos=True)
        _cinturon(F, J)
        if clave == 'jefe':
            _boina(F, cab)
        else:
            _casco(F, cab)
        if clave == 'soldado':
            _fusil(F, J)
        elif clave == 'tambor':
            _redoblante(F, J)
    elif clave.startswith('sentado'):
        J = _pose('sentado')
        tipo = clave.split('_')[1]
        if tipo == 'civil':
            traje = _tela('Traje oscuro', '#20232a', 0.75, 0.3, 0.15)
            cab = _cuerpo(F, J, traje, piel, _bsdf('Zapatos', '#0a0a0a', 0.25), chaqueta=True)
            _pelo(F, cab)
            F.cap(_tela('Camisa blanca', '#e9e9e4', 0.6), Vector(J['cuello0']) + Vector((0.035, 0, 0.0)),
                  Vector(J['cuello0']) + Vector((0.05, 0, -0.08)), 0.03)
            F.cap(_tela('Corbata', '#5a1a20', 0.5), Vector(J['cuello0']) + Vector((0.06, 0, -0.02)),
                  Vector(J['pecho']) + Vector((0.12, 0, -0.08)), 0.014)
        else:
            col = {'verde': '#4a5136', 'azul': '#3f5068'}[tipo]
            tela = _tela('Uniforme de servicio ' + tipo, col, 0.8, 0.25, 0.15)
            cab = _cuerpo(F, J, tela, piel, _bsdf('Zapatos', '#0a0a0a', 0.25), chaqueta=True)
            _gorra(F, cab, tela)
            F.cap(_tela('Corbata negra', '#101010', 0.5), Vector(J['cuello0']) + Vector((0.06, 0, -0.02)),
                  Vector(J['pecho']) + Vector((0.12, 0, -0.08)), 0.013)
            dor = _bsdf('Dorado', '#c9a43a', 0.3, 1.0)
            for s in (1, -1):        # palas con soles de general y barras de condecoraciones
                F.caja(dor, Vector(J['hombroI' if s > 0 else 'hombroD']) + Vector((0.0, -0.03 * s, 0.05)), (0.09, 0.045, 0.008))
            F.caja(_bsdf('Condecoraciones', '#7a2a2a', 0.5), Vector(J['pecho']) + Vector((0.125, 0.07, 0.04)), (0.01, 0.07, 0.035))
    elif clave == 'maestro':      # maestro de ceremonia en el atril (civil, traje oscuro)
        J = _pose('atril')
        traje = _tela('Traje oscuro', '#20232a', 0.75, 0.3, 0.15)
        cab = _cuerpo(F, J, traje, piel, _bsdf('Zapatos', '#0a0a0a', 0.25), chaqueta=True)
        _pelo(F, cab)
    return F.malla()


# ------------------------------------------------------------------------------------------------ tarima y toldo
def _obj(nombre, me, col, loc=(0, 0, 0), rot_z=0.0):
    o = bpy.data.objects.new(nombre, me); col.objects.link(o)
    o.location = loc; o.rotation_euler = (0, 0, rot_z)
    return o


def _malla_bm(nombre, bm, mats):
    me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free()
    for m in mats:
        me.materials.append(m)
    return me


def _caja_bm(bm, c, t, mi=0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=t, verts=r['verts']); bmesh.ops.translate(bm, vec=Vector(c), verts=r['verts'])
    for f in {f for v in r['verts'] for f in v.link_faces}:
        f.material_index = mi
    return r['verts']


def mat_lona():
    """Lona de PVC blanca del toldo: algo translúcida (bajo el sol la cara de abajo se ilumina)."""
    m = bpy.data.materials.get('Lona toldo blanca')
    if m:
        return m
    m = bpy.data.materials.new('Lona toldo blanca'); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']; out = nt.nodes['Material Output']
    b.inputs['Base Color'].default_value = (0.86, 0.86, 0.84, 1); b.inputs['Roughness'].default_value = 0.42
    b.inputs['Coat Weight'].default_value = 0.15
    tr = _n(nt, 'ShaderNodeBsdfTranslucent'); tr.inputs['Color'].default_value = (0.8, 0.79, 0.75, 1)
    mx = _n(nt, 'ShaderNodeMixShader'); mx.inputs['Fac'].default_value = 0.28
    nt.links.new(b.outputs['BSDF'], mx.inputs[1]); nt.links.new(tr.outputs['BSDF'], mx.inputs[2])
    nt.links.new(mx.outputs['Shader'], out.inputs['Surface'])
    _arrugas(nt, b, 0.08, 3.0)
    return m


def mat_alfombra():
    m = bpy.data.materials.get('Alfombra roja')
    if m:
        return m
    m = _bsdf('Alfombra roja', '#6a121b', 0.95)
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Sheen Weight'].default_value = 0.6; b.inputs['Sheen Roughness'].default_value = 0.4
    _arrugas(m.node_tree, b, 0.12, 900)
    return m


def tarima_y_toldo(col):
    T, D = TARIMA, TOLDO
    cx, cz, fd, lg, h = T['cx'], T['cz'], T['fondo'], T['largo'], T['alto']
    x0, x1, z0, z1 = cx - fd / 2, cx + fd / 2, cz - lg / 2, cz + lg / 2
    giro = RUMBO_ACTO
    # Todo se arma en el marco local con x hacia la parada invertida: punto local (x, z, h) -> malla con (x, -z, h)
    # y el objeto va en _A(0, 0) con giro RUMBO_ACTO (el +x local de Blender = +x del acto; +y = -z del acto).
    origen = _A(0, 0)

    def L(x, z, hh=0.0):
        return Vector((x, -z, hh))

    alf, madera, blanco = mat_alfombra(), _bsdf('Tarima madera', '#4a3a2a', 0.7), _tela('Faldón blanco', '#e9e8e3', 0.7, 0.3, 0.05)
    acero = _bsdf('Aluminio toldo', '#b9bcbf', 0.3, 1.0)
    # --- plataforma (estructura + tablero con alfombra)
    bm = bmesh.new()
    _caja_bm(bm, L(cx, cz, h - 0.03), (fd, lg, 0.06), 0)
    _caja_bm(bm, L(cx, cz, (h - 0.06) / 2), (fd - 0.3, lg - 0.3, h - 0.06), 1)
    # escaleras: centro del frente y a los dos lados, 3 escalones con alfombra
    pasos = 3; alto_p = h / pasos
    for k in range(pasos):
        prof = 0.32 * (pasos - k)
        _caja_bm(bm, L(x0 - prof / 2, cz, alto_p * (k + 0.5)), (prof, 3.2, alto_p), 0)
        for s in (-1, 1):
            _caja_bm(bm, L(cx - 1.2, cz + s * (lg / 2 + prof / 2), alto_p * (k + 0.5)), (2.4, prof, alto_p), 0)
    _obj('Tarima protocolar', _malla_bm('Tarima protocolar', bm, [alf, madera]), col, origen, giro)

    # --- faldón blanco plisado al frente y a los lados, con la cinta tricolor arriba
    bm = bmesh.new()

    def faldon(p0, p1, alto_f, tope):
        n = max(8, int((p1 - p0).length / 0.06))
        d = (p1 - p0).normalized(); nrm = Vector((d.y, -d.x, 0))
        vs = []
        for i in range(n + 1):
            p = p0 + (p1 - p0) * i / n + nrm * (0.018 * math.sin(i * math.pi / 2))
            vs.append((bm.verts.new(p + Vector((0, 0, tope - alto_f))), bm.verts.new(p + Vector((0, 0, tope)))))
        for (a, b), (c, d2) in zip(vs, vs[1:]):
            bm.faces.new((a, c, d2, b))
    off = 0.03
    tramos = [(L(x0 - off, z0), L(x0 - off, cz - 1.6)), (L(x0 - off, cz + 1.6), L(x0 - off, z1)),
              (L(x0, z0 - off), L(x1, z0 - off)), (L(x1, z1 + off), L(x0, z1 + off))]
    for a, b in tramos:
        faldon(a, b, h - 0.08, h - 0.08)
    _obj('Faldón tarima', _malla_bm('Faldón tarima', bm, [blanco]), col, origen, giro)
    bm = bmesh.new()
    for i, (a, b) in enumerate(tramos):
        for k, hh in enumerate((h - 0.05, h - 0.1, h - 0.15)):
            d = b - a; c = (a + b) / 2
            v = _caja_bm(bm, Vector((c.x, c.y, hh)), (abs(d.x) + 0.02 if abs(d.x) > 0.1 else 0.012,
                                                      abs(d.y) + 0.02 if abs(d.y) > 0.1 else 0.012, 0.05), k)
            bmesh.ops.translate(bm, vec=Vector((-0.012, 0, 0)) if abs(d.y) > 0.1 else Vector((0, 0.012 * (1 if i == 2 else -1), 0)), verts=v)
    tri = [_tela('Cinta amarilla', '#f4c300', 0.6), _tela('Cinta azul', '#00247d', 0.6), _tela('Cinta roja', '#cf142b', 0.6)]
    _obj('Cinta tricolor', _malla_bm('Cinta tricolor', bm, tri), col, origen, giro)

    # --- toldo protocolar blanco a dos aguas, con postes de aluminio, cerchas y faldón ondulado
    tx0, tx1 = x0 - D['margen_x'], x1 + D['margen_x'] + 0.6
    tz0, tz1 = z0 - D['margen_z'], z1 + D['margen_z']
    eave, ridge = D['alero'], D['cumbrera']; xm = (tx0 + tx1) / 2
    nmod = max(1, round((tz1 - tz0) / D['modulo']))
    nmod += 1 - nmod % 2                  # impar: no queda un poste delante de la escalera central
    paso = (tz1 - tz0) / nmod
    bm = bmesh.new()                      # techo: dos faldones con un poco de comba entre cerchas
    nz = nmod * 12
    for lado in (0, 1):
        xa, xb = (tx0, xm) if lado == 0 else (xm, tx1)
        ha, hb = (eave, ridge) if lado == 0 else (ridge, eave)
        filas = []
        for j in range(9):
            t = j / 8; x = xa + (xb - xa) * t; hh = ha + (hb - ha) * t
            fila = []
            for i in range(nz + 1):
                z = tz0 + (tz1 - tz0) * i / nz
                comba = 0.06 * math.sin(math.pi * ((z - tz0) / paso % 1.0)) * math.sin(math.pi * t)
                fila.append(bm.verts.new(L(x, z, hh - comba)))
            filas.append(fila)
        for fa, fb in zip(filas, filas[1:]):
            for i in range(nz):
                bm.faces.new((fa[i], fa[i + 1], fb[i + 1], fb[i]))
    for z in (tz0, tz1):                  # hastiales (triángulos de los extremos), abiertos abajo
        v = [bm.verts.new(L(tx0, z, eave)), bm.verts.new(L(xm, z, ridge)), bm.verts.new(L(tx1, z, eave))]
        bm.faces.new(v)
    for f in bm.faces:
        f.smooth = True
    _obj('Toldo protocolar', _malla_bm('Toldo protocolar', bm, [mat_lona()]), col, origen, giro)
    # faldón (bambalina) ondulado alrededor del alero
    bm = bmesh.new()
    contorno = [L(tx0, tz0, eave), L(tx0, tz1, eave), L(tx1, tz1, eave), L(tx1, tz0, eave), L(tx0, tz0, eave)]
    for a, b in zip(contorno, contorno[1:]):
        n = max(4, int((b - a).length / 0.75)); fila = []
        for i in range(n * 8 + 1):
            p = a + (b - a) * i / (n * 8)
            ond = 0.38 - 0.14 * abs(math.sin(math.pi * i / 8))      # festones
            fila.append((bm.verts.new(p + Vector((0, 0, 0.02))), bm.verts.new(p - Vector((0, 0, ond)))))
        for (a1, b1), (a2, b2) in zip(fila, fila[1:]):
            bm.faces.new((a1, a2, b2, b1))
    _obj('Bambalina toldo', _malla_bm('Bambalina toldo', bm, [mat_lona()]), col, origen, giro)
    # postes, cerchas, cumbrera y bases de lastre
    bm = bmesh.new()
    for i in range(nmod + 1):
        z = tz0 + paso * i
        for x in (tx0, tx1):
            _caja_bm(bm, L(x, z, eave / 2), (0.1, 0.1, eave), 0)
            _caja_bm(bm, L(x, z, 0.12), (0.5, 0.5, 0.24), 1)              # lastre de concreto
        for xa, xb, ha, hb in ((tx0, xm, eave, ridge), (xm, tx1, ridge, eave)):
            a, b = L(xa, z, ha - 0.07), L(xb, z, hb - 0.07)
            r = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=((b - a).length, 0.07, 0.12), verts=r['verts'])
            ang = math.atan2(b.z - a.z, b.x - a.x)
            bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(-ang, 3, 'Y'))
            bmesh.ops.translate(bm, vec=(a + b) / 2, verts=r['verts'])
    _caja_bm(bm, L(xm, (tz0 + tz1) / 2, ridge - 0.07), (0.07, tz1 - tz0, 0.1), 0)
    for x in (tx0, tx1):
        _caja_bm(bm, L(x, (tz0 + tz1) / 2, eave - 0.05), (0.07, tz1 - tz0, 0.1), 0)
    _obj('Estructura toldo', _malla_bm('Estructura toldo', bm, [acero, _bsdf('Lastre concreto', '#8f8d88', 0.85)]), col, origen, giro)
    # cortina blanca de fondo (detrás de la tarima) y telón azul marino central con el rótulo
    bm = bmesh.new()
    n = int((tz1 - tz0) / 0.07)
    vs = []
    for i in range(n + 1):
        z = tz0 + (tz1 - tz0) * i / n; xx = tx1 - 0.15 + 0.03 * math.sin(i * math.pi / 2)
        vs.append((bm.verts.new(L(xx, z, 0.0)), bm.verts.new(L(xx, z, eave - 0.05))))
    for (a, b), (c, d2) in zip(vs, vs[1:]):
        bm.faces.new((a, c, d2, b))
    _obj('Cortina fondo toldo', _malla_bm('Cortina fondo toldo', bm, [blanco]), col, origen, giro)
    telon(col, x1 - 0.25, cz, 15.0, 2.2, h + 1.25, origen, giro)
    # atril de madera con micrófono, a un lado de la escalera central
    bm = bmesh.new()
    za = cz + 5.0; xa = x0 + 0.9
    _caja_bm(bm, L(xa, za, h + 0.55), (0.45, 0.62, 1.1), 0)
    _caja_bm(bm, L(xa - 0.02, za, h + 1.13), (0.55, 0.7, 0.06), 0)
    _caja_bm(bm, L(xa - 0.235, za, h + 0.62), (0.012, 0.36, 0.32), 1)          # escudo/placa
    _obj('Atril', _malla_bm('Atril', bm, [madera, _bsdf('Placa atril', '#00247d', 0.4)]), col, origen, giro)
    mic = Figura('Micrófono atril')
    mic.cil(_bsdf('Micrófono', '#151515', 0.4, 0.6), L(xa - 0.15, za, h + 1.16), L(xa - 0.33, za, h + 1.42), 0.006, seg=8)
    mic.esfera(_bsdf('Micrófono', '#151515', 0.4, 0.6), L(xa - 0.34, za, h + 1.43), (0.022, 0.022, 0.03), seg=12)
    _obj('Micrófono atril', mic.malla(), col, origen, giro)
    # materos con plantas ornamentales delante de la tarima
    plantas(col, [(x0 - 0.55, z) for z in [z0 + 1.0 + i * (lg - 2.0) / 9 for i in range(10)] if abs(z - cz) > 2.4], origen, giro)
    return dict(x0=x0, x1=x1, z0=z0, z1=z1, h=h, atril=(xa, za))


def _texto_malla(texto, tam, fuente, ancho_max=None):
    cu = bpy.data.curves.new('txt', 'FONT'); cu.body = texto; cu.size = tam; cu.align_x = 'CENTER'; cu.align_y = 'CENTER'
    if fuente:
        cu.font = fuente
    o = bpy.data.objects.new('_txt', cu); bpy.context.scene.collection.objects.link(o)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    bpy.data.objects.remove(o); bpy.data.curves.remove(cu)
    if ancho_max:
        xs = [v.co.x for v in me.vertices]
        w = max(xs) - min(xs) if xs else 1
        if w > ancho_max:
            me.transform(Matrix.Scale(ancho_max / w, 4))
    return me


def _fuente_acto(nombres):
    for n in nombres:
        ruta = 'C:/Windows/Fonts/' + n
        try:
            return bpy.data.fonts.load(ruta, check_existing=True)
        except Exception:
            continue
    return None


def telon(col, x, cz, ancho, alto, base, origen, giro):
    """Telón azul marino al fondo de la tarima: 106 aniversario AMB, con franja tricolor y estrellas."""
    azul = _tela('Telón azul marino', '#0f2350', 0.8, 0.3, 0.05)
    bm = bmesh.new()
    _caja_bm(bm, Vector((x, -cz, base + alto / 2)), (0.05, ancho, alto), 0)
    for k, c in enumerate((1, 2, 3)):
        _caja_bm(bm, Vector((x - 0.03, -cz, base + 0.12 + k * 0.1)), (0.01, ancho, 0.1), c)
    me = _malla_bm('Telón protocolar', bm, [azul, _bsdf('Franja roja', '#cf142b', 0.6), _bsdf('Franja azul', '#00247d', 0.6),
                                            _bsdf('Franja amarilla', '#f4c300', 0.6)])
    _obj('Telón protocolar', me, col, origen, giro)
    negrita = _fuente_acto(['AGENCYB.TTF', 'arialbd.ttf'])
    normal = _fuente_acto(['arialbd.ttf'])
    blanco = _bsdf('Letras telón', '#f2f2f0', 0.4)
    dorado = _bsdf('Letras doradas', '#d4ae45', 0.3, 0.9)
    for texto, tam, hh, mat, fu in (('106 ANIVERSARIO', 0.6, base + alto * 0.7, blanco, negrita),
                                    ('AVIACIÓN MILITAR BOLIVARIANA', 0.28, base + alto * 0.44, dorado, normal),
                                    ('34 AÑOS DE LA REBELIÓN CÍVICO-MILITAR DEL 27N92', 0.16, base + alto * 0.3, blanco, normal)):
        me = _texto_malla(texto, tam, fu, ancho * 0.85)
        me.materials.append(mat)
        # el texto se arma en XY: se para (XZ) y se gira para mirar a -x (hacia la parada)
        me.transform(Matrix.Rotation(math.pi / 2, 4, 'X'))
        me.transform(Matrix.Rotation(-math.pi / 2, 4, 'Z'))
        me.transform(Matrix.Translation(Vector((x - 0.04, -cz, hh))))
        _obj('Rótulo ' + texto[:12], me, col, origen, giro)


def plantas(col, puntos, origen, giro):
    """Materos blancos con palmitas (areca) delante de la tarima."""
    F = Figura('Matero con planta')
    F.cil(_bsdf('Matero blanco', '#e6e4de', 0.35), (0, 0, 0), (0, 0, 0.55), 0.2, 0.26, seg=24)
    F.cil(_bsdf('Tierra matero', '#2b2018', 0.95), (0, 0, 0.5), (0, 0, 0.53), 0.24, seg=24)
    hoja = _bsdf('Hoja areca', '#2f5a1e', 0.55, 0.0, **{'Subsurface Weight': 0.0})
    rnd = random.Random(7)
    for i in range(9):
        ang = i * 2.39996; incl = 0.5 + 0.35 * rnd.random(); largo = 0.9 + 0.4 * rnd.random()
        a = Vector((0.03 * math.cos(ang), 0.03 * math.sin(ang), 0.53))
        b = a + Vector((math.cos(ang) * math.sin(incl), math.sin(ang) * math.sin(incl), math.cos(incl))) * largo
        F.cil(hoja, a, b, 0.008, 0.004, seg=5)
        for j in range(1, 9):     # folíolos
            t = j / 9; p = a + (b - a) * t; d = (b - a).normalized(); lado = Vector((-d.y, d.x, 0)).normalized()
            for s in (1, -1):
                q = p + lado * s * 0.16 * (1 - t * 0.6) - Vector((0, 0, 0.06))
                F.cil(hoja, p, q, 0.012, 0.004, seg=4)
    me = F.malla()
    for x, z in puntos:
        loc = Vector((x, -z, 0.0))
        o = _obj('Matero', me, col, origen, giro)
        o.location = origen + Matrix.Rotation(giro, 4, 'Z') @ loc
        o.rotation_euler = (0, 0, giro + rnd.random() * 6.28)


# ------------------------------------------------------------------------------------------------ sillas
def _silla_forrada():
    """Silla protocolar con forro blanco hasta el piso y lazo azul marino en el respaldo."""
    me = bpy.data.meshes.get('Silla protocolar')
    if me:
        return me
    F = Figura('Silla protocolar')
    forro = _tela('Forro silla blanco', '#ecebe6', 0.75, 0.35, 0.12)
    bm = F.pieza(forro)
    # falda: tronco de pirámide del piso al asiento, asiento y respaldo (mirando a +x)
    def anillo(z, sx, sy, dx=0.0):
        return [bm.verts.new((dx + sx * cx, sy * cy, z)) for cx, cy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    a0 = anillo(0.0, 0.26, 0.25); a1 = anillo(0.46, 0.23, 0.23); a2 = anillo(0.5, 0.23, 0.23)
    for ra, rb in ((a0, a1), (a1, a2)):
        for i in range(4):
            bm.faces.new((ra[i], ra[(i + 1) % 4], rb[(i + 1) % 4], rb[i]))
    bm.faces.new(list(reversed(a2)))
    r = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(0.07, 0.44, 0.55), verts=r['verts'])
    bmesh.ops.rotate(bm, verts=r['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(-0.12, 3, 'Y'))
    bmesh.ops.translate(bm, vec=(-0.2, 0, 0.77), verts=r['verts'])
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.02, segments=3, affect='EDGES')
    lazo = _tela('Lazo azul marino', '#14275a', 0.55, 0.5, 0.1)
    F.caja(lazo, (-0.24, 0, 0.62), (0.02, 0.46, 0.08))
    F.esfera(lazo, (-0.26, 0, 0.62), (0.03, 0.1, 0.06), seg=12)
    return F.malla()


def _sillon_honor():
    """Sillón de honor de la primera fila (centro): madera dorada y tapiz vino tinto."""
    me = bpy.data.meshes.get('Sillón de honor')
    if me:
        return me
    F = Figura('Sillón de honor')
    dor = _bsdf('Madera dorada', '#a8842f', 0.35, 0.8); tap = _tela('Tapiz vino', '#5c0f1a', 0.6, 0.6, 0.1)
    for x in (0.22, -0.22):
        for y in (0.26, -0.26):
            F.cil(dor, (x, y, 0.0), (x, y, 0.45), 0.025, 0.03, seg=10)
    F.caja(dor, (0, 0, 0.42), (0.56, 0.6, 0.07), bisel=0.01)
    F.caja(tap, (0.01, 0, 0.48), (0.5, 0.52, 0.08), bisel=0.025)
    F.caja(dor, (-0.26, 0, 0.85), (0.06, 0.6, 0.8), bisel=0.015)
    F.caja(tap, (-0.22, 0, 0.83), (0.04, 0.5, 0.62), bisel=0.015)
    for y in (0.29, -0.29):
        F.caja(dor, (0.0, y, 0.67), (0.5, 0.06, 0.05), bisel=0.01)
        F.cil(dor, (0.2, y, 0.45), (0.2, y, 0.67), 0.022, seg=8)
    return F.malla()


# ------------------------------------------------------------------------------------------------ todo junto
def _quitar_tribuna_vieja():
    x0, x1, z0, z1 = ZONA_TRIBUNA_VIEJA
    quitar = []
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.name.startswith(('Persona', 'Silla')):
            continue
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        loc = [_local(p) for p in pts]
        if all(x0 < x < x1 and z0 < z < z1 for x, z in loc) and max(p.z for p in pts) < 9.0:
            quitar.append(o)
    for o in quitar:
        bpy.data.objects.remove(o, do_unlink=True)
    print('Tribuna y gradas del visor quitadas:', len(quitar), 'piezas')


def _poner(col, me, nombre, x, z, h=0.0, giro_extra=0.0, escala=1.0):
    o = bpy.data.objects.new(nombre, me); col.objects.link(o)
    o.location = _A(x, z, h); o.rotation_euler = (0, 0, RUMBO_ACTO + giro_extra)
    o.scale = (escala, escala, escala)
    return o


def parada(col):
    """Agrupaciones de la parada (Anexo 3 del plano), todas mirando a la tarima (+x)."""
    rnd = random.Random(27)
    modelo = malla_soldado()
    if modelo:
        mano = Vector(modelo['mano_d'])
        fusil, tambor = _accesorio('fusil', mano), _accesorio('redoblante', mano)
        sold, tamb, band, jefe = (modelo, fusil), (modelo, tambor), (modelo, None), (modelo, None)
        agarre = (mano.x, mano.y)
    else:
        sold, tamb, band, jefe = [(_figura(k), None) for k in ('soldado', 'tambor', 'bandera', 'jefe')]
        agarre = (0.34, -0.12)
    n = 0

    def uno(tipo, x, z):
        nonlocal n
        me, extra = tipo
        x += rnd.uniform(-0.03, 0.03); z += rnd.uniform(-0.03, 0.03)
        g, e = rnd.uniform(-0.03, 0.03), rnd.uniform(0.97, 1.03)
        _poner(col, me, f'Militar {n:04d}', x, z, 0.0, g, e)
        if extra:
            _poner(col, extra, f'Militar {n:04d} ' + extra.name.split()[-1], x, z, 0.0, g, e)
        n += 1

    def bloque(cx, cz, dx, dz, paso, me):
        x = cx - dx / 2 + paso / 2
        while x < cx + dx / 2:
            z = cz - dz / 2 + paso / 2
            while z < cz + dz / 2:
                uno(me, x, z)
                z += paso
            x += paso

    # banda de guerra (redoblantes) y bloque del estandarte
    x, z = _PL(727, 450); bloque(x, z, 17, 15, 1.2, tamb)
    x, z = _PL(791, 450); bloque(x, z, 17, 15, 1.2, sold)
    # 12 agrupaciones con su jefe al lado
    for X in (868, 932, 995, 1060, 1125, 1190):
        for Y in (435, 467):
            x, z = _PL(X, Y); bloque(x, z, 6.9, 7.8, 1.05, sold)
            jx, jz = _PL(X - 24, Y); uno(jefe, jx, jz)
    # escolta de banderas: el abanderado sostiene el asta que ya está en la escena (x + 0.3, z + 0.25)
    for X in (595, 610, 625, 640):
        for Y in (462, 476):
            x, z = _PL(X, Y)
            uno(band, x + 0.3 - agarre[0], z + 0.25 + agarre[1])      # la mano derecha en el asta
    for X in (652, 664, 676, 688):
        x, z = _PL(X, 470); uno(jefe, x, z)
    print('Parada:', n, 'militares')
    return n


def autoridades(col, t):
    """Tres filas de sillas protocolares en la tarima, con las autoridades sentadas."""
    rnd = random.Random(106)
    silla, sillon = _silla_forrada(), _sillon_honor()
    azul, verde = malla_autoridad('sentado', 'azul'), malla_autoridad('sentado', 'verde')
    if azul:
        tipos = [(azul, 0.55), (verde, 0.45)]
    else:
        tipos = [(_figura('sentado_verde'), 0.45), (_figura('sentado_azul'), 0.3), (_figura('sentado_civil'), 0.25)]
    h = t['h']; z0, z1 = t['z0'] + 1.6, t['z1'] - 1.6
    cz = (t['z0'] + t['z1']) / 2
    ns = np = 0
    for fila in range(FILAS_SILLAS):
        x = t['x0'] + 2.4 + fila * 1.35
        z = z0
        while z <= z1 + 1e-6:
            honor = fila == 0 and abs(z - cz) <= 3.2
            me = sillon if honor else silla
            _poner(col, me, f'Silla autoridades {ns:03d}', x, z, h, math.pi)        # miran hacia la parada (-x)
            ns += 1
            if rnd.random() < (1.0 if honor else OCUPACION):
                tipo = rnd.choices([a for a, _ in tipos], [w for _, w in tipos])[0]
                _poner(col, tipo, f'Autoridad {np:03d}', x, z, h + (0.035 if honor else 0.0), math.pi + rnd.uniform(-0.12, 0.12),
                       rnd.uniform(0.96, 1.03))
                np += 1
            z += PASO_SILLAS * (1.15 if honor else 1.0)
    # maestro de ceremonia en el atril
    xa, za = t['atril']
    _poner(col, malla_autoridad('atril', 'azul') or _figura('maestro'), 'Maestro de ceremonia', xa + 0.42, za, h, math.pi)
    print('Sillas protocolares:', ns, ' autoridades sentadas:', np)


def camaras_acto(t):
    """Vistas del acto: desde la tarima hacia la parada, la tarima desde la parada y la parada de lado."""
    def cam(nombre, pos, mira, lente=35, res=(2560, 1440), ev=0.0):
        cd = bpy.data.cameras.get(nombre) or bpy.data.cameras.new(nombre)
        cd.lens = lente; cd.sensor_fit = 'HORIZONTAL'; cd.sensor_width = 36; cd.clip_start = 0.1; cd.clip_end = 60000
        o = bpy.data.objects.get('Cam_' + nombre)
        if not o:
            o = bpy.data.objects.new('Cam_' + nombre, cd)
            (bpy.data.collections.get('Camaras') or bpy.context.scene.collection).objects.link(o)
        o.data = cd
        p, m = _A(*pos), _A(*mira)
        o.location = p; o.rotation_euler = (m - p).to_track_quat('-Z', 'Y').to_euler()
        o['resolucion'] = res
        o['exposicion'] = ev
        return o
    cz = (t['z0'] + t['z1']) / 2
    cam('tribuna', (t['x1'] - 0.6, cz + 9.0, t['h'] + 1.75), (-34.0, -175.0, 1.0), 28)
    cam('toldo', (-21.0, cz + 19.0, 1.7), (t['x0'] + 2.0, cz - 1.0, 1.9), 32)
    cam('parada', (-12.0, -103.0, 7.5), (-34.0, -168.0, 0.6), 35)
    cam('autoridades', (t['x0'] - 5.5, cz - 7.0, 1.6), (t['x0'] + 2.5, cz + 2.0, 1.25), 35, ev=1.2)   # bajo la sombra del toldo
    cam('formacion', (-19.0, -151.5, 1.75), (-33.0, -146.0, 1.1), 40)


def acto_protocolar():
    col = bpy.data.collections.get('Acto protocolar') or bpy.data.collections.new('Acto protocolar')
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    _quitar_tribuna_vieja()
    t = tarima_y_toldo(col)
    autoridades(col, t)
    parada(col)
    camaras_acto(t)
    return t
