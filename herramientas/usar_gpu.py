"""Activa la tarjeta gráfica para Cycles si hay una disponible (NVIDIA, AMD, Intel o Apple); si no, deja el procesador."""
import bpy


def activar_gpu(escena):
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for tipo in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
        try:
            prefs.compute_device_type = tipo
        except TypeError:
            continue
        prefs.refresh_devices()
        gpus = [d for d in prefs.devices if d.type == tipo]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == tipo
            escena.cycles.device = 'GPU'
            print('Render con tarjeta gráfica:', tipo, ', '.join(d.name for d in gpus))
            return True
    escena.cycles.device = 'CPU'
    print('No se encontró tarjeta gráfica compatible: render con el procesador')
    return False
