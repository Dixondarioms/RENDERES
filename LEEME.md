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
| `Actualizar_acto.bat` | Rehace solo el acto (tarima, toldo, autoridades y parada) dentro de `blender\feria.blend`, sin armar toda la escena (unos 3 min y poca memoria). |
| `Recorrido.bat` | Video del recorrido por los 4 stands en 2K (2560 × 1440, 30 fps, 30 s): `blender\renders\recorrido_stands_2K.mp4`. Tarda varias horas (~25 s por cuadro en una RTX 5060); si se corta, se vuelve a correr y sigue donde quedó. |
| `Edificio_SAAG.bat` | Escena aparte solo con el SAAG (unos 2 min y poca memoria): edificio blanco, lo que tiene al lado izquierdo y el hangar por dentro. Guarda `blender\edificio_saag.blend` y las vistas `via`, `entrada`, `izquierda`, `esquina`, `techo`, `hangar`, `hangar_centro`, `hangar_derecha`, `hangar_afuera` en `blender\renders\saag_<vista>.png`. Para alta calidad: `Edificio_SAAG.bat hangar --muestras 512 --escala 100`. |

Ejemplos de `Renderizar.bat` (en una ventana de comandos dentro de la carpeta):

```bash
Renderizar.bat panoramica
```

```bash
Renderizar.bat acto tribuna hercules --muestras 512
```

Vistas disponibles: `panoramica`, `aerea`, `feria`, `acto`, `tribuna`, `toldo`, `autoridades`, `parada`, `formacion`, `hangar`, `porton`, `proyectos`, `stands`, `stands2`, `stand_igla`, `stand_juego`, `stand_mecanismo`, `stand_ultraligero`,
`tucanos`, `hercules`, `da40`, `carretera`, `planta`. Las imágenes quedan en `blender\renders\render_<vista>.png`.
La panorámica sale a 2880 × 1200 y las demás a 1920 × 1080.

Vistas de presentación de los stands, en 2K (2560 × 1440): `stands_general` (los 4 juntos), `frente_<stand>` (de frente,
a la altura de una persona) y `detalle_<stand>` (la exhibición de cerca), con `<stand>` = `igla`, `juego`, `mecanismo`, `ultraligero`.

## Cómo está armado

- `index.html` es el visor 3D (three.js). De ahí se exportó `blender\escena.glb`: terreno, vías, hangar, gradas, tribuna y aviones hechos a mano.
- `herramientas\armar_blender.py` importa esa escena en Blender y pone sol, cielo, cámaras y calidad de render.
- `herramientas\mejoras_blender.py` mejora lo importado: concreto de la plataforma, marcas, edificios del SAAG y vecinos, árboles reales, hangar, y los aviones descargados:
  - **T-27 Tucano** con camuflaje AMB (arena, verde y verde oscuro), bandera y distintivo en la cola.
  - **C-130 Hércules** en lugar del Y-8F, con bandera de Venezuela y número 4951 en la cola.
  - **Diamond DA40**.
- `herramientas\realismo_blender.py` es la capa de realismo (se aplica sola al armar la escena):
  - **Luz física**: el sol se saca del HDR (traía el sol adentro *y* había una lámpara encima: dos soles) y se
    pasa a una lámpara con la misma irradiancia y color; la exposición se calcula a partir de ella.
  - **Cielo 8k** solo para lo que ve la cámara (el 2k se veía borroso en la panorámica).
  - **Bruma** (perspectiva aérea): lo lejano se funde con el color del cielo en el horizonte.
  - **Relieve** rehecho con todos los datos (37 m entre puntos, antes 150 m) y detalle fractal en las laderas;
    el Lago de Valencia a su nivel real.
  - **Campo** alrededor de la base: parcelas aradas con surcos, potreros, siembras en hileras, pasto seco y monte en los linderos.
  - **Arboleda de fondo**: miles de copias de los árboles reales en linderos, manchas de monte y sueltos (nodos de geometría).
  - **Grama 3D** cerca de las cámaras a ras de piso (`CAMARAS_SUELO`); si se agrega una cámara nueva a ras de piso, sumarla ahí.
  - Copas de mango más densas y oscuras, palmas con hojas pinnadas, palmas de Bismarck plateadas en abanico.
  - Lámparas industriales dentro del hangar; la vista `proyectos` lleva +4 EV (`EXPOSICION_CAMARA`).
  - **Stands de los 4 proyectos tecnológicos de la AMB** (propuesta), en los puestos más cercanos a la entrada del hangar:
    1. Simulador de disparo Igla-S: el lanzador sobre una base simple frente a la pantalla LED con el escenario;
       pantalla y caja de luz con cuadros del video del simulador (`fotos/igla_sim/`).
    2. Cóndor (simulador de juegos de guerra): pantalla LED grande, monitores y mesa táctica con capturas del
       software (`fotos/condor/`); caja de luz con la pantalla de inicio.
    3. Disparo automatizado Igla-S: el lanzador en un cabezal motorizado sobre plataforma móvil con ruedas,
       PC con monitor y joystick, y pantalla.
    4. Aeronave ultraligera ULV: maqueta 1:6 del prototipo SIBO 200-1 en vitrina; pantalla con la foto y caja de luz
       con los planos del resumen ejecutivo (`fotos/ulv/`).
    El lanzador es el modelo 9K310 `assets/igla/Igla.obj` pintado de verde. Cada stand lleva un letrero con el estilo
    de la portada del simulador (azul marino, título blanco, línea y "AVIACIÓN MILITAR BOLIVARIANA" en dorado).
    Textos, colores, imágenes y tamaños se cambian en `PROYECTOS_AMB` (`herramientas/realismo_blender.py`).
  - **Diamond DA40 con la librea AMB**: blanco, deriva roja con "E", puntas de ala rojas, capó negro, matrícula
    (`MATRICULA_DA40`) y bandera.
  - Composición de lente: brillo suave en altas luces, aberración cromática leve y viñeta.
