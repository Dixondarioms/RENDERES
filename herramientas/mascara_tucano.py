"""Genera la máscara de pintura del Tucano (blanco = superficie pintada, negro = piezas que conservan su color).

La textura original trae el esquema azul/amarillo de la FAB. Se marcan como 'pintura' los colores saturados
y, con un cierre morfológico, las franjas blancas, letras y escarapelas que quedan dentro de ellos.
Uso: python -I herramientas/mascara_tucano.py
"""
import os
from PIL import Image, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, 'assets', 'aeronaves', 'tucano', 'texturas')

im = Image.open(os.path.join(CARPETA, 'Diffuse.jpg')).convert('RGB')
hsv = im.convert('HSV')
h, s, v = hsv.split()
# pintura = colores saturados o el gris medio de la panza/raíz de las alas (el fondo sin usar da igual)
sat = s.point(lambda x: 255 if x > 90 else 0)
gris_medio = Image.eval(v, lambda x: 255 if 100 <= x <= 155 else 0)
poco_sat = Image.eval(s, lambda x: 255 if x < 40 else 0)
from PIL import ImageChops
mascara = ImageChops.lighter(sat, ImageChops.multiply(gris_medio, poco_sat))
# cierre: dilatar y luego erosionar para absorber franjas blancas y letras dentro de la pintura
for tam in (9, 9, 9):
    mascara = mascara.filter(ImageFilter.MaxFilter(tam))
for tam in (9, 9, 9):
    mascara = mascara.filter(ImageFilter.MinFilter(tam))
mascara = mascara.filter(ImageFilter.GaussianBlur(1.5))
mascara.save(os.path.join(CARPETA, 'Mascara_pintura.png'))
mascara.resize((768, 768)).save(os.path.join(CARPETA, 'Mascara_pintura_peq.png'))
# suciedad: cociente entre la versión sucia y la limpia (1 = limpio, menor = sucio)
limpio = im.convert('L')
sucio = Image.open(os.path.join(CARPETA, 'Dirty.jpg')).convert('L')
suc = Image.new('L', im.size)
pl, ps = limpio.load(), sucio.load()
pr = suc.load()
for y in range(im.size[1]):
    for x in range(im.size[0]):
        a = pl[x, y]
        pr[x, y] = 255 if a < 8 else max(0, min(255, int(255 * ps[x, y] / a)))
suc.save(os.path.join(CARPETA, 'Suciedad.png'))
suc.resize((512, 512)).save(os.path.join(CARPETA, 'Suciedad_peq.png'))
print('listo', mascara.size)
