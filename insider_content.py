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
def render_tarjeta_teaser(art: dict) -> str:
    """HTML de una tarjeta tipo teaser — mismo lenguaje visual que las
    tarjetas de la pestaña News (clase .noticia-card): foto con la
    categoría sobrepuesta, título, deck, resumen y línea de autor/fecha.
    Toda la tarjeta es un hipervínculo real (?articulo=ID), igual que ya
    se usa para navegar a equipos y partidos en el resto del sitio."""
    color_cat = CATEGORIAS_COLOR.get(art.get("categoria"), "#BD4E1E")
    etiqueta_cat = CATEGORIAS_LABEL.get(art.get("categoria"), "Insider")
    articulo_id = urllib.parse.quote(str(art.get("id", "")), safe="")

    if art.get("imagen"):
        sello_auto = (
            '<span style="position:absolute; bottom:6px; right:8px; background:rgba(0,0,0,0.6); '
            'color:#FFFFFF; font-size:0.65rem; padding:2px 7px; border-radius:4px;">⚙️ auto</span>'
            if art.get("auto") else ""
        )
        imagen_html = f"""
        <div style="position:relative; flex-shrink:0;">
            <img src="{art['imagen']}" style="width:100%; height:180px;
                 object-fit:cover; object-position:center top; border-radius:6px; display:block;">
            <span style="position:absolute; top:6px; left:8px; background:{color_cat};
                 color:#FFFFFF; font-weight:700; font-size:0.68rem; padding:2px 8px; border-radius:4px;">{etiqueta_cat}</span>
            {sello_auto}
        </div>"""
    else:
        sello_auto = " · ⚙️ auto" if art.get("auto") else ""
        imagen_html = f"""
        <div style="margin-bottom:6px;">
            <span style="background:{color_cat}; color:#FFFFFF; font-weight:700;
                 font-size:0.68rem; padding:2px 8px; border-radius:4px;">{etiqueta_cat}</span>
            <span style="color:#8B9187; font-size:0.68rem;">{sello_auto}</span>
        </div>"""

    deck_html = (
        f'<p style="color:#5A5A5A; font-size:0.8rem; font-style:italic; margin:8px 0 4px 0;">{art["deck"]}</p>'
        if art.get("deck") else ""
    )
    meta_txt = _linea_meta(art)

    return _sin_sangria(f"""
    <a href="?articulo={articulo_id}" target="_self" style="text-decoration:none;">
    <div class="noticia-card">
        {imagen_html}
        <p class="noticia-titulo">{art.get('titulo', '')}</p>
        {deck_html}
        <p class="noticia-desc">{art.get('resumen', '')}</p>
        {f'<p style="color:#8B9187; font-size:0.72rem; margin-top:auto;">{meta_txt}</p>' if meta_txt else ''}
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


def render_articulo_completo(art: dict):
    """Pantalla de artículo completo: masthead, foto con crédito, cuerpo en
    Markdown y — si el artículo lo trae — el bloque destacado 'Warrior
    Verdict' (o cualquier otro bloque ':::verdict ... :::')."""
    color_cat = CATEGORIAS_COLOR.get(art.get("categoria"), "#BD4E1E")
    etiqueta_cat = CATEGORIAS_LABEL.get(art.get("categoria"), "Insider")

    st.markdown(
        _sin_sangria(f"""
        <span style="background:{color_cat}; color:#FFFFFF; font-weight:700;
            font-size:0.75rem; padding:3px 10px; border-radius:4px;">{etiqueta_cat}</span>
        """),
        unsafe_allow_html=True,
    )

    st.markdown(f"# {art.get('titulo', '')}")
    if art.get("deck"):
        st.markdown(
            _sin_sangria(f"""
            <p style="color:#9CB3A3; font-size:1.15rem; font-style:italic; margin-top:-8px;">{art['deck']}</p>
            """),
            unsafe_allow_html=True,
        )

    meta_txt = _linea_meta(art)
    if meta_txt:
        st.caption(meta_txt)

    if art.get("imagen"):
        st.image(art["imagen"], use_container_width=True)
        if art.get("imagen_credito"):
            st.caption(art["imagen_credito"])

    st.divider()

    antes, verdict, despues = _separar_bloque_verdict(art.get("contenido", ""))
    if antes.strip():
        st.markdown(antes)
    if verdict:
        st.markdown(
            _sin_sangria(f"""
            <div style="border:2px solid {color_cat}; border-radius:10px; padding:16px 18px;
                 margin:18px 0; background:rgba(189,78,30,0.08);">
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

    if not (antes.strip() or verdict or despues.strip()):
        st.info("_(sin contenido)_")
