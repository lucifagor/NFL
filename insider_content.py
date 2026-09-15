"""
Lógica de contenido de la sección Insider de NFLWarriors
=========================================================

Insider es una sección independiente de Fantasy: aquí SOLO viven notas
periodísticas escritas por ti (el "staff" de NFLWarriors) — análisis,
columnas de opinión, notas de Fantasy Insider redactadas a mano, etc.
No hay contenido generado automáticamente a partir de los datos de la app
(eso vive en la pantalla Fantasy). Cada nota se clasifica con una de estas
categorías, solo para organizarla dentro de Insider:

  1. "fantasy"  — Notas de Fantasy Insider (start/sit, waiver wire, etc.)
                  escritas por ti, no generadas por la app.
  2. "analisis" — Análisis y opinión NFL en general.
  3. "datos"    — Notas basadas en datos que tú redactas a mano.
  4. "columna"  — Columnas de autor.

Cada nota se muestra en dos formas, igual que una nota de prensa:

  - TEASER: una tarjeta (con foto, categoría, título, deck y resumen) en la
    grilla de Insider — el mismo lenguaje visual que las tarjetas de la
    pestaña News.
  - ARTÍCULO COMPLETO: al hacer clic en la tarjeta, se navega a una pantalla
    aparte con el artículo entero (título grande, deck, línea de autor/
    fecha/tiempo de lectura, foto con crédito, cuerpo en Markdown, y un
    bloque especial "Warrior Verdict" si el artículo lo incluye).

Todas las notas se manejan como archivos Markdown dentro de la carpeta
`insider_articles/`, cada uno con un encabezado simple al estilo:

    ---
    titulo: Mi título
    categoria: analisis
    autor: Tu nombre
    fecha: 2026-09-14
    tiempo_lectura: 7 min       (opcional)
    deck: Subtítulo/gancho de una línea (opcional)
    resumen: Resumen corto para la tarjeta (1-3 líneas).
    imagen: https://...                     (opcional)
    imagen_credito: Foto: Fulano / Fuente (Licencia)   (opcional)
    ---

    El resto del archivo es el cuerpo del artículo completo, en Markdown
    normal. Para resaltar un bloque como "Warrior Verdict" (o cualquier otro
    llamado especial), envuélvelo así en cualquier parte del cuerpo:

    :::verdict
    **THE BATTLE TO WATCH**

    DENVER PASS RUSH vs. MAHOMES + KC OFFENSIVE LINE
    :::

Para publicar una nota nueva: crea un archivo `.md` dentro de
`insider_articles/`, súbelo a tu repo de GitHub junto con el resto del
código, y aparecerá automáticamente la próxima vez que cargue la app (no
hace falta tocar nada más).
"""

from __future__ import annotations

import os
import re
import datetime
import urllib.parse
import streamlit as st


# ---------------------------------------------------------------------------
# Utilidades compartidas
# ---------------------------------------------------------------------------
def _sin_sangria(html: str) -> str:
    """Igual que en app.py — evita que Streamlit interprete HTML con
    sangría como bloque de código."""
    return "\n".join(line.strip() for line in html.strip().split("\n"))


CATEGORIAS_LABEL = {
    "fantasy": "Fantasy Insider",
    "analisis": "Análisis NFL",
    "datos": "Reporte automático",
    "columna": "Columna",
}

CATEGORIAS_COLOR = {
    "fantasy": "#BD4E1E",
    "analisis": "#1B5FBF",
    "datos": "#5CB85C",
    "columna": "#8B5CF6",
}

# Campos de metadatos que reconocemos en el encabezado de los .md — el resto
# de líneas del encabezado se ignoran en vez de tronar, por si alguien
# agrega algo extra a mano.
_CAMPOS_FRONTMATTER = [
    "titulo", "categoria", "autor", "fecha", "tiempo_lectura",
    "deck", "resumen", "imagen", "imagen_credito",
]


