"""Servidor local mínimo que recibe la escena exportada desde el navegador y la guarda en ../blender/.
Uso: python recibir_exportacion.py   (escucha solo en 127.0.0.1:8766)"""
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

DESTINO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'blender')
os.makedirs(DESTINO, exist_ok=True)


class Receptor(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:8765')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_POST(self):
        nombre = self.path.rsplit('/', 1)[-1]
        if not re.fullmatch(r'[\w.-]+\.(glb|json)', nombre):
            self.send_response(400); self._cors(); self.end_headers(); return
        n = int(self.headers.get('Content-Length', 0))
        datos = self.rfile.read(n)
        with open(os.path.join(DESTINO, nombre), 'wb') as f:
            f.write(datos)
        self.send_response(200); self._cors(); self.end_headers()
        self.wfile.write(f'guardado {nombre} ({len(datos)} bytes)'.encode())


HTTPServer(('127.0.0.1', 8766), Receptor).serve_forever()
