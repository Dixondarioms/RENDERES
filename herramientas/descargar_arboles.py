"""Descarga modelos de árboles de Poly Haven (licencia CC0) en formato glTF 1k a assets/arboles/<nombre>/."""
import json
import os
import sys
import urllib.request

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
H = {'User-Agent': 'render-feria/1.0'}


def bajar(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=300).read()


for nombre in sys.argv[1:]:
    info = json.loads(bajar('https://api.polyhaven.com/files/' + nombre))['gltf']['1k']['gltf']
    destino = os.path.join(RAIZ, 'assets', 'arboles', nombre)
    os.makedirs(destino, exist_ok=True)
    archivos = {os.path.basename(info['url']): info['url'], **{k: v['url'] for k, v in info['include'].items()}}
    for rel, url in archivos.items():
        ruta = os.path.normpath(os.path.join(destino, rel))
        assert ruta.startswith(destino)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, 'wb') as f:
            f.write(bajar(url))
    print(nombre, 'listo:', len(archivos), 'archivos')
