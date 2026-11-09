"""Capa de realismo para la escena de Blender. Se ejecuta desde armar_blender.py DESPUÉS del cielo y las cámaras
(usa escena, amb, mapeo, RAIZ, DIR_B y las funciones de mejoras_blender.py: nodos, tex_pbr, ruido, rampa, mezclar, _mate).

Qué hace:
  - Bruma (perspectiva aérea): los objetos lejanos se funden con el color del cielo en el horizonte.
  - Relieve rehecho a la resolución completa de los datos (75 m) con detalle fractal: crestas creíbles.
  - Lago de Valencia a su nivel real (el de los datos), no inundando las partes bajas.
  - Campo alrededor de la base: parcelas con surcos, potreros verdes, siembras, monte en los linderos.
  - Árboles de fondo (miles de copias de los modelos reales) en linderos, manchas de monte y sueltos.
  - Copas de mango densas y oscuras; palmas con hojas de verdad (raquis y foliolos).
  - Luces del hangar por dentro (lámparas industriales) y exposición por cámara.
  - Composición: brillo suave de altas luces, aberración cromática leve y viñeta de lente.
"""
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

EXPOSICION_BASE = 0.0                       # se ajusta abajo según la irradiancia del sol (ver calibrar_exposicion)
EXPOSICION_CAMARA = {'proyectos': 4.0}      # ajustes por vista: adentro del hangar hay ~1 % de la luz de afuera
ALCANCE_BRUMA = 13000.0                     # m: distancia a la que queda 63 % de bruma (valle de Aragua, día húmedo)
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def entrada(nodo, nombre):
    """Socket de entrada visible con ese nombre (algunos nodos repiten nombres por tipo de dato)."""
    return next(s for s in nodo.inputs if s.name == nombre and s.enabled)


def salida_n(nodo, nombre):
    return next(s for s in nodo.outputs if s.name == nombre and s.enabled)


def unir(nt, a, b):
    nt.links.new(a, b)


# ============================================================================ bruma (perspectiva aérea)
def grupo_bruma():
    """Mezcla el sombreado con el cielo del horizonte en la misma dirección: L = L·T + cielo·(1−T), T = e^(−d/ℓ).
    Entrada 'Opacidad' para hojas recortadas (la bruma no debe pintar los huecos del recorte)."""
    g = bpy.data.node_groups.get('Bruma')
    if g:
        return g
    g = bpy.data.node_groups.new('Bruma', 'ShaderNodeTree')
    g.interface.new_socket('Shader', in_out='INPUT', socket_type='NodeSocketShader')
    s_op = g.interface.new_socket('Opacidad', in_out='INPUT', socket_type='NodeSocketFloat'); s_op.default_value = 1.0
    g.interface.new_socket('Shader', in_out='OUTPUT', socket_type='NodeSocketShader')
    ent = g.nodes.new('NodeGroupInput'); sal = g.nodes.new('NodeGroupOutput')
    cam = g.nodes.new('ShaderNodeCameraData')
    f = _mate(g, 'MULTIPLY', cam.outputs['View Distance'], -1.0 / ALCANCE_BRUMA)
    f = _mate(g, 'SUBTRACT', 1.0, _mate(g, 'EXPONENT', f))
    f = _mate(g, 'MULTIPLY', f, ent.outputs['Opacidad'])
    # dirección de vista aplanada al horizonte (un poco por encima) -> mismo giro que el mundo -> cielo
    geo = g.nodes.new('ShaderNodeNewGeometry')
    sep = g.nodes.new('ShaderNodeSeparateXYZ'); unir(g, geo.outputs['Incoming'], sep.inputs[0])
    comb = g.nodes.new('ShaderNodeCombineXYZ')
    unir(g, _mate(g, 'MULTIPLY', sep.outputs['X'], -1.0), comb.inputs['X'])
    unir(g, _mate(g, 'MULTIPLY', sep.outputs['Y'], -1.0), comb.inputs['Y'])
    comb.inputs['Z'].default_value = 0.0
    nrm = g.nodes.new('ShaderNodeVectorMath'); nrm.operation = 'NORMALIZE'; unir(g, comb.outputs[0], nrm.inputs[0])
    sube = g.nodes.new('ShaderNodeVectorMath'); sube.operation = 'ADD'; sube.inputs[1].default_value = (0, 0, 0.035)
    unir(g, nrm.outputs[0], sube.inputs[0])
    mp = g.nodes.new('ShaderNodeMapping'); mp.inputs['Rotation'].default_value = mapeo.inputs['Rotation'].default_value
    unir(g, sube.outputs[0], mp.inputs['Vector'])
    env = g.nodes.new('ShaderNodeTexEnvironment'); env.image = amb.image
    unir(g, mp.outputs['Vector'], env.inputs['Vector'])
    em = g.nodes.new('ShaderNodeEmission'); unir(g, env.outputs['Color'], em.inputs['Color'])
    mix = g.nodes.new('ShaderNodeMixShader')
    unir(g, f, mix.inputs['Fac']); unir(g, ent.outputs['Shader'], mix.inputs[1]); unir(g, em.outputs[0], mix.inputs[2])
    unir(g, mix.outputs[0], sal.inputs['Shader'])
    return g


def con_bruma(m):
    """Mete el grupo Bruma entre el sombreado y la salida del material (una sola vez)."""
    if not m or not m.use_nodes or m.get('bruma'):
        return
    nt = m.node_tree
    if not m.get('mango') and any(n.type in ('BSDF_TRANSPARENT', 'HOLDOUT') for n in nt.nodes):
        return                                     # pinturas de piso recortadas: están cerca, no hace falta
    out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None) \
        or next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if not out or not out.inputs['Surface'].links:
        return
    origen = out.inputs['Surface'].links[0].from_socket
    gn = nt.nodes.new('ShaderNodeGroup'); gn.node_tree = grupo_bruma()
    unir(nt, origen, gn.inputs['Shader']); unir(nt, gn.outputs['Shader'], out.inputs['Surface'])
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf and bsdf.inputs['Alpha'].links:
        unir(nt, bsdf.inputs['Alpha'].links[0].from_socket, gn.inputs['Opacidad'])
    # La emisión de la bruma NO es una fuente de luz: si Cycles la muestrea, arma el árbol de luces con cada
    # triángulo de la escena (millones de hojas x miles de árboles) y se queda horas en "Updating Lights".
    m.cycles.emission_sampling = 'NONE'
    m['bruma'] = True


# ============================================================================ relieve a resolución completa
LAT, LON, ZOOM, TX, TY, N_DEM = 10.246466, -67.650342, 11, 638, 964, 768


def _ruido_valor(n, periodo_px, semilla):
    """Ruido de valor suave (bicúbico simple) en una grilla n x n, periodo en píxeles."""
    rng = np.random.default_rng(semilla)
    k = int(math.ceil(n / periodo_px)) + 3
    g = rng.standard_normal((k, k)).astype(np.float32)
    t = np.arange(n, dtype=np.float32) / periodo_px
    i = np.floor(t).astype(int); f = t - i
    f = f * f * (3 - 2 * f)
    a = g[np.ix_(i, i)]; b = g[np.ix_(i, i + 1)]; c = g[np.ix_(i + 1, i)]; d = g[np.ix_(i + 1, i + 1)]
    fy, fx = f[:, None], f[None, :]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def rehacer_relieve():
    """El visor usaba 1 de cada 2 datos (150 m): de lejos las montañas se veían como lomas lisas de pocos triángulos.
    Se rehace con todos los datos (75 m), duplicados a 37,5 m con interpolación y detalle fractal en las laderas."""
    ruta = os.path.join(RAIZ, 'assets', 'relieve', 'terrarium_z11_638-640_964-966.png')
    viejo = bpy.data.objects.get('relieve')
    if not os.path.exists(ruta) or not viejo:
        return None
    im = bpy.data.images.load(ruta); im.colorspace_settings.name = 'Non-Color'
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32); im.pixels.foreach_get(px)
    px = np.flipud(px.reshape(h, w, 4))[:N_DEM, :N_DEM] * 255.0         # filas de arriba hacia abajo, como el PNG
    alt = px[..., 0] * 256 + px[..., 1] + px[..., 2] / 256 - 32768
    bpy.data.images.remove(im)
    n = 2 ** ZOOM; lr = math.radians(LAT)
    sx = ((LON + 180) / 360 * n - TX) * 256
    sy = ((1 - math.asinh(math.tan(lr)) / math.pi) / 2 * n - TY) * 256
    mpp = 40075016.686 * math.cos(lr) / (n * 256)
    base = alt[int(round(sy)), int(round(sx))]
    # nivel real del Lago de Valencia en los datos: la altura más repetida entre 380 y 425 m (agua = plano)
    agua = alt[(alt > 380) & (alt < 425)]
    nivel_lago = float(np.bincount(np.round(agua).astype(int) - 380).argmax() + 380) if agua.size else 409.5
    # duplicar resolución (bilineal) y mantener la extensión
    F = 2
    M = (N_DEM - 1) * F + 1
    t = np.arange(M, dtype=np.float32) / F
    i0 = np.minimum(np.floor(t).astype(int), N_DEM - 2); fr = t - i0
    A = alt[np.ix_(i0, i0)]; B = alt[np.ix_(i0, i0 + 1)]; C = alt[np.ix_(i0 + 1, i0)]; D = alt[np.ix_(i0 + 1, i0 + 1)]
    fy, fx = fr[:, None], fr[None, :]
    H = (A * (1 - fx) + B * fx) * (1 - fy) + (C * (1 - fx) + D * fx) * fy
    I, J = np.meshgrid(t, t)                     # I: columna (x), J: fila (z del visor)
    X = (I - sx) * mpp; Z = (J - sy) * mpp
    r = np.hypot(X, Z)
    s = np.clip((r - 1600) / (3800 - 1600), 0, 1); s = s * s * (3 - 2 * s)
    # detalle fractal en laderas (crestas, cárcavas): más fuerte cuanto más alto sobre el valle
    sobre = np.clip((H - base) / 350.0, 0.0, 1.0)
    det = np.zeros_like(H)
    for k, (per_m, amp) in enumerate(((1500, 34), (700, 18), (330, 9), (160, 4.5), (80, 2.2))):
        det += amp * _ruido_valor(M, per_m / (mpp / F), 11 + k)
    det = np.abs(det) * -0.6 + det * 0.4 + 6       # algo de "cresta" (ruido plegado), sin subir el valle
    tierra = H > nivel_lago + 0.5
    Hf = np.where(tierra, H + det * sobre * (0.25 + 0.75 * s), H)
    Y = (1 - s) * -0.6 + s * (np.maximum(Hf, 0) - base)
    verts = np.stack([X, -Z, Y], axis=-1).reshape(-1, 3).astype(np.float32)
    ii, jj = np.meshgrid(np.arange(M - 1), np.arange(M - 1))
    k = (jj * M + ii).ravel()
    caras = np.stack([k, k + M, k + M + 1, k + 1], axis=1)
    me = bpy.data.meshes.new('relieve')
    me.vertices.add(len(verts)); me.vertices.foreach_set('co', verts.ravel())
    me.loops.add(caras.size); me.loops.foreach_set('vertex_index', caras.ravel().astype(np.int32))
    me.polygons.add(len(caras))
    me.polygons.foreach_set('loop_start', np.arange(0, caras.size, 4, dtype=np.int32))
    me.update(); me.validate()
    me.shade_smooth()
    ob = bpy.data.objects.new('relieve', me)
    for c in viejo.users_collection:
        c.objects.link(ob)
    bpy.data.objects.remove(viejo, do_unlink=True)
    ob.name = 'relieve'
    lago = bpy.data.objects.get('Mesh_1197')
    if lago:
        lago.name = 'lago'
        lago.location.z += (nivel_lago - base + 0.15) - lago.matrix_world.translation.z
        lago.data.materials.clear(); lago.data.materials.append(mat_lago())
    print(f'Relieve: {M}x{M} vértices ({mpp / F:.1f} m), base {base:.0f} m, lago a {nivel_lago:.0f} m')
    return ob


def mat_lago():
    m = bpy.data.materials.new('Lago de Valencia')
    nt, bsdf, out = nodos(m); unir(nt, bsdf.outputs[0], out.inputs[0])
    bsdf.inputs['Base Color'].default_value = (0.03, 0.045, 0.035, 1)   # agua eutrófica, verdosa
    bsdf.inputs['Roughness'].default_value = 0.08
    pos = nt.nodes.new('ShaderNodeNewGeometry').outputs['Position']
    ola = nt.nodes.new('ShaderNodeBump'); ola.inputs['Strength'].default_value = 0.15; ola.inputs['Distance'].default_value = 0.5
    unir(nt, ruido(nt, pos, 0.02, 4), ola.inputs['Height']); unir(nt, ola.outputs[0], bsdf.inputs['Normal'])
    return m


# ============================================================================ materiales de terreno
PARCELA_M = 170.0           # tamaño medio de las parcelas de cultivo (m)
PARCELA_AZAR = 0.85


def _coord_xy(nt):
    """Posición en el mundo aplanada (x, y, 0): lo mismo que usan los nodos de geometría para los árboles."""
    pos = nt.nodes.new('ShaderNodeNewGeometry').outputs['Position']
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); unir(nt, pos, sep.inputs[0])
    c = nt.nodes.new('ShaderNodeCombineXYZ'); unir(nt, sep.outputs['X'], c.inputs['X']); unir(nt, sep.outputs['Y'], c.inputs['Y'])
    return pos, c.outputs[0]


def _voronoi(nt, coord, rasgo):
    v = nt.nodes.new('ShaderNodeTexVoronoi'); v.voronoi_dimensions = '2D'; v.feature = rasgo
    v.inputs['Scale'].default_value = 1.0 / PARCELA_M; v.inputs['Randomness'].default_value = PARCELA_AZAR
    unir(nt, coord, v.inputs['Vector'])
    return v


def _img(nt, coord, archivo, escala, color=True):
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1 / escala,) * 3
    unir(nt, coord, mp.inputs['Vector'])
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = imagen(archivo)
    if not color:
        t.image.colorspace_settings.name = 'Non-Color'
    unir(nt, mp.outputs['Vector'], t.inputs['Vector'])
    return t.outputs['Color']


def _lejania(nt, d0, d1):
    """0 cerca de la cámara, 1 a partir de d1 (para apagar detalles finos que de lejos hacen moiré)."""
    cam = nt.nodes.new('ShaderNodeCameraData')
    mr = nt.nodes.new('ShaderNodeMapRange'); mr.inputs['From Min'].default_value = d0; mr.inputs['From Max'].default_value = d1
    unir(nt, cam.outputs['View Distance'], mr.inputs['Value'])
    return mr.outputs['Result']


