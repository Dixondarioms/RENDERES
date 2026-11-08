"""Cambia la cola del C-130: borra el caballo y la matrícula extranjera y pone la bandera de Venezuela y un número AMB.

Lee las texturas originales extraídas del .glb (assets/aeronaves/c130/texturas_originales/img1.png e img5.png)
y escribe img1_amb.png e img5_amb.png en assets/aeronaves/c130/texturas/.
img5 es el lado izquierdo (letras normales); img1 el derecho (letras en espejo).
Uso: python -I herramientas/matricula_c130.py [NUMERO]
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG = os.path.join(RAIZ, 'assets', 'aeronaves', 'c130', 'texturas_originales')
DEST = os.path.join(RAIZ, 'assets', 'aeronaves', 'c130', 'texturas')
NUMERO = sys.argv[1] if len(sys.argv) > 1 else '4951'
ZONA = (770, 780, 960, 965)          # caja (x0, y0, x1, y1) del caballo y la matrícula en la textura de 1024 px
CENTRO_X = 862                       # eje de la deriva donde se centran bandera y número


def borrar_marcas(im):
    """Rellena lo negro de la zona con el color del camuflaje más cercano (bordes nítidos, como las manchas)."""
    a = np.asarray(im.convert('RGB')).astype(np.float32)
    x0, y0, x1, y1 = ZONA
    sub = a[y0:y1, x0:x1].copy()
    hueco = sub.max(axis=2) < 45
    # ensanchar 2 px para quitar el borde suavizado de las letras
    for _ in range(2):
        h = hueco.copy()
        h[1:] |= hueco[:-1]; h[:-1] |= hueco[1:]; h[:, 1:] |= hueco[:, :-1]; h[:, :-1] |= hueco[:, 1:]
        hueco = h
    lleno = ~hueco
    while hueco.any():
        nuevo = np.zeros_like(sub); cuenta = np.zeros(hueco.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            vec = np.roll(lleno, (dy, dx), axis=(0, 1)); col = np.roll(sub, (dy, dx), axis=(0, 1))
            nuevo += col * vec[..., None]; cuenta += vec
        frontera = hueco & (cuenta > 0)
        sub[frontera] = nuevo[frontera] / cuenta[frontera][:, None]
        lleno |= frontera; hueco &= ~frontera
    a[y0:y1, x0:x1] = sub
    out = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    # suavizar solo el relleno para que no se note el corte
    suave = out.crop(ZONA).filter(ImageFilter.GaussianBlur(1.2))
    out.paste(suave, ZONA[:2])
    return out


def estrella(dib, cx, cy, r, color):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    dib.polygon(pts, fill=color)


def calcomania():
    """Bandera de Venezuela (con el arco de 8 estrellas) y el número debajo, en una capa transparente."""
    an, al = 190, 175
    capa = Image.new('RGBA', (an * 4, al * 4), (0, 0, 0, 0))   # se dibuja a 4x y se reduce (bordes limpios)
    d = ImageDraw.Draw(capa)
    fw, fh = 112 * 4, 74 * 4
    fx = (capa.width - fw) // 2; fy = 8 * 4
    franja = fh / 3
    for k, col in enumerate(((247, 200, 20), (0, 36, 125), (207, 20, 43))):
        d.rectangle((fx, fy + k * franja, fx + fw, fy + (k + 1) * franja), fill=col + (255,))
    cx, cy = fx + fw / 2, fy + franja * 1.95
    radio = franja * 1.05
    for i in range(8):
        ang = math.radians(-160 + i * (140 / 7))
        estrella(d, cx + radio * math.cos(ang), cy + radio * math.sin(ang), franja * 0.13, (255, 255, 255, 255))
    fuente = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 40 * 4)
    caja = d.textbbox((0, 0), NUMERO, font=fuente)
    d.text(((capa.width - (caja[2] - caja[0])) / 2 - caja[0], fy + fh + 30 * 4), NUMERO, font=fuente, fill=(8, 8, 8, 255))
    return capa.resize((an, al), Image.LANCZOS)


def aplicar(nombre, espejo):
    im = borrar_marcas(Image.open(os.path.join(ORIG, nombre)))
    capa = calcomania()
    if espejo:
        capa = capa.transpose(Image.FLIP_LEFT_RIGHT)
    pos = (CENTRO_X - capa.width // 2, 802)
    base = im.convert('RGBA'); base.alpha_composite(capa, pos)
    os.makedirs(DEST, exist_ok=True)
    salida = os.path.join(DEST, nombre.replace('.png', '_amb.png'))
    base.convert('RGB').save(salida)
    base.convert('RGB').crop((700, 640, 1024, 1024)).save(salida.replace('.png', '_recorte.png'))
    print('listo', salida)


aplicar('img5.png', espejo=False)
aplicar('img1.png', espejo=True)
