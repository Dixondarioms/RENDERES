# Render del Acto Central — 106 aniversario AMB y 34 años del 27N92

Render 3D de la plataforma del Grupo de Entrenamiento Aéreo N°19 "Nido del Cóndor" y del edificio del SAAG,
Base Aérea Escuela "Mariscal Sucre", Maracay, para mostrar cómo se verá el acto del 27-11-2026.

## Qué se necesita en la PC nueva

1. **Git con Git LFS** (Git para Windows ya trae LFS): https://git-scm.com/download/win
2. **Blender 4.5 LTS**: https://www.blender.org/download/lts/
   Sirve instalado o portable. Si es portable, déjelo en `Documentos\Blender\blender-4.5...\`;
   los .bat lo encuentran solos.
3. **Python 3** (solo para el visor web y los scripts de texturas): https://www.python.org/downloads/

## Bajar el proyecto

```bash
git lfs install
git clone https://github.com/Dixondarioms/RENDERES.git
```

## Trabajar

| Archivo | Para qué |
|---|---|
| `Armar_escena.bat` | Arma `blender\feria.blend` (unos 10 min) y saca imágenes de prueba en `blender\renders\previa_*.png`. Hay que correrlo una vez al bajar el proyecto y cada vez que se cambien los scripts. |
| `Abrir_en_Blender.bat` | Abre la escena en Blender para verla o moverla a mano. |
| `Renderizar.bat` | Renders finales en alta calidad. Usa la tarjeta gráfica si hay (NVIDIA, AMD o Intel). |
| `Abrir_render.bat` | Abre el visor 3D en el navegador (versión web, más simple). |

Ejemplos de `Renderizar.bat` (en una ventana de comandos dentro de la carpeta):

```bash
Renderizar.bat panoramica
```

```bash
Renderizar.bat acto tribuna hercules --muestras 512
```

Vistas disponibles: `panoramica`, `aerea`, `feria`, `acto`, `tribuna`, `hangar`, `porton`, `proyectos`,
`tucanos`, `hercules`, `carretera`, `planta`. Las imágenes quedan en `blender\renders\render_<vista>.png`.
La panorámica sale a 2880 × 1200 y las demás a 1920 × 1080.

## Cómo está armado

- `index.html` es el visor 3D (three.js). De ahí se exportó `blender\escena.glb`: terreno, vías, hangar, gradas, tribuna y aviones hechos a mano.
- `herramientas\armar_blender.py` importa esa escena en Blender y pone sol, cielo, cámaras y calidad de render.
- `herramientas\mejoras_blender.py` mejora lo importado: concreto de la plataforma, marcas, edificios del SAAG y vecinos, árboles reales, hangar, y los aviones descargados:
  - **T-27 Tucano** con camuflaje AMB (arena, verde y verde oscuro), bandera y distintivo en la cola.
  - **C-130 Hércules** en lugar del Y-8F, con bandera de Venezuela y número 4951 en la cola.
  - **Diamond DA40**.
- Siguen hechos a mano: DA42, SF-260 y helicópteros Enstrom.
- `herramientas\matricula_c130.py 4951` cambia el número de la cola del Hércules (después correr `Armar_escena.bat`).
- `herramientas\mascara_tucano.py` regenera la máscara de pintura del Tucano.
- Las personas están apagadas. Para encenderlas, agregar `--personas` en la línea de Blender dentro de `Armar_escena.bat`.

## Pendiente

- Terreno de fondo: ahora se ve como arena lisa; en la realidad hay grama y sembradíos.
- Modelos reales del DA42, SF-260 y Enstrom.
- Personas.

## Créditos

Ver `CREDITOS.txt`. Los modelos del C-130 y del DA40 son CC-BY 4.0: hay que mencionar a sus autores si se publica el render.