def mat_campo():
    """Campo de Aragua a fin de lluvias: potreros verdes, parcelas aradas con surcos, caña/maíz joven en hileras,
    pasto seco y monte en los linderos. Las parcelas son celdas de Voronoi (las mismas que usan los árboles)."""
    m = bpy.data.materials.new('Campo cultivado')
    nt, bsdf, out = nodos(m); unir(nt, bsdf.outputs[0], out.inputs[0])
    pos, xy = _coord_xy(nt)
    celda = _voronoi(nt, xy, 'F1')
    borde = _voronoi(nt, xy, 'DISTANCE_TO_EDGE')
    sep = nt.nodes.new('ShaderNodeSeparateColor'); unir(nt, celda.outputs['Color'], sep.inputs[0])
    r_tipo, r_ang, r_tono = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    # surcos: franjas en una dirección propia de cada parcela
    ang = _mate(nt, 'MULTIPLY', r_ang, math.pi)
    sx = nt.nodes.new('ShaderNodeSeparateXYZ'); unir(nt, pos, sx.inputs[0])
    u = _mate(nt, 'ADD', _mate(nt, 'MULTIPLY', sx.outputs['X'], _mate(nt, 'COSINE', ang)),
              _mate(nt, 'MULTIPLY', sx.outputs['Y'], _mate(nt, 'SINE', ang)))
    surco = _mate(nt, 'ADD', _mate(nt, 'MULTIPLY', _mate(nt, 'SINE', _mate(nt, 'MULTIPLY', u, 2 * math.pi / 0.95)), 0.5), 0.5)
    lejos = _lejania(nt, 60, 450)
    surco_v = _mate(nt, 'ADD', _mate(nt, 'MULTIPLY', surco, _mate(nt, 'SUBTRACT', 1.0, lejos)), _mate(nt, 'MULTIPLY', lejos, 0.5))
    # texturas reales
    t_gra = _img(nt, pos, 'grama_diff.jpg', 2.0)
    t_tie = _img(nt, pos, 'tierra_diff.jpg', 2.5)
    t_cam = _img(nt, pos, 'campo_diff.jpg', 3.0)
    var_g = rampa(nt, ruido(nt, pos, 0.02, 6), [(0.3, (0.75, 0.75, 0.75, 1)), (0.7, (1.2, 1.2, 1.15, 1))])
    # tipos de parcela (colores lineales, calibrados con la foto aérea y las fotos del usuario)
    potrero = mezclar(nt, mezclar(nt, rampa(nt, r_tono, [(0.0, (0.055, 0.09, 0.025, 1)), (1.0, (0.11, 0.14, 0.045, 1))]),
                                  t_gra, 0.75, 'MULTIPLY'), var_g, 1.0, 'MULTIPLY')
    arado = mezclar(nt, mezclar(nt, rampa(nt, r_tono, [(0.0, (0.13, 0.085, 0.055, 1)), (1.0, (0.2, 0.15, 0.1, 1))]), t_tie, 0.7, 'MULTIPLY'),
                    rampa(nt, surco_v, [(0.0, (0.55, 0.55, 0.55, 1)), (1.0, (1.1, 1.1, 1.1, 1))]), 1.0, 'MULTIPLY')
    hileras = mezclar(nt, arado, mezclar(nt, (0.05, 0.1, 0.02, 1), t_gra, 0.5, 'MULTIPLY'),
                      _mate(nt, 'GREATER_THAN', surco_v, 0.42))
    seco = mezclar(nt, mezclar(nt, (0.2, 0.17, 0.08, 1), t_cam, 0.7, 'MULTIPLY'), var_g, 1.0, 'MULTIPLY')
    col = mezclar(nt, potrero, arado, _mate(nt, 'GREATER_THAN', r_tipo, 0.5))
    col = mezclar(nt, col, hileras, _mate(nt, 'GREATER_THAN', r_tipo, 0.68))
    col = mezclar(nt, col, seco, _mate(nt, 'GREATER_THAN', r_tipo, 0.88))
    # monte bajo en los linderos (franja de 4 m) y manchas de maleza
    lindero = _mate(nt, 'LESS_THAN', _mate(nt, 'DIVIDE', borde.outputs['Distance'], 1.0 / PARCELA_M), 4.0)
    maleza = rampa(nt, ruido(nt, pos, 0.05, 4), [(0.55, (0, 0, 0, 1)), (0.62, (1, 1, 1, 1))])
    sepm = nt.nodes.new('ShaderNodeSeparateColor'); unir(nt, maleza, sepm.inputs[0])
    monte = mezclar(nt, (0.03, 0.055, 0.018, 1), t_gra, 0.6, 'MULTIPLY')
    col = mezclar(nt, col, monte, _mate(nt, 'MAXIMUM', lindero, sepm.outputs[0]))
    # variación grande (humedad del suelo)
    col = mezclar(nt, col, rampa(nt, ruido(nt, pos, 0.0025, 4), [(0.35, (0.82, 0.82, 0.82, 1)), (0.65, (1.12, 1.1, 1.05, 1))]), 1.0, 'MULTIPLY')
    unir(nt, col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.96
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.4; bump.inputs['Distance'].default_value = 0.08
    unir(nt, _mate(nt, 'MULTIPLY', surco, _mate(nt, 'SUBTRACT', 1.0, lejos)), bump.inputs['Height'])
    unir(nt, bump.outputs[0], bsdf.inputs['Normal'])
    return m


def mat_montana():
    """Relieve lejano: valle con potreros, caña y arboledas; laderas con bosque (más oscuro en lo alto),
    claros secos en pendientes fuertes, y relieve fino con bump (las laderas no se ven lisas)."""
    m = bpy.data.materials.new('Montanas y valle')
    nt, bsdf, out = nodos(m); unir(nt, bsdf.outputs[0], out.inputs[0])
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    pos = geo.outputs['Position']
    sz = nt.nodes.new('ShaderNodeSeparateXYZ'); unir(nt, pos, sz.inputs[0])
    sn = nt.nodes.new('ShaderNodeSeparateXYZ'); unir(nt, geo.outputs['Normal'], sn.inputs[0])
    altura = sz.outputs['Z']
    pendiente = _mate(nt, 'SUBTRACT', 1.0, sn.outputs['Z'])
    # valle: mosaico de potreros/caña/arboledas a escala de 300 m
    vv = nt.nodes.new('ShaderNodeTexVoronoi'); vv.inputs['Scale'].default_value = 1 / 320.0; unir(nt, pos, vv.inputs['Vector'])
    valle = rampa(nt, salida_n(vv, 'Color'), [(0.0, (0.035, 0.06, 0.022, 1)), (0.35, (0.07, 0.1, 0.035, 1)),
                                               (0.7, (0.11, 0.13, 0.05, 1)), (1.0, (0.16, 0.15, 0.08, 1))])
    # bosque: verde oscuro con copas (ruido fino) y variación grande
    copas = rampa(nt, ruido(nt, pos, 1 / 30.0, 3), [(0.35, (0.65, 0.65, 0.65, 1)), (0.65, (1.15, 1.15, 1.1, 1))])
    bosque = rampa(nt, ruido(nt, pos, 1 / 900.0, 4), [(0.3, (0.018, 0.036, 0.012, 1)), (0.7, (0.04, 0.066, 0.022, 1))])
    bosque = mezclar(nt, bosque, copas, 1.0, 'MULTIPLY')
    claro = (0.13, 0.12, 0.065, 1)
    fac_monte = nt.nodes.new('ShaderNodeMapRange'); fac_monte.inputs['From Min'].default_value = 25; fac_monte.inputs['From Max'].default_value = 140
    unir(nt, altura, fac_monte.inputs['Value'])
    fac_monte = _mate(nt, 'MAXIMUM', fac_monte.outputs['Result'], _mate(nt, 'MULTIPLY', pendiente, 16.0))   # cerros de Aragua: monte cerrado
    col = mezclar(nt, valle, bosque, _mate(nt, 'MINIMUM', fac_monte, 1.0))
    # claros secos/rocosos en pendientes fuertes, según ruido
    seco = _mate(nt, 'MULTIPLY', _mate(nt, 'GREATER_THAN', pendiente, 0.38), _mate(nt, 'GREATER_THAN', ruido(nt, pos, 1 / 400.0, 3), 0.55))
    col = mezclar(nt, col, claro, _mate(nt, 'MULTIPLY', seco, 0.45))
    unir(nt, col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.92
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 1.0; bump.inputs['Distance'].default_value = 25.0
    unir(nt, ruido(nt, pos, 1 / 120.0, 8), bump.inputs['Height']); unir(nt, bump.outputs[0], bsdf.inputs['Normal'])
    return m


def terreno():
    relieve = rehacer_relieve() or bpy.data.objects.get('relieve')
    if relieve:
        relieve.data.materials.clear(); relieve.data.materials.append(mat_montana())
    campo = bpy.data.objects.get('tex_campo_1')
    if campo:
        campo.data.materials.clear(); campo.data.materials.append(mat_campo())
    return relieve


# ============================================================================ plataforma y pistas según la imagen satelital
# fotos/satelital_aerodromo.webp (captura de Google Maps, 1,18 m/px) georreferenciada con 5 puntos comunes con la
# referencia vieja (SAAG, hangar verde, edificio gris y dos edificios blancos; residuo 1-5 m). Similitud px nuevo -> px viejo:
SIMIL_A, SIMIL_B = complex(3.807696, 0.025200), complex(-2082.1627, -1183.3033)
ZONAS_SIN_ARBOLES = []      # franjas anchas alrededor de pistas: la arboleda de fondo no entra ahí


def sat(x, y):
    """Píxel de la imagen satelital del aeródromo -> Blender (z = 0)."""
    zv = SIMIL_A * complex(x, y) + SIMIL_B
    return Vector(((zv.real - OX) * S, -(zv.imag - OY) * S, 0))


def _zona(puntos, ancho):
    bm = bmesh.new()
    for a, b in zip(puntos[:-1], puntos[1:]):
        d = (b - a); d.z = 0; d.normalize(); n = Vector((-d.y, d.x, 0)) * ancho / 2
        bm.faces.new([bm.verts.new(p) for p in (a - n, a + n, b + n, b - n)])
    me = bpy.data.meshes.new('zona sin arboles'); bm.to_mesh(me); bm.free()
    ZONAS_SIN_ARBOLES.append(bpy.data.objects.new('zona sin arboles', me))


def _discontinua(nombre, a, b, ancho, mat, z, lleno=30.0, hueco=20.0, margen=50.0):
    u = (b - a); L = u.length; u.normalize(); t = margen
    while t + lleno < L - margen:
        franja(nombre, [a + u * t, a + u * (t + lleno)], ancho, mat, z)
        t += lleno + hueco


def pistas_y_plataforma():
    """El concreto de la plataforma era ~800 m más largo hacia el NE (y ~100 m al SO) que el real, y no había pistas:
    al NO de la plataforma todo era grama. Se recorta la plataforma con los bordes de la imagen y se agregan la pista
    paralela, la pista grande del norte, la calle de rodaje cruzada y las dos calles de rodaje del extremo NE."""
    ap = bpy.data.objects.get('tex_apron_1')
    if ap:
        bm = bmesh.new(); bm.from_mesh(ap.data); bm.transform(ap.matrix_world)
        for p, q in ((sat(852, 118), sat(903, 212)), (sat(425, 480), sat(350, 613))):
            d = q - p; n = Vector((d.y, -d.x, 0)).normalized()
            if (-p).dot(n) > 0:                     # la normal apunta al lado que se borra (lejos del centro)
                n = -n
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=p, plane_no=n, clear_outer=True)
        bm.transform(ap.matrix_world.inverted()); bm.to_mesh(ap.data); bm.free()
        print('Plataforma recortada al tamaño real')
    asfalto = bpy.data.materials.get('Asfalto') or mat_asfalto()
    concreto = bpy.data.materials.get('Concreto plataforma')
    blanca = bpy.data.materials.get('Pintura blanca') or pintura_gastada('Pintura blanca', (0.75, 0.74, 0.7, 1))
    amarilla = bpy.data.materials.get('Pintura amarilla') or pintura_gastada('Pintura amarilla', (0.42, 0.3, 0.07, 1))
    # pista paralela (asfalto, 30 m): umbral con cebra en el extremo SO, se une a la pista norte en el NE
    r1a, r1b = sat(220, 490), sat(756, 52)
    franja('tex_pista_paralela', [r1a, r1b], 30.0, asfalto, 0.03)
    u = (r1b - r1a).normalized(); perp = Vector((-u.y, u.x, 0))
    _discontinua('Eje pista', r1a, r1b, 0.9, blanca, 0.04)
    for lado in (-1, 1):
        franja('Borde pista', [r1a + perp * lado * 14.2 + u * 6, r1b + perp * lado * 14.2 - u * 40], 0.6, blanca, 0.04)
        for k in range(4):
            off = perp * lado * (3.0 + 3.6 * k)
            franja('Umbral pista', [r1a + u * 6 + off, r1a + u * 36 + off], 1.8, blanca, 0.04)
    _zona([r1a - u * 200, r1b + u * 100], 30 + 2 * 140)
    # pista norte (más ancha); en la imagen solo se ve un tramo: se prolonga a ambos lados
    r2a, r2b = sat(230, -80), sat(1650, 270)
    franja('tex_pista_norte', [r2a, r2b], 38.0, asfalto, 0.03)
    _discontinua('Eje pista norte', r2a, r2b, 0.9, blanca, 0.04)
    _zona([r2a, r2b], 38 + 2 * 150)
    # calle de rodaje cruzada (concreto viejo) que baja del NO hasta el extremo SO de la plataforma
    x1a, x1b = sat(-249, -126), sat(415, 490)
    franja('tex_rodaje_cruzada', [x1a, x1b], 25.0, concreto, 0.02)
    _zona([x1a, x1b], 25 + 2 * 120)
    # calles de rodaje del extremo NE: hacia el este y en diagonal hasta la pista norte
    for nombre, pts, ancho in (('tex_rodaje_este', [sat(895, 208), sat(1093, 270), sat(1300, 335)], 18.0),
                               ('tex_rodaje_norte', [sat(925, 215), sat(1040, 115)], 15.0),
                               ('tex_rodaje_enlace', [sat(855, 122), sat(880, 95)], 22.0)):
        franja(nombre, pts, ancho, concreto, 0.02)
        franja('Eje rodaje', pts, 0.3, amarilla, 0.03)
        _zona(pts, ancho + 120)
    print('Pistas y calles de rodaje según la imagen satelital')


# ============================================================================ árboles de fondo (nodos de geometría)
EXCLUIR_ARBOLES = ('tex_grama_1', 'tex_apron_1', 'tex_apron_2', 'tex_apron_3', 'tex_apron_4', 'tex_asfalto_1', 'tex_asfalto_2')


def _gn(g, tipo, **props):
    n = g.nodes.new(tipo)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def arboleda(relieve):
    """Miles de árboles reales (copias) en linderos de parcelas, manchas de monte y sueltos, de 330 m a 6 km.
    Usa el mismo Voronoi que el material del campo, así los árboles caen en los linderos pintados."""
    fuentes = [c for c in bpy.data.collections if c.name.startswith('Modelo ') and ('tree' in c.name)]
    if not fuentes or not relieve:
        return
    col_f = bpy.data.collections.new('Fuente arboleda'); escena.collection.children.link(col_f)
    for c in fuentes:
        e = bpy.data.objects.new('fuente ' + c.name, None); e.instance_type = 'COLLECTION'; e.instance_collection = c
        col_f.objects.link(e)
    bpy.context.view_layer.layer_collection.children[col_f.name].exclude = True
    col_x = bpy.data.collections.new('Excluir arboleda'); escena.collection.children.link(col_x)
    # (las zonas excluidas se pasan como colección para no tocar los objetos originales)
    g = bpy.data.node_groups.new('Arboleda', 'GeometryNodeTree')
    g.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    g.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    ent = g.nodes.new('NodeGroupInput'); sal = g.nodes.new('NodeGroupOutput')
    dist = _gn(g, 'GeometryNodeDistributePointsOnFaces', distribute_method='RANDOM')
    dist.inputs['Density'].default_value = 0.01; dist.inputs['Seed'].default_value = 3
    unir(g, ent.outputs[0], dist.inputs['Mesh'])
    pos = g.nodes.new('GeometryNodeInputPosition')
    sp = g.nodes.new('ShaderNodeSeparateXYZ'); unir(g, pos.outputs[0], sp.inputs[0])
    xy = g.nodes.new('ShaderNodeCombineXYZ'); unir(g, sp.outputs['X'], xy.inputs['X']); unir(g, sp.outputs['Y'], xy.inputs['Y'])
    vor = _gn(g, 'ShaderNodeTexVoronoi', voronoi_dimensions='2D', feature='DISTANCE_TO_EDGE')
    vor.inputs['Scale'].default_value = 1.0 / PARCELA_M; vor.inputs['Randomness'].default_value = PARCELA_AZAR
    unir(g, xy.outputs[0], vor.inputs['Vector'])
    borde_m = _mate(g, 'DIVIDE', vor.outputs['Distance'], 1.0 / PARCELA_M)

    def ruido_g(escala, det=3.0):
        n = g.nodes.new('ShaderNodeTexNoise'); n.inputs['Scale'].default_value = escala; n.inputs['Detail'].default_value = det
        unir(g, xy.outputs[0], n.inputs['Vector'])
        return n.outputs['Fac']
    azar = _gn(g, 'FunctionNodeRandomValue', data_type='FLOAT'); entrada(azar, 'Seed').default_value = 5
    r1 = salida_n(azar, 'Value')
    # linderos: trozos de cerca viva (no todos los linderos tienen árboles)
    lindero = _mate(g, 'MULTIPLY', _mate(g, 'LESS_THAN', borde_m, 3.0), _mate(g, 'GREATER_THAN', ruido_g(1 / 110.0), 0.5))
    lindero = _mate(g, 'MULTIPLY', lindero, _mate(g, 'LESS_THAN', r1, 0.6))       # ~1 árbol cada 28 m de cerca
    # manchas de monte (arboledas cerradas) y árboles sueltos en los potreros
    mancha = _mate(g, 'MULTIPLY', _mate(g, 'GREATER_THAN', ruido_g(1 / 280.0, 4), 0.66), _mate(g, 'LESS_THAN', r1, 0.9))
    suelto = _mate(g, 'LESS_THAN', r1, 0.004)
    elegir = _mate(g, 'MAXIMUM', _mate(g, 'MAXIMUM', lindero, mancha), suelto)
    # anillo: fuera de la zona modelada a mano y dentro de 6 km
    radio = g.nodes.new('ShaderNodeVectorMath'); radio.operation = 'LENGTH'; unir(g, xy.outputs[0], radio.inputs[0])
    anillo = _mate(g, 'MULTIPLY', _mate(g, 'GREATER_THAN', radio.outputs['Value'], 330.0), _mate(g, 'LESS_THAN', radio.outputs['Value'], 6000.0))
    # lejos de pista, plataforma, grama del aeródromo y vías
    oi = _gn(g, 'GeometryNodeCollectionInfo', transform_space='RELATIVE')
    oi.inputs['Collection'].default_value = col_x; oi.inputs['Separate Children'].default_value = False
    real = g.nodes.new('GeometryNodeRealizeInstances'); unir(g, oi.outputs[0], real.inputs[0])
    prox = _gn(g, 'GeometryNodeProximity', target_element='FACES')
    unir(g, real.outputs[0], prox.inputs[0]); unir(g, xy.outputs[0], entrada(prox, 'Sample Position'))
    libre = _mate(g, 'GREATER_THAN', salida_n(prox, 'Distance'), 28.0)
    quedan = _mate(g, 'MULTIPLY', _mate(g, 'MULTIPLY', elegir, anillo), libre)
    borra = _gn(g, 'GeometryNodeDeleteGeometry', domain='POINT')
    unir(g, dist.outputs['Points'], borra.inputs['Geometry']); unir(g, _mate(g, 'LESS_THAN', quedan, 0.5), borra.inputs['Selection'])
    # apoyar en el relieve
    ori = _gn(g, 'GeometryNodeObjectInfo', transform_space='RELATIVE'); ori.inputs['Object'].default_value = relieve
    arriba = g.nodes.new('ShaderNodeCombineXYZ'); unir(g, sp.outputs['X'], arriba.inputs['X']); unir(g, sp.outputs['Y'], arriba.inputs['Y'])
    arriba.inputs['Z'].default_value = 4000.0
    rc = g.nodes.new('GeometryNodeRaycast')
    unir(g, ori.outputs['Geometry'], rc.inputs['Target Geometry']); unir(g, arriba.outputs[0], entrada(rc, 'Source Position'))
    entrada(rc, 'Ray Direction').default_value = (0, 0, -1); entrada(rc, 'Ray Length').default_value = 9000.0
    setp = g.nodes.new('GeometryNodeSetPosition')
    unir(g, borra.outputs[0], setp.inputs['Geometry']); unir(g, salida_n(rc, 'Hit Position'), setp.inputs['Position'])
    # copias de los árboles: modelo, giro y tamaño al azar (mangos y samanes de 9 a 18 m)
    ci = _gn(g, 'GeometryNodeCollectionInfo', transform_space='ORIGINAL')
    ci.inputs['Collection'].default_value = col_f; ci.inputs['Separate Children'].default_value = True; ci.inputs['Reset Children'].default_value = True
    cual = _gn(g, 'FunctionNodeRandomValue', data_type='INT'); entrada(cual, 'Min').default_value = 0
    entrada(cual, 'Max').default_value = len(fuentes) - 1; entrada(cual, 'Seed').default_value = 9
    giro = _gn(g, 'FunctionNodeRandomValue', data_type='FLOAT_VECTOR')
    entrada(giro, 'Min').default_value = (-0.06, -0.06, 0); entrada(giro, 'Max').default_value = (0.06, 0.06, 2 * math.pi)
    tam = _gn(g, 'FunctionNodeRandomValue', data_type='FLOAT'); entrada(tam, 'Min').default_value = 1.9
    entrada(tam, 'Max').default_value = 3.6; entrada(tam, 'Seed').default_value = 21
    inst = g.nodes.new('GeometryNodeInstanceOnPoints')
    unir(g, setp.outputs[0], inst.inputs['Points']); unir(g, ci.outputs[0], inst.inputs['Instance'])
    inst.inputs['Pick Instance'].default_value = True
    unir(g, salida_n(cual, 'Value'), inst.inputs['Instance Index'])
    unir(g, salida_n(giro, 'Value'), inst.inputs['Rotation']); unir(g, salida_n(tam, 'Value'), inst.inputs['Scale'])
    unir(g, inst.outputs[0], sal.inputs[0])
    # objeto base: un cuadrado de 12 km
    me = bpy.data.meshes.new('arboleda'); L = 6000.0
    me.from_pydata([(-L, -L, 0), (L, -L, 0), (L, L, 0), (-L, L, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new('Arboleda de fondo', me); escena.collection.objects.link(ob)
    mod = ob.modifiers.new('Arboleda', 'NODES'); mod.node_group = g
    # copias de las zonas a excluir (solo geometría) en su colección, ocultas al render
    for nombre in EXCLUIR_ARBOLES:
        o = bpy.data.objects.get(nombre)
        if o:
            c = bpy.data.objects.new('excl ' + nombre, o.data); c.matrix_world = o.matrix_world.copy()
            col_x.objects.link(c)
    for z in ZONAS_SIN_ARBOLES:          # alrededor de las pistas (despeje de obstáculos)
        col_x.objects.link(z)
    bpy.context.view_layer.layer_collection.children[col_x.name].exclude = True
    deps = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(deps)
    try:
        n = len(ev.evaluated_get(deps).data.vertices)
    except Exception:
        n = '?'
    print('Arboleda de fondo lista (puntos base:', n, ')')


# ============================================================================ copas de mango y palmas
def copas_densas():
    """Los árboles de Poly Haven son ralos (parecen olivos). Los mangos del sitio tienen copa redonda, cerrada y
    oscura: se agregan copias giradas de las hojas y se oscurece el follaje, con translucidez real (no refracción)."""
    for c in bpy.data.collections:
        if not (c.name.startswith('Modelo ') and 'tree' in c.name):
            continue
        for o in list(c.objects):
            if o.type != 'MESH' or o.get('copa'):
                continue
            idx = [i for i, m in enumerate(o.data.materials) if m and 'lea' in m.name.lower()]
            if not idx:
                continue
            bm = bmesh.new(); bm.from_mesh(o.data)
            hojas = [f for f in bm.faces if f.material_index in idx]
            vs_h = list({v for f in hojas for v in f.verts})
            co = np.array([v.co[:] for v in vs_h], dtype=np.float32)
            centro = Vector(co.mean(axis=0))
            # copias de las hojas giradas alrededor del eje de la copa (operaciones de bmesh en C: rápido, conserva UV)
            for giro, esc, dz in ((math.radians(72), 0.9, 0.0), (math.radians(200), 0.8, 0.04), (math.radians(290), 0.95, -0.03)):
                M = Matrix.Translation(centro + Vector((0, 0, dz))) @ Matrix.Rotation(giro, 4, 'Z') @ Matrix.Scale(esc, 4) @ Matrix.Translation(-centro)
                dup = bmesh.ops.duplicate(bm, geom=hojas)
                nuevos = [e for e in dup['geom'] if isinstance(e, bmesh.types.BMVert)]
                bmesh.ops.transform(bm, matrix=M, verts=nuevos)
            bm.to_mesh(o.data); bm.free()
            o['copa'] = True
            print('Copa densa:', o.name, len(o.data.vertices), 'vértices')
        # follaje: más oscuro y verde (mango), translucidez de hoja delgada
        for o in c.objects:
            for s in getattr(o, 'material_slots', []):
                m = s.material
                if not m or not m.use_nodes or 'lea' not in m.name.lower() or m.get('mango'):
                    continue
                nt = m.node_tree
                b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if not b:
                    continue
                if 'Transmission Weight' in b.inputs:
                    b.inputs['Transmission Weight'].default_value = 0.0
                if b.inputs['Base Color'].links:
                    src = b.inputs['Base Color'].links[0].from_socket
                    hsv = nt.nodes.new('ShaderNodeHueSaturation')
                    hsv.inputs['Hue'].default_value = 0.51; hsv.inputs['Saturation'].default_value = 1.15; hsv.inputs['Value'].default_value = 0.62
                    unir(nt, src, hsv.inputs['Color']); unir(nt, hsv.outputs[0], b.inputs['Base Color'])
                    col = hsv.outputs[0]
                else:
                    col = None
                b.inputs['Roughness'].default_value = 0.45            # hoja de mango: cerosa, brilla un poco
                out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
                origen = out.inputs['Surface'].links[0].from_socket
                tr = nt.nodes.new('ShaderNodeBsdfTranslucent')
                if col is not None:
                    tint = nt.nodes.new('ShaderNodeMix'); tint.data_type = 'RGBA'; tint.blend_type = 'MULTIPLY'
                    tint.inputs['Factor'].default_value = 1.0; unir(nt, col, tint.inputs['A']); tint.inputs['B'].default_value = (0.9, 1.1, 0.35, 1)
                    unir(nt, tint.outputs['Result'], tr.inputs['Color'])
                mix = nt.nodes.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = 0.22
                unir(nt, origen, mix.inputs[1]); unir(nt, tr.outputs[0], mix.inputs[2])
                if b.inputs['Alpha'].links:                       # el translúcido también respeta el recorte
                    tra = nt.nodes.new('ShaderNodeBsdfTransparent'); m2 = nt.nodes.new('ShaderNodeMixShader')
                    unir(nt, b.inputs['Alpha'].links[0].from_socket, m2.inputs['Fac'])
                    unir(nt, tra.outputs[0], m2.inputs[1]); unir(nt, tr.outputs[0], m2.inputs[2])
                    unir(nt, m2.outputs[0], mix.inputs[2])
                unir(nt, mix.outputs[0], out.inputs['Surface'])
                m['mango'] = True


def malla_hoja_palma(semilla, largo=4.6):
    """Hoja de palma (pinnada): raquis arqueado y ~70 pares de foliolos en V, con caída hacia la punta."""
    rnd = random.Random(semilla)
    bm = bmesh.new()
    n = 36
    pts = []
    for i in range(n + 1):
        t = i / n
        x = t * largo
        z = math.sin(math.radians(38)) * x - 0.55 * (x ** 2) / largo * (1.2 + rnd.uniform(-0.2, 0.3))
        pts.append(Vector((x, 0, z)))
    # raquis
    for a, b in zip(pts[:-1], pts[1:]):
        w = 0.035
        vs = [bm.verts.new(p) for p in (a + Vector((0, -w, 0)), b + Vector((0, -w * 0.6, 0)), b + Vector((0, w * 0.6, 0)), a + Vector((0, w, 0)))]
        bm.faces.new(vs)
    pares = 68
    for k in range(pares):
        t = 0.08 + 0.9 * k / pares
        i = min(n - 1, int(t * n)); p = pts[i].lerp(pts[i + 1], t * n - i)
        d = (pts[i + 1] - pts[i]).normalized()
        lf = (0.25 + 0.55 * math.sin(math.pi * min(1, t * 1.15))) * rnd.uniform(0.85, 1.1)
        ancho = 0.035 + 0.02 * math.sin(math.pi * t)
        for lado in (-1, 1):
            # foliolo: sale hacia adelante (45°), cae en V y se curva
            dirf = (d * 0.6 + Vector((0, lado, 0)) * 0.8 + Vector((0, 0, -0.35 - 0.3 * t))).normalized()
            caida = Vector((0, 0, -0.12 * lf))
            seg = 3; prev = None
            for s in range(seg + 1):
                q = s / seg
                c = p + dirf * lf * q + caida * q * q
                wq = ancho * (1 - 0.85 * q) + 0.004
                perp = d.cross(dirf).normalized() * wq
                a1, a2 = bm.verts.new(c - perp), bm.verts.new(c + perp)
                if prev:
                    bm.faces.new((prev[0], prev[1], a2, a1))
                prev = (a1, a2)
    me = bpy.data.meshes.new(f'hoja palma {semilla}'); bm.to_mesh(me); bm.free()
    return me


def mat_hoja_palma():
    m = bpy.data.materials.get('Hoja de palma')
    if m:
        return m
    m = bpy.data.materials.new('Hoja de palma')
    nt, bsdf, out = nodos(m)
    info = nt.nodes.new('ShaderNodeObjectInfo')
    col = rampa(nt, info.outputs['Random'], [(0.0, (0.06, 0.1, 0.025, 1)), (0.6, (0.09, 0.13, 0.03, 1)), (1.0, (0.16, 0.15, 0.05, 1))])
    unir(nt, col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.5
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent'); tint = mezclar(nt, col, (1.0, 1.25, 0.5, 1), 1.0, 'MULTIPLY')
    unir(nt, tint, tr.inputs['Color'])
    mix = nt.nodes.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = 0.25
    unir(nt, bsdf.outputs[0], mix.inputs[1]); unir(nt, tr.outputs[0], mix.inputs[2]); unir(nt, mix.outputs[0], out.inputs[0])
    return m


def palmas():
    """Cambia las hojas de palma del visor (planchas en estrella) por hojas pinnadas de verdad."""
    copas = {}
    for o in list(bpy.data.objects):
        if o.type == 'MESH' and o.material_slots and o.material_slots[0].material and o.material_slots[0].material.name == 'Material_37':
            clave = tuple(round(x, 1) for x in o.matrix_world.translation)
            copas.setdefault(clave, []).append(o)
    if not copas:
        return
    hojas = [malla_hoja_palma(s) for s in range(4)]
    mat = mat_hoja_palma()
    for me in hojas:
        me.materials.append(mat)
    col = bpy.data.collections.new('Palmas'); escena.collection.children.link(col)
    rnd = random.Random(4)
    for k, (clave, objs) in enumerate(copas.items()):
        centro = Vector(clave)
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        n = rnd.randint(14, 18)
        for i in range(n):
            ob = bpy.data.objects.new(f'Palma {k} hoja {i}', hojas[rnd.randrange(len(hojas))]); col.objects.link(ob)
            az = 2 * math.pi * i / n + rnd.uniform(-0.15, 0.15)
            alza = rnd.uniform(-0.35, 0.45) if i % 3 else rnd.uniform(0.5, 0.9)   # algunas hojas nuevas casi verticales
            ob.location = centro + Vector((0, 0, rnd.uniform(-0.25, 0.15)))
            ob.rotation_euler = (0, -alza, az)
            s = rnd.uniform(0.8, 1.1); ob.scale = (s, s, s)
    print('Palmas con hojas nuevas:', len(copas))


def malla_hoja_abanico(semilla, radio=0.95):
    """Hoja de palma de Bismarck (costapalmada): pecíolo largo y abanico de ~44 segmentos plegados en V,
    con las puntas partidas y el limbo algo ahuecado."""
    rnd = random.Random(100 + semilla)
    bm = bmesh.new()
    P = Vector((1.05, 0, 0.55))
    u = P.normalized(); v = Vector((0, 1, 0)); n = u.cross(v).normalized()
    # pecíolo
    for a, b in ((Vector(), P * 0.5), (P * 0.5, P)):
        w = 0.025
        bm.faces.new([bm.verts.new(p) for p in (a - v * w, b - v * w * 0.8, b + v * w * 0.8, a + v * w)])
    segs, anillos = 44, 6
    ang0 = math.radians(115)
    filas = []
    for i in range(anillos + 1):
        r = 0.06 + (radio - 0.06) * i / anillos
        fila = []
        for j in range(segs + 1):
            t = j / segs
            th = -ang0 + 2 * ang0 * t
            pliegue = 0.045 * (r / radio) * (1 if j % 2 else -1)              # plegado en V
            ahueca = -0.16 * (r / radio) ** 2
            rr = r
            if i == anillos:                                                  # puntas partidas
                rr = r * (1.0 if j % 2 else rnd.uniform(0.78, 0.86))
            p = P + (u * math.cos(th) + v * math.sin(th)) * rr + n * (pliegue + ahueca)
            fila.append(bm.verts.new(p))
        filas.append(fila)
    for i in range(anillos):
        for j in range(segs):
            bm.faces.new((filas[i][j], filas[i][j + 1], filas[i + 1][j + 1], filas[i + 1][j]))
    me = bpy.data.meshes.new(f'hoja abanico {semilla}'); bm.to_mesh(me); bm.free()
    return me


def mat_hoja_abanico():
    m = bpy.data.materials.new('Hoja palma de Bismarck')
    nt, bsdf, out = nodos(m)
    info = nt.nodes.new('ShaderNodeObjectInfo')
    col = rampa(nt, info.outputs['Random'], [(0.0, (0.26, 0.34, 0.32, 1)), (0.7, (0.32, 0.4, 0.37, 1)), (1.0, (0.36, 0.38, 0.3, 1))])
    unir(nt, col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.42                         # hoja cerosa, plateada
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent'); unir(nt, mezclar(nt, col, (0.6, 0.9, 0.5, 1), 1.0, 'MULTIPLY'), tr.inputs['Color'])
    mix = nt.nodes.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = 0.15
    unir(nt, bsdf.outputs[0], mix.inputs[1]); unir(nt, tr.outputs[0], mix.inputs[2]); unir(nt, mix.outputs[0], out.inputs[0])
    return m


def palmas_abanico():
    """Las palmas plateadas del frente del hangar (Bismarckia, como en las fotos) venían como 'estrellas' de planchas."""
    copas = {}
    for o in list(bpy.data.objects):
        if o.type == 'MESH' and o.material_slots and o.material_slots[0].material and o.material_slots[0].material.name == 'Material_36':
            copas.setdefault(tuple(round(x, 1) for x in o.matrix_world.translation), []).append(o)
    if not copas:
        return
    hojas = [malla_hoja_abanico(s) for s in range(3)]
    mat = mat_hoja_abanico()
    for me in hojas:
        me.materials.append(mat)
    col = bpy.data.collections.get('Palmas') or bpy.data.collections.new('Palmas')
    if col.name not in escena.collection.children:
        escena.collection.children.link(col)
    rnd = random.Random(8)
    for k, (clave, objs) in enumerate(copas.items()):
        centro = Vector(clave)
        alto = max(o.dimensions.z for o in objs)
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        n = rnd.randint(13, 17)
        for i in range(n):
            ob = bpy.data.objects.new(f'Bismarck {k} hoja {i}', hojas[rnd.randrange(3)]); col.objects.link(ob)
            ob.location = centro + Vector((0, 0, rnd.uniform(-0.2, 0.25) - alto * 0.15))
            ob.rotation_euler = (rnd.uniform(-0.15, 0.15), -rnd.uniform(0.0, 0.9), 2 * math.pi * i / n + rnd.uniform(-0.2, 0.2))
            s = rnd.uniform(1.1, 1.4); ob.scale = (s, s, s)
    print('Palmas de Bismarck:', len(copas))


def jardines():
    """Céspedes que venían del visor como planos de verde liso (p. ej. el jardín del hangar): material de grama real
    y marca 'cesped' para que les crezca grama 3D. Se reconocen por ser planos, de más de 3 m² y verdes lisos."""
    grama = bpy.data.materials.get('Grama')
    n = 0
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.name.startswith('tex_') or o.dimensions.z > 0.35 or o.dimensions.x * o.dimensions.y < 3:
            continue
        m = o.active_material
        b = next((x for x in m.node_tree.nodes if x.type == 'BSDF_PRINCIPLED'), None) if m and m.use_nodes else None
        if not b:
            continue
        # el visor tiñe una textura gris de detalle con un nodo Mix (multiplicar); el verde puede estar ahí
        colores = [] if b.inputs['Base Color'].links else [b.inputs['Base Color'].default_value]
        for x in m.node_tree.nodes:
            if x.type == 'MIX' and x.data_type == 'RGBA':
                colores += [s.default_value for s in x.inputs if s.enabled and s.type == 'RGBA' and not s.links]
        if any(c[1] > 0.06 and c[1] > 1.25 * c[0] and c[1] > 1.25 * c[2] for c in colores):
            for i in range(len(o.data.materials)):
                o.data.materials[i] = grama
            o['cesped'] = True
            n += 1
            print('  césped:', o.name, tuple(round(x, 1) for x in o.dimensions), tuple(round(x) for x in o.matrix_world.translation))
    print('Céspedes con grama real:', n)


# ============================================================================ grama del aeródromo
def mat_grama_realista():
    """Grama cortada del aeródromo: menos saturada, con parches secos y matas (el verde plano delataba el render)."""
    m = bpy.data.materials.get('Grama')
    if not m:
        return
    nt, bsdf, out = nodos(m); unir(nt, bsdf.outputs[0], out.inputs[0])
    pos = nt.nodes.new('ShaderNodeNewGeometry').outputs['Position']
    t = _img(nt, pos, 'grama_diff.jpg', 2.2)
    tn = _img(nt, pos, 'grama_nor.jpg', 2.2, color=False)
    base = rampa(nt, ruido(nt, pos, 0.015, 6), [(0.3, (0.06, 0.095, 0.03, 1)), (0.55, (0.085, 0.115, 0.035, 1)), (0.75, (0.13, 0.13, 0.05, 1))])
    seco = rampa(nt, ruido(nt, pos, 0.06, 5), [(0.6, (1, 1, 1, 1)), (0.72, (1.5, 1.2, 0.9, 1))])
    matas = rampa(nt, ruido(nt, pos, 0.9, 4), [(0.3, (0.8, 0.85, 0.8, 1)), (0.7, (1.1, 1.08, 1.0, 1))])
    col = mezclar(nt, mezclar(nt, mezclar(nt, base, t, 0.8, 'MULTIPLY'), seco, 1.0, 'MULTIPLY'), matas, 1.0, 'MULTIPLY')
    unir(nt, col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.93
    nm = nt.nodes.new('ShaderNodeNormalMap'); unir(nt, tn, nm.inputs['Color']); nm.inputs['Strength'].default_value = 0.8
    unir(nt, nm.outputs[0], bsdf.inputs['Normal'])


# ============================================================================ grama en 3D cerca de las cámaras a ras de piso
CAMARAS_SUELO = ('hangar', 'carretera', 'porton', 'tribuna', 'tucanos', 'hercules')


def mata_grama(semilla):
    """Mata de grama cortada: 9 hojas curvas y afinadas de 6 a 16 cm."""
    rnd = random.Random(semilla)
    bm = bmesh.new()
    for _ in range(9):
        a = rnd.uniform(0, 2 * math.pi); r0 = rnd.uniform(0, 0.03)
        base = Vector((math.cos(a) * r0, math.sin(a) * r0, 0))
        alto = rnd.uniform(0.06, 0.16); inclina = rnd.uniform(0.15, 0.6); giro = rnd.uniform(0, 2 * math.pi)
        d = Vector((math.cos(giro), math.sin(giro), 0)); lado = Vector((-d.y, d.x, 0))
        prev = None
        for s in range(4):
            q = s / 3
            c = base + d * inclina * alto * q * q + Vector((0, 0, alto * q))
            w = 0.0035 * (1 - q) + 0.0003
            v1, v2 = bm.verts.new(c - lado * w), bm.verts.new(c + lado * w)
            if prev:
                bm.faces.new((prev[0], prev[1], v2, v1))
            prev = (v1, v2)
    me = bpy.data.meshes.new(f'mata grama {semilla}'); bm.to_mesh(me); bm.free()
    return me


def mat_hoja_grama():
    m = bpy.data.materials.new('Hoja de grama')
    nt, bsdf, out = nodos(m)
    info = nt.nodes.new('ShaderNodeObjectInfo')
    coord = nt.nodes.new('ShaderNodeTexCoord').outputs['Generated']
    sz = nt.nodes.new('ShaderNodeSeparateXYZ'); unir(nt, coord, sz.inputs[0])
    col = rampa(nt, info.outputs['Random'], [(0.0, (0.05, 0.085, 0.022, 1)), (0.55, (0.075, 0.11, 0.03, 1)),
                                            (0.85, (0.11, 0.12, 0.04, 1)), (1.0, (0.17, 0.15, 0.07, 1))])
    punta = rampa(nt, sz.outputs['Z'], [(0.6, (1, 1, 1, 1)), (1.0, (1.5, 1.3, 1.0, 1))])     # puntas secas
    col = mezclar(nt, mezclar(nt, col, punta, 1.0, 'MULTIPLY'), rampa(nt, sz.outputs['Z'], [(0.0, (0.55, 0.55, 0.55, 1)), (0.5, (1, 1, 1, 1))]), 1.0, 'MULTIPLY')
    unir(nt, col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.55
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent'); unir(nt, mezclar(nt, col, (1.0, 1.3, 0.5, 1), 1.0, 'MULTIPLY'), tr.inputs['Color'])
    mix = nt.nodes.new('ShaderNodeMixShader'); mix.inputs['Fac'].default_value = 0.3
    unir(nt, bsdf.outputs[0], mix.inputs[1]); unir(nt, tr.outputs[0], mix.inputs[2]); unir(nt, mix.outputs[0], out.inputs[0])
    return m


def grama_3d():
    """Hojas de grama de verdad donde la cámara está a ras de piso. Un disco de densidad bajo cada cámara
    (densidad 1/(1+(r/8)²)): pasto tupido cerca del lente y nada a 60 m, donde ya no se distingue."""
    cams = [bpy.data.objects.get('Cam_' + n) for n in CAMARAS_SUELO]
    cams = [c for c in cams if c]
    if not cams:
        return
    # marcar qué superficies son grama (atributo que lee el rayo)
    col_s = bpy.data.collections.new('Suelo para grama'); escena.collection.children.link(col_s)
    suelo = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('tex_') and o.name != 'tex_campo_1']
    suelo += [o for o in (COL_EDIF.objects if COL_EDIF else [])]
    h = bpy.data.objects.get('hangar')
    suelo += [o for o in (h.children_recursive if h else []) if o.type == 'MESH']
    suelo += [o for o in bpy.data.objects if o.get('cesped') and o not in suelo]
    for o in suelo:
        me = o.data
        if 'es_grama' not in me.attributes:
            at = me.attributes.new('es_grama', 'FLOAT', 'POINT')
            at.data.foreach_set('value', [1.0 if (o.name.startswith('tex_grama') or o.get('cesped')) else 0.0] * len(me.vertices))
        c = bpy.data.objects.new('suelo ' + o.name, me); c.matrix_world = o.matrix_world.copy(); col_s.objects.link(c)
    bpy.context.view_layer.layer_collection.children[col_s.name].exclude = True
    # discos de densidad (anillos con atributo 'densidad')
    R, nr, ns = 60.0, 40, 72
    verts, caras, dens = [], [], []
    for cam in cams:
        p = cam.matrix_world.translation
        d = cam.matrix_world.to_3x3() @ Vector((0, 0, -1)); d.z = 0
        centro = Vector((p.x, p.y, 0)) + (d.normalized() * 6 if d.length > 1e-3 else Vector())
        i0 = len(verts)
        verts.append(centro[:]); dens.append(220.0)
        for i in range(1, nr + 1):
            r = R * (i / nr) ** 1.6
            for j in range(ns):
                a = 2 * math.pi * j / ns
                verts.append((centro.x + r * math.cos(a), centro.y + r * math.sin(a), 0))
                dens.append(220.0 / (1 + (r / 8.0) ** 2) * (1 - (r / R) ** 4))
        for j in range(ns):
            caras.append((i0, i0 + 1 + j, i0 + 1 + (j + 1) % ns))
        for i in range(1, nr):
            for j in range(ns):
                a0 = i0 + 1 + (i - 1) * ns; a1 = i0 + 1 + i * ns
                caras.append((a0 + j, a0 + (j + 1) % ns, a1 + (j + 1) % ns, a1 + j))
    me = bpy.data.meshes.new('discos grama'); me.from_pydata(verts, [], caras)
    at = me.attributes.new('densidad', 'FLOAT', 'POINT'); at.data.foreach_set('value', dens)
    ob = bpy.data.objects.new('Grama 3D', me); escena.collection.objects.link(ob)
    # matas (3 variantes) en su colección fuente
    col_m = bpy.data.collections.new('Fuente grama'); escena.collection.children.link(col_m)
    mat = mat_hoja_grama()
    for s in range(3):
        mm = mata_grama(s); mm.materials.append(mat)
        col_m.objects.link(bpy.data.objects.new(f'mata {s}', mm))
    bpy.context.view_layer.layer_collection.children[col_m.name].exclude = True
    # nodos de geometría
    g = bpy.data.node_groups.new('Grama 3D', 'GeometryNodeTree')
    g.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    g.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    ent = g.nodes.new('NodeGroupInput'); sal = g.nodes.new('NodeGroupOutput')
    nd = _gn(g, 'GeometryNodeInputNamedAttribute', data_type='FLOAT'); nd.inputs['Name'].default_value = 'densidad'
    dist = _gn(g, 'GeometryNodeDistributePointsOnFaces', distribute_method='RANDOM'); dist.inputs['Seed'].default_value = 1
    unir(g, ent.outputs[0], dist.inputs['Mesh']); unir(g, salida_n(nd, 'Attribute'), dist.inputs['Density'])
    pos = g.nodes.new('GeometryNodeInputPosition')
    arriba = g.nodes.new('ShaderNodeVectorMath'); arriba.operation = 'ADD'; arriba.inputs[1].default_value = (0, 0, 40)
    unir(g, pos.outputs[0], arriba.inputs[0])
    ci = _gn(g, 'GeometryNodeCollectionInfo', transform_space='RELATIVE'); ci.inputs['Collection'].default_value = col_s
    real = g.nodes.new('GeometryNodeRealizeInstances'); unir(g, ci.outputs[0], real.inputs[0])
    es = _gn(g, 'GeometryNodeInputNamedAttribute', data_type='FLOAT'); es.inputs['Name'].default_value = 'es_grama'
    rc = _gn(g, 'GeometryNodeRaycast', data_type='FLOAT')
    unir(g, real.outputs[0], rc.inputs['Target Geometry']); unir(g, salida_n(es, 'Attribute'), entrada(rc, 'Attribute'))
    unir(g, arriba.outputs[0], entrada(rc, 'Source Position'))
    entrada(rc, 'Ray Direction').default_value = (0, 0, -1); entrada(rc, 'Ray Length').default_value = 80.0
    ok = _mate(g, 'MULTIPLY', _mate(g, 'GREATER_THAN', salida_n(rc, 'Attribute'), 0.5), salida_n(rc, 'Is Hit'))
    borra = _gn(g, 'GeometryNodeDeleteGeometry', domain='POINT')
    unir(g, dist.outputs['Points'], borra.inputs['Geometry']); unir(g, _mate(g, 'LESS_THAN', ok, 0.5), borra.inputs['Selection'])
    setp = g.nodes.new('GeometryNodeSetPosition')
    unir(g, borra.outputs[0], setp.inputs['Geometry']); unir(g, salida_n(rc, 'Hit Position'), setp.inputs['Position'])
    cm = _gn(g, 'GeometryNodeCollectionInfo', transform_space='ORIGINAL'); cm.inputs['Collection'].default_value = col_m
    cm.inputs['Separate Children'].default_value = True; cm.inputs['Reset Children'].default_value = True
    cual = _gn(g, 'FunctionNodeRandomValue', data_type='INT'); entrada(cual, 'Max').default_value = 2; entrada(cual, 'Seed').default_value = 4
    giro = _gn(g, 'FunctionNodeRandomValue', data_type='FLOAT_VECTOR')
    entrada(giro, 'Min').default_value = (-0.15, -0.15, 0); entrada(giro, 'Max').default_value = (0.15, 0.15, 2 * math.pi)
    tam = _gn(g, 'FunctionNodeRandomValue', data_type='FLOAT'); entrada(tam, 'Min').default_value = 0.7; entrada(tam, 'Max').default_value = 1.35
    inst = g.nodes.new('GeometryNodeInstanceOnPoints')
    unir(g, setp.outputs[0], inst.inputs['Points']); unir(g, cm.outputs[0], inst.inputs['Instance'])
    inst.inputs['Pick Instance'].default_value = True; unir(g, salida_n(cual, 'Value'), inst.inputs['Instance Index'])
    unir(g, salida_n(giro, 'Value'), inst.inputs['Rotation']); unir(g, salida_n(tam, 'Value'), inst.inputs['Scale'])
    unir(g, inst.outputs[0], sal.inputs[0])
    ob.modifiers.new('Grama 3D', 'NODES').node_group = g
    print('Grama 3D bajo', len(cams), 'cámaras')


# ============================================================================ librea AMB del Diamond DA40
MATRICULA_DA40 = '61559'
ROJO_AMB, NEGRO_MATE, BLANCO_AVION = (0.5, 0.012, 0.02, 1), (0.02, 0.02, 0.022, 1), (0.78, 0.78, 0.76, 1)


def _fuente(negrita=True):
    ruta = r'C:\Windows\Fonts\arialbd.ttf' if negrita else r'C:\Windows\Fonts\arial.ttf'
    if os.path.exists(ruta):
        return bpy.data.fonts.get(os.path.basename(ruta)) or bpy.data.fonts.load(ruta)
    return None


def librea_da40():
    """El DA40 descargado traía franjas azules. Librea AMB (foto del usuario): blanco, deriva roja con 'E' blanca,
    puntas de ala rojas, parche rojo bajo el fuselaje detrás del ala, capó y hélice negros, matrícula y bandera."""
    from mathutils.bvhtree import BVHTree
    col = bpy.data.collections.get('Modelo Diamond DA40')
    mat = bpy.data.materials.get('DefaultWhite')
    if not col or not mat:
        return
    ext = [o for o in col.all_objects if o.type == 'MESH' and any(s.material == mat for s in o.material_slots)]
    # posición de cada vértice en el marco del avión (proa -X, envergadura Y, Z arriba)
    V, P, base = [], [], 0
    for o in ext:
        me = o.data
        v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', v); v = v.reshape(-1, 3)
        M = np.array(o.matrix_world); w = v @ M[:3, :3].T + M[:3, 3]
        at = me.attributes.get('pos_avion') or me.attributes.new('pos_avion', 'FLOAT_VECTOR', 'POINT')
        at.data.foreach_set('vector', w.astype(np.float32).ravel())
        V.extend(map(tuple, w)); P.extend([tuple(base + i for i in p.vertices) for p in me.polygons]); base += len(w)
    arbol = BVHTree.FromPolygons(V, P)
    # material: textura original sin el azul, y zonas de la librea
    nt = mat.node_tree
    b = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = b.inputs['Base Color'].links[0].from_socket
    hsv = nt.nodes.new('ShaderNodeSeparateColor'); hsv.mode = 'HSV'; unir(nt, tex, hsv.inputs[0])
    azul = _mate(nt, 'MULTIPLY', _mate(nt, 'GREATER_THAN', hsv.outputs[1], 0.25),
                 _mate(nt, 'MULTIPLY', _mate(nt, 'GREATER_THAN', hsv.outputs[0], 0.5), _mate(nt, 'LESS_THAN', hsv.outputs[0], 0.78)))
    claro = _mate(nt, 'GREATER_THAN', hsv.outputs[2], 0.45)
    col_b = mezclar(nt, tex, BLANCO_AVION, _mate(nt, 'MAXIMUM', azul, claro))
    at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_name = 'pos_avion'
    s = nt.nodes.new('ShaderNodeSeparateXYZ'); unir(nt, at.outputs['Vector'], s.inputs[0])
    x, y, z = s.outputs['X'], s.outputs['Y'], s.outputs['Z']
    ay = _mate(nt, 'ABSOLUTE', y)
    Y = lambda a, b_: _mate(nt, 'MULTIPLY', a, b_)
    deriva = Y(Y(_mate(nt, 'GREATER_THAN', x, 2.45), _mate(nt, 'LESS_THAN', ay, 0.13)),
               _mate(nt, 'MAXIMUM', Y(_mate(nt, 'GREATER_THAN', z, 0.2), _mate(nt, 'LESS_THAN', z, 0.82)),
                     Y(_mate(nt, 'LESS_THAN', z, -0.18), _mate(nt, 'GREATER_THAN', x, 2.9))))
    puntas = _mate(nt, 'GREATER_THAN', ay, 5.1)
    parche = Y(Y(_mate(nt, 'GREATER_THAN', x, -0.75), _mate(nt, 'LESS_THAN', x, 0.3)),
               Y(_mate(nt, 'LESS_THAN', z, -0.12), _mate(nt, 'LESS_THAN', ay, 0.62)))
    rojo = _mate(nt, 'MAXIMUM', _mate(nt, 'MAXIMUM', deriva, puntas), parche)
    capo = _mate(nt, 'MAXIMUM', Y(_mate(nt, 'LESS_THAN', x, -2.55), _mate(nt, 'GREATER_THAN', z, -0.35)),
                 _mate(nt, 'LESS_THAN', x, -3.75))
    col_b = mezclar(nt, col_b, ROJO_AMB, rojo)
    col_b = mezclar(nt, col_b, NEGRO_MATE, capo)
    unir(nt, col_b, b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.28                       # pintura de avión: brillante
    # rótulos sobre la piel (rayo desde afuera hacia el plano de simetría)
    fuente = _fuente()
    m_blanco = mat_simple('Rotulo blanco', BLANCO_AVION[:3], 0.35)
    m_negro = mat_simple('Rotulo negro', NEGRO_MATE[:3], 0.4)

    def rotulo(cuerpo, x0, z0, alto, m, giro_extra=0.0):
        for lado in (-1, 1):
            hit, n, _, _ = arbol.ray_cast(Vector((x0, lado * 3.0, z0)), Vector((0, -lado, 0)), 4.0)
            if hit is None:
                continue
            cu = bpy.data.curves.new('rotulo', 'FONT'); cu.body = cuerpo; cu.size = alto
            cu.align_x = 'CENTER'; cu.align_y = 'CENTER'; cu.extrude = 0.0006
            if fuente:
                cu.font = fuente
            ob = bpy.data.objects.new(f'Rotulo {cuerpo} {lado}', cu); ob.data.materials.append(m)
            ob.location = hit + n * 0.004
            # texto de pie, legible desde afuera: en el lado +Y la proa (-X) queda a la derecha y viceversa
            ob.rotation_euler = (math.pi / 2, 0, (0 if lado < 0 else math.pi) + giro_extra)
            col.objects.link(ob)

    rotulo(MATRICULA_DA40, 1.25, 0.02, 0.15, m_negro)
    rotulo('E', 3.25, 0.5, 0.36, m_blanco)
    rotulo('CE', 3.3, 0.89, 0.09, m_negro)
    # bandera de Venezuela (amarillo, azul, rojo), pequeña, delante de la matrícula
    for k, c in enumerate(((0.9, 0.62, 0.02), (0.0, 0.03, 0.25), (0.62, 0.01, 0.025))):
        for lado in (-1, 1):
            zc = 0.07 - k * 0.033
            hit, n, _, _ = arbol.ray_cast(Vector((0.62, lado * 3.0, zc)), Vector((0, -lado, 0)), 4.0)
            if hit is None:
                continue
            me = bpy.data.meshes.new('franja bandera')
            me.from_pydata([(-0.09, -0.0165, 0), (0.09, -0.0165, 0), (0.09, 0.0165, 0), (-0.09, 0.0165, 0)], [], [(0, 1, 2, 3)])
            me.materials.append(mat_simple(f'Bandera {k}', c, 0.4))
            ob = bpy.data.objects.new('Bandera DA40', me); ob.location = hit + n * 0.004
            ob.rotation_euler = n.to_track_quat('Z', 'Y').to_euler()
            col.objects.link(ob)
    print('DA40 con librea AMB', MATRICULA_DA40)


# ============================================================================ stands de proyectos de la AMB (en el hangar)
# Los 4 proyectos tecnológicos de la AMB (pedido del cliente), en los puestos más cercanos a la entrada del hangar.
# Orden = puestos por cercanía: 1 y 3 en la misma fila (vista 'stands': los dos de Igla-S), 2 y 4 enfrente ('stands2').
#   titulo: letrero de identificación (estilo de la portada del video del simulador); corto: torre; mostrador: su frente.
#   tv: tamaño de la pantalla del fondo; pantalla / caja_img: imagen de la pantalla y de la caja de luz, sacadas del
#   material del cliente (video del simulador, capturas de Cóndor, resumen ejecutivo del ULV); caja_luz: su tamaño.
UNIDAD_LETRERO = 'AVIACIÓN MILITAR BOLIVARIANA'     # pedido del cliente: igual en los cuatro letreros
# Pantalla del fondo, la más grande que cabe (pedido del cliente): casi todo el ancho libre de la pared entre la pared
# lateral y la torre, y desde 0,64 m hasta justo debajo del letrero (2,64 m).
PANTALLA_STAND = (3.55, 2.0)
PANTALLA_TOPE = 2.64
# Maqueta del ULV: en el centro del stand, sobre su base y con luz propia (pedido del cliente)
VITRINA_ULV = (-0.2, 0.25)
PROYECTOS_AMB = [
    dict(clave='igla', titulo='SIMULADOR DE DISPARO IGLA-S', corto='SIMULADOR\nIGLA-S', mostrador='SIMULADOR DE\nDISPARO IGLA-S',
         sub='Simulador MANPADS · Sistema de entrenamiento integrado', color=(0.01, 0.045, 0.19), tv=PANTALLA_STAND,
         pantalla='fotos/igla_sim/helicoptero.jpg', caja_img='fotos/igla_sim/titulo.jpg', caja_luz=(2.2, 1.24),
         monitor_pc='fotos/igla_sim/consola_seguimiento.jpg'),
    dict(clave='juego', titulo='CÓNDOR · SIMULADOR DE JUEGOS DE GUERRA', corto='CÓNDOR', mostrador='CÓNDOR\nJUEGOS DE GUERRA',
         sub='Simulador de entrenamiento táctico y estratégico en tiempo real', color=(0.035, 0.052, 0.022), tv=PANTALLA_STAND,
         pantalla='fotos/condor/captura_tutorial.png', caja_img='fotos/condor/inicio_sesion.png', caja_luz=(1.85, 2.36),
         monitores=('fotos/condor/captura_s300.png', 'fotos/condor/captura_tutorial.png', 'fotos/condor/captura_fuerzas.png'),
         mesa='fotos/condor/captura_s300.png'),
    dict(clave='mecanismo', titulo='DISPARO AUTOMATIZADO IGLA-S', corto='DISPARO\nAUTOMATIZADO', mostrador='DISPARO\nAUTOMATIZADO IGLA-S',
         sub='Mecanismo de disparo automatizado sobre plataforma móvil', color=(0.07, 0.075, 0.085), tv=PANTALLA_STAND,
         pantalla='fotos/igla_sim/consola_seguimiento.jpg', caja_img='fotos/igla_sim/impacto.jpg', caja_luz=(2.2, 1.24),
         monitor_pc='fotos/igla_sim/camara_misil.jpg'),
    dict(clave='ultraligero', titulo='AERONAVE ULTRALIGERA ULV', corto='AERONAVE\nULTRALIGERA', mostrador='AERONAVE\nULTRALIGERA ULV',
         sub='Biplaza de alto rendimiento · Fabricación venezolana', color=(0.07, 0.3, 0.62), tv=PANTALLA_STAND,
         pantalla='fotos/ulv/foto_ulv.png', caja_img='fotos/ulv/planos_sibo200.png', caja_luz=(2.2, 1.43)),
]
PANTALLA = 0.07          # luminancia de pantallas (adentro se expone +4 EV: 0,07 x 2^3,5 ≈ 0,8)
QUITAR_PUESTOS_SOBRANTES = True   # el hangar muestra solo los 4 stands de la AMB (False: quedan como expositores genéricos)


def _fuente_archivo(nombre):
    ruta = os.path.join(r'C:\Windows\Fonts', nombre)
    if os.path.exists(ruta):
        return bpy.data.fonts.get(nombre) or bpy.data.fonts.load(ruta)
    return _fuente()


def _tam_texto(texto, ancho, maximo, em=0.68):
    """Tamaño de letra para que el renglón más largo quepa en 'ancho' metros (em = ancho medio por letra:
    0,68 Arial Negrita, ~0,45 Agency FB Negrita, que es condensada)."""
    largo = max(len(r) for r in texto.split('\n'))
    return min(maximo, ancho / (em * max(1, largo)))


class Stand:
    """Constructor en el marco local del puesto: origen en el centro del piso, +Y hacia el pasillo,
    pared de fondo en y=-2.5, pared lateral en x=-2.9 (si s=-1 el puesto se refleja y queda en x=+2.9)."""

    def __init__(self, nombre, matriz, s, coleccion):
        self.s, self.col = s, coleccion
        self.raiz = bpy.data.objects.new(nombre, None); self.raiz.matrix_world = matriz; coleccion.objects.link(self.raiz)
        self.raiz['reflejo'] = s

    def P(self, x, y, z):
        return Vector((x * self.s, y, z))

    def sub(self, nombre, pos, giro_z=0.0, elev=0.0, frente_y=False):
        """Marco hijo (p. ej. azimut y elevación de una torreta): +X hacia adelante tras girar giro_z y subir elev.
        En un puesto reflejado (x -> -x) un reflejo no se puede hacer solo con un giro: si el frente del objeto es +X
        (lanzador, torreta) el ángulo g pasa a π - g; si el frente es +Y (mesa, PC: lo que mira al pasillo), a -g.
        Con π - g una mesa quedaba de espaldas al pasillo."""
        e = bpy.data.objects.new(nombre, None); self.col.objects.link(e); e.parent = self.raiz
        if self.s < 0:
            giro_z = -giro_z if frente_y else math.pi - giro_z
        e.location = self.P(*pos); e.rotation_euler = (0, -elev, giro_z)
        hijo = Stand.__new__(Stand); hijo.s = 1; hijo.col = self.col; hijo.raiz = e
        return hijo

    def _obj(self, nombre, me, pos, rot_z=0.0):
        ob = bpy.data.objects.new(nombre, me); self.col.objects.link(ob)
        ob.parent = self.raiz; ob.location = self.P(*pos); ob.rotation_euler.z = rot_z * self.s
        return ob

    def caja(self, nombre, tam, pos, mat, rot_z=0.0, bisel=0.004):
        bm = bmesh.new(); r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=tam, verts=r['verts'])
        if bisel and min(tam) > 4 * bisel:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bisel, segments=2, affect='EDGES', profile=0.5)
        me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free(); me.materials.append(mat)
        for p in me.polygons:
            p.use_smooth = False
        return self._obj(nombre, me, pos, rot_z)

    def cilindro(self, nombre, r1, r2, alto, pos, mat, rot=(0, 0, 0), lados=32):
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=lados, radius1=r1, radius2=r2, depth=alto)
        me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free(); me.materials.append(mat); me.shade_smooth()
        ob = self._obj(nombre, me, pos)
        ob.rotation_euler = (rot[0], rot[1] * self.s, (rot[2]) * self.s)
        return ob

    def tubo(self, nombre, a, b, r, mat, lados=12):
        """Tubo recto entre dos puntos (marco sin reflejar)."""
        a, b = Vector(a), Vector(b)
        ob = self.cilindro(nombre, r, r, (b - a).length, tuple((a + b) / 2), mat, lados=lados)
        v = b - a
        ob.rotation_euler = Vector((v.x * self.s, v.y, v.z)).to_track_quat('Z', 'Y').to_euler()
        return ob

    def plano(self, nombre, ancho, alto, pos, cara, mat):
        """Rectángulo vertical mirando a 'cara' (+Y, -Y, +X, -X en el marco sin reflejar)."""
        me = bpy.data.meshes.new(nombre)
        me.from_pydata([(-ancho / 2, 0, -alto / 2), (ancho / 2, 0, -alto / 2), (ancho / 2, 0, alto / 2), (-ancho / 2, 0, alto / 2)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(); [setattr(uv.data[i], 'uv', c) for i, c in enumerate(((0, 0), (1, 0), (1, 1), (0, 1)))]
        me.materials.append(mat)
        ob = self._obj(nombre, me, pos)
        ob.rotation_euler.z = self._giro_cara(cara)
        return ob

    def _giro_cara(self, cara):
        if self.s < 0 and cara in ('+X', '-X'):
            cara = '-X' if cara == '+X' else '+X'
        # un plano/texto en XZ mira a -Y; se gira para que mire a 'cara'
        return {'-Y': 0.0, '+Y': math.pi, '+X': math.pi / 2, '-X': -math.pi / 2}[cara]

    def texto(self, cuerpo, tam, pos, cara, mat, fuente=None, espacio=1.0):
        cu = bpy.data.curves.new('texto', 'FONT'); cu.body = cuerpo; cu.size = tam
        cu.align_x = 'CENTER'; cu.align_y = 'CENTER'; cu.extrude = 0.002; cu.space_character = espacio
        if fuente:
            cu.font = fuente
        cu.materials.append(mat)
        ob = bpy.data.objects.new('Texto ' + cuerpo[:16], cu); self.col.objects.link(ob)
        ob.parent = self.raiz; ob.location = self.P(*pos)
        ob.rotation_euler = (math.pi / 2, 0, self._giro_cara(cara))
        return ob

    def foco(self, pos, apunta, energia=4.0):
        """Reflector de brazo sobre la pared (como en la referencia) con su luz."""
        mat = mat_simple('Reflector', (0.02, 0.02, 0.02), 0.35, 0.6)
        p = self.P(*pos); q = self.P(*apunta)
        d = (q - p).normalized()
        rot = d.to_track_quat('-Z', 'Y').to_euler()
        cab = self.cilindro('Reflector', 0.05, 0.035, 0.14, pos, mat)
        cab.rotation_euler = rot
        ld = bpy.data.lights.new('Foco stand', 'SPOT'); ld.energy = energia; ld.spot_size = math.radians(55)
        ld.spot_blend = 0.5; ld.shadow_soft_size = 0.03; ld.color = (1.0, 0.93, 0.84)
        lo = bpy.data.objects.new('Foco stand', ld); self.col.objects.link(lo)
        lo.parent = self.raiz; lo.location = p + d * 0.06; lo.rotation_euler = rot
        self.cilindro('Brazo reflector', 0.008, 0.008, 0.4, (pos[0], pos[1] + 0.2 * (1 if apunta[1] > pos[1] else -1), pos[2] + 0.03), mat,
                      rot=(math.pi / 2, 0, 0))
        return lo


def _img_np(nombre, arr):
    """Imagen empaquetada en el .blend a partir de un arreglo (alto, ancho, 3) en sRGB 0..1 (fila 0 = arriba)."""
    h, w = arr.shape[:2]
    im = bpy.data.images.new(nombre, w, h, alpha=False)
    px = np.ones((h, w, 4), dtype=np.float32); px[..., :3] = np.clip(arr, 0, 1)
    im.pixels.foreach_set(np.flipud(px).ravel()); im.pack()
    return im


def mat_imagen(nombre, im, brillo=0.0, rug=0.4):
    """Impresión/pantalla: color de la imagen + emisión opcional (cajas de luz y pantallas)."""
    m = bpy.data.materials.new(nombre)
    nt, bsdf, out = nodos(m)
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = im
    unir(nt, t.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = rug
    if brillo > 0:
        unir(nt, t.outputs['Color'], bsdf.inputs['Emission Color']); bsdf.inputs['Emission Strength'].default_value = brillo
        if rug < 0.2:                                       # pantalla: el vidrio negro refleja, el fondo es oscuro
            bsdf.inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1)
            nt.links.remove(bsdf.inputs['Base Color'].links[0])
    unir(nt, bsdf.outputs[0], out.inputs[0])
    return m


def _imagen_proyecto(ruta_rel):
    im = bpy.data.images.load(os.path.join(RAIZ, ruta_rel), check_existing=True); im.pack()
    return im


def _mat_captura(ruta_rel, brillo=None):
    """Pantalla que muestra una imagen del proyecto (captura, cuadro de video, página del PDF); una por archivo."""
    nombre = 'Pantalla ' + os.path.basename(ruta_rel)
    return bpy.data.materials.get(nombre) or mat_imagen(nombre, _imagen_proyecto(ruta_rel), PANTALLA if brillo is None else brillo, 0.12)


def _mat_impresion(ruta_rel, brillo=0.022):
    """Gráfica impresa de caja de luz (retroiluminada apenas)."""
    nombre = 'Grafica ' + os.path.basename(ruta_rel)
    return bpy.data.materials.get(nombre) or mat_imagen(nombre, _imagen_proyecto(ruta_rel), brillo, 0.5)


def _mats_militar():
    return (mat_simple('Verde lanzador Igla', (0.05, 0.085, 0.03), 0.5),
            mat_simple('Negro mate', (0.015, 0.015, 0.016), 0.5),
            mat_simple('Aluminio stand', (0.75, 0.76, 0.78), 0.3, 1.0))


def letrero(st, titulo, sub):
    """Letrero de identificación con el estilo de la portada del simulador: fondo azul marino, título blanco condensado,
    línea dorada, unidad en dorado espaciado y una línea gris con la descripción."""
    navy = mat_simple('Letrero azul marino', (0.006, 0.013, 0.035), 0.45)
    dorado = mat_simple('Dorado letrero', (0.62, 0.4, 0.06), 0.35, 0.3)
    gris = mat_simple('Gris letrero', (0.32, 0.33, 0.35), 0.5)
    blanco = mat_simple('Texto blanco stand', (0.85, 0.85, 0.85), 0.4)
    st.caja('Letrero', (3.76, 0.03, 0.56), (-0.95, -2.385, 2.97), navy, bisel=0.003)
    st.texto(titulo, _tam_texto(titulo, 3.4, 0.25, em=0.45), (-0.95, -2.366, 3.1), '+Y', blanco, _fuente_archivo('AGENCYB.TTF'))
    st.caja('Linea dorada', (1.9, 0.004, 0.009), (-0.95, -2.368, 2.958), dorado, bisel=0)
    st.texto(UNIDAD_LETRERO, 0.058, (-0.95, -2.366, 2.888), '+Y', dorado, _fuente_archivo('arialbd.ttf'), espacio=1.25)
    st.texto('«' + sub + '»', 0.04, (-0.95, -2.366, 2.8), '+Y', gris, _fuente_archivo('arial.ttf'))


# ---------------------------------------------------------------------------- lanzador Igla (modelo 3D del cliente)
def modelo_lanzador_igla():
    """Lanzador 9K310 Igla-1 (assets/igla/Igla.obj, del .zip que dejó el cliente), pintado de verde por pedido.
    Se lleva a metros (1,70 m de largo), con el eje del tubo en el origen y la proa (lado de la empuñadura) hacia +X."""
    col = bpy.data.collections.get('Modelo lanzador Igla-S')
    if col:
        return col
    ruta = os.path.join(RAIZ, 'assets', 'igla', 'Igla.obj')
    if not os.path.exists(ruta):
        return None
    antes = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=ruta)
    nuevos = [o for o in bpy.data.objects if o not in antes]
    malla = [o for o in nuevos if o.type == 'MESH']
    if not malla:
        return None
    o = malla[0]
    me = o.data; me.transform(o.matrix_world); o.matrix_world = Matrix.Identity(4)
    v = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', v); v = v.reshape(-1, 3)
    idx_mat = np.empty(len(me.polygons), dtype=np.int32); me.polygons.foreach_get('material_index', idx_mat)

    def verts_de(prefijo):
        ids = [i for i, m in enumerate(me.materials) if m and m.name.startswith(prefijo)]
        sel = {vi for p, mi in zip(me.polygons, idx_mat) if mi in ids for vi in p.vertices}
        return v[list(sel)] if sel else v
    tubo, culata = verts_de('115'), verts_de('255')
    x0, x1 = v[:, 0].min(), v[:, 0].max()
    centro = Vector(((x0 + x1) / 2, float(np.median(tubo[:, 1])), float(np.median(tubo[:, 2]))))
    giro = math.pi if culata[:, 0].mean() < centro.x else 0.0
    me.transform(Matrix.Rotation(giro, 4, 'Z') @ Matrix.Scale(1.70 / (x1 - x0), 4) @ Matrix.Translation(-centro))
    verde, negro, _ = _mats_militar()
    for i, m in enumerate(me.materials):
        me.materials[i] = negro if (m and m.name.startswith('10,')) else verde
    col = bpy.data.collections.new('Modelo lanzador Igla-S'); escena.collection.children.link(col)
    for ob in nuevos:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        col.objects.link(ob)
    bpy.context.view_layer.layer_collection.children[col.name].exclude = True
    print('Lanzador Igla (modelo del cliente):', len(me.vertices), 'vértices, escala', round(1.70 / (x1 - x0), 5))
    return col


def _lanzador_igla(fr):
    """Lanzador en el marco 'fr' (tubo a lo largo de +X, centrado). La empuñadura queda entre x=+0,10 y +0,48 m:
    los soportes van detrás (x < 0)."""
    col = modelo_lanzador_igla()
    if col:
        e = bpy.data.objects.new('Lanzador Igla-S', None); e.instance_type = 'COLLECTION'; e.instance_collection = col
        fr.col.objects.link(e); e.parent = fr.raiz
        return e
    verde, negro, _ = _mats_militar()                       # respaldo si falta el modelo
    eje_x = (0, math.pi / 2, 0)
    fr.cilindro('Tubo Igla-S', 0.036, 0.036, 1.57, (0, 0, 0), verde, rot=eje_x)
    fr.cilindro('Tapa delantera', 0.05, 0.05, 0.11, (0.8, 0, 0), negro, rot=eje_x)
    fr.cilindro('Tapa trasera', 0.048, 0.048, 0.1, (-0.8, 0, 0), negro, rot=eje_x)
    fr.caja('Mecanismo de disparo', (0.3, 0.07, 0.11), (0.25, 0, -0.085), verde)
    return None


# ---------------------------------------------------------------------------- exhibiciones
def _exhibicion_igla(st, proy):
    """Simulador de disparo: el lanzador sobre una base simple, apuntando a la pantalla LED donde se proyecta el
    escenario (como en el video del simulador), con el puesto de tiro marcado y la consola del instructor."""
    _, negro, alu = _mats_militar()
    amarillo = mat_simple('Franja amarilla Igla', (0.6, 0.42, 0.02), 0.5)
    px_, py_, alto = 0.55, 0.9, 1.42
    objetivo = Vector((-0.9, -2.4, 1.75))                                  # centro de la pantalla
    d = objetivo - Vector((px_, py_, alto))
    giro = math.atan2(d.y, d.x); elev = math.atan2(d.z, d.xy.length)
    u = Vector((math.cos(elev) * math.cos(giro), math.cos(elev) * math.sin(giro), math.sin(elev)))
    c = Vector((px_, py_, alto)) + u * -0.3 + Vector((0, 0, -0.06))         # cuna detrás de la empuñadura
    st.cilindro('Base lanzador', 0.24, 0.26, 0.03, (c.x, c.y, 0.075), negro)
    h = c.z - 0.115
    st.cilindro('Poste lanzador', 0.028, 0.028, h, (c.x, c.y, 0.09 + h / 2), alu)
    st.caja('Cuna lanzador', (0.12, 0.11, 0.05), (c.x, c.y, c.z), negro, rot_z=giro)
    _lanzador_igla(st.sub('Lanzador simulador', (px_, py_, alto), giro, elev))
    for (cx, cy, sx, sy) in ((px_, py_ - 0.6, 1.2, 0.06), (px_, py_ + 0.6, 1.2, 0.06), (px_ - 0.6, py_, 0.06, 1.2), (px_ + 0.6, py_, 0.06, 1.2)):
        st.caja('Marca puesto de tiro', (sx, sy, 0.004), (cx, cy, 0.062), amarillo, bisel=0)
    # mesa de control del instructor (pedido del cliente: monitor, teclado y la PC de la foto)
    _mesa_control(st.sub('Mesa de control', (-1.35, -0.95, 0.0), math.radians(18), frente_y=True), _mat_captura(proy['monitor_pc']))


def _mat_rgb():
    """LED arcoíris de los ventiladores: el color recorre el aro según el ángulo (como los de la PC de la foto)."""
    m = bpy.data.materials.get('LED RGB ventilador')
    if m:
        return m
    m = bpy.data.materials.new('LED RGB ventilador')
    nt, _, out = nodos(m)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sp = nt.nodes.new('ShaderNodeSeparateXYZ'); unir(nt, tc.outputs['Object'], sp.inputs[0])
    ang = _mate(nt, 'ADD', _mate(nt, 'DIVIDE', _mate(nt, 'ARCTAN2', sp.outputs['Z'], sp.outputs['X']), 2 * math.pi), 0.5)
    r = nt.nodes.new('ShaderNodeValToRGB')
    cols = ((0.0, (1, 0, 0.05, 1)), (0.17, (1, 0.45, 0, 1)), (0.33, (0.9, 1, 0, 1)), (0.5, (0, 1, 0.3, 1)),
            (0.67, (0, 0.6, 1, 1)), (0.83, (0.55, 0, 1, 1)), (1.0, (1, 0, 0.05, 1)))
    r.color_ramp.elements[0].position, r.color_ramp.elements[0].color = cols[0]
    r.color_ramp.elements[1].position, r.color_ramp.elements[1].color = cols[-1]
    for pos, c in cols[1:-1]:
        e = r.color_ramp.elements.new(pos); e.color = c
    unir(nt, ang, r.inputs['Fac'])
    em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 0.6
    unir(nt, r.outputs['Color'], em.inputs['Color']); unir(nt, em.outputs[0], out.inputs[0])
    return m


def _aro(fr, nombre, centro, radio, ancho, normal, mat, lados=32):
    """Aro plano (anillo) centrado en 'centro', mirando a lo largo de 'normal' ('X' o 'Y')."""
    bm = bmesh.new()
    vi, ve = [], []
    for i in range(lados):
        a = 2 * math.pi * i / lados
        for lista, r in ((vi, radio - ancho), (ve, radio)):
            p = (math.cos(a) * r, 0, math.sin(a) * r) if normal == 'Y' else (0, math.cos(a) * r, math.sin(a) * r)
            lista.append(bm.verts.new(p))
    for i in range(lados):
        j = (i + 1) % lados
        bm.faces.new((vi[i], ve[i], ve[j], vi[j]))
    me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    return fr._obj(nombre, me, centro)


def _pc_rgb(fr, x, y, z):
    """PC de la foto del cliente: chasis negro con vidrio templado al frente y a un lado, tres ventiladores RGB al frente,
    uno atrás y el del procesador, tarjeta gráfica y cubierta de la fuente; luces de color adentro para el resplandor."""
    _, negro, _ = _mats_militar()
    placa = mat_simple('Placa base', (0.02, 0.025, 0.03), 0.4, 0.3)
    vidrio = bpy.data.materials.get('Vidrio templado PC')
    if not vidrio:
        vidrio = bpy.data.materials.new('Vidrio templado PC')
        nt, _, out = nodos(vidrio)
        fr_ = nt.nodes.new('ShaderNodeFresnel'); fr_.inputs['IOR'].default_value = 1.5
        tr = nt.nodes.new('ShaderNodeBsdfTransparent'); tr.inputs['Color'].default_value = (0.8, 0.8, 0.83, 1)
        gl = nt.nodes.new('ShaderNodeBsdfGlossy'); gl.inputs['Roughness'].default_value = 0.01
        mx = nt.nodes.new('ShaderNodeMixShader'); geo = nt.nodes.new('ShaderNodeNewGeometry')
        unir(nt, _mate(nt, 'MULTIPLY', fr_.outputs[0], _mate(nt, 'SUBTRACT', 1.0, geo.outputs['Backfacing'])), mx.inputs['Fac'])
        unir(nt, tr.outputs[0], mx.inputs[1]); unir(nt, gl.outputs[0], mx.inputs[2]); unir(nt, mx.outputs[0], out.inputs[0])
    rgb = _mat_rgb()
    W, D, H = 0.24, 0.46, 0.5                      # ancho (x), fondo (y, frente hacia +y), alto
    c = Vector((x, y, z + H / 2))
    def P(dx, dy, dz):
        return tuple(c + Vector((dx, dy, dz)))
    fr.caja('Chasis PC fondo', (W, 0.01, H), P(0, -D / 2 + 0.005, 0), negro, bisel=0)
    fr.caja('Chasis PC techo', (W, D, 0.012), P(0, 0, H / 2 - 0.006), negro, bisel=0)
    fr.caja('Chasis PC base', (W, D, 0.015), P(0, 0, -H / 2 + 0.0075), negro, bisel=0)
    fr.caja('Chasis PC lateral', (0.01, D, H), P(W / 2 - 0.005, 0, 0), negro, bisel=0)
    for sx in (-1, 1):                              # aristas del marco
        fr.caja('Arista PC', (0.012, 0.012, H), P(sx * (W / 2 - 0.006), D / 2 - 0.006, 0), negro, bisel=0)
    fr.caja('Vidrio frontal PC', (W - 0.02, 0.004, H - 0.03), P(0, D / 2 - 0.004, 0), vidrio, bisel=0)
    fr.caja('Vidrio lateral PC', (0.004, D - 0.02, H - 0.03), P(-W / 2 + 0.004, 0, 0), vidrio, bisel=0)
    fr.caja('Placa base PC', (0.006, 0.34, 0.36), P(W / 2 - 0.014, -0.03, 0.04), placa, bisel=0)
    fr.caja('Tarjeta grafica', (0.12, 0.28, 0.05), P(0.04, -0.02, -0.05), negro, bisel=0.003)
    fr.caja('LED grafica', (0.002, 0.24, 0.006), P(-0.021, -0.02, -0.03), rgb, bisel=0)
    fr.caja('Cubierta fuente', (W - 0.02, D - 0.02, 0.08), P(0, 0, -H / 2 + 0.055), negro, bisel=0)
    for dz in (-0.1, 0.03, 0.16):                  # tres ventiladores al frente
        _aro(fr, 'Aro ventilador', P(0, D / 2 - 0.025, dz), 0.058, 0.009, 'Y', rgb)
        fr.cilindro('Ventilador', 0.05, 0.05, 0.012, P(0, D / 2 - 0.03, dz), negro, rot=(math.pi / 2, 0, 0), lados=24)
    _aro(fr, 'Aro ventilador trasero', P(0, -D / 2 + 0.03, 0.14), 0.05, 0.008, 'Y', rgb)
    _aro(fr, 'Aro disipador CPU', P(0.06, -0.06, 0.1), 0.045, 0.008, 'X', rgb)
    for col_luz, pos in (((1.0, 0.2, 0.8), P(0, 0.12, 0.05)), ((0.2, 0.6, 1.0), P(0, -0.1, 0.12))):
        # 0,025 W: a 30 cm da ~la mitad de la luz del hangar (que se ve con +4 EV); más, y la PC "alumbra" la mesa
        ld = bpy.data.lights.new('Resplandor RGB', 'POINT'); ld.energy = 0.025; ld.color = col_luz; ld.shadow_soft_size = 0.05
        lo = bpy.data.objects.new('Resplandor RGB', ld); fr.col.objects.link(lo); lo.parent = fr.raiz; lo.location = pos


def _mesa_control(fr, mat_monitor):
    """Mesa de control (como la de la foto): tablero claro, monitor en su pie, teclado, ratón y la PC con vidrio y RGB."""
    _, negro, alu = _mats_militar()
    madera = mat_simple('Tablero mesa control', (0.5, 0.4, 0.27), 0.45)
    fr.caja('Tablero mesa control', (1.5, 0.75, 0.03), (0, 0, 0.75), madera, bisel=0.004)
    for dx in (-0.68, 0.68):
        for dy in (-0.3, 0.3):
            fr.cilindro('Pata mesa control', 0.028, 0.028, 0.69, (dx, dy, 0.405), alu)
    fr.caja('Base monitor', (0.24, 0.18, 0.012), (-0.25, -0.16, 0.772), negro)
    fr.caja('Cuello monitor', (0.05, 0.03, 0.22), (-0.25, -0.2, 0.88), negro)
    fr.caja('Monitor', (0.62, 0.035, 0.37), (-0.25, -0.2, 1.13), negro)
    fr.plano('Imagen monitor control', 0.6, 0.34, (-0.25, -0.181, 1.13), '+Y', mat_monitor)
    fr.caja('Teclado', (0.45, 0.15, 0.02), (-0.25, 0.12, 0.775), negro)
    fr.caja('Raton', (0.06, 0.1, 0.03), (0.08, 0.13, 0.78), negro)
    _pc_rgb(fr, 0.43, -0.1, 0.765)
    fr.cilindro('Asiento instructor', 0.24, 0.24, 0.07, (-0.2, 0.75, 0.55), negro)
    fr.cilindro('Columna silla', 0.03, 0.03, 0.45, (-0.2, 0.75, 0.3), alu)


def _exhibicion_mecanismo(st, proy):
    """Mecanismo de disparo automatizado: el lanzador en un cabezal motorizado (azimut y elevación) sobre una plataforma
    móvil con ruedas, caja de baterías y cámara; PC con monitor, joystick y cable a la plataforma."""
    verde, negro, alu = _mats_militar()
    acero = mat_simple('Acero pavonado', (0.05, 0.05, 0.055), 0.35, 0.9)
    lente = mat_simple('Lente sensor', (0.0, 0.0, 0.0), 0.05, 0.0)
    x0, y0 = 1.3, 0.85
    # plataforma móvil
    st.caja('Chasis plataforma movil', (1.1, 0.75, 0.1), (x0, y0, 0.28), verde)
    for dx in (-0.46, 0.46):
        for dy in (-0.3, 0.3):
            st.caja('Horquilla rueda', (0.07, 0.09, 0.09), (x0 + dx, y0 + dy, 0.2), acero)
            st.cilindro('Rueda', 0.065, 0.065, 0.05, (x0 + dx, y0 + dy, 0.125), negro, rot=(math.pi / 2, 0, 0), lados=24)
    for dy in (-0.28, 0.28):
        st.tubo('Manija', (x0 - 0.55, y0 + dy, 0.33), (x0 - 0.68, y0 + dy, 0.95), 0.016, acero)
    st.tubo('Manija', (x0 - 0.68, y0 - 0.3, 0.95), (x0 - 0.68, y0 + 0.3, 0.95), 0.018, negro)
    st.caja('Caja de baterias', (0.36, 0.34, 0.2), (x0 - 0.3, y0, 0.43), negro)
    led = mat_imagen('LED verde', _img_np('led verde', np.ones((2, 2, 3)) * np.array((0.1, 1.0, 0.2))), 2.0, 0.3)
    st.caja('LED', (0.02, 0.01, 0.02), (x0 - 0.3, y0 + 0.172, 0.48), led, bisel=0)
    st.cilindro('Mastil', 0.06, 0.05, 0.42, (x0 + 0.12, y0, 0.54), verde)
    st.cilindro('Corona de azimut', 0.13, 0.13, 0.05, (x0 + 0.12, y0, 0.775), acero)
    az = st.sub('Cabezal azimut', (x0 + 0.12, y0, 0.8), math.radians(150))
    az.caja('Caja de servos', (0.26, 0.24, 0.14), (0, 0, 0.07), verde)
    for lado in (-1, 1):
        az.caja('Brazo horquilla', (0.07, 0.035, 0.34), (0, lado * 0.15, 0.27), verde)
        az.cilindro('Servo elevacion', 0.045, 0.045, 0.1, (0, lado * 0.21, 0.34), negro, rot=(math.pi / 2, 0, 0))
    el = az.sub('Cuna elevacion', (0, 0, 0.34), 0.0, math.radians(25))
    el.cilindro('Eje elevacion', 0.02, 0.02, 0.36, (0, 0, 0), acero, rot=(math.pi / 2, 0, 0))
    el.caja('Riel', (0.75, 0.08, 0.03), (-0.3, 0, 0.0), verde)
    for x in (-0.55, -0.1):
        el.caja('Abrazadera', (0.05, 0.11, 0.09), (x, 0, 0.045), negro)
    _lanzador_igla(el.sub('Lanzador', (0, 0, 0.075)))
    el.caja('Camara', (0.17, 0.09, 0.09), (-0.32, 0, 0.17), negro)
    el.cilindro('Lente camara', 0.03, 0.03, 0.03, (-0.22, 0, 0.17), lente, rot=(0, math.pi / 2, 0))
    # PC: escritorio, torre, monitor (cámara del misil), teclado, ratón, joystick y silla
    ex, ey = -1.0, -1.35
    escritorio = mat_simple('Escritorio blanco', (0.75, 0.75, 0.74), 0.35)
    st.caja('Escritorio PC', (1.3, 0.62, 0.035), (ex, ey, 0.76), escritorio)
    for dx in (-0.6, 0.6):
        st.caja('Pata escritorio', (0.04, 0.58, 0.7), (ex + dx, ey, 0.41), escritorio)
    st.caja('Torre PC', (0.2, 0.45, 0.45), (ex + 0.38, ey, 0.29), negro)
    led_pc = mat_imagen('LED azul', _img_np('led azul', np.ones((2, 2, 3)) * np.array((0.2, 0.5, 1.0))), 2.0, 0.3)
    st.caja('LED PC', (0.012, 0.004, 0.012), (ex + 0.38, ey + 0.226, 0.46), led_pc, bisel=0)
    st.caja('Monitor PC', (0.64, 0.04, 0.38), (ex - 0.1, ey - 0.12, 1.08), negro)
    st.plano('Imagen monitor PC', 0.6, 0.34, (ex - 0.1, ey - 0.098, 1.08), '+Y', _mat_captura(proy['monitor_pc']))
    st.caja('Pie monitor', (0.05, 0.05, 0.13), (ex - 0.1, ey - 0.14, 0.84), negro)
    st.caja('Teclado', (0.44, 0.15, 0.02), (ex - 0.1, ey + 0.12, 0.787), negro)
    st.caja('Raton', (0.06, 0.1, 0.03), (ex + 0.22, ey + 0.12, 0.79), negro)
    st.caja('Base joystick', (0.15, 0.15, 0.05), (ex - 0.5, ey + 0.08, 0.8), negro)
    st.cilindro('Palanca joystick', 0.014, 0.02, 0.15, (ex - 0.5, ey + 0.08, 0.9), negro)
    st.cilindro('Asiento operador', 0.24, 0.24, 0.07, (ex, ey + 0.7, 0.55), negro)
    st.cilindro('Columna silla', 0.03, 0.03, 0.45, (ex, ey + 0.7, 0.3), alu)
    cu = bpy.data.curves.new('cable', 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = 0.01; cu.bevel_resolution = 2
    sp = cu.splines.new('BEZIER'); pts = [(ex + 0.38, ey + 0.2, 0.1), (ex + 0.9, ey + 0.8, 0.07), (x0 - 0.6, y0 - 0.2, 0.07), (x0 - 0.3, y0 - 0.17, 0.4)]
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = st.P(*p); bp.handle_left_type = bp.handle_right_type = 'AUTO'
    cu.materials.append(negro)
    cab = bpy.data.objects.new('Cable', cu); st.col.objects.link(cab); cab.parent = st.raiz


def _exhibicion_ultraligero(st):
    """Maqueta 1:6 del prototipo ULV (SIBO 200-1, resumen ejecutivo DIDA/AMB): ala alta de 8 m con puntas rojas,
    escarapela y 'FANB', estructura de tubos a la vista, dos asientos lado a lado, motor y hélice tripala propulsora,
    tren triciclo y timón rojo con la 'E'. En vitrina de acrílico sobre base negra."""
    k = 1.0 / 6.0
    blanco = mat_simple('Maqueta entelado blanco', (0.78, 0.78, 0.76), 0.45)
    rojo = mat_simple('Maqueta rojo', (0.5, 0.012, 0.02), 0.35)
    amarillo = mat_simple('Maqueta amarillo', (0.8, 0.55, 0.02), 0.35)
    azul = mat_simple('Maqueta azul', (0.01, 0.04, 0.2), 0.35)
    cuero = mat_simple('Maqueta cuero', (0.12, 0.055, 0.025), 0.6)
    madera = mat_simple('Maqueta helice', (0.35, 0.2, 0.08), 0.4)
    motor = mat_simple('Maqueta motor', (0.12, 0.12, 0.13), 0.35, 0.8)
    _, negro, alu = _mats_militar()
    (x0, y0), zt = VITRINA_ULV, 0.62
    # marco de la maqueta: proa (+X) hacia el pasillo, envergadura a lo largo del lado largo de la vitrina
    m = st.sub('Maqueta ULV', (x0, y0, zt + 0.03), math.pi / 2)

    def K(*p):
        return tuple(c * k for c in p)

    def tubo(a, b, r=0.03, mat=None):
        m.tubo('Tubo estructura', K(*a), K(*b), r * k, mat or alu, lados=8)
    # ala (8 m, cuerda 1,25 m) con puntas rojas, escarapela y FANB
    m.caja('Ala', K(1.25, 6.8, 0.14), K(0.0, 0.0, 2.0), blanco, bisel=0.002)
    for lado in (-1, 1):
        m.caja('Punta de ala', K(1.25, 0.6, 0.145), K(0.0, lado * 3.7, 2.0), rojo, bisel=0.002)
    for r, mat in ((0.45, amarillo), (0.32, azul), (0.18, rojo)):
        m.cilindro('Escarapela', r * k, r * k, 0.004, K(0.0, -2.4, 2.075 + (0.45 - r) * 0.02), mat, lados=32)
    fanb = m.texto('FANB', 0.42 * k, K(0.0, 2.4, 2.08), '-Y', negro, _fuente_archivo('arialbd.ttf'))
    fanb.rotation_euler = (0, 0, -math.pi / 2)
    # estructura de tubos: piso de cabina, jaula de asientos, nariz y botalón de cola
    for lado in (-1, 1):
        y = 0.45 * lado
        tubo((1.2, y * 0.6, 0.45), (-0.6, y, 0.45))                     # largueros del piso
        tubo((0.5, y, 0.45), (0.45, y, 1.93))                           # montantes delanteros
        tubo((-0.55, y, 0.45), (-0.5, y, 1.93))                         # montantes traseros
        tubo((0.0, y, 0.48), (0.35, lado * 2.4, 1.93))                  # montantes del ala en V
        tubo((0.0, y, 0.48), (-0.45, lado * 2.4, 1.93))
        tubo((-0.2, y, 0.45), (-0.2, lado * 0.88, 0.2), 0.035)          # patas del tren principal
        m.cilindro('Rueda', 0.2 * k, 0.2 * k, 0.1 * k, K(-0.2, lado * 0.88, 0.2), negro, rot=(math.pi / 2, 0, 0), lados=20)
    tubo((1.2, -0.27, 0.45), (1.6, 0, 0.55)); tubo((1.2, 0.27, 0.45), (1.6, 0, 0.55))
    tubo((1.55, 0, 0.55), (1.5, 0, 0.18), 0.035)                        # tren de nariz
    m.cilindro('Rueda de nariz', 0.17 * k, 0.17 * k, 0.09 * k, K(1.5, 0, 0.17), negro, rot=(math.pi / 2, 0, 0), lados=20)
    sup = lambda x: 1.25 + (x + 0.55) * 0.0408                          # botalón superior: (-0.55, 1.25) -> (-3.0, 1.15)
    inf = lambda x: 0.45 - (x + 0.6) * 0.285                            # botalón inferior: (-0.6, 0.45) -> (-2.95, 1.12)
    tubo((-0.55, 0, sup(-0.55)), (-3.0, 0, sup(-3.0)), 0.045)
    tubo((-0.6, 0, inf(-0.6)), (-2.95, 0, inf(-2.95)), 0.035)
    for x in (-0.9, -1.5, -2.1, -2.7):                                  # celosía (Warren) entre los dos botalones
        tubo((x, 0, sup(x)), (x - 0.3, 0, inf(x - 0.3)))
        tubo((x - 0.3, 0, inf(x - 0.3)), (x - 0.6, 0, sup(x - 0.6)))
    # asientos lado a lado
    for lado in (-1, 1):
        y = 0.27 * lado
        m.caja('Asiento', K(0.5, 0.42, 0.1), K(0.05, y, 0.6), cuero, bisel=0.002)
        respaldo = m.caja('Respaldo', K(0.1, 0.42, 0.65), K(-0.25, y, 0.95), cuero, bisel=0.002)
        respaldo.rotation_euler.y = math.radians(-12)
    # motor detrás de la cabina y hélice tripala propulsora
    m.caja('Motor', K(0.55, 0.5, 0.38), K(-0.8, 0, 1.65), motor, bisel=0.002)
    m.cilindro('Buje', 0.09 * k, 0.09 * k, 0.15 * k, K(-1.12, 0, 1.75), negro, rot=(0, math.pi / 2, 0))
    for i in range(3):
        a = math.radians(90 + i * 120)
        pala = m.caja('Pala', K(0.05, 0.12, 0.78), K(-1.15, math.cos(a) * 0.42, 1.75 + math.sin(a) * 0.42), madera, bisel=0)
        pala.rotation_euler.x = a - math.pi / 2
    # cola: estabilizador 2,6 m y deriva con timón rojo y la 'E'
    m.caja('Estabilizador', K(0.5, 2.6, 0.06), K(-3.0, 0, 1.18), blanco, bisel=0.002)
    m.caja('Deriva', K(0.32, 0.05, 1.2), K(-2.95, 0, 1.8), blanco, bisel=0.002)
    m.caja('Timon', K(0.32, 0.055, 1.2), K(-3.27, 0, 1.8), rojo, bisel=0.002)
    for lado in (-1, 1):
        m.texto('E', 0.32 * k, K(-3.27, lado * 0.03, 2.05), '+Y' if lado > 0 else '-Y', mat_simple('Texto blanco stand', (0.85, 0.85, 0.85), 0.4))
    # base negra y vitrina de acrílico (vidrio delgado: transparente + Fresnel solo en la cara exterior)
    st.caja('Base vitrina', (1.58, 1.23, 0.02), (x0, y0, zt + 0.02), mat_simple('Base negra vitrina', (0.012, 0.012, 0.014), 0.35), bisel=0)
    vidrio = bpy.data.materials.get('Acrilico vitrina')
    if not vidrio:
        vidrio = bpy.data.materials.new('Acrilico vitrina')
        nt, _, out = nodos(vidrio)
        fr = nt.nodes.new('ShaderNodeFresnel'); fr.inputs['IOR'].default_value = 1.49
        tr = nt.nodes.new('ShaderNodeBsdfTransparent'); tr.inputs['Color'].default_value = (0.97, 0.98, 0.98, 1)
        gl = nt.nodes.new('ShaderNodeBsdfGlossy'); gl.inputs['Roughness'].default_value = 0.02
        mx = nt.nodes.new('ShaderNodeMixShader')
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        fac = _mate(nt, 'MULTIPLY', fr.outputs[0], _mate(nt, 'SUBTRACT', 1.0, geo.outputs['Backfacing']))
        unir(nt, fac, mx.inputs['Fac']); unir(nt, tr.outputs[0], mx.inputs[1]); unir(nt, gl.outputs[0], mx.inputs[2])
        unir(nt, mx.outputs[0], out.inputs[0])
    e, L, A, H = 0.006, 1.6, 1.25, 0.62
    for (tam, pos) in (((L, A, e), (x0, y0, zt + H)), ((L, e, H), (x0, y0 - A / 2, zt + H / 2)), ((L, e, H), (x0, y0 + A / 2, zt + H / 2)),
                       ((e, A, H), (x0 - L / 2, y0, zt + H / 2)), ((e, A, H), (x0 + L / 2, y0, zt + H / 2))):
        st.caja('Vitrina', tam, pos, vidrio, bisel=0)


def _exhibicion_juego(st, proy):
    """Cóndor (software de juegos de guerra): mesa táctica digital con el mapa del escenario y estación de trabajo con
    tres monitores con capturas del simulador, delante de la pantalla LED grande."""
    _, negro, alu = _mats_militar()
    escritorio = mat_simple('Escritorio blanco', (0.75, 0.75, 0.74), 0.35)
    x0, y0 = 1.4, 1.0
    st.caja('Mesa tactica', (1.9, 1.15, 0.8), (x0, y0, 0.46), negro)
    st.caja('Marco mesa tactica', (1.96, 1.21, 0.04), (x0, y0, 0.88), alu)
    carta = st.plano('Pantalla mesa tactica', 1.82, 1.07, (x0, y0, 0.902), '-Y', _mat_captura(proy['mesa']))
    carta.data.transform(Matrix.Rotation(-math.pi / 2, 4, 'X'))        # acostada, mirando hacia arriba
    ex, ey = -0.95, -1.6
    st.caja('Escritorio', (1.7, 0.7, 0.04), (ex, ey, 0.8), escritorio)
    for dx in (-0.8, 0.8):
        st.caja('Pata escritorio', (0.05, 0.65, 0.74), (ex + dx, ey, 0.43), escritorio)
    for k, dx in enumerate((-0.55, 0.0, 0.55)):
        giro = (0.35, 0.0, -0.35)[k]
        st.caja('Monitor', (0.56, 0.04, 0.34), (ex + dx, ey + 0.05, 1.12), negro, rot_z=giro)
        pl = st.plano('Imagen monitor', 0.53, 0.31, (ex + dx - math.sin(giro) * 0.026, ey + 0.05 + math.cos(giro) * 0.026, 1.12), '+Y',
                      _mat_captura(proy['monitores'][k]))
        pl.rotation_euler.z = math.pi + giro * st.s
        st.caja('Pie monitor', (0.04, 0.04, 0.2), (ex + dx, ey + 0.03, 0.92), negro)
    st.caja('Teclado', (0.44, 0.15, 0.02), (ex, ey + 0.2, 0.83), negro)
    for dx in (-0.45, 0.45):
        st.cilindro('Asiento operador', 0.24, 0.24, 0.07, (ex + dx, ey + 0.75, 0.55), negro)
        st.cilindro('Columna silla', 0.03, 0.03, 0.45, (ex + dx, ey + 0.75, 0.3), alu)


def _piezas_puesto(piso):
    """Piezas de un puesto del visor (piso de 5,8 x 5 m, paredes, rótulo, mostrador) y su marco:
    (centro, eje x, eje y hacia el pasillo, piezas). Solo las del rectángulo de ESTE puesto (la pared del vecino
    también queda a < 4,5 m del centro)."""
    C = piso.matrix_world.translation.copy()

    def centro(o):
        return sum((o.matrix_world @ Vector(v) for v in o.bound_box), Vector()) / 8
    cerca = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == piso.parent and o is not piso
             and (o.matrix_world.translation.xy - C.xy).length < 4.5]
    fondo = next((o for o in cerca if o.dimensions.x > 5 and o.dimensions.z > 2), None)
    if not fondo:
        return None
    ny = (C - centro(fondo)); ny.z = 0; ny.normalize()
    nx = Vector((ny.y, -ny.x, 0))
    cerca = [o for o in cerca if abs((centro(o) - C).dot(nx)) < 3.0 and abs((centro(o) - C).dot(ny)) < 2.8]
    return C, nx, ny, cerca


def stands_amb():
    pisos = [o for o in bpy.data.objects if o.type == 'MESH' and o.active_material and o.active_material.name == 'Material_158']
    cam = bpy.data.objects.get('Cam_proyectos')
    if not pisos or not cam:
        return
    pcam = cam.matrix_world.translation
    pisos.sort(key=lambda f: (f.matrix_world.translation - pcam).length)
    col = bpy.data.collections.new('Stands AMB'); escena.collection.children.link(col)
    fuente = _fuente()
    condensada = _fuente_archivo('AGENCYB.TTF')
    blanco_txt = mat_simple('Texto blanco stand', (0.85, 0.85, 0.85), 0.4)
    blanco_panel = mat_simple('Panel blanco stand', (0.72, 0.72, 0.71), 0.45)
    alu = mat_simple('Aluminio stand', (0.75, 0.76, 0.78), 0.3, 1.0)
    navy = mat_simple('Letrero azul marino', (0.006, 0.013, 0.035), 0.45)
    dorado = mat_simple('Dorado letrero', (0.62, 0.4, 0.06), 0.35, 0.3)
    moqueta = bpy.data.materials.new('Moqueta stand')
    nt, b, out = nodos(moqueta); unir(nt, b.outputs[0], out.inputs[0])
    b.inputs['Base Color'].default_value = (0.035, 0.036, 0.04, 1); b.inputs['Roughness'].default_value = 0.95
    bu = nt.nodes.new('ShaderNodeBump'); bu.inputs['Strength'].default_value = 0.3
    unir(nt, ruido(nt, nt.nodes.new('ShaderNodeTexCoord').outputs['Object'], 120.0, 2), bu.inputs['Height']); unir(nt, bu.outputs[0], b.inputs['Normal'])
    for proy, piso in zip(PROYECTOS_AMB, pisos[:4]):
        pz = _piezas_puesto(piso)
        if not pz:
            continue
        C, nx, ny, cerca = pz
        # pared lateral del lado más lejano a la cámara de la entrada: desde ahí se ve el interior del puesto.
        s = 1 if (pcam - C).dot(nx) > 0 else -1
        M = Matrix(((nx.x, ny.x, 0, C.x), (nx.y, ny.y, 0, C.y), (0, 0, 1, 0.1), (0, 0, 0, 1)))
        for o in cerca + [piso]:
            bpy.data.objects.remove(o, do_unlink=True)
        st = Stand('Stand ' + proy['titulo'], M, s, col)
        clave, color = proy['clave'], proy['color']
        pared = mat_simple('Pared stand ' + clave, color, 0.5)
        junta = mat_simple('Junta stand ' + clave, tuple(c * 0.45 for c in color), 0.6)
        # piso elevado con perfil de aluminio
        st.caja('Tarima', (5.8, 5.0, 0.06), (0, 0, 0.03), moqueta, bisel=0.003)
        st.caja('Perfil frente', (5.8, 0.02, 0.065), (0, 2.5, 0.033), alu, bisel=0)
        st.caja('Perfil lado', (0.02, 5.0, 0.065), (2.9, 0, 0.033), alu, bisel=0)
        # paredes en L de 3,2 m con juntas de panel cada metro
        H = 3.2
        st.caja('Pared fondo', (5.8, 0.1, H), (0, -2.45, 0.06 + H / 2), pared)
        st.caja('Pared lateral', (0.1, 4.9, H), (-2.85, 0.05, 0.06 + H / 2), pared)
        for k in range(1, 6):
            st.caja('Junta', (0.008, 0.004, H - 0.05), (-2.9 + k * 0.97, -2.398, 0.06 + H / 2), junta, bisel=0)
        for k in range(1, 5):
            st.caja('Junta', (0.004, 0.008, H - 0.05), (-2.798, -2.5 + k * 1.0, 0.06 + H / 2), junta, bisel=0)
        # torre con remate azul marino (mismo estilo del letrero): AMB, línea dorada y el nombre corto
        st.caja('Torre', (1.1, 1.1, 4.4), (1.55, -1.85, 0.06 + 2.2), pared)
        st.caja('Remate torre', (1.14, 1.14, 0.9), (1.55, -1.85, 0.06 + 3.95), navy)
        st.texto('AMB', 0.42, (1.55, -1.276, 4.2), '+Y', blanco_txt, condensada)
        st.caja('Linea dorada torre', (0.7, 0.004, 0.008), (1.55, -1.278, 4.0), dorado, bisel=0)
        st.texto(proy['corto'], _tam_texto(proy['corto'], 0.95, 0.17, em=0.45), (1.55, -1.276, 3.76), '+Y', blanco_txt, condensada)
        st.texto('AMB', 0.42, (2.122, -1.85, 4.2), '+X', blanco_txt, condensada)
        # letrero de identificación arriba de la pared de fondo
        letrero(st, proy['titulo'], proy['sub'])
        # pantalla del fondo: el borde superior justo debajo del letrero
        tw, th = proy['tv']
        tz = PANTALLA_TOPE - th / 2
        st.caja('Marco TV', (tw + 0.05, 0.05, th + 0.05), (-0.9, -2.37, tz), mat_simple('Negro mate', (0.015, 0.015, 0.016), 0.5))
        st.plano('Imagen TV', tw, th, (-0.9, -2.343, tz), '+Y', _mat_captura(proy['pantalla']))
        # caja de luz con la gráfica del proyecto en la pared lateral
        cw, ch = proy['caja_luz']
        cz = 1.5 if ch > 2 else 1.62
        st.caja('Marco caja de luz', (0.06, cw + 0.1, ch + 0.1), (-2.77, -0.55, cz), alu)
        st.plano('Grafica caja de luz', cw, ch, (-2.739, -0.55, cz), '+X', _mat_impresion(proy['caja_img']))
        # mostrador con el nombre
        st.caja('Mostrador', (1.3, 0.55, 1.0), (-1.55, 1.65, 0.56), pared)
        st.caja('Tope mostrador', (1.36, 0.6, 0.03), (-1.55, 1.65, 1.075), blanco_panel)
        st.texto(proy['mostrador'], _tam_texto(proy['mostrador'], 1.15, 0.13), (-1.55, 1.93, 0.8), '+Y', blanco_txt, fuente)
        st.caja('Linea dorada mostrador', (0.8, 0.004, 0.007), (-1.55, 1.926, 0.63), dorado, bisel=0)
        st.texto(UNIDAD_LETRERO, 0.042, (-1.55, 1.93, 0.56), '+Y', dorado, fuente, espacio=1.2)
        # base de exhibición de la maqueta, en el centro del stand, con su luz: dos reflectores dirigidos y una luz
        # oculta en el techo de la vitrina (como en un museo)
        if clave == 'ultraligero':
            vx, vy = VITRINA_ULV
            st.caja('Base exhibicion', (1.9, 1.5, 0.56), (vx, vy, 0.34), pared)
            st.caja('Tope base', (1.92, 1.52, 0.02), (vx, vy, 0.63), blanco_panel, bisel=0)
            st.texto('Maqueta a escala 1:6 · Prototipo SIBO 200-1', 0.055, (vx, vy + 0.76, 0.4), '+Y', blanco_txt, fuente)
            st.foco((vx, -2.15, H + 0.12), (vx, vy, 1.0), 12.0)
            st.foco((-2.55, vy, H + 0.12), (vx, vy, 1.0), 10.0)
            ld = bpy.data.lights.new('Luz vitrina', 'AREA'); ld.energy = 0.6; ld.size = 1.2; ld.color = (1.0, 0.97, 0.92)
            lv = bpy.data.objects.new('Luz vitrina', ld); col.objects.link(lv); lv.parent = st.raiz
            lv.location = st.P(vx, vy, 0.62 + 0.6); lv.visible_camera = False
        {'igla': _exhibicion_igla, 'mecanismo': _exhibicion_mecanismo, 'juego': _exhibicion_juego}.get(
            clave, lambda st_, proy_: _exhibicion_ultraligero(st_))(st, proy)
        # reflectores de brazo sobre las paredes
        for x in (-1.6, 0.0):
            st.foco((x, -2.15, H + 0.12), (x, -1.2, 1.4), 5.0)
        st.foco((-2.55, -1.0, H + 0.12), (-1.8, -0.6, 1.3), 4.0)
        if clave != 'ultraligero':                     # (el del ULV ya tiene sus reflectores sobre la maqueta)
            st.foco((-2.55, 1.2, H + 0.12), (1.2, 1.1, 0.7), 6.0)
        print('Stand listo:', proy['titulo'])
    # puestos restantes del visor ("PROYECTO n"): se quitan (son 4 proyectos) o quedan como expositores genéricos
    if QUITAR_PUESTOS_SOBRANTES:
        n = 0
        for piso in pisos[4:]:
            pz = _piezas_puesto(piso)
            for o in (pz[3] if pz else []) + [piso]:
                bpy.data.objects.remove(o, do_unlink=True)
            n += 1
        print('Puestos sobrantes quitados:', n)
    for nombre, valores in (('Material_20', ((0.72, 0.72, 0.71), 0.5)), ('Material_138', ((0.01, 0.045, 0.19), 0.45)),
                            ('Material_158', ((0.035, 0.036, 0.04), 0.95)), ('Material_161', ((0.72, 0.72, 0.71), 0.35))):
        mm = bpy.data.materials.get(nombre)
        bb = mm and next((n for n in mm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bb and not bb.inputs['Base Color'].links:
            bb.inputs['Base Color'].default_value = valores[0] + (1,); bb.inputs['Roughness'].default_value = valores[1]
    # una cámara por stand para la propuesta (tres cuartos desde arriba del pasillo, lado abierto del puesto)
    for proy in PROYECTOS_AMB:
        r = bpy.data.objects.get('Stand ' + proy['titulo'])
        if not r:
            continue
        s = r.get('reflejo', 1); M = r.matrix_world
        cd = bpy.data.cameras.new('stand_' + proy['clave']); cd.sensor_fit = 'HORIZONTAL'; cd.lens = 19; cd.clip_start = 0.1; cd.clip_end = 60000
        c = bpy.data.objects.new('Cam_stand_' + proy['clave'], cd); escena.collection.objects.link(c)
        c.location = M @ Vector((2.6 * s, 7.0, 4.7))
        c.rotation_euler = (M @ Vector((-0.4 * s, -0.6, 0.9)) - c.location).to_track_quat('-Z', 'Y').to_euler()
        c['stand'] = r.name; c['resolucion'] = (2560, 1440)      # vista individual: renderizar.py oculta los otros
        EXPOSICION_CAMARA['stand_' + proy['clave']] = 4.2
    # vistas de a dos: 'stands' (los dos de Igla-S) y 'stands2' (Cóndor y ultraligero)
    for nombre_cam, (i, j) in (('stands', (0, 2)), ('stands2', (1, 3))):
        a = bpy.data.objects.get('Stand ' + PROYECTOS_AMB[i]['titulo']); b2 = bpy.data.objects.get('Stand ' + PROYECTOS_AMB[j]['titulo'])
        if not (a and b2):
            continue
        pa, pb = a.matrix_world.translation, b2.matrix_world.translation
        fila = (pb - pa).normalized(); frente = a.matrix_world.to_3x3() @ Vector((0, 1, 0))
        cd = bpy.data.cameras.new(nombre_cam); cd.sensor_fit = 'HORIZONTAL'; cd.lens = 20; cd.clip_start = 0.1; cd.clip_end = 60000
        c = bpy.data.objects.new('Cam_' + nombre_cam, cd); escena.collection.objects.link(c)
        c.location = pa + frente * 7.5 + fila * -1.5 + Vector((0, 0, 4.6))
        c.rotation_euler = (pb * 0.35 + pa * 0.65 + Vector((0, 0, 1.0)) - c.location).to_track_quat('-Z', 'Y').to_euler()
        EXPOSICION_CAMARA[nombre_cam] = 4.2
    vistas_presentacion()
    recorrido_stands()


def _marcos_stands():
    """Raíces de los 4 stands, puntos del pasillo y ejes: M1 (entre la fila 1), M2 (entre la fila 2), G (centro),
    d (dirección del pasillo desde la entrada) y L(clave, x, y, z) para pasar del marco de un stand al mundo."""
    st = {p['clave']: bpy.data.objects.get('Stand ' + p['titulo']) for p in PROYECTOS_AMB}
    if not all(st.values()):
        return None
    pos = {k: r.matrix_world.translation.copy() for k, r in st.items()}
    M1 = (pos['igla'] + pos['juego']) / 2; M2 = (pos['mecanismo'] + pos['ultraligero']) / 2
    d = M2 - M1; d.z = 0; d.normalize()
    G = (M1 + M2) / 2

    def L(clave, x, y, z):
        r = st[clave]
        return r.matrix_world @ Vector((x * r.get('reflejo', 1), y, z))
    return M1, M2, G, d, L


def _camara(nombre, pos, mira, lente, res=(2560, 1440), ev=4.2, stand=None):
    cd = bpy.data.cameras.new(nombre); cd.sensor_fit = 'HORIZONTAL'; cd.lens = lente; cd.clip_start = 0.05; cd.clip_end = 60000
    c = bpy.data.objects.new('Cam_' + nombre, cd); escena.collection.objects.link(c)
    c.location = pos; c.rotation_euler = (mira - pos).to_track_quat('-Z', 'Y').to_euler()
    c['resolucion'] = res
    if stand:
        c['stand'] = stand                  # vista individual: renderizar.py oculta los otros stands
    EXPOSICION_CAMARA[nombre] = ev
    return c


def vistas_presentacion():
    """Vistas para la propuesta (2K): general de los 4 stands, de frente a la altura de una persona y detalle de cada
    exhibición. Las posiciones de frente/detalle están en el marco de cada stand (+Y hacia el pasillo)."""
    m = _marcos_stands()
    if not m:
        return
    M1, M2, G, d, L = m
    Z = Vector((0, 0, 1))
    _camara('stands_general', M1 - d * 8.0 + Z * 6.5, G + Z * 0.5, 17)
    for p in PROYECTOS_AMB:
        k, raiz = p['clave'], 'Stand ' + p['titulo']
        _camara('frente_' + k, L(k, 0.6, 6.0, 1.65), L(k, -0.3, -0.9, 1.35), 20, stand=raiz)
        # lateral: desde la esquina abierta del stand (el lado sin pared), a la altura de una persona
        _camara('lateral_' + k, L(k, 6.0, 3.4, 1.7), L(k, -0.7, -0.6, 1.25), 20, stand=raiz)
    detalles = {'igla': ((2.4, 3.0, 1.75), (0.45, 0.85, 1.3), 30),           # lanzador en su base, pantalla detrás
                'mecanismo': ((2.7, 3.1, 1.6), (1.25, 0.85, 0.9), 30),       # plataforma móvil con el lanzador
                'juego': ((2.6, 3.4, 2.1), (0.4, -0.6, 1.2), 24),            # mesa táctica, monitores y pantalla
                'ultraligero': ((VITRINA_ULV[0] + 1.6, VITRINA_ULV[1] + 2.5, 1.65), (VITRINA_ULV[0], VITRINA_ULV[1], 0.95), 35)}
    for k, (pos, mira, lente) in detalles.items():
        raiz = 'Stand ' + next(p['titulo'] for p in PROYECTOS_AMB if p['clave'] == k)
        _camara('detalle_' + k, L(k, *pos), L(k, *mira), lente, stand=raiz)


RECORRIDO_FPS, RECORRIDO_SEG = 30, 30


def recorrido_stands():
    """Cámara animada 'Recorrido stands' (sin el prefijo Cam_: no entra en los renders fijos): entra desde la puerta
    del hangar, recorre el pasillo a la altura de una persona mirando cada stand en orden y sube para la vista final.
    La mira es un Empty con restricción 'Track To'; las claves usan Bézier, así arranca y frena suave."""
    m = _marcos_stands()
    if not m:
        return
    M1, M2, G, d, L = m
    Z = Vector((0, 0, 1))

    def adentro(k):
        return L(k, -0.2, -0.4, 1.25)                   # centro del stand, a la altura de las pantallas
    camino = [                                          # (segundo, posición de la cámara)
        (0.0, M1 - d * 9.0 + Z * 4.0),
        (4.0, M1 - d * 4.5 + Z * 2.0),
        (8.0, M1 - d * 1.2 + Z * 1.65),
        (12.0, M1 + d * 1.0 + Z * 1.65),
        (16.5, M2 - d * 1.2 + Z * 1.65),
        (20.5, M2 + d * 1.0 + Z * 1.65),
        (24.0, M2 + d * 0.5 + Z * 3.5),                 # sube por encima de las paredes (3,26 m)...
        (30.0, M1 - d * 7.5 + Z * 6.0),                 # ...y se aleja hacia la entrada: vista general final
    ]
    # Punto al que mira. Entre un stand y el del otro lado del pasillo la mira pasa POR DELANTE (pasillo adelante),
    # cerca y bajo, para que se vean los stands siguientes y no el fondo vacío del hangar; en línea recta de un lado
    # al otro pasaría debajo de la cámara y esta miraría al piso. Al final mira siempre hacia adelante (los stands
    # están abiertos hacia la entrada; desde el fondo se verían sus paredes laterales).
    miradas = [
        (0.0, G + Z * 0.8),
        (4.0, M1 + d * 1.0 + Z * 1.2),
        (8.0, adentro('igla')),
        (10.0, M1 + d * 3.0 + Z * 1.4),
        (12.0, adentro('juego')),
        (14.25, M2 + d * 1.0 + Z * 1.3),
        (16.5, adentro('mecanismo')),
        (18.5, M2 + d * 2.5 + Z * 1.1),
        (20.5, adentro('ultraligero')),
        (24.0, adentro('ultraligero')),                # mientras sube sigue mirando la maqueta
        (30.0, G + d * 0.5 + Z * 0.5),
    ]
    cd = bpy.data.cameras.new('recorrido'); cd.sensor_fit = 'HORIZONTAL'; cd.lens = 20; cd.clip_start = 0.05; cd.clip_end = 60000
    cam = bpy.data.objects.new('Recorrido stands', cd); escena.collection.objects.link(cam)
    mira = bpy.data.objects.new('Recorrido mira', None); escena.collection.objects.link(mira)
    tr = cam.constraints.new('TRACK_TO'); tr.target = mira; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
    for ob, claves in ((cam, camino), (mira, miradas)):
        for seg, p in claves:
            ob.location = p; ob.keyframe_insert('location', frame=1 + round(seg * RECORRIDO_FPS))
    for ob in (cam, mira):
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'; kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    cam['exposicion'] = 4.2; cam['resolucion'] = (2560, 1440)
    escena.render.fps = RECORRIDO_FPS
    escena.frame_start, escena.frame_end = 1, 1 + RECORRIDO_FPS * RECORRIDO_SEG
    print('Recorrido de los stands:', escena.frame_end, 'cuadros a', RECORRIDO_FPS, 'fps')


# ============================================================================ hangar por dentro
def luces_hangar():
    """Lámparas industriales (campana LED) en dos filas bajo la bóveda; con 3 luces de 1 W el interior salía negro."""
    h = bpy.data.objects.get('hangar')
    if not h:
        return
    bov = next((o for o in h.children_recursive if o.type == 'MESH' and o.material_slots and o.material_slots[0].material
                and o.material_slots[0].material.name == 'Lamina hangar'), None)
    if not bov:
        return
    P = np.array([(bov.matrix_world @ v.co)[:] for v in bov.data.vertices])
    alto = P[:, 2].max()
    # rectángulo de área mínima en planta (no hace falta saber cómo viene girado el hangar)
    mejor = None
    for gr in range(0, 180):
        a = math.radians(gr); e = np.array([math.cos(a), math.sin(a)]); q = np.array([-e[1], e[0]])
        u, w = P[:, :2] @ e, P[:, :2] @ q
        area = np.ptp(u) * np.ptp(w)
        if mejor is None or area < mejor[0]:
            mejor = (area, e, q, u, w)
    _, e, q, u, w = mejor
    if np.ptp(w) > np.ptp(u):
        e, q, u, w = q, e, w, u
    eje, perp = Vector((e[0], e[1], 0)), Vector((q[0], q[1], 0))
    largo, ancho = float(np.ptp(u)), float(np.ptp(w))
    c2 = e * (u.max() + u.min()) / 2 + q * (w.max() + w.min()) / 2
    centro = Vector((c2[0], c2[1], 0))
    for o in [o for o in bpy.data.objects if o.type == 'LIGHT' and o.data.type == 'POINT' and o.data.energy < 5]:
        bpy.data.objects.remove(o, do_unlink=True)
    mat_lamp = bpy.data.materials.new('Lampara LED')
    nt, bsdf, out = nodos(mat_lamp)
    em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (1.0, 0.95, 0.88, 1); em.inputs['Strength'].default_value = 25
    unir(nt, em.outputs[0], out.inputs[0])
    carcasa = mat_simple('Carcasa lampara', (0.12, 0.12, 0.13), 0.4, 0.8)
    filas, por_fila = 2, max(3, int(largo / 9))
    n = 0
    for f in range(filas):
        off = (f - (filas - 1) / 2) * ancho * 0.28
        for k in range(por_fila):
            u = (k + 0.5) / por_fila - 0.5
            p = centro + eje * u * largo * 0.86 + perp * off
            p.z = alto * 0.78
            ld = bpy.data.lights.new(f'Campana LED {n}', 'SPOT')
            ld.energy = 18; ld.spot_size = math.radians(120); ld.spot_blend = 0.6; ld.shadow_soft_size = 0.22
            ld.color = (1.0, 0.95, 0.88)
            lo = bpy.data.objects.new(f'Campana LED {n}', ld); lo.location = p; escena.collection.objects.link(lo)
            # pantalla de la lámpara (visible)
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=False, segments=20, radius1=0.24, radius2=0.12, depth=0.3)
            disco = bmesh.ops.create_circle(bm, cap_ends=True, segments=20, radius=0.2)
            bmesh.ops.translate(bm, vec=(0, 0, -0.149), verts=disco['verts'])
            for fc in bm.faces:
                fc.material_index = 1 if fc.calc_center_median().z < -0.14 and len(fc.verts) > 4 else 0
            me = bpy.data.meshes.new('campana'); bm.to_mesh(me); bm.free()
            me.materials.append(carcasa); me.materials.append(mat_lamp)
            ob = bpy.data.objects.new(f'Lampara {n}', me); ob.location = p + Vector((0, 0, 0.17)); escena.collection.objects.link(ob)
            ob.visible_shadow = False
            n += 1
    print('Lámparas en el hangar:', n)


# ============================================================================ cámara, exposición y composición
def calibrar_exposicion():
    """AgX con la irradiancia real del sol del HDR: se fija la exposición para que un concreto de albedo 0,35
    a pleno sol quede cerca del gris medio-alto, como en una foto bien expuesta."""
    global EXPOSICION_BASE
    sol = bpy.data.objects.get('Sol')
    E = sol.data.energy if sol else 4.0
    # radiancia de un difuso de albedo a bajo el sol (+ ~30 % de cielo): a·E·(cosθ·1.3)/π
    cos_t = 0.79
    L = 0.35 * E * cos_t * 1.3 / math.pi
    objetivo = 0.36                     # valor lineal que AgX lleva a un gris claro de foto
    EXPOSICION_BASE = round(math.log2(objetivo / L), 2)
    escena['exposicion_base'] = EXPOSICION_BASE
    for nombre, ev in EXPOSICION_CAMARA.items():
        cam = bpy.data.objects.get('Cam_' + nombre)
        if cam:
            cam['exposicion'] = ev
    print('Exposición base:', EXPOSICION_BASE, 'EV (sol', round(E, 2), ')')


def postproceso(escena):
    """Composición de lente: brillo suave en altas luces, aberración cromática leve y viñeta."""
    escena.use_nodes = True
    nt = escena.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new('CompositorNodeRLayers')
    comp = nt.nodes.new('CompositorNodeComposite')
    ultimo = rl.outputs['Image']
    gl = nt.nodes.new('CompositorNodeGlare')            # API de Blender 4.5 (entradas en vez de propiedades)
    gl.glare_type = 'FOG_GLOW'; gl.quality = 'HIGH'
    gl.inputs['Threshold'].default_value = 1.4
    gl.inputs['Strength'].default_value = 0.1
    gl.inputs['Size'].default_value = 0.6
    unir(nt, ultimo, gl.inputs['Image']); ultimo = gl.outputs['Image']
    ld = nt.nodes.new('CompositorNodeLensdist')
    ld.inputs['Dispersion'].default_value = 0.01        # aberración cromática leve en los bordes
    ld.inputs['Distortion'].default_value = 0.0
    ld.inputs['Fit'].default_value = True
    unir(nt, ultimo, ld.inputs['Image']); ultimo = ld.outputs['Image']
    # viñeta: elipse difuminada -> multiplicar
    el = nt.nodes.new('CompositorNodeEllipseMask')
    el.inputs['Size'].default_value = (1.15, 1.25)
    bl = nt.nodes.new('CompositorNodeBlur')
    bl.inputs['Size'].default_value = (420, 420)
    unir(nt, el.outputs['Mask'], bl.inputs['Image'])
    mr = nt.nodes.new('CompositorNodeMapRange')
    mr.inputs['From Min'].default_value = 0; mr.inputs['From Max'].default_value = 1
    mr.inputs['To Min'].default_value = 0.8; mr.inputs['To Max'].default_value = 1.0; mr.use_clamp = True
    unir(nt, bl.outputs['Image'], mr.inputs['Value'])
    mul = nt.nodes.new('CompositorNodeMixRGB'); mul.blend_type = 'MULTIPLY'; mul.inputs['Fac'].default_value = 1.0
    unir(nt, ultimo, mul.inputs[1]); unir(nt, mr.outputs['Value'], mul.inputs[2])
    unir(nt, mul.outputs['Image'], comp.inputs['Image'])


# ============================================================================ todo
def aplicar_realismo():
    relieve = terreno()
    pistas_y_plataforma()
    mat_grama_realista()
    copas_densas()
    arboleda(relieve)
    palmas()
    palmas_abanico()
    jardines()
    grama_3d()
    luces_hangar()
    stands_amb()
    librea_da40()
    if 'acto_protocolar' in globals():      # tarima con toldo, autoridades y parada (acto_blender.py)
        acto_protocolar()
    # bruma en todos los materiales (las pinturas recortadas del piso se saltan solas)
    for m in list(bpy.data.materials):
        con_bruma(m)
    calibrar_exposicion()
