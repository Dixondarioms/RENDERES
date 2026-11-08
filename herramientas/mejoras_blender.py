"""Mejoras de aspecto para la escena en Blender: piso (plataforma, vía, grama), edificios detallados y árboles reales.
Se ejecuta desde armar_blender.py (usa las variables RAIZ, DIR_B, escena, a_blender)."""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

random.seed(7)
S, OX, OY = 0.31, 595, 238          # escala y origen de la imagen satelital (igual que en el visor)


def px(x, y):
    return Vector(((x - OX) * S, -(y - OY) * S, 0))


def imagen(nombre):
    ruta = os.path.join(RAIZ, 'assets', 'texturas', nombre)
    return bpy.data.images.get(nombre) or bpy.data.images.load(ruta)


def nodos(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return nt, nt.nodes.new('ShaderNodeBsdfPrincipled'), nt.nodes.new('ShaderNodeOutputMaterial')


def tex_pbr(nt, coord, nombre, escala, giro=0.0):
    """Nodos de textura real (color de detalle, normal y rugosidad) con coordenadas en metros."""
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (1 / escala, 1 / escala, 1 / escala)
    mp.inputs['Rotation'].default_value = (0, 0, giro)
    nt.links.new(coord, mp.inputs['Vector'])
    salida = {}
    for clave, archivo, color in (('col', f'{nombre}_det.jpg', True), ('nor', f'{nombre}_nor.jpg', False), ('rug', f'{nombre}_rough.jpg', False)):
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = imagen(archivo)
        if not color:
            t.image.colorspace_settings.name = 'Non-Color'
        nt.links.new(mp.outputs['Vector'], t.inputs['Vector'])
        salida[clave] = t.outputs['Color']
    nm = nt.nodes.new('ShaderNodeNormalMap'); nt.links.new(salida['nor'], nm.inputs['Color'])
    salida['normal'] = nm.outputs['Normal']
    return salida


def ruido(nt, coord, escala, detalle=6.0):
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = escala; n.inputs['Detail'].default_value = detalle
    nt.links.new(coord, n.inputs['Vector'])
    return n.outputs['Fac']


def rampa(nt, fac, colores):
    r = nt.nodes.new('ShaderNodeValToRGB')
    r.color_ramp.elements[0].position, r.color_ramp.elements[0].color = colores[0]
    r.color_ramp.elements[1].position, r.color_ramp.elements[1].color = colores[-1]
    for pos, col in colores[1:-1]:
        e = r.color_ramp.elements.new(pos); e.color = col
    nt.links.new(fac, r.inputs['Fac'])
    return r.outputs['Color']


def mezclar(nt, a, b, fac, modo='MIX'):
    m = nt.nodes.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.blend_type = modo
    for entrada, v in (('Factor', fac), ('A', a), ('B', b)):
        if isinstance(v, (int, float, tuple)):
            m.inputs[entrada].default_value = v
        else:
            nt.links.new(v, m.inputs[entrada])
    return m.outputs['Result']


ANG_HANGAR = math.radians(47.9)
ANG_RODAJE = math.radians(33.0)   # dirección de la calle de rodaje (y de las juntas de las losas) en Blender


# ----------------------------------------------------------------------------- pisos
def mat_concreto():
    m = bpy.data.materials.new('Concreto plataforma')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    coord = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    t = tex_pbr(nt, coord, 'apron', 3.0)
    # Losas de 6 x 5 m alineadas con la calle de rodaje (como en la imagen satelital), cada una con su tono
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Rotation'].default_value = (0, 0, -ANG_RODAJE)
    nt.links.new(coord, mp.inputs['Vector'])
    lad = nt.nodes.new('ShaderNodeTexBrick')
    lad.offset = 0.0; lad.squash = 1.0
    lad.inputs['Scale'].default_value = 1.0; lad.inputs['Brick Width'].default_value = 6.0; lad.inputs['Row Height'].default_value = 5.0
    lad.inputs['Mortar Size'].default_value = 0.025; lad.inputs['Mortar Smooth'].default_value = 0.4; lad.inputs['Bias'].default_value = 0.0
    lad.inputs['Color1'].default_value = (0.47, 0.42, 0.32, 1); lad.inputs['Color2'].default_value = (0.58, 0.53, 0.42, 1)
    lad.inputs['Mortar'].default_value = (0.24, 0.21, 0.17, 1)
    nt.links.new(mp.outputs['Vector'], lad.inputs['Vector'])
    base = mezclar(nt, lad.outputs['Color'], t['col'], 0.35, 'MULTIPLY')
    # zonas gastadas más claras y zonas más oscuras (grandes)
    desgaste = rampa(nt, ruido(nt, coord, 0.012, 5), [(0.3, (0.86, 0.84, 0.8, 1)), (0.5, (1, 1, 1, 1)), (0.72, (1.15, 1.13, 1.08, 1))])
    # manchas de aceite y suciedad
    aceite = rampa(nt, ruido(nt, coord, 0.18, 12), [(0.58, (1, 1, 1, 1)), (0.72, (0.62, 0.58, 0.52, 1))])
    polvo = rampa(nt, ruido(nt, coord, 2.5, 3), [(0.35, (0.94, 0.94, 0.94, 1)), (0.65, (1.04, 1.04, 1.04, 1))])
    col = mezclar(nt, mezclar(nt, mezclar(nt, base, desgaste, 1.0, 'MULTIPLY'), aceite, 1.0, 'MULTIPLY'), polvo, 1.0, 'MULTIPLY')
    nt.links.new(col, bsdf.inputs['Base Color'])
    rug = nt.nodes.new('ShaderNodeMath'); rug.operation = 'MULTIPLY_ADD'; rug.inputs[1].default_value = 0.25; rug.inputs[2].default_value = 0.72
    nt.links.new(t['rug'], rug.inputs[0]); nt.links.new(rug.outputs[0], bsdf.inputs['Roughness'])
    junta = nt.nodes.new('ShaderNodeBump'); junta.inputs['Strength'].default_value = 0.35
    nt.links.new(lad.outputs['Fac'], junta.inputs['Height']); nt.links.new(t['normal'], junta.inputs['Normal'])
    nt.links.new(junta.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def mat_asfalto(claro=False):
    m = bpy.data.materials.new('Hombrillo' if claro else 'Asfalto')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    coord = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    t = tex_pbr(nt, coord, 'apron' if claro else 'asfalto', 2.5)
    tono = (0.42, 0.41, 0.38, 1) if claro else (0.16, 0.16, 0.155, 1)
    var = rampa(nt, ruido(nt, coord, 0.08, 6), [(0.3, tono), (0.7, tuple(c * 1.25 for c in tono[:3]) + (1,))])
    nt.links.new(mezclar(nt, var, t['col'], 0.6, 'MULTIPLY'), bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.85
    nt.links.new(t['normal'], bsdf.inputs['Normal'])
    return m


def mat_grama(seca=False):
    m = bpy.data.materials.new('Grama seca' if seca else 'Grama')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    coord = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    t = tex_pbr(nt, coord, 'grama', 2.0)
    if seca:
        c = [(0.25, (0.24, 0.22, 0.1, 1)), (0.55, (0.33, 0.3, 0.14, 1)), (0.8, (0.2, 0.22, 0.09, 1))]
    else:
        c = [(0.25, (0.08, 0.15, 0.03, 1)), (0.55, (0.13, 0.2, 0.05, 1)), (0.8, (0.2, 0.22, 0.08, 1))]
    manchas = rampa(nt, ruido(nt, coord, 0.03, 8), c)
    fino = rampa(nt, ruido(nt, coord, 1.5, 4), [(0.3, (0.85, 0.85, 0.85, 1)), (0.7, (1.1, 1.1, 1.1, 1))])
    col = mezclar(nt, mezclar(nt, manchas, t['col'], 0.7, 'MULTIPLY'), fino, 1.0, 'MULTIPLY')
    nt.links.new(col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.95
    nt.links.new(t['normal'], bsdf.inputs['Normal'])
    return m


def mejorar_pisos():
    mats = {'apron': mat_concreto(), 'asfalto': mat_asfalto(), 'grama': mat_grama(), 'campo': mat_grama(seca=True)}
    for ob in bpy.data.objects:
        if not ob.name.startswith('tex_') or ob.type != 'MESH':
            continue
        clave = ob.name.split('_')[1]
        if clave in mats:
            ob.data.materials.clear(); ob.data.materials.append(mats[clave])
    h = bpy.data.objects.get('hangar')   # losa frente al portón del hangar
    for o in (h.children_recursive if h else []):
        if o.type == 'MESH' and len(o.data.vertices) == 4 and min(o.dimensions.x, o.dimensions.y) > 20:
            o.data.materials.clear(); o.data.materials.append(mats['apron'])
    marcas_plataforma()


def franja(nombre, puntos, ancho, mat, z=0.07):
    """Línea pintada sobre el piso a partir de puntos en metros (Blender)."""
    bm = bmesh.new()
    for a, b in zip(puntos[:-1], puntos[1:]):
        d = (b - a); d.z = 0; d.normalize(); n = Vector((-d.y, d.x, 0)) * ancho / 2
        vs = [bm.verts.new(p + Vector((0, 0, z))) for p in (a - n, a + n, b + n, b - n)]
        bm.faces.new(vs)
    me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    ob = bpy.data.objects.new(nombre, me); escena.collection.objects.link(ob)
    return ob


def pintura_gastada(nombre, color):
    """Pintura de piso desteñida y con partes borradas (deja ver el concreto)."""
    m = bpy.data.materials.new(nombre)
    nt, bsdf, out = nodos(m)
    coord = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    fac = rampa(nt, ruido(nt, coord, 0.9, 8), [(0.42, (1, 1, 1, 1)), (0.62, (0, 0, 0, 1))])
    sep = nt.nodes.new('ShaderNodeSeparateColor'); nt.links.new(fac, sep.inputs['Color'])
    bsdf.inputs['Base Color'].default_value = color; bsdf.inputs['Roughness'].default_value = 0.8
    transp = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(sep.outputs[0], mix.inputs['Fac']); nt.links.new(transp.outputs[0], mix.inputs[1]); nt.links.new(bsdf.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    return m


def marca_y(base, ang, largo=12.0, brazo=4.0, mat=None):
    """Marca de estacionamiento en 'Y': tallo y dos brazos abiertos."""
    d = Vector((math.cos(ang), math.sin(ang), 0))
    fin = base + d * largo
    franja('Marca Y', [base, fin], 0.25, mat)
    for s in (-1, 1):
        a = ang + s * math.radians(28)
        franja('Marca Y', [fin, fin + Vector((math.cos(a), math.sin(a), 0)) * brazo], 0.25, mat)


def marcas_plataforma():
    amarillo = pintura_gastada('Pintura amarilla', (0.42, 0.3, 0.07, 1))
    blanco = pintura_gastada('Pintura blanca', (0.75, 0.74, 0.7, 1))
    # línea de rodaje (visible en la imagen satelital)
    franja('Linea de rodaje', [px(-120, 395), px(0, 330), px(560, 0), px(700, -82)], 0.3, amarillo)
    # marcas en "Y" de los puestos de estacionamiento (lado del campo), según la imagen satelital
    perp = ANG_RODAJE + math.pi / 2
    for k in range(6):
        nx, ny = 40 + k * 66, 482 - k * 58          # posiciones en la imagen nueva (más cercana)
        marca_y(px(0.71 * nx + 51.7, 0.71 * ny - 36.3), perp + math.pi, mat=amarillo)
    # helipuertos: círculo y letra H
    for cx, cy in ((330, 100), (385, 45), (440, 5)):
        c = px(cx, cy); r = 7.4
        pts = [c + Vector((math.cos(a) * r, math.sin(a) * r, 0)) for a in [i * 2 * math.pi / 64 for i in range(65)]]
        franja(f'Helipuerto {cx}', pts, 0.4, blanco)
        for dx in (-1.6, 1.6):
            franja('H', [c + Vector((dx, -2.4, 0)), c + Vector((dx, 2.4, 0))], 0.45, blanco)
        franja('H', [c + Vector((-1.6, 0, 0)), c + Vector((1.6, 0, 0))], 0.45, blanco)


# ----------------------------------------------------------------------------- edificios
EDIFICIOS = [
    dict(id='saag', c=(660, 142), L=33, W=15, ang=-36.3, h=7.5, techo='cuatro_aguas', cumbre=2.6, muro=(0.86, 0.85, 0.82), color=(0.55, 0.16, 0.1), rejas=True),
    dict(id='saag_anexo', c=(695, 174), L=23, W=12, ang=-36.9, h=4.5, techo='plano', muro=(0.78, 0.77, 0.74), color=(0.5, 0.5, 0.5)),
    dict(id='saag_caseta', c=(690, 82), L=5, W=4, ang=-36, h=3.5, techo='plano', muro=(0.45, 0.47, 0.48), color=(0.3, 0.31, 0.32)),
    dict(id='anexo_oscuro', c=(427, 272), L=16, W=9, ang=47.9, h=7, techo='plano', muro=(0.62, 0.61, 0.58), color=(0.2, 0.21, 0.22)),
    dict(id='anexo_marron', c=(383, 286), L=18, W=12, ang=47.9, h=5, techo='dos_aguas', cumbre=1.2, muro=(0.66, 0.62, 0.55), color=(0.33, 0.25, 0.18)),
    dict(id='anexo_blanco', c=(457, 330), L=22, W=9, ang=47.9, h=4.8, techo='dos_aguas', cumbre=1.6, muro=(0.6, 0.63, 0.66), color=(0.72, 0.73, 0.74), franja=True),
    dict(id='edif_verde', c=(405, 371), L=21, W=15, ang=47.9, h=6, techo='dos_aguas', cumbre=1.8, muro=(0.74, 0.72, 0.66), color=(0.35, 0.5, 0.28)),
    dict(id='edif_azul', c=(345, 366), L=18, W=9, ang=47.9, h=7, techo='plano', muro=(0.66, 0.64, 0.6), color=(0.15, 0.17, 0.2)),
]
VECINOS = [
    ((275, 470), 46, 22, 47.9, 9, 'dos_aguas', 3, (0.7, 0.68, 0.62), (0.4, 0.52, 0.34)),
    ((195, 552), 46, 22, 47.9, 9, 'dos_aguas', 3, (0.7, 0.68, 0.62), (0.75, 0.75, 0.73)),
    ((112, 612), 46, 22, 47.9, 9, 'dos_aguas', 3, (0.7, 0.68, 0.62), (0.4, 0.1, 0.07)),
    ((30, 640), 40, 22, 47.9, 9, 'dos_aguas', 3, (0.7, 0.68, 0.62), (0.6, 0.6, 0.58)),
    ((275, 398), 14, 8, 47.9, 5, 'dos_aguas', 1.2, (0.74, 0.7, 0.62), (0.65, 0.3, 0.2)),
    ((318, 445), 20, 9, 47.9, 5, 'plano', 0, (0.74, 0.7, 0.62), (0.75, 0.75, 0.72)),
    ((915, 266), 34, 15, -3, 6, 'plano', 0, (0.66, 0.63, 0.57), (0.45, 0.45, 0.44)),
    ((912, 228), 34, 9, -3, 7.5, 'plano', 0, (0.6, 0.58, 0.53), (0.15, 0.16, 0.17)),
    ((942, 305), 8, 9, 0, 4, 'plano', 0, (0.66, 0.63, 0.57), (0.4, 0.4, 0.4)),
    ((986, 305), 5, 6, 0, 3, 'plano', 0, (0.8, 0.78, 0.74), (0.85, 0.85, 0.82)),
    ((890, 468), 28, 12, 0, 5, 'plano', 0, (0.74, 0.72, 0.68), (0.6, 0.61, 0.6)),
    ((889, 513), 28, 13, 0, 5, 'plano', 0, (0.78, 0.77, 0.74), (0.88, 0.88, 0.86)),
    ((980, 474), 7, 10, 0, 3.5, 'plano', 0, (0.78, 0.77, 0.74), (0.88, 0.88, 0.86)),
    ((930, 424), 7, 4, 0, 3, 'plano', 0, (0.66, 0.63, 0.57), (0.5, 0.5, 0.5)),
]


def mat_simple(nombre, color, rug=0.6, metal=0.0):
    m = bpy.data.materials.get(nombre)
    if m:
        return m
    m = bpy.data.materials.new(nombre); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = color + (1,) if len(color) == 3 else color
    b.inputs['Roughness'].default_value = rug; b.inputs['Metallic'].default_value = metal
    return m


def mat_friso(color):
    nombre = 'Friso %.2f %.2f %.2f' % color
    if nombre in bpy.data.materials:
        return bpy.data.materials[nombre]
    m = bpy.data.materials.new(nombre)
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    tc = nt.nodes.new('ShaderNodeTexCoord')
    t = tex_pbr(nt, tc.outputs['Object'], 'friso', 2.0)
    # suciedad que sube desde el piso (salpicaduras de lluvia) y manchas
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Object'], sep.inputs[0])
    sucio = rampa(nt, sep.outputs['Z'], [(0.0, (0.55, 0.5, 0.45, 1)), (0.9, (1, 1, 1, 1))])
    manchas = rampa(nt, ruido(nt, tc.outputs['Object'], 0.6, 8), [(0.45, (1, 1, 1, 1)), (0.75, (0.86, 0.84, 0.8, 1))])
    col = mezclar(nt, mezclar(nt, mezclar(nt, color + (1,), t['col'], 0.55, 'MULTIPLY'), sucio, 1.0, 'MULTIPLY'), manchas, 1.0, 'MULTIPLY')
    nt.links.new(col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.9
    nt.links.new(t['normal'], bsdf.inputs['Normal'])
    return m


def mat_lamina_techo(color):
    nombre = 'Lamina %.2f %.2f %.2f' % color
    if nombre in bpy.data.materials:
        return bpy.data.materials[nombre]
    m = bpy.data.materials.new(nombre)
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    t = tex_pbr(nt, nt.nodes.new('ShaderNodeTexCoord').outputs['UV'], 'lamina', 1.0)
    nt.links.new(mezclar(nt, color + (1,), t['col'], 0.5, 'MULTIPLY'), bsdf.inputs['Base Color'])
    bsdf.inputs['Metallic'].default_value = 0.5; bsdf.inputs['Roughness'].default_value = 0.5
    nt.links.new(t['normal'], bsdf.inputs['Normal'])
    return m


VIDRIO = None


def caja_bm(bm, cx, cy, cz, sx, sy, sz, mat_idx=0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=r['verts'])
    bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=r['verts'])
    for f in {f for v in r['verts'] for f in v.link_faces}:
        f.material_index = mat_idx


def uv_metros(me):
    """UV en metros para cada cara según su orientación (para texturas de lámina)."""
    bm = bmesh.new(); bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        for lp in f.loops:
            p = lp.vert.co
            if abs(n.z) > 0.7:
                lp[uv].uv = (p.x, p.y)
            elif abs(n.x) > abs(n.y):
                lp[uv].uv = (p.y, p.z / max(0.2, abs(n.x)) if abs(n.z) > 0.2 else p.z)
            else:
                lp[uv].uv = (p.x, p.z / max(0.2, abs(n.y)) if abs(n.z) > 0.2 else p.z)
    bm.to_mesh(me); bm.free()


def edificio(nombre, c, L, W, ang, h, techo, cumbre, muro, color, rejas=False, franja_gris=False):
    """Edificio con paredes, zócalo, ventanas con marco (y rejas), puerta, aires acondicionados y techo."""
    global VIDRIO
    VIDRIO = VIDRIO or mat_simple('Vidrio ventana', (0.02, 0.03, 0.035), rug=0.05, metal=0.2)
    mats = [mat_friso(muro), mat_simple('Zocalo', (0.25, 0.25, 0.25), 0.85), VIDRIO, mat_simple('Marco ventana', (0.85, 0.85, 0.83), 0.4),
            mat_simple('Reja', (0.05, 0.05, 0.05), 0.5, 0.6), mat_simple('Puerta metalica', (0.3, 0.32, 0.33), 0.5, 0.5),
            mat_simple('Aire acondicionado', (0.75, 0.75, 0.73), 0.5, 0.2), mat_simple('Pretil', (0.7, 0.7, 0.68), 0.85)]
    bm = bmesh.new()
    caja_bm(bm, 0, 0, h / 2, L, W, h, 0)                                       # paredes
    caja_bm(bm, 0, 0, 0.3, L + 0.04, W + 0.04, 0.6, 1)                         # zócalo
    if franja_gris:
        caja_bm(bm, 0, 0, 0.75, L + 0.03, W + 0.03, 1.5, 1)
        caja_bm(bm, 0, 0, 1.55, L + 0.035, W + 0.035, 0.1, 3)
    pisos = max(1, round(h / 3.4))
    for lado, largo, eje in ((1, L, 'x'), (-1, L, 'x'), (1, W, 'y'), (-1, W, 'y')):
        n = int((largo - 2.5) // 3.3)
        if n < 1:
            continue
        paso = (largo - 2.5) / n
        prof = (W if eje == 'x' else L) / 2
        for p in range(pisos):
            zc = 1.0 + 0.65 + p * 3.3
            if zc + 0.7 > h - 0.3:
                continue
            for k in range(n):
                u = -largo / 2 + 1.25 + paso * (k + 0.5)
                if p == 0 and lado == 1 and eje == 'x' and k == n // 2:
                    # puerta
                    caja_bm(bm, u, prof + 0.03, 1.1, 1.2, 0.08, 2.2, 5)
                    caja_bm(bm, u, prof + 0.05, 2.3, 1.5, 0.12, 0.12, 3)
                    continue
                def pieza(du, dz, su, sz, grosor, sale, idx):
                    if eje == 'x':
                        caja_bm(bm, u + du, lado * (prof + sale), zc + dz, su, grosor, sz, idx)
                    else:
                        caja_bm(bm, lado * (prof + sale), u + du, zc + dz, grosor, su, sz, idx)
                pieza(0, 0, 1.5, 1.4, 0.06, 0.0, 3)                        # marco
                pieza(0, 0, 1.3, 1.2, 0.04, 0.02, 2)                       # vidrio
                pieza(0, -0.78, 1.7, 0.1, 0.2, 0.06, 3)                    # alféizar
                if rejas:
                    for b in range(-3, 4):
                        pieza(b * 0.2, 0, 0.025, 1.3, 0.025, 0.06, 4)
                    pieza(0, 0.3, 1.3, 0.025, 0.025, 0.06, 4)
                    pieza(0, -0.3, 1.3, 0.025, 0.025, 0.06, 4)
                if random.random() < 0.25:                                    # aire acondicionado de ventana
                    pieza(0.3, -0.35, 0.6, 0.45, 0.5, 0.25, 6)
    techo_mat = mat_lamina_techo(color)
    mats.append(techo_mat)
    idx_techo = len(mats) - 1
    if techo == 'plano':
        caja_bm(bm, 0, 0, h + 0.05, L - 0.3, W - 0.3, 0.1, 7)                  # azotea
        for (sx, sy, cx, cy) in ((L, 0.2, 0, W / 2 - 0.1), (L, 0.2, 0, -W / 2 + 0.1), (0.2, W, L / 2 - 0.1, 0), (0.2, W, -L / 2 + 0.1, 0)):
            caja_bm(bm, cx, cy, h + 0.35, sx, sy, 0.7, 7)                      # pretil
        if L * W > 60:
            tq = bpy.data.materials.get('Tanque') or mat_simple('Tanque', (0.03, 0.15, 0.45), 0.4)
            if 'Tanque' not in [m.name for m in mats]:
                mats.append(tq)
            r = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.7, radius2=0.7, depth=1.5)
            bmesh.ops.translate(bm, vec=(L / 2 - 2, W / 2 - 2, h + 0.85), verts=r['verts'])
            for f in {f for v in r['verts'] for f in v.link_faces}:
                f.material_index = len(mats) - 1
            for k in range(max(1, int(L // 10))):
                caja_bm(bm, -L / 2 + 3 + k * 6, 0, h + 0.45, 1.0, 0.8, 0.7, 6)  # aires centrales
    else:
        ov = 0.6; a = L / 2 + ov; b = W / 2 + ov; r = cumbre
        e = max(0.0, (L - W) / 2) if techo == 'cuatro_aguas' else a
        v = [bm.verts.new(p) for p in ((-a, -b, h), (a, -b, h), (a, b, h), (-a, b, h), (-e, 0, h + r), (e, 0, h + r))]
        caras = [(v[0], v[1], v[5], v[4]), (v[2], v[3], v[4], v[5])]
        caras += [(v[1], v[2], v[5]), (v[3], v[0], v[4])] if techo == 'cuatro_aguas' else []
        for cara in caras:
            f = bm.faces.new(cara); f.material_index = idx_techo
        if techo == 'dos_aguas':                                               # hastiales
            for s in (-1, 1):
                f = bm.faces.new([bm.verts.new((s * L / 2, -W / 2, h)), bm.verts.new((s * L / 2, W / 2, h)), bm.verts.new((s * L / 2, 0, h + r))])
                f.material_index = 0
        # techo con espesor
        geom = [f for f in bm.faces if f.material_index == idx_techo]
        bmesh.ops.solidify(bm, geom=geom, thickness=0.08)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free()
    for m in mats:
        me.materials.append(m)
    uv_metros(me)
    ob = bpy.data.objects.new(nombre, me)
    COL_EDIF.objects.link(ob)
    centro = px(*c)
    ob.location = centro
    ob.rotation_euler = (0, 0, -math.radians(ang))
    return ob


COL_EDIF = None


def borrar_jerarquia(raiz):
    for hijo in list(raiz.children_recursive):
        bpy.data.objects.remove(hijo, do_unlink=True)
    bpy.data.objects.remove(raiz, do_unlink=True)


def mejorar_edificios():
    global COL_EDIF
    COL_EDIF = bpy.data.collections.new('Edificios'); escena.collection.children.link(COL_EDIF)
    for d in EDIFICIOS:
        viejo = bpy.data.objects.get(d['id'])
        if viejo:
            borrar_jerarquia(viejo)
        edificio(d['id'], d['c'], d['L'], d['W'], d['ang'], d['h'], d['techo'], d.get('cumbre', 0), d['muro'], d['color'],
                 rejas=d.get('rejas', False), franja_gris=d.get('franja', False))
    for i, (c, L, W, ang, h, techo, cumbre, muro, color) in enumerate(VECINOS):
        viejo = bpy.data.objects.get(f'vecino_{i}')
        if viejo:
            borrar_jerarquia(viejo)
        edificio(f'vecino_{i}', c, L, W, ang, h, techo, cumbre, muro, color)


# ----------------------------------------------------------------------------- árboles
def cargar_modelo_arbol(nombre):
    ruta = os.path.join(RAIZ, 'assets', 'arboles', nombre, f'{nombre}_1k.gltf')
    if not os.path.exists(ruta):
        return None
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=ruta)
    nuevos = [o for o in bpy.data.objects if o not in antes]
    col = bpy.data.collections.new('Modelo ' + nombre)
    bpy.context.scene.collection.children.link(col)
    for o in nuevos:
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)
    # medidas del modelo (para escalarlo a la copa de cada árbol)
    pts = [o.matrix_world @ Vector(v) for o in nuevos if o.type == 'MESH' for v in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    col.instance_offset = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
    # hojas: un poco de translucidez para que no se vean negras a contraluz
    for o in nuevos:
        for ranura in getattr(o, 'material_slots', []):
            m = ranura.material
            if m and m.use_nodes:
                b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if b and 'Transmission Weight' in b.inputs and ('leaf' in m.name.lower() or 'leaves' in m.name.lower()):
                    b.inputs['Transmission Weight'].default_value = 0.15
    return col, max(mx.x - mn.x, mx.y - mn.y), mx.z - mn.z


def mejorar_arboles():
    modelos = [m for m in (cargar_modelo_arbol('island_tree_01'), cargar_modelo_arbol('tree_small_02')) if m]
    if not modelos:
        print('No hay modelos de árboles descargados; se dejan los actuales.')
        return
    col_arb = bpy.data.collections.new('Arboles'); escena.collection.children.link(col_arb)
    for ob in [o for o in bpy.data.objects if o.name.startswith('arbol_') and o.type == 'EMPTY']:
        pts = [h.matrix_world @ Vector(v) for h in ob.children_recursive if h.type == 'MESH' for v in h.bound_box]
        if not pts:
            continue
        ancho = max(max(p.x for p in pts) - min(p.x for p in pts), max(p.y for p in pts) - min(p.y for p in pts))
        pos = ob.matrix_world.translation.copy(); pos.z = 0
        i = int(ob.name.split('_')[1])
        col, ancho_m, _ = modelos[0] if (i % 3 or len(modelos) == 1) else modelos[1]
        inst = bpy.data.objects.new(f'Arbol_{i:02d}', None)
        inst.instance_type = 'COLLECTION'; inst.instance_collection = col
        inst.location = pos; inst.rotation_euler = (0, 0, random.uniform(0, 2 * math.pi))
        inst.scale = (ancho / ancho_m,) * 3
        col_arb.objects.link(inst)
        borrar_jerarquia(ob)
    for col, _, _ in modelos:   # los modelos originales quedan ocultos (solo se usan como fuente)
        lc = bpy.context.view_layer.layer_collection.children.get(col.name)
        if lc:
            lc.exclude = True


def mejorar_hangar():
    """Bóveda del hangar: lámina verde menta por fuera (como en las fotos) y galvanizada por dentro, en una sola superficie."""
    h = bpy.data.objects.get('hangar')
    if not h:
        return
    bovedas = [o for o in h.children_recursive if o.type == 'MESH' and len(o.data.vertices) == 146 and o.material_slots
               and o.material_slots[0].material and o.material_slots[0].material.node_tree
               and any(n.type == 'TEX_IMAGE' for n in o.material_slots[0].material.node_tree.nodes)]
    if not bovedas:
        print('Bóveda del hangar no encontrada'); return
    for o in bovedas[1:]:
        bpy.data.objects.remove(o, do_unlink=True)
    m = bpy.data.materials.new('Lamina hangar')
    nt, bsdf, out = nodos(m); nt.links.new(bsdf.outputs[0], out.inputs[0])
    t = tex_pbr(nt, nt.nodes.new('ShaderNodeTexCoord').outputs['UV'], 'lamina', 1.2)
    verde = mezclar(nt, (0.03, 0.42, 0.25, 1), t['col'], 0.45, 'MULTIPLY')
    gris = mezclar(nt, (0.45, 0.47, 0.48, 1), t['col'], 0.6, 'MULTIPLY')
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    nt.links.new(mezclar(nt, verde, gris, geo.outputs['Backfacing']), bsdf.inputs['Base Color'])
    bsdf.inputs['Metallic'].default_value = 0.35; bsdf.inputs['Roughness'].default_value = 0.45
    nt.links.new(t['normal'], bsdf.inputs['Normal'])
    b = bovedas[0]; b.data.materials.clear(); b.data.materials.append(m)


# ----------------------------------------------------------------------------- aeronaves descargadas
# Marco del acto (= marco del hangar en el visor): posición y giro del hangar en three.js
ACTO_POS, ACTO_GIRO = (-27.28, 11.16), -0.83601


def acto_a_blender(x, z):
    """Coordenadas locales del acto (x hacia la vía, z) -> Blender."""
    a = ACTO_GIRO
    X = x * math.cos(a) + z * math.sin(a) + ACTO_POS[0]
    Z = -x * math.sin(a) + z * math.cos(a) + ACTO_POS[1]
    return Vector((X, -Z, 0))


def plano_a_blender(X, Y):
    """Píxel del plano de distribución ampliado -> Blender (0,245 m/px, centro del hangar en 282, 588)."""
    return acto_a_blender((Y - 588) * 0.245, -(X - 282) * 0.245)


RUMBO_TRIBUNA = math.atan2(math.sin(ACTO_GIRO), math.cos(ACTO_GIRO))   # dirección +x del acto en Blender
TUCANOS = [(700, 195), (810, 195), (1090, 195), (1200, 195)]           # fila detrás del Y-8F (píxeles del plano)


# Piezas que conservan el color de la textura original (cauchos, hélice, tren, cabina, escapes)
PIEZAS_TUCANO = ('Blade', 'Wheel', 'Seat', 'Cockpit', 'Exhausts', 'Cylinder', 'Scissor', 'TaxiLights', 'Grill',
                 'Antenna', 'PanelBack', 'PanelFront', 'Arch')
# Camuflaje AMB (lineal): arena, verde y verde oscuro, como el T-27 de la foto del usuario
CAMO_ARENA, CAMO_VERDE, CAMO_OSCURO = (0.36, 0.27, 0.15, 1), (0.10, 0.14, 0.075, 1), (0.035, 0.055, 0.03, 1)
AMARILLO_VE, AZUL_VE, ROJO_VE, BLANCO = (0.9, 0.6, 0.02, 1), (0.0, 0.02, 0.21, 1), (0.62, 0.01, 0.025, 1), (0.8, 0.8, 0.78, 1)


def _mate(nt, op, a, b=None):
    n = nt.nodes.new('ShaderNodeMath'); n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _caja(nt, y, z, nx, y0, y1, z0, z1):
    """1 dentro del rectángulo (y, z) de la superficie lateral del avión (normal hacia los lados), 0 fuera."""
    f = _mate(nt, 'MULTIPLY', _mate(nt, 'GREATER_THAN', y, y0), _mate(nt, 'LESS_THAN', y, y1))
    f = _mate(nt, 'MULTIPLY', f, _mate(nt, 'GREATER_THAN', z, z0))
    f = _mate(nt, 'MULTIPLY', f, _mate(nt, 'LESS_THAN', z, z1))
    return _mate(nt, 'MULTIPLY', f, _mate(nt, 'GREATER_THAN', _mate(nt, 'ABSOLUTE', nx), 0.4))


def _rampa_fija(nt, fac, colores):
    s = rampa(nt, fac, colores); s.node.color_ramp.interpolation = 'CONSTANT'
    return s


def pintar_tucano_amb(nuevos, carpeta):
    mats = {s.material for o in nuevos if o.type == 'MESH' for s in o.material_slots if s.material}
    pintura = next((m for m in mats if m.name.lower().startswith('paint')), None)
    vidrio = next((m for m in mats if m.name.lower().startswith('glass')), None)
    if vidrio:
        b = next((n for n in vidrio.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        b.inputs['Base Color'].default_value = (0.6, 0.7, 0.72, 1)
        b.inputs['Roughness'].default_value = 0.03; b.inputs['Metallic'].default_value = 0.0
        if 'Transmission Weight' in b.inputs:
            b.inputs['Transmission Weight'].default_value = 0.9
    if not pintura:
        return
    # piezas: copia del material original con su textura tal cual
    piezas = pintura.copy(); piezas.name = 'Tucano piezas'
    bp = next((n for n in piezas.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bp:
        bp.inputs['Roughness'].default_value = 0.55; bp.inputs['Metallic'].default_value = 0.2
        # el azul de la FAB en marcos y piezas pasa a gris oscuro (las puntas amarillas de la hélice se quedan)
        pt = piezas.node_tree
        im = next((n for n in pt.nodes if n.type == 'TEX_IMAGE'), None)
        if im:
            hs = pt.nodes.new('ShaderNodeSeparateColor'); hs.mode = 'HSV'; pt.links.new(im.outputs['Color'], hs.inputs[0])
            azul = _mate(pt, 'MULTIPLY', _mate(pt, 'GREATER_THAN', hs.outputs[1], 0.4),
                         _mate(pt, 'MULTIPLY', _mate(pt, 'GREATER_THAN', hs.outputs[0], 0.5), _mate(pt, 'LESS_THAN', hs.outputs[0], 0.8)))
            pt.links.new(mezclar(pt, im.outputs['Color'], (0.035, 0.037, 0.04, 1), azul), bp.inputs['Base Color'])
    for o in nuevos:
        if o.type == 'MESH' and o.name.startswith(PIEZAS_TUCANO):
            for i, m in enumerate(o.data.materials):
                if m == pintura:
                    o.data.materials[i] = piezas

    def img(nombre, color=False):
        n = nt.nodes.new('ShaderNodeTexImage'); n.image = bpy.data.images.load(os.path.join(carpeta, nombre))
        n.image.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
        return n
    nt, bsdf, out = nodos(pintura); nt.links.new(bsdf.outputs[0], out.inputs[0])
    original, mascara, suciedad = img('Diffuse.jpg', True), img('Mascara_pintura.png'), img('Suciedad.png')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    # coordenadas del avión en metros: el FBX viene en cm con Y hacia arriba (x, y, z) -> (x, -z, y)
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Object'], sep.inputs[0])
    X = _mate(nt, 'MULTIPLY', sep.outputs['X'], 0.01)
    Y = _mate(nt, 'MULTIPLY', sep.outputs['Z'], -0.01)
    Z = _mate(nt, 'MULTIPLY', sep.outputs['Y'], 0.01)
    p = nt.nodes.new('ShaderNodeCombineXYZ')
    for i, v in enumerate((X, Y, Z)):
        nt.links.new(v, p.inputs[i])
    nsep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Normal'], nsep.inputs[0])
    nx = nsep.outputs['X']
    # camuflaje: manchas grandes de bordes definidos (dos ruidos: arena / verdes, verde / oscuro)
    manchas = []
    for k, (esc, desf) in enumerate(((0.32, (0, 0, 0)), (0.45, (13.7, 5.1, 2.3)))):
        d = nt.nodes.new('ShaderNodeVectorMath'); d.operation = 'ADD'; d.inputs[1].default_value = desf
        nt.links.new(p.outputs[0], d.inputs[0])
        n = nt.nodes.new('ShaderNodeTexNoise')
        n.inputs['Scale'].default_value = esc; n.inputs['Detail'].default_value = 1.5
        n.inputs['Roughness'].default_value = 0.45; n.inputs['Distortion'].default_value = 0.35
        nt.links.new(d.outputs[0], n.inputs['Vector'])
        manchas.append(n.outputs['Fac'])
    verdes = _rampa_fija(nt, manchas[1], [(0.0, CAMO_OSCURO), (0.5, CAMO_VERDE), (1.0, CAMO_VERDE)])
    camo = mezclar(nt, verdes, CAMO_ARENA, _mate(nt, 'GREATER_THAN', manchas[0], 0.57))
    # bandera de Venezuela en el fuselaje trasero (ambos lados)
    bandera = _caja(nt, Y, Z, nx, 1.99, 2.41, 0.99, 1.27)
    franjas = _rampa_fija(nt, _mate(nt, 'DIVIDE', _mate(nt, 'SUBTRACT', Z, 0.99), 0.28),
                          [(0.0, ROJO_VE), (0.333, AZUL_VE), (0.667, AMARILLO_VE), (1.0, AMARILLO_VE)])
    camo = mezclar(nt, camo, franjas, bandera)
    # distintivo en la deriva: campo rojo con triángulo blanco apuntando hacia la proa
    y0, y1, z0, z1 = 3.46, 3.88, 2.60, 2.89
    deriva = _caja(nt, Y, Z, nx, y0, y1, z0, z1)
    u = _mate(nt, 'DIVIDE', _mate(nt, 'SUBTRACT', Y, y0), y1 - y0)
    v = _mate(nt, 'ABSOLUTE', _mate(nt, 'SUBTRACT', _mate(nt, 'DIVIDE', _mate(nt, 'SUBTRACT', Z, z0), z1 - z0), 0.5))
    tri = _mate(nt, 'LESS_THAN', _mate(nt, 'MULTIPLY', v, 2.2), u)
    flash = mezclar(nt, ROJO_VE, BLANCO, tri)
    camo = mezclar(nt, camo, flash, deriva)
    # desgaste: suciedad de la textura (realzada) y manchas suaves de polvo y aceite
    suc = _mate(nt, 'POWER', suciedad.outputs['Color'], 3.0)
    camo = mezclar(nt, camo, suc, 1.0, 'MULTIPLY')
    polvo = rampa(nt, ruido(nt, p.outputs[0], 2.5, 4.0), [(0.3, (0.82, 0.8, 0.78, 1)), (0.7, (1, 1, 1, 1))])
    camo = mezclar(nt, camo, polvo, 1.0, 'MULTIPLY')
    # también se pinta todo lo que conserve color de la FAB (piezas sueltas azules o amarillas)
    hsv = nt.nodes.new('ShaderNodeSeparateColor'); hsv.mode = 'HSV'; nt.links.new(original.outputs['Color'], hsv.inputs[0])
    pinta = _mate(nt, 'MAXIMUM', mascara.outputs['Color'], _mate(nt, 'GREATER_THAN', hsv.outputs[1], 0.45))
    color = mezclar(nt, original.outputs['Color'], camo, pinta)
    nt.links.new(color, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.62; bsdf.inputs['Metallic'].default_value = 0.0
    bu = nt.nodes.new('ShaderNodeBump'); bu.inputs['Strength'].default_value = 0.25
    nt.links.new(img('Bumpmap.jpg').outputs['Color'], bu.inputs['Height']); nt.links.new(bu.outputs['Normal'], bsdf.inputs['Normal'])


def aeronaves_tucano():
    ruta = os.path.join(RAIZ, 'assets', 'aeronaves', 'tucano', 'EMB_312.fbx')
    if not os.path.exists(ruta):
        return
    antes = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=ruta)
    nuevos = [o for o in bpy.data.objects if o not in antes]
    col = bpy.data.collections.new('Modelo Tucano'); escena.collection.children.link(col)
    for o in nuevos:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    pintar_tucano_amb(nuevos, os.path.join(os.path.dirname(ruta), 'texturas'))
    lc = bpy.context.view_layer.layer_collection.children.get(col.name)
    if lc:
        lc.exclude = True
    col_a = bpy.data.collections.new('Tucanos'); escena.collection.children.link(col_a)
    for k, (X, Y) in enumerate(TUCANOS):
        inst = bpy.data.objects.new(f'Tucano_{k + 1}', None)
        inst.instance_type = 'COLLECTION'; inst.instance_collection = col
        inst.location = plano_a_blender(X, Y)
        inst.rotation_euler = (0, 0, RUMBO_TRIBUNA + math.pi / 2)   # el modelo trae la proa hacia -Y
        col_a.objects.link(inst)
    # cámara para ver la fila de Tucanos de cerca
    # vista de tres cuartos desde adelante y a un lado de la fila, mirando a lo largo de ella
    t1, t2 = plano_a_blender(*TUCANOS[0]), plano_a_blender(*TUCANOS[1])
    d = Vector((math.cos(RUMBO_TRIBUNA), math.sin(RUMBO_TRIBUNA), 0))
    fila = (t2 - t1).normalized()
    cd = bpy.data.cameras.new('tucanos'); cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(32); cd.clip_end = 60000
    cam = bpy.data.objects.new('Cam_tucanos', cd); escena.collection.objects.link(cam)
    cam.location = t1 + d * 16 - fila * 14 + Vector((0, 0, 1.9))
    cam.rotation_euler = ((t1 + t2) / 2 + Vector((0, 0, 1.2)) - cam.location).to_track_quat('-Z', 'Y').to_euler()


# Modelos descargados (Sketchfab, CC-BY 4.0) que reemplazan a los hechos a mano en el visor.
# (archivo, píxeles del plano, giro para que la proa mire a la tribuna, mínimo de piezas del modelo viejo)
AERONAVES_GLB = [
    ('c130/lockheed_c-130_hercules.glb', 'Hercules C-130', [(950, 258)], math.pi / 2, 30),   # en lugar del Y-8F
    ('da40/diamond_da40.glb', 'Diamond DA40', [(920, 380)], math.pi, 10),                  # proa del modelo hacia -X
]


# Texturas con la cola AMB (bandera y número), hechas con herramientas/matricula_c130.py
TEXTURAS_AMB = {'Hercules C-130': {'C130_Wings_Right': 'c130/texturas/img1_amb.png',
                                   'C130_Wings_Left': 'c130/texturas/img5_amb.png'}}


def borrar_avion_viejo(pos, min_piezas):
    """Borra el avión procedural del visor que está en esa posición (grupo con muchas piezas)."""
    for o in list(bpy.data.objects):
        if o.type == 'EMPTY' and o.parent and len(o.children_recursive) >= min_piezas \
                and (o.matrix_world.translation.xy - pos.xy).length < 0.5:
            borrar_jerarquia(o)
            return True
    return False


def aeronaves_glb():
    for archivo, nombre, puestos, giro, min_piezas in AERONAVES_GLB:
        ruta = os.path.join(RAIZ, 'assets', 'aeronaves', archivo)
        if not os.path.exists(ruta):
            continue
        antes = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=ruta)
        nuevos = [o for o in bpy.data.objects if o not in antes]
        col = bpy.data.collections.new('Modelo ' + nombre); escena.collection.children.link(col)
        for o in nuevos:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            col.objects.link(o)
        for prefijo, archivo_tex in TEXTURAS_AMB.get(nombre, {}).items():
            ruta_tex = os.path.join(RAIZ, 'assets', 'aeronaves', archivo_tex)
            if not os.path.exists(ruta_tex):
                continue
            nueva = bpy.data.images.load(ruta_tex)
            for m in {s.material for o in nuevos if o.type == 'MESH' for s in o.material_slots if s.material}:
                if m.name.startswith(prefijo) and m.use_nodes:
                    b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                    if b and b.inputs['Base Color'].is_linked:
                        nodo = b.inputs['Base Color'].links[0].from_node
                        if nodo.type == 'TEX_IMAGE':
                            nodo.image = nueva
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ v.co for o in nuevos if o.type == 'MESH' for v in o.data.vertices]
        mn = Vector([min(p[i] for p in pts) for i in range(3)]); mx = Vector([max(p[i] for p in pts) for i in range(3)])
        col.instance_offset = ((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z)   # centro del avión, ruedas en el piso
        lc = bpy.context.view_layer.layer_collection.children.get(col.name)
        if lc:
            lc.exclude = True
        for k, (X, Y) in enumerate(puestos):
            p = plano_a_blender(X, Y)
            borrar_avion_viejo(p, min_piezas)
            inst = bpy.data.objects.new(f'{nombre}_{k + 1}', None)
            inst.instance_type = 'COLLECTION'; inst.instance_collection = col
            inst.location = p; inst.rotation_euler = (0, 0, RUMBO_TRIBUNA + giro)
            escena.collection.objects.link(inst)
            if k == 0 and nombre.startswith('Hercules'):
                # cámara de tres cuartos desde adelante, a la altura de una persona
                d = Vector((math.cos(RUMBO_TRIBUNA), math.sin(RUMBO_TRIBUNA), 0)); lado = Vector((-d.y, d.x, 0))
                cd = bpy.data.cameras.new('hercules'); cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(40); cd.clip_end = 60000
                cam = bpy.data.objects.new('Cam_hercules', cd); escena.collection.objects.link(cam)
                cam.location = p + d * 22 + lado * 30 + Vector((0, 0, 1.7))   # antes de la fila de helicópteros
                cam.rotation_euler = (p + Vector((0, 0, 4.5)) - cam.location).to_track_quat('-Z', 'Y').to_euler()


def camara_panoramica():
    """Vista panorámica alta desde el oeste: aviones, tribuna, SAAG y hangar en una sola imagen (2880 x 1200)."""
    centro = Vector((15, 75, 0)); perp = Vector((0.92, -0.38, 0)); izq = Vector((0.38, 0.92, 0))
    cd = bpy.data.cameras.new('panoramica'); cd.sensor_fit = 'HORIZONTAL'; cd.angle_x = math.radians(96); cd.clip_end = 60000
    cam = bpy.data.objects.new('Cam_panoramica', cd); escena.collection.objects.link(cam)
    cam.location = centro - perp * 128 + izq * 4 + Vector((0, 0, 36))
    cam.rotation_euler = (centro + izq * 2 + Vector((0, 0, 9)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam['resolucion'] = (2880, 1200)   # renderizar.py usa esta resolución en vez de 1920 x 1080


def aplicar_todo():
    camara_panoramica()
    aeronaves_glb()
    aeronaves_tucano()
    mejorar_hangar()
    mejorar_pisos()
    mejorar_edificios()
    mejorar_arboles()