# ---------------------------------------------------------------------------
# 1. Carga de columnas/artículos manuales (archivos .md en insider_articles/)
# ---------------------------------------------------------------------------
def _parsear_frontmatter(texto: str) -> tuple[dict, str]:
    """Parsea un encabezado simple `clave: valor` (una por línea) delimitado
    por líneas '---' al inicio del archivo. No soporta listas ni anidamiento
    — alcanza para los campos que usamos, y evita depender de una librería
    de YAML."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", texto, re.DOTALL)
    if not m:
        return {}, texto.strip()
    bloque, cuerpo = m.groups()
    meta = {}
    for linea in bloque.splitlines():
        if ":" in linea:
            clave, _, valor = linea.partition(":")
            meta[clave.strip().lower()] = valor.strip().strip('"').strip("'")
    return meta, cuerpo.strip()


def cargar_columnas_manuales(carpeta: str = "insider_articles") -> list:
    """Lee todos los archivos .md de la carpeta de artículos (menos los que
    empiezan con '_' o son un README/LEEME, que se tratan como
    documentación, no como artículos) y los convierte en la misma forma de
    diccionario que usan los reportes automáticos."""
    if not os.path.isdir(carpeta):
        return []

    articulos = []
    for nombre in sorted(os.listdir(carpeta)):
        if not nombre.lower().endswith(".md"):
            continue
        if nombre.startswith("_") or nombre.lower() in ("readme.md", "leeme.md"):
            continue

        ruta = os.path.join(carpeta, nombre)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                texto = f.read()
        except Exception:
            continue

        meta, cuerpo = _parsear_frontmatter(texto)
        categoria = meta.get("categoria", "columna").lower()
        if categoria not in CATEGORIAS_LABEL:
            categoria = "columna"

        articulos.append({
            "id": nombre,
            "titulo": meta.get("titulo", nombre.replace(".md", "")),
            "categoria": categoria,
            "autor": meta.get("autor", "NFLWarriors"),
            "fecha": meta.get("fecha", ""),
            "tiempo_lectura": meta.get("tiempo_lectura", ""),
            "deck": meta.get("deck", ""),
            "resumen": meta.get("resumen", ""),
            "imagen": meta.get("imagen", ""),
            "imagen_credito": meta.get("imagen_credito", ""),
            "contenido": cuerpo,
            "auto": False,
        })

    articulos.sort(key=lambda a: a.get("fecha", ""), reverse=True)
    return articulos


# ---------------------------------------------------------------------------
# 2. Bloques especiales dentro del cuerpo (ej. ":::verdict ... :::")
# ---------------------------------------------------------------------------
_VERDICT_RE = re.compile(r":::verdict\s*\n(.*?)\n:::", re.DOTALL | re.IGNORECASE)


def _separar_bloque_verdict(contenido: str) -> tuple[str, str | None, str]:
    """Si el cuerpo trae un bloque ':::verdict ... :::', lo separa del
    resto para poder renderizarlo aparte con un estilo destacado. Devuelve
    (texto_antes, texto_del_bloque_o_None, texto_despues)."""
    m = _VERDICT_RE.search(contenido)
    if not m:
        return contenido, None, ""
    return contenido[:m.start()].strip(), m.group(1).strip(), contenido[m.end():].strip()


def _md_simple_a_html(texto: str) -> str:
    """Conversión mínima de Markdown a HTML — solo **negritas** y párrafos
    separados por línea en blanco. Alcanza para bloques cortos como
    'Warrior Verdict'; el cuerpo normal del artículo usa st.markdown, que
    soporta Markdown completo."""
    partes = [p.strip() for p in texto.strip().split("\n\n") if p.strip()]
    html_partes = []
    for p in partes:
        p_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p_html = p_html.replace("\n", "<br>")
        html_partes.append(f"<p style='margin:4px 0;'>{p_html}</p>")
    return "".join(html_partes)


def _linea_meta(art: dict) -> str:
    partes = [p for p in [
        f"Por {art['autor']}" if art.get("autor") else "",
        art.get("fecha", ""),
        f"{art['tiempo_lectura']} de lectura" if art.get("tiempo_lectura") else "",
    ] if p]
    return "  ·  ".join(partes)


# ---------------------------------------------------------------------------
# 3. Render — teaser (tarjeta) y artículo completo
# ---------------------------------------------------------------------------
def _vista_previa_cuerpo(art: dict) -> str:
    """Arma el texto de vista previa que se muestra en la tarjeta teaser:
    si el cuerpo del artículo ya trae un subtítulo (## Así), usa ESE
    subtítulo en negrita más el párrafo que le sigue — el mismo fragmento
    que se ve al entrar al artículo completo — para que la tarjeta
    "adelante" contenido real en vez de un resumen aparte. Si el cuerpo no
    tiene subtítulos, cae de nuevo al campo `resumen` del encabezado."""
    intro, resto = _dividir_intro_resto(art.get("contenido", ""))
    if resto:
        primera_linea, _, resto_cuerpo = resto.partition("\n")
        encabezado = primera_linea.lstrip("#").strip()
        primer_parrafo = resto_cuerpo.strip().split("\n\n", 1)[0].strip()
        if encabezado:
            return (
                f"<strong>{encabezado}</strong><br>{primer_parrafo}"
                if primer_parrafo else f"<strong>{encabezado}</strong>"
            )
    if intro:
        return intro.split("\n\n", 1)[0].strip()
    return art.get("resumen", "")


def render_tarjeta_teaser(art: dict) -> str:
    """HTML de una tarjeta tipo teaser: foto chica a la izquierda (con la
    categoría sobrepuesta, se ve completa gracias al mismo recorte que usa
    News) y a la derecha, alineado a la izquierda, el título en naranja, el
    deck en cursiva, un adelanto del cuerpo del artículo y la línea de
    autor/fecha. Toda la tarjeta es un hipervínculo real (?articulo=ID),
    igual que ya se usa para navegar a equipos y partidos en el resto del
    sitio."""
    color_cat = CATEGORIAS_COLOR.get(art.get("categoria"), "#BD4E1E")
    etiqueta_cat = CATEGORIAS_LABEL.get(art.get("categoria"), "Insider")
    articulo_id = urllib.parse.quote(str(art.get("id", "")), safe="")

    deck_html = (
        f'<p style="color:#5A5A5A; font-size:0.8rem; font-style:italic; margin:0 0 6px 0;">{art["deck"]}</p>'
        if art.get("deck") else ""
    )
    meta_txt = _linea_meta(art)
    meta_html = (
        f'<p style="color:#8B9187; font-size:0.7rem; margin:8px 0 0 0;">{meta_txt}</p>'
        if meta_txt else ""
    )
    vista_previa = _vista_previa_cuerpo(art)

    if art.get("imagen"):
        return _sin_sangria(f"""
        <a href="?articulo={articulo_id}" target="_self" style="text-decoration:none;">
        <div style="background:#D8DBD4; border-radius:8px; box-shadow:0 4px 10px rgba(0,0,0,0.35);
             padding:12px; margin-bottom:14px; display:flex; gap:12px; align-items:flex-start;
             height:196px; overflow:hidden; max-width:96%; width:96%; margin-left:auto; margin-right:auto;">
            <div style="position:relative; flex-shrink:0; width:110px; height:172px;">
                <img src="{art['imagen']}" style="width:110px; height:172px; object-fit:cover;
                     object-position:center top; border-radius:6px; display:block;">
                <span style="position:absolute; top:6px; left:6px; background:{color_cat};
                     color:#FFFFFF; font-weight:700; font-size:0.6rem; padding:2px 6px; border-radius:4px;">{etiqueta_cat}</span>
            </div>
            <div style="flex:1; min-width:0; text-align:left; overflow:hidden; height:172px;">
                <p style="color:#BD4E1E; font-weight:800; font-size:1rem; margin:0 0 4px 0;
                     display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">{art.get('titulo', '')}</p>
                {deck_html}
                <p style="color:#14241A; font-size:0.82rem; margin:0;
                     display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">{vista_previa}</p>
                {meta_html}
            </div>
        </div>
        </a>
        """)

    return _sin_sangria(f"""
    <a href="?articulo={articulo_id}" target="_self" style="text-decoration:none;">
    <div style="background:#D8DBD4; border-radius:8px; box-shadow:0 4px 10px rgba(0,0,0,0.35);
         padding:14px; margin-bottom:14px; text-align:left; max-width:96%; width:96%;
         margin-left:auto; margin-right:auto; min-height:150px;">
        <span style="background:{color_cat}; color:#FFFFFF; font-weight:700;
             font-size:0.68rem; padding:2px 8px; border-radius:4px;">{etiqueta_cat}</span>
        <p style="color:#BD4E1E; font-weight:800; font-size:1rem; margin:8px 0 4px 0;
             display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">{art.get('titulo', '')}</p>
        {deck_html}
        <p style="color:#14241A; font-size:0.82rem; margin:0;
             display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">{vista_previa}</p>
        {meta_html}
    </div>
    </a>
    """)


def render_grid_teasers(articulos: list):
    """Grilla de 2 columnas de tarjetas teaser — mismo patrón que
    renderizar_noticias() en app.py."""
    if not articulos:
        return
    for i in range(0, len(articulos), 2):
        par = articulos[i:i + 2]
        cols = st.columns(2, gap="small")
        for col, art in zip(cols, par):
            with col:
                st.markdown(render_tarjeta_teaser(art), unsafe_allow_html=True)


_ENCABEZADO_RE = re.compile(r"^#{2,4}\s+.+$", re.MULTILINE)


def _dividir_intro_resto(contenido: str) -> tuple[str, str]:
    """Separa el cuerpo en la 'intro' (todo el texto antes del primer
    encabezado ##/###/####) y el 'resto' (desde ese encabezado en
    adelante). La intro se muestra junto a la foto; el resto se muestra a
    todo el ancho debajo — igual que en el ejemplo de referencia, donde el
    arranque del texto acompaña la foto y las secciones con subtítulo van
    a todo lo ancho."""
    m = _ENCABEZADO_RE.search(contenido)
    if not m:
        return contenido.strip(), ""
    return contenido[:m.start()].strip(), contenido[m.start():].strip()


def _render_cuerpo_articulo(contenido: str, color_cat: str):
    """Renderiza un fragmento del cuerpo del artículo: Markdown normal más
    el bloque ':::verdict ... :::' destacado si lo trae. Recibe el texto
    directamente (no el `art` completo) para poder reusarse tanto con la
    intro (junto a la foto) como con el resto del cuerpo (ancho completo)."""
    if not contenido or not contenido.strip():
        return
    antes, verdict, despues = _separar_bloque_verdict(contenido)
    if antes.strip():
        st.markdown(antes)
    if verdict:
        st.markdown(
            _sin_sangria(f"""
            <div style="border:2px solid {color_cat}; border-radius:10px; padding:16px 18px;
                 margin:18px 0; background:rgba(189,78,30,0.10);">
                <div style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:0.85rem;
                     letter-spacing:0.05em; color:{color_cat}; text-transform:uppercase; margin-bottom:6px;">
                    Warrior Verdict
                </div>
                {_md_simple_a_html(verdict)}
            </div>
            """),
            unsafe_allow_html=True,
        )
    if despues.strip():
        st.markdown(despues)


def render_articulo_completo(art: dict):
    """Pantalla de artículo completo, estilo revista (como el ejemplo de
    referencia): dentro de un único cuadro claro —mismo tono que las
    tarjetas de la pestaña News—, la foto chica a la izquierda con el
    título sobrepuesto, el deck/autor y el arranque del texto a la
    derecha, y el resto del cuerpo (con sus subtítulos en el naranja de la
    marca) a todo el ancho debajo. Si el artículo no trae foto, todo el
    cuerpo ocupa el ancho completo del cuadro."""
    color_cat = CATEGORIAS_COLOR.get(art.get("categoria"), "#BD4E1E")
    etiqueta_cat = CATEGORIAS_LABEL.get(art.get("categoria"), "Insider")
    titulo = art.get("titulo", "")
    meta_txt = _linea_meta(art)
    contenido = art.get("contenido", "")

    # El cuadro tiene que quedar con fondo BLANCO explícito y letra negra —
    # no basta con heredar el gris que usan otros cuadros del sitio (la
    # regla genérica por data-testid a veces no alcanza a pintar este
    # contenedor en particular), así que forzamos el fondo directamente
    # sobre la clase del propio contenedor (.st-key-<key>), no solo sobre
    # el texto de adentro. Los subtítulos del cuerpo (## Así) van en el
    # naranja que ya se usa en el resto del sitio, para que resalten.
    st.markdown(
        _sin_sangria("""
        <style>
        .st-key-caja_articulo_insider {
            background: #FFFFFF !important;
        }
        .st-key-caja_articulo_insider p, .st-key-caja_articulo_insider li,
        .st-key-caja_articulo_insider span, .st-key-caja_articulo_insider strong,
        .st-key-caja_articulo_insider em, .st-key-caja_articulo_insider div {
            color: #000000 !important;
        }
        .st-key-caja_articulo_insider h1, .st-key-caja_articulo_insider h2,
        .st-key-caja_articulo_insider h3, .st-key-caja_articulo_insider h4 {
            color: #BD4E1E !important;
        }
        </style>
        """),
        unsafe_allow_html=True,
    )

    with st.container(border=True, key="caja_articulo_insider"):
        if art.get("imagen"):
            intro, resto = _dividir_intro_resto(contenido)
            col_foto, col_texto = st.columns([1, 1.5], gap="medium")
            with col_foto:
                st.markdown(
                    _sin_sangria(f"""
                    <div style="position:relative;">
                        <img src="{art['imagen']}" style="width:100%; height:260px; max-width:100%; object-fit:cover;
                             object-position:center top; border-radius:8px; display:block;">
                        <span style="position:absolute; top:10px; left:10px; background:{color_cat};
                             color:#FFFFFF; font-weight:700; font-size:0.68rem; padding:2px 8px;
                             border-radius:4px;">{etiqueta_cat}</span>
                        <div style="position:absolute; top:38px; left:10px; right:10px;">
                            <span style="background:#FFFFFF; color:#14241A; font-weight:800;
                                 font-size:1.35rem; line-height:1.35; padding:2px 8px;
                                 -webkit-box-decoration-break:clone; box-decoration-break:clone;
                                 text-transform:uppercase;">{titulo}</span>
                        </div>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )
                if art.get("imagen_credito"):
                    st.markdown(
                        _sin_sangria(f"""
                        <p style="color:#5A5A5A; font-size:0.72rem; margin-top:6px;">{art['imagen_credito']}</p>
                        """),
                        unsafe_allow_html=True,
                    )
            with col_texto:
                if art.get("deck"):
                    st.markdown(
                        _sin_sangria(f"""
                        <p style="color:#5A5A5A; font-size:1.05rem; font-style:italic; margin:0 0 6px 0;">{art['deck']}</p>
                        """),
                        unsafe_allow_html=True,
                    )
                if meta_txt:
                    st.markdown(
                        _sin_sangria(f"""
                        <p style="color:#8B9187; font-size:0.85rem; margin-bottom:10px;">{meta_txt}</p>
                        """),
                        unsafe_allow_html=True,
                    )
                _render_cuerpo_articulo(intro, color_cat)
            if resto.strip():
                _render_cuerpo_articulo(resto, color_cat)
            if not contenido.strip():
                st.info("_(sin contenido)_")
        else:
            st.markdown(
                _sin_sangria(f"""
                <p style="color:#14241A; font-size:1.8rem; font-weight:800; margin:0 0 4px 0;">{titulo}</p>
                """),
                unsafe_allow_html=True,
            )
            if art.get("deck"):
                st.markdown(
                    _sin_sangria(f"""
                    <p style="color:#5A5A5A; font-size:1.05rem; font-style:italic; margin:0 0 6px 0;">{art['deck']}</p>
                    """),
                    unsafe_allow_html=True,
                )
            if meta_txt:
                st.markdown(
                    _sin_sangria(f"""
                    <p style="color:#8B9187; font-size:0.85rem; margin-bottom:10px;">{meta_txt}</p>
                    """),
                    unsafe_allow_html=True,
                )
            _render_cuerpo_articulo(contenido, color_cat)
            if not contenido.strip():
                st.info("_(sin contenido)_")
