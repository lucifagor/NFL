Cómo publicar contenido en Insider
===================================

Este archivo NO se muestra como artículo (empieza con "_", y `insider_content.py`
ignora esos archivos y los README/LEEME).

Para publicar un artículo nuevo (columna de autor o análisis):

1. Crea un archivo `.md` en esta carpeta, por ejemplo `2026-w3-mi-columna.md`.
2. Empieza el archivo con este encabezado (los campos son planos, sin listas):

```
---
titulo: Tu título aquí
categoria: analisis
autor: Tu nombre
fecha: 2026-09-21
tiempo_lectura: 5 min
deck: Un subtítulo/gancho de una línea (opcional, se muestra en la tarjeta y en el artículo)
resumen: Un resumen de una o dos líneas para la tarjeta.
imagen: https://... (opcional — foto de portada tipo teaser, respeta la licencia de uso)
imagen_credito: Foto: Fulano / Fuente (Licencia) (opcional, se muestra bajo la foto)
---

Aquí va el cuerpo del artículo completo, en Markdown normal
(negritas con **así**, listas con "- ", encabezados de sección con "## Así").
```

3. `categoria` puede ser: `fantasy`, `analisis`, `datos` o `columna` — es
   solo una etiqueta para organizar/filtrar dentro de Insider (Insider es
   independiente de la pestaña Fantasy: aquí NUNCA se genera nada
   automático ni se muestra tu roster — solo lo que tú escribas aquí).
4. Cada artículo se muestra primero como una tarjeta (teaser) en la grilla
   de Insider, y al hacer clic lleva a una pantalla aparte con el artículo
   completo — igual que las noticias de la pestaña News.
5. Para destacar un bloque especial dentro del cuerpo (por ejemplo un
   veredicto o resumen final), envuélvelo así en cualquier parte del texto:

```
:::verdict
**THE BATTLE TO WATCH**

DENVER PASS RUSH vs. MAHOMES + KC OFFENSIVE LINE
:::
```

   Ese bloque se muestra con un recuadro de color aparte del resto del
   texto, tanto si lo llamas "Warrior Verdict" como cualquier otro título
   que le pongas dentro del bloque.

6. Sube el archivo a tu repo de GitHub junto con el resto del código y
   aparecerá automáticamente la próxima vez que cargue la app. No hace
   falta tocar `app.py` ni `insider_content.py`.

Ejemplos incluidos en esta carpeta: `2026-09-14-ejemplo-analisis.md`,
`2026-09-14-ejemplo-columna.md` y `2026-09-14-warrior-the-comeback.md` (este
último con foto, deck y bloque de veredicto — úsalo como plantilla completa).
Puedes borrarlos cuando ya no los necesites.