- `herramientas\acto_blender.py` arma el acto en lugar de la tribuna y las gradas del visor:
  - **Tarima protocolar** de 40 × 9 m elevada 0,60 m, con alfombra roja, faldón blanco plisado, cinta tricolor,
    escaleras al frente y a los lados, atril con micrófono, materos y telón azul marino "106 ANIVERSARIO".
  - **Toldo protocolar blanco** a dos aguas (lona algo translúcida), con bambalina de festones, postes de aluminio
    con lastres y cortina blanca de fondo.
  - **Tres filas de sillas protocolares** con forro blanco y lazo azul; sillones de honor dorados en el centro de la
    primera fila. Las autoridades son el modelo `assets/personas/capitan.glb`, sentado por código (se deforma la
    malla con huesos definidos en `_POSES_AUTORIDAD`), con uniforme azul o verde oliva y zapatos negros.
  - **La parada**: unos 950 militares con el modelo `assets/personas/soldado_tactico.glb` en su pose de descanso,
    con el uniforme pintado en pixelado verde (como el venezolano) y fusil al pie; banda de guerra con redoblantes,
    jefes de agrupación y abanderados. Las agrupaciones siguen el Anexo 3 del plano (`parada()`).
    Si faltan esos modelos, se usan figuras hechas por código.
  - Medidas, colores y ocupación de las sillas: `TARIMA`, `TOLDO`, `CAMO_VE`, `OCUPACION` al principio del archivo.
  - Vistas: `tribuna` (desde la tarima hacia la parada), `toldo` (la tarima desde el frente), `autoridades`
    (de cerca), `parada` (las agrupaciones desde arriba) y `formacion` (los soldados a la altura de una persona), en 2K.
- **SAAG** (con las fotos del 10-11-2026), medidas al principio de cada archivo:
  - `herramientas\edificio_saag.py`: el edificio blanco hacia la vía (antes `saag_anexo`): losa con alero gris, dos franjas
    grises, zócalo y franja de piedra laja, marquesina que sale de la esquina izquierda, puerta de vidrio con paños de reja,
    emblema del SAAGBA, rejas blancas y reflectores LED. `construir_entorno_saag()` pone al lado izquierdo el poste con
    transformadores, la planta eléctrica, el tanque de agua y el pulmón de aire.
  - `herramientas\galpon_saag.py`: el hangar (galpón del techo rojo), solo instalaciones: dos naves a dos aguas, columnas
    del medio con el rayado amarillo y rojo, claraboyas, lámparas, paredes de bloque con bloque calado y extractores,
    canasta de baloncesto, extintores, lavamanos, ducha de emergencia, escalera con el cuartico y portones de malla.
  - `herramientas\stands_saag.py`: los 4 stands de la AMB dentro del hangar (los mismos de `stands_amb()`, sin cambiar ese
    código), dos por nave contra el fondo: ULV y Cóndor a la izquierda, disparo automatizado e Igla-S a la derecha;
    con alfombra roja en T, tótems AMB, letrero colgante «PROYECTOS TECNOLÓGICOS DE LA AMB», palmas y arbustos.
    Vistas: `stands` (desde la plataforma) y las de cada stand (`frente_igla`, `detalle_ultraligero`, etc.).
    `Edificio_SAAG.bat --sin-stands` deja el hangar vacío.
  - Se trabaja aparte con `Edificio_SAAG.bat` (`herramientas\escena_edificio.py`). El render principal ya usa el edificio
    blanco y su entorno; el hangar y sus stands todavía no (ahí sigue el galpón de la otra PC).
- Siguen hechos a mano: DA42, SF-260 y helicópteros Enstrom.
- `herramientas\matricula_c130.py 4951` cambia el número de la cola del Hércules (después correr `Armar_escena.bat`).
- `herramientas\mascara_tucano.py` regenera la máscara de pintura del Tucano.

## Pendiente

- Árboles cercanos: siguen siendo los modelos de Poly Haven con la copa densificada; un modelo real de mango mejoraría las vistas a ras de piso.
- Modelos reales del DA42, SF-260 y Enstrom.
- Personas: todos los soldados y todas las autoridades son el mismo modelo (misma cara); se podrían sumar más modelos.

## Créditos

Ver `CREDITOS.txt`. Los modelos del C-130 y del DA40 son CC-BY 4.0: hay que mencionar a sus autores si se publica el render.
