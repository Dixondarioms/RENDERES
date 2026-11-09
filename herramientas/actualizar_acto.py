"""Rehace solo el acto (tarima con toldo, autoridades y parada) dentro de un blender/feria.blend ya armado, sin volver
a armar toda la escena (útil si la PC no tiene memoria para Armar_escena.bat o para probar cambios de acto_blender.py).

Uso (desde la carpeta del proyecto):
  blender.exe -b blender/feria.blend -P herramientas/actualizar_acto.py
"""
import json
import os
import sys

import bpy

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DIR_B = os.path.join(RAIZ, 'blender')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
DATOS = json.load(open(os.path.join(DIR_B, 'escena.json'), encoding='utf-8'))
escena = bpy.context.scene

# Funciones de realismo (bruma) y del acto
exec(open(os.path.join(RAIZ, 'herramientas', 'realismo_blender.py'), encoding='utf-8').read())
exec(open(os.path.join(RAIZ, 'herramientas', 'acto_blender.py'), encoding='utf-8').read())

# Lo que había antes: sillas de la tribuna vieja, personas del visor y un acto anterior
for nombre in ('Sillas', 'Personas', 'Acto protocolar'):
    col = bpy.data.collections.get(nombre)
    if col:
        for o in list(col.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(col)
for me in list(bpy.data.meshes):
    if me.users == 0:
        bpy.data.meshes.remove(me)

acto_protocolar()
for m in list(bpy.data.materials):
    con_bruma(m)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(DIR_B, 'feria.blend'))
print('Acto actualizado en', os.path.join(DIR_B, 'feria.blend'))
