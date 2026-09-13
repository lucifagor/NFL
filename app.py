"""
App web (Streamlit) del comparador de equipos NFL
====================================================

Ejecutar localmente:
    pip install streamlit nfl_data_py pandas requests
    streamlit run app.py

Desplegar gratis en línea:
    1. Sube este archivo + comparador_nfl.py + requirements.txt a un repo de GitHub.
    2. Entra a https://share.streamlit.io (Streamlit Community Cloud), conecta
       tu cuenta de GitHub, selecciona el repo y el archivo app.py.
    3. En "Secrets" (configuración de la app) agrega tus API keys:
           OPENWEATHER_API_KEY = "..."
           ODDS_API_KEY = "..."
    4. Listo — obtienes una URL pública tipo tuapp.streamlit.app

Este archivo reutiliza toda la lógica de comparador_nfl.py (no la duplica).
"""

import streamlit as st
import pandas as pd
import datetime
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

from comparador_nfl import (
    obtener_stats_temporada,
    obtener_stats_combinadas,
    obtener_jugadores_clave,
    obtener_lideres_estadisticos,
    combinar_stats_con_jugadores,
    obtener_calendario_semana,
    obtener_proximos_partidos,
    obtener_clima_estadio,
    obtener_lineas_apuestas,
    obtener_noticias_nfl,
    obtener_noticias_equipo,
    obtener_noticias_combinadas,
    obtener_lesiones_liga,
    obtener_lesiones_liga_api_sports,
    obtener_standings,
    obtener_standings_api_sports,
    obtener_marcadores_actuales,
    obtener_calendario_equipo,
    obtener_roster_equipo,
    _DIVISIONES_NFL,
    obtener_marcadores_api_sports,
    logo_url,
    favorito_segun_mercado,
    comparar_equipos,
    probabilidad_victoria,
    WEIGHTS,
    HOME_FIELD_BONUS,
    NFL_DATA_PY_OK,
    OPENWEATHER_API_KEY,
    ODDS_API_KEY,
)

try:
    API_SPORTS_KEY = st.secrets.get("API_SPORTS_KEY", "")
except Exception:
    API_SPORTS_KEY = ""

st.set_page_config(page_title="NFLWarriors", page_icon="🛡️", layout="wide")


def _sin_sangria(html: str) -> str:
    """Streamlit/markdown puede interpretar líneas con 4+ espacios de
    sangría como bloque de código en vez de HTML — quita la sangría de
    cada línea para que siempre se renderice como HTML real."""
    return "\n".join(line.strip() for line in html.strip().split("\n"))


def inyectar_estilos():
    """Capa visual del sitio — tipografía condensada tipo marcador de
    estadio para títulos, Inter para el resto, acento dorado único
    (evita el look genérico de plantilla)."""
    st.markdown(_sin_sangria(f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background-image: url("{FONDO_URL}");
        background-size: cover;
        background-position: center top;
        background-attachment: fixed;
        background-repeat: no-repeat;
        overflow-x: hidden;
    }}
    [data-testid="stAppViewContainer"] > .main {{ background: transparent; overflow-x: hidden; }}
    html, body {{ overflow-x: hidden; max-width: 100%; }}
    [data-testid="stMainBlockContainer"], .block-container {{
        max-width: 96vw !important; margin-left: auto !important; margin-right: auto !important;
        overflow-x: hidden;
    }}
    * {{ box-sizing: border-box; }}
    </style>
    """), unsafe_allow_html=True)

    st.markdown(_sin_sangria("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Inter:wght@400;500;600&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    h1, h2, h3 {
        font-family: 'Barlow Condensed', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 0.01em;
    }

    /* Oculta el chrome por default de Streamlit para un look más limpio */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }

    /* Botón primario: acento dorado único */
    [data-testid="stButton"] button[kind="primary"] {
        background: #BD4E1E;
        color: #14241A;
        border: none;
        font-weight: 600;
        border-radius: 6px;
    }
    [data-testid="stButton"] button[kind="primary"]:hover {
        background: #D9683A;
        color: #14241A;
    }
    [data-testid="stButton"] button:not([kind="primary"]) {
        border-radius: 6px;
        border: 1px solid #26402F;
    }

    /* Métricas con el tono condensado del marcador */
    [data-testid="stMetricValue"] {
        font-family: 'Barlow Condensed', sans-serif;
        font-weight: 700;
    }
    [data-testid="stMetricLabel"] { color: #9CB3A3; }

    /* Tabs: subrayado dorado en la pestaña activa */
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: #BD4E1E !important;
        border-bottom-color: #BD4E1E !important;
    }

    /* Barra de progreso (probabilidad) en dorado */
    [data-testid="stProgress"] > div > div > div {
        background-color: #BD4E1E !important;
    }

    /* Sidebar con borde sutil */
    [data-testid="stSidebar"] { border-right: 1px solid #26402F; }

    /* Banner ilustrado tipo estadio (graderías + campo + postes) */
    .franja-campo {
        margin: -1rem -1rem 1rem -1rem;
        border-bottom: 2px solid #BD4E1E;
        position: relative;
        overflow: hidden;
        line-height: 0;
    }

    /* Ticker de marcadores — scroll horizontal */
    .ticker-marcadores {
        display: flex; gap: 10px; overflow-x: auto; padding: 4px 2px 12px 2px;
        margin-bottom: 12px; scrollbar-width: thin;
    }
    .ticker-juego {
        flex: 0 0 auto; border: 1px solid #AEB4A9; border-radius: 6px;
        overflow: hidden; min-width: 140px; max-width: 170px;
    }
    .ticker-equipos { background: #FFFFFF; padding: 6px 10px; }
    .ticker-info { background: #CDD1C7; padding: 5px 10px; }
    .ticker-equipo { display:flex; align-items:center; justify-content:flex-start; gap:6px; }
    .ticker-equipo img { width:20px; height:20px; }
    .ticker-abbr { font-weight:700; font-size:0.85rem; color:#14241A; margin-right:auto; }
    .ticker-score { font-weight:700; font-size:0.85rem; color:#000000; }
    .ticker-estado { font-size:0.7rem; color:#1F241E; text-align:center; line-height:1.3; white-space:normal; }
    .ticker-estadio { font-size:0.65rem; color:#3E4A42; font-weight:600; text-align:center; margin-top:1px; line-height:1.3; white-space:normal; }

    /* Tarjetas de noticias — blancas con sombra, texto negro (mismo
       lenguaje visual que las tarjetas de equipo, para que se lea bien
       sobre el fondo con imagen). */
    .noticia-card {
        background: #D8DBD4; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.35);
        padding: 14px; text-align: center; margin-bottom: 14px;
        display: flex; flex-direction: column; height: 360px; overflow: hidden;
        max-width: 94%; width: 94%; margin-left: auto; margin-right: auto;
    }
    .noticia-card img { flex-shrink: 0; max-width: 100%; }
    .noticia-card p { color: #14241A; }
    .noticia-card a { color: #BD4E1E; font-weight: 700; text-decoration: underline; }
    .noticia-titulo {
        font-weight: 700; margin: 10px 0 6px 0; font-size: 1rem; flex-shrink: 0;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    }
    .noticia-desc {
        color: #3A3A3A; font-size: 0.88rem; margin: 0;
        display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
    }
    /* Selector de temporada (Standings) — angosto, del ancho de la palabra */
    div[class*="st-key-selector_temporada"] { max-width: 130px; }

    /* Todos los cuadros/casillas de información (contenedores con borde,
       métricas, tablas) del mismo gris que las tarjetas de noticias */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #D8DBD4 !important; border-color: #AEB4A9 !important; border-radius: 8px !important;
    }
    [data-testid="stMetric"] {
        background: #D8DBD4; border-radius: 8px; padding: 10px 12px;
    }
    [data-testid="stMetric"] label, [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #14241A !important;
    }
    [data-testid="stDataFrame"] { background: #D8DBD4; border-radius: 8px; }
    </style>
    """), unsafe_allow_html=True)


def franja_campo():
    """Banner del estadio (imagen subida por el usuario) con el wordmark
    NFL WARRIORS sobrepuesto en grande, arriba."""
    st.markdown(_sin_sangria(f"""
    <div class="franja-campo" style="position:relative;">
        <img src="{BANNER_URL}" style="width:100%; height:auto; display:block;">
        <img src="{LOGO_TEXTO_URL}" style="position:absolute; top:2%; left:50%;
             transform:translateX(-50%); height:44%; width:auto; max-width:85%;">
    </div>
    """), unsafe_allow_html=True)


_MESES_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
             7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


def _temporada_nfl_actual() -> int:
    """La temporada de NFL se identifica por el año en que arranca (ej.
    la que empieza en septiembre de 2026 y termina en febrero de 2027 es
    'temporada 2026'). Antes de que arranque la temporada de este año
    (~septiembre), la temporada 'actual' sigue siendo la del año
    anterior."""
    hoy = datetime.date.today()
    return hoy.year if hoy.month >= 9 else hoy.year - 1


def _fecha_corta(fecha_iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(fecha_iso)
        return f"{d.day} {_MESES_ES[d.month]}"
    except Exception:
        return fecha_iso


def _fecha_hora_local(p: dict) -> str:
    """Convierte el timestamp UTC del partido a la zona horaria detectada
    del navegador (o America/Cancun por default) — así el horario que se
    ve es el real de quien está viendo la app, no la hora cruda de la
    API (que viene en UTC)."""
    ts = p.get("timestamp")
    if ts:
        try:
            zona = st.session_state.get("zona_horaria", "America/Cancun")
            local = datetime.datetime.fromtimestamp(ts, tz=ZoneInfo(zona))
            return f"{local.day} {_MESES_ES[local.month]} · {local.strftime('%H:%M')}"
        except Exception:
            pass
    # Respaldo si no hay timestamp (ej. viene del fallback de ESPN).
    return " · ".join(x for x in [_fecha_corta(p["fecha"]) if p.get("fecha") else "", p.get("hora", "")] if x)


def ticker_marcadores(partidos: list, standings: pd.DataFrame = None):
    """Renderiza el ticker horizontal de marcadores estilo NFL.com.
    Si el partido no se ha jugado, en vez de '-' muestra el récord
    ganados-perdidos de cada equipo en la temporada (ej. 3-4)."""
    if not partidos:
        return

    registros = {}
    if standings is not None and not standings.empty:
        for _, fila in standings.iterrows():
            registros[fila["Equipo"]] = f"{int(fila['V'])}-{int(fila['D'])}"

    tarjetas = ""
    for p in partidos:
        away_score = p["away_score"] if p["away_score"] is not None else registros.get(p["away_abbr"], "-")
        home_score = p["home_score"] if p["home_score"] is not None else registros.get(p["home_abbr"], "-")
        if p["estado"] in ("FT", "AOT"):
            linea1 = "Final" if p["estado"] == "FT" else "Final (OT)"
            linea2 = ""
        else:
            linea1 = _fecha_hora_local(p) or "Por confirmar"
            linea2 = p.get("estadio", "")
        tarjetas += f"""
        <a href="?partido={p['away_abbr']}-{p['home_abbr']}" target="_self" style="text-decoration:none; color:inherit;">
        <div class="ticker-juego">
            <div class="ticker-equipos">
                <div class="ticker-equipo">
                    <img src="{logo_url(p['away_abbr'])}"><span class="ticker-abbr">{p['away_abbr']}</span>
                    <span class="ticker-score">{away_score}</span>
                </div>
                <div class="ticker-equipo">
                    <img src="{logo_url(p['home_abbr'])}"><span class="ticker-abbr">{p['home_abbr']}</span>
                    <span class="ticker-score">{home_score}</span>
                </div>
            </div>
            <div class="ticker-info">
                <div class="ticker-estado">{linea1}</div>
                {f'<div class="ticker-estadio">{linea2}</div>' if linea2 else ''}
            </div>
        </div>
        </a>"""
    st.markdown(_sin_sangria(f'<div class="ticker-marcadores">{tarjetas}</div>'), unsafe_allow_html=True)


def hero(titulo: str, subtitulo: str = ""):
    """Título de sección centrado, más grande, con una línea de acento
    a cada lado (simétrico)."""
    st.markdown(_sin_sangria(f"""
    <div style="text-align:center; margin: 0 0 10px 0;">
        <div style="display:flex; align-items:center; justify-content:center; gap:18px;">
            <span style="flex:1; max-width:110px; height:3px; background:#BD4E1E; border-radius:2px;"></span>
            <h1 style="margin:0; font-size:3.1rem; white-space:nowrap;">{titulo}</h1>
            <span style="flex:1; max-width:110px; height:3px; background:#BD4E1E; border-radius:2px;"></span>
        </div>
        {f'<p style="color: #9CB3A3; margin-top: 4px;">{subtitulo}</p>' if subtitulo else ''}
    </div>
    """), unsafe_allow_html=True)


# Logo oficial de NFLWarriors — súbelos a tu repo de GitHub en una carpeta
# "assets/" y ajusta esta ruta si tu usuario/repo son distintos.
LOGO_ESCUDO_URL = "https://raw.githubusercontent.com/lucifagor/nfl/main/assets/escudo.png"
LOGO_TEXTO_URL = "https://raw.githubusercontent.com/lucifagor/nfl/main/assets/wordmark_transparente.png"
LOGO_COMPLETO_URL = "https://raw.githubusercontent.com/lucifagor/nfl/main/assets/escudo_completo.png"
BANNER_URL = "https://raw.githubusercontent.com/lucifagor/nfl/main/assets/banner.png"
FONDO_URL = "https://raw.githubusercontent.com/lucifagor/nfl/main/assets/fondo.png"


def _escudo_svg(tamano: int = 40) -> str:
    """Logo oficial de NFLWarriors (imagen subida por el usuario) — ya no
    es el escudo dibujado a mano, se conserva el nombre de la función
    para no tocar cada punto donde se usa."""
    alto = int(tamano * 1.1)
    return f'<img src="{LOGO_ESCUDO_URL}" width="{tamano}" height="{alto}" style="object-fit:contain;">'


def marca_completa():
    """Lockup completo de la marca — logo + wordmark + tagline. Se usa una
    sola vez, en la pantalla de Inicio."""
    st.markdown(_sin_sangria(f"""
    <div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">
        {_escudo_svg(52)}
        <div>
            <div style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:2.1rem; line-height:1; letter-spacing:0.01em;">
                <span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">WARRIORS</span>
            </div>
            <div style="color:#9CB3A3; font-size:0.95rem; margin-top:2px;">Pronósticos con lógica, no con corazonadas.</div>
        </div>
    </div>
    """), unsafe_allow_html=True)


def marca_compacta():
    """Barra de marca angosta — logo + wordmark, sin tagline. Se usa en
    pantallas secundarias (como el detalle de un partido) que no forman
    parte del menú principal."""
    st.markdown(_sin_sangria(f"""
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:18px;
                padding-bottom:12px; border-bottom:1px solid #26402F;">
        {_escudo_svg(28)}
        <div style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:1.2rem; letter-spacing:0.01em;">
            <span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">WARRIORS</span>
        </div>
    </div>
    """), unsafe_allow_html=True)


_SECCIONES_NAV = [
    ("inicio", "News"),
    ("estadisticas", "Standings"),
    ("lesiones", "Injuries"),
    ("pronosticos", "Predictions"),
    ("fantasy", "Fantasy"),
    ("blog", "Insider"),
]


def logo_grande_centrado():
    """Ya no se usa por separado — el escudo ahora vive junto al menú en
    barra_navegacion(). Se deja como no-op por si algo más la referencia."""
    pass


def barra_navegacion(activo: str):
    """Menú en una sola línea, centrado. La sección activa se resalta en
    dorado. (El logo ya va en grande sobre el banner del estadio, no se
    repite aquí)."""
    col_izq, col_menu, col_der = st.columns([1, 6, 1])

    with col_menu:
        cols = st.columns(len(_SECCIONES_NAV))
        for col, (clave, etiqueta) in zip(cols, _SECCIONES_NAV):
            with col:
                es_activo = clave == activo
                if st.button(
                    etiqueta, key=f"nav_{clave}",
                    type="primary" if es_activo else "secondary",
                    use_container_width=True,
                ) and not es_activo:
                    st.session_state.pagina = clave
                    st.rerun()

    st.markdown('<hr style="border-color:#26402F; margin-top:0; margin-bottom:6px;">', unsafe_allow_html=True)


def encabezado_sitio(activo: str):
    """Encabezado compartido por TODA la app: franja de campo, resultados
    de la semana, menú de navegación, y la fila de logos de equipo — se
    ve igual arriba de cualquier pantalla en la que estés."""
    franja_campo()
    with st.spinner("Cargando marcadores..."):
        partidos_ticker = marcadores_cacheados(datetime.date.today().year, api_key=API_SPORTS_KEY)
        try:
            standings_ticker = standings_cacheados(datetime.date.today().year, api_key=API_SPORTS_KEY)
        except Exception:
            standings_ticker = None
    ticker_marcadores(partidos_ticker, standings_ticker)
    logo_grande_centrado()
    barra_navegacion(activo)
    fila_equipos_alfabetica()


inyectar_estilos()

EQUIPOS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LA", "LAC", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
]

NOMBRES_EQUIPO = {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills",
    "CAR": "Panthers", "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns",
    "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
    "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs",
    "LA": "Rams", "LAC": "Chargers", "LV": "Raiders", "MIA": "Dolphins",
    "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
    "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks",
    "SF": "49ers", "TB": "Buccaneers", "TEN": "Titans", "WAS": "Commanders",
}

NOMBRES_COMPLETOS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


def nombre_equipo(abbr: str) -> str:
    return f"{NOMBRES_EQUIPO.get(abbr, abbr)} ({abbr})"


def tabla_division_html(nombre_division: str, filas: pd.DataFrame, color_header: str, color_borde: str) -> str:
    """Genera una tabla de una división: fondo blanco uniforme en toda la
    caja (incluido el marco de color), líneas punteadas horizontales
    entre equipos, encabezados grandes en negritas, texto negro en todas
    partes, borde de color redondeado alrededor de toda la división.
    Incluye G/P/E/%/PF/PC/Loc./Vis./Racha."""
    BLANCO = "#FFFFFF"
    NEGRO = "#14241A"
    PUNTEADO = "1px dotted #C7CBC3"
    tiene_extra = "PF" in filas.columns

    filas_html = ""
    for _, row in filas.iterrows():
        pct = row["% Victorias"] / 100
        pct_txt = "-" if row["V"] == 0 else f"{pct:.3f}".lstrip("0")
        extra_html = ""
        if tiene_extra:
            extra_html = f"""
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-size:0.85rem; border-bottom:{PUNTEADO};">{row.get('PF', '')}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-size:0.85rem; border-bottom:{PUNTEADO};">{row.get('PC', '')}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-size:0.85rem; border-bottom:{PUNTEADO};">{row.get('Loc', '')}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-size:0.85rem; border-bottom:{PUNTEADO};">{row.get('Vis', '')}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-size:0.85rem; border-bottom:{PUNTEADO}; padding-right:14px;">{row.get('Racha', '')}</td>"""
        filas_html += f"""
        <tr>
            <td style="padding:6px 6px; background:{BLANCO}; border-bottom:{PUNTEADO};"><img src="{logo_url(row['Equipo'])}" width="24" style="vertical-align:middle;"></td>
            <td style="padding:8px 10px; font-weight:700; color:{NEGRO}; white-space:nowrap; background:{BLANCO}; font-size:1rem; border-bottom:{PUNTEADO};">{NOMBRES_COMPLETOS.get(row['Equipo'], row['Equipo'])}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; border-bottom:{PUNTEADO};">{row['V']}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; border-bottom:{PUNTEADO};">{row['D']}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; border-bottom:{PUNTEADO};">{row['E']}</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:600; background:{BLANCO}; white-space:nowrap; border-bottom:{PUNTEADO};">{pct_txt}</td>
            {extra_html}
        </tr>"""

    columnas_extra_header = ""
    colgroup_extra = ""
    if tiene_extra:
        columnas_extra_header = "".join(
            f'<td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">{c}</td>'
            for c in ["PF", "PC", "Loc.", "Vis."]
        )
        columnas_extra_header += f'<td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap; padding-right:14px;">Racha</td>'
        colgroup_extra = "".join('<col style="width:56px;">' for _ in range(5))

    return _sin_sangria(f"""
    <div style="border:3px solid {color_borde}; border-radius:12px; overflow:hidden; margin-bottom:20px; min-width:420px; background:{BLANCO};">
    <table style="width:100%; border-collapse:collapse; font-family:'Inter',sans-serif; table-layout:fixed; background:{BLANCO};">
        <colgroup>
            <col style="width:42px;"><col><col style="width:46px;">
            <col style="width:46px;"><col style="width:46px;"><col style="width:72px;">
            {colgroup_extra}
        </colgroup>
        <tr style="background:{BLANCO};">
            <td colspan="2" style="padding:8px 10px; color:{NEGRO}; font-weight:700; white-space:nowrap;
                font-family:'Barlow Condensed',sans-serif; font-size:1.15rem;">{nombre_division}</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">G</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">P</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">E</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">.PCT</td>
            {columnas_extra_header}
        </tr>
        {filas_html}
    </table>
    </div>
    """)


def agregar_standings_por_division(standings: pd.DataFrame) -> pd.DataFrame:
    """Suma el récord de los equipos de cada división — un renglón por
    división en vez de uno por equipo."""
    cols_sum = [c for c in ["V", "D", "E", "PF", "PC"] if c in standings.columns]
    agg = standings.groupby(["Conferencia", "División"], as_index=False)[cols_sum].sum()
    total = agg["V"] + agg["D"] + agg["E"]
    agg["% Victorias"] = ((agg["V"] + 0.5 * agg["E"]) / total.replace(0, pd.NA) * 100).round(1).fillna(0.0)
    return agg


def agregar_standings_por_conferencia(standings: pd.DataFrame) -> pd.DataFrame:
    """Suma el récord de TODOS los equipos de la conferencia — un
    renglón único con el total de las 4 divisiones."""
    cols_sum = [c for c in ["V", "D", "E", "PF", "PC"] if c in standings.columns]
    agg = standings.groupby(["Conferencia"], as_index=False)[cols_sum].sum()
    total = agg["V"] + agg["D"] + agg["E"]
    agg["% Victorias"] = ((agg["V"] + 0.5 * agg["E"]) / total.replace(0, pd.NA) * 100).round(1).fillna(0.0)
    return agg


def tabla_conferencia_agregada_html(nombre_conferencia: str, filas_division: pd.DataFrame,
                                      fila_total: pd.Series, color_borde: str, color_nombre: str) -> str:
    """Tabla de comparación por división dentro de una conferencia — cada
    renglón es una división completa (suma de sus 4 equipos), y al final
    un renglón de TOTAL con la suma de toda la conferencia. Mismo
    lenguaje visual que tabla_division_html (blanco, líneas punteadas,
    encabezados grandes en negritas, texto negro, bordes redondeados)."""
    BLANCO = "#FFFFFF"
    NEGRO = "#14241A"
    PUNTEADO = "1px dotted #C7CBC3"
    tiene_extra = "PF" in filas_division.columns

    def _fila(nombre, row, es_total=False):
        pct = row["% Victorias"] / 100
        total_juegos = row["V"] + row["D"] + row["E"]
        pct_txt = "-" if total_juegos == 0 else f"{pct:.3f}".lstrip("0")
        peso = "800" if es_total else "700"
        borde = "" if es_total else f"border-bottom:{PUNTEADO};"
        extra_html = ""
        if tiene_extra:
            extra_html = f"""
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-size:0.85rem; font-weight:{peso}; {borde}">{int(row.get('PF', 0))}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-size:0.85rem; font-weight:{peso}; {borde} padding-right:14px;">{int(row.get('PC', 0))}</td>"""
        return f"""
        <tr>
            <td colspan="2" style="padding:8px 10px; font-weight:{peso}; color:{NEGRO}; white-space:nowrap;
                background:{BLANCO}; font-size:1rem; {borde}">{nombre}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-weight:{peso}; {borde}">{int(row['V'])}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-weight:{peso}; {borde}">{int(row['D'])}</td>
            <td style="text-align:center; color:{NEGRO}; background:{BLANCO}; white-space:nowrap; font-weight:{peso}; {borde}">{int(row['E'])}</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:{peso}; background:{BLANCO}; white-space:nowrap; {borde}">{pct_txt}</td>
            {extra_html}
        </tr>"""

    filas_html = "".join(_fila(row["División"], row) for _, row in filas_division.iterrows())
    filas_html += _fila(f"Total {nombre_conferencia}", fila_total, es_total=True)

    columnas_extra_header = ""
    colgroup_extra = ""
    if tiene_extra:
        columnas_extra_header = f'<td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">PF</td>'
        columnas_extra_header += f'<td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap; padding-right:14px;">PC</td>'
        colgroup_extra = "".join('<col style="width:56px;">' for _ in range(2))

    return _sin_sangria(f"""
    <div style="border:3px solid {color_borde}; border-radius:12px; overflow:hidden; margin-bottom:20px; min-width:420px; background:{BLANCO};">
    <table style="width:100%; border-collapse:collapse; font-family:'Inter',sans-serif; table-layout:fixed; background:{BLANCO};">
        <colgroup>
            <col style="width:42px;"><col><col style="width:46px;">
            <col style="width:46px;"><col style="width:46px;"><col style="width:72px;">
            {colgroup_extra}
        </colgroup>
        <tr style="background:{BLANCO};">
            <td colspan="2" style="padding:8px 10px; color:{color_nombre}; font-weight:700; white-space:nowrap;
                font-family:'Barlow Condensed',sans-serif; font-size:1.15rem;">{nombre_conferencia}</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">G</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">P</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">E</td>
            <td style="text-align:center; color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;">.PCT</td>
            {columnas_extra_header}
        </tr>
        {filas_html}
    </table>
    </div>
    """)


def avisar_temporadas_faltantes(stats: pd.DataFrame):
    """Si alguna temporada del combinado no se pudo descargar, avisa cuáles
    sí se usaron en vez de fallar en silencio o tumbar todo el resultado.
    También avisa si no se pudo agregar el desempeño de jugadores clave."""
    faltantes = stats.attrs.get("temporadas_faltantes")
    usadas = stats.attrs.get("temporadas_usadas")
    if faltantes:
        st.caption(f"⚠️ No se encontraron datos para {faltantes} — se usaron solo {usadas}.")

    error_jugadores = stats.attrs.get("jugadores_clave_error")
    if error_jugadores:
        st.caption(f"⚠️ No se pudo agregar el desempeño de jugadores clave (QB1/RB1/WR1/TE1): {error_jugadores}")


@st.cache_data(show_spinner=False, ttl=3600)
def stats_cacheadas(season: int, temporadas_historicas: int = 0) -> pd.DataFrame:
    """Cachea las estadísticas 1 hora — evita re-descargar en cada partido.
    Si temporadas_historicas > 0, combina esa cantidad de temporadas previas
    completas + lo disponible de `season` (normalizado por partido).
    Si es 0, usa solo `season` (comportamiento de una sola temporada).

    También intenta agregar el desempeño de QB1/RB1/WR1/TE1 de cada equipo.
    Si esa parte falla (cambios en nfl_data_py, datos faltantes, etc.), no
    tumba la app — simplemente sigue sin esas columnas (el modelo las
    ignora automáticamente si no están presentes)."""
    if temporadas_historicas > 0:
        stats = obtener_stats_combinadas(season, temporadas_historicas)
    else:
        stats = obtener_stats_temporada(season)

    try:
        jugadores = obtener_jugadores_clave(season, temporadas_historicas)
        stats = combinar_stats_con_jugadores(stats, jugadores)
    except Exception as e:
        stats.attrs["jugadores_clave_error"] = str(e)

    return stats


@st.cache_data(show_spinner=False, ttl=900)
def noticias_cacheadas(limite_por_fuente: int = 10):
    """Combina ESPN + NBC Sports + Yahoo Sports, sin duplicados."""
    return obtener_noticias_combinadas(limite_por_fuente)


@st.cache_data(show_spinner=False, ttl=900)
def noticias_equipo_cacheadas(team_abbr: str, limite: int = 10):
    return obtener_noticias_equipo(team_abbr, limite)


@st.cache_data(show_spinner=False, ttl=1800)
def calendario_equipo_cacheado(team_abbr: str, season: int):
    return obtener_calendario_equipo(team_abbr, season)


@st.cache_data(show_spinner=False, ttl=1800)
def roster_equipo_cacheado(team_abbr: str, season: int):
    return obtener_roster_equipo(team_abbr, season)


@st.cache_data(show_spinner=False, ttl=1800)
def jugadores_clave_cacheados(season: int):
    return obtener_jugadores_clave(season)


@st.cache_data(show_spinner=False, ttl=1800)
def lideres_estadisticos_cacheados(season: int, top_n: int = 10):
    return obtener_lideres_estadisticos(season, top_n)


def fila_equipos_alfabetica():
    """Fila horizontal con los 32 logos de equipo, en orden alfabético,
    cuadrados y alineados — cada logo es un hipervínculo real
    (?equipo=ABBR), sin depender de botones ni overlays de Streamlit."""
    orden_alfabetico = sorted(EQUIPOS)
    tarjetas = "".join(
        f'''<a href="?equipo={abbr}" target="_self" style="text-decoration:none; flex:0 0 auto;">
            <div style="width:38px; height:38px; background:#D8DBD4; border:1px solid #AEB4A9;
                 border-radius:6px; display:flex; align-items:center; justify-content:center;
                 box-shadow:0 2px 0 #8B9187, 0 3px 5px rgba(0,0,0,0.3);">
                <img src="{logo_url(abbr)}" style="width:29px; height:29px; object-fit:contain; display:block;">
            </div>
        </a>'''
        for abbr in orden_alfabetico
    )
    st.markdown(_sin_sangria(f"""
    <div style="display:flex; flex-wrap:wrap; justify-content:center; gap:5px; margin:4px 0 20px 0;">{tarjetas}</div>
    """), unsafe_allow_html=True)


def renderizar_noticias(noticias: list):
    """Grilla de 2 columnas: tarjeta gris con sombra, tamaño fijo y
    simétrico — foto (con la fuente sobrepuesta en la esquina) arriba,
    título y nota abajo, "Leer más" al final del párrafo — usado tanto
    en Noticias generales como por equipo."""
    if noticias and "error" in noticias[0]:
        st.info(f"No se pudieron cargar las noticias: {noticias[0]['error']}")
    elif not noticias:
        st.info("No hay noticias disponibles en este momento.")
    else:
        for i in range(0, len(noticias), 2):
            par = noticias[i:i + 2]
            cols = st.columns(2, gap="small")
            for col, n in zip(cols, par):
                with col:
                    link = n.get("link", "")
                    fuente = n.get("fuente", "")
                    imagen_html = ""
                    if n.get("imagen"):
                        img_tag = f"""
                        <div style="position:relative; flex-shrink:0;">
                            <img src="{n['imagen']}" style="width:100%; height:180px;
                                 object-fit:cover; object-position:center top; border-radius:6px; display:block;">
                            {f'<span style="position:absolute; bottom:6px; left:8px; background:rgba(189,78,30,0.9); color:#FFFFFF; font-weight:700; font-size:0.68rem; padding:2px 7px; border-radius:4px;">Leer más</span>' if link else ''}
                            {f'<span style="position:absolute; bottom:6px; right:8px; background:rgba(0,0,0,0.6); color:#FFFFFF; font-size:0.68rem; padding:2px 7px; border-radius:4px;">{fuente}</span>' if fuente else ''}
                        </div>"""
                        imagen_html = f'<a href="{link}">{img_tag}</a>' if link else img_tag

                    st.markdown(_sin_sangria(f"""
                    <div class="noticia-card">
                        {imagen_html}
                        <p class="noticia-titulo">{n['titulo']}</p>
                        <p class="noticia-desc">{n.get('descripcion', '')}</p>
                    </div>
                    """), unsafe_allow_html=True)


def grid_iconos_equipos():
    """Ya no se usa — se quitó la idea de noticias por equipo (el
    endpoint de ESPN por equipo no traía resultados)."""
    pass


@st.cache_data(show_spinner=False, ttl=900)
def lesiones_liga_cacheadas(limite: int = 25, season: int = None, api_key: str = ""):
    """Usa API-Sports si hay key configurada (más confiable); si no, o si
    falla, cae de vuelta al scraping de ESPN equipo por equipo."""
    if api_key:
        try:
            return obtener_lesiones_liga_api_sports(api_key, season, limite)
        except Exception as e:
            resultado = obtener_lesiones_liga(limite)
            if resultado and "error" not in resultado[0]:
                return resultado
            return [{"error": f"API-Sports falló ({e}) y el respaldo de ESPN también."}]
    return obtener_lesiones_liga(limite)


@st.cache_data(show_spinner=False, ttl=900)
def standings_cacheados(season: int, api_key: str = ""):
    """Usa API-Sports si hay key configurada (datos oficiales completos);
    si no, o si falla, cae de vuelta al cálculo manual desde nfl_data_py."""
    if api_key:
        try:
            return obtener_standings_api_sports(api_key, season)
        except Exception:
            pass
    return obtener_standings(season)


@st.cache_data(show_spinner=False, ttl=300)
def marcadores_cacheados(season: int, api_key: str = ""):
    """Marcadores de la semana actual — API-Sports si hay key (más
    confiable, incluye el marcador exacto); si no, respaldo con ESPN."""
    if api_key:
        try:
            return obtener_marcadores_api_sports(api_key, season)
        except Exception:
            pass
    crudo = obtener_marcadores_actuales()
    if crudo and "error" in crudo[0]:
        return []
    return [
        {
            "away_abbr": p["away_abbr"], "home_abbr": p["home_abbr"],
            "away_score": p["away_score"] if p["away_score"] not in ("-", "", None) else None,
            "home_score": p["home_score"] if p["home_score"] not in ("-", "", None) else None,
            "estado": "FT" if "final" in p.get("estado", "").lower() else "NS",
            "fecha": p.get("fecha", ""), "hora": "", "timestamp": None, "estadio": "", "ciudad": "",
        }
        for p in crudo
    ]


def ejecutar_comparacion(stats, equipo_a, equipo_b, local, usar_clima, usar_odds):
    """Corre el modelo para un partido y devuelve (resultado, clima) —
    lógica compartida entre el modo individual y el modo semana completa."""
    clima = None
    if usar_clima and local:
        clima = obtener_clima_estadio(local)
        if clima.get("error"):
            clima = None

    favorito = None
    if usar_odds:
        odds_df = obtener_lineas_apuestas()
        favorito = favorito_segun_mercado(odds_df, equipo_a, equipo_b)

    resultado = comparar_equipos(
        stats, equipo_a, equipo_b,
        local=local, favorito_mercado=favorito, clima_local=clima,
    )
    return resultado, clima


def encabezado_equipo(abbr: str, tamano_col=None):
    """Muestra el logo + nombre del equipo. Se usa dentro de columnas."""
    st.image(logo_url(abbr), width=48)
    st.markdown(f"**{nombre_equipo(abbr)}**")


def mostrar_resultado(resultado, equipo_a, equipo_b, clima=None, local=None, compacto=False,
                       boton_detalle_key=None, contexto_detalle=None):
    """Renderiza el resultado de una comparación. compacto=True usa un
    formato más chico, pensado para listas de varios partidos seguidos.
    Si boton_detalle_key se pasa (en modo compacto), agrega un botón que
    lleva a una página aparte con el desglose completo de ese partido."""
    puntaje = resultado["puntaje"]
    ganador = max(puntaje, key=puntaje.get)
    max_posible = sum(WEIGHTS.values()) + HOME_FIELD_BONUS
    prob = probabilidad_victoria(puntaje, equipo_a, equipo_b, max_posible)

    if compacto:
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            st.image(logo_url(equipo_a), width=36)
            st.metric(nombre_equipo(equipo_a), f"{puntaje[equipo_a]:.1f} pts", f"{prob[equipo_a]*100:.0f}%")
        with col2:
            st.image(logo_url(equipo_b), width=36)
            st.metric(nombre_equipo(equipo_b), f"{puntaje[equipo_b]:.1f} pts", f"{prob[equipo_b]*100:.0f}%")
        with col3:
            st.image(logo_url(ganador), width=36)
            st.metric("Pronóstico", NOMBRES_EQUIPO.get(ganador, ganador), f"{prob[ganador]*100:.0f}% prob.")
        st.progress(prob[equipo_a], text=f"{nombre_equipo(equipo_a)}: {prob[equipo_a]*100:.0f}%  vs  {nombre_equipo(equipo_b)}: {prob[equipo_b]*100:.0f}%")

        if boton_detalle_key and contexto_detalle:
            if st.button("🔍 Ver detalle completo", key=boton_detalle_key, use_container_width=True):
                st.session_state.detalle_partido = contexto_detalle
                st.session_state.pagina = "detalle"
                st.rerun()
    else:
        col_logo1, col_titulo, col_logo2 = st.columns([1, 4, 1])
        col_logo1.image(logo_url(equipo_a), width=64)
        col_titulo.subheader(f"🏆 {nombre_equipo(ganador)} ({prob[ganador]*100:.0f}% de probabilidad)")
        col_logo2.image(logo_url(equipo_b), width=64)

        col1, col2 = st.columns(2)
        col1.metric(nombre_equipo(equipo_a), f"{puntaje[equipo_a]:.1f} pts", f"{prob[equipo_a]*100:.1f}% de ganar")
        col2.metric(nombre_equipo(equipo_b), f"{puntaje[equipo_b]:.1f} pts", f"{prob[equipo_b]*100:.1f}% de ganar")
        st.progress(prob[equipo_a], text=f"{nombre_equipo(equipo_a)} {prob[equipo_a]*100:.0f}%  —  {prob[equipo_b]*100:.0f}% {nombre_equipo(equipo_b)}")

        st.divider()
        st.subheader("Desglose por categoría")
        st.caption(
            "Calificación de 1 (peor de la liga) a 10 (mejor de la liga) en esa métrica. "
            "Los puntos de cada categoría se reparten proporcional a esa calificación, "
            "no todo-o-nada."
        )
        filas = [
            {
                "Categoría": fila["categoria"],
                f"{nombre_equipo(equipo_a)} — valor": fila["valor_a"],
                f"{nombre_equipo(equipo_a)} — score": fila["score_a"],
                f"{nombre_equipo(equipo_a)} — pts": fila["puntos_a"],
                f"{nombre_equipo(equipo_b)} — valor": fila["valor_b"],
                f"{nombre_equipo(equipo_b)} — score": fila["score_b"],
                f"{nombre_equipo(equipo_b)} — pts": fila["puntos_b"],
            }
            for fila in resultado["desglose"]
        ]
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

        if clima:
            st.caption(f"Clima en {local}: {clima.get('temp_c', '?')}°C, viento {clima.get('viento_kmh', '?')} km/h")


# ============================================================
# NAVEGACIÓN ENTRE PANTALLAS (Inicio ↔ Pronósticos)
# ============================================================
if "pagina" not in st.session_state:
    st.session_state.pagina = "inicio"

# El logo de cada equipo es un hipervínculo real (?equipo=ABBR) — mucho
# más confiable que intentar cubrir toda la tarjeta con un botón
# invisible. Si llega ese parámetro en la URL, navega al detalle.
if st.query_params.get("equipo"):
    st.session_state.equipo_detalle = st.query_params["equipo"]
    st.session_state.pagina = "equipo_detalle"
    st.query_params.clear()

# Cada cuadrícula del ticker de resultados es un hipervínculo real
# (?partido=AWAY-HOME) a nuestra pantalla de detalle/comparación de ese
# partido — usa el mismo patrón de navegación por URL que los equipos.
if st.query_params.get("partido"):
    try:
        away_p, home_p = st.query_params["partido"].split("-")
        st.session_state.detalle_partido = {
            "away": away_p, "home": home_p,
            "season": datetime.date.today().year, "temporadas_historicas": 0,
        }
        st.session_state.pagina = "detalle"
    except Exception:
        pass
    st.query_params.clear()

# Detecta la zona horaria del navegador de quien ve la app (una sola vez
# por sesión) para mostrar los horarios de los partidos convertidos a su
# hora local, en vez de la hora cruda (UTC) que da la API. Mientras se
# detecta, usa America/Cancun como valor por default.
if "zona_horaria" not in st.session_state:
    tz_detectada = st.query_params.get("tz")
    if tz_detectada:
        st.session_state.zona_horaria = tz_detectada
        st.query_params.pop("tz", None)
    else:
        st.session_state.zona_horaria = "America/Cancun"
        components.html("""
        <script>
        try {
            const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
            const url = new URL(window.parent.location.href);
            if (url.searchParams.get('tz') !== tz) {
                url.searchParams.set('tz', tz);
                window.parent.location.href = url.toString();
            }
        } catch (e) {}
        </script>
        """, height=0)

if not NFL_DATA_PY_OK:
    st.error("nfl_data_py no está instalado en este entorno. Ejecuta: pip install nfl_data_py")
    st.stop()


# ============================================================
# PANTALLA: INICIO — solo noticias y lesiones recientes de la liga
# ============================================================
if st.session_state.pagina == "inicio":
    encabezado_sitio("inicio")

    hero(
        '<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">News</span>',
    )

    with st.spinner("Cargando noticias..."):
        noticias = noticias_cacheadas(25)

    principales = noticias[:10] if not (noticias and "error" in noticias[0]) else noticias
    pasadas = noticias[10:30] if not (noticias and "error" in noticias[0]) else []

    col_margen_izq, col_lista, col_principal, col_margen_der = st.columns([0.03, 0.7, 1.8, 0.47], gap="small")

    with col_lista:
        filas_html = ""
        for n in pasadas:
            link = n.get("link", "")
            titulo_html = f'<a href="{link}" style="color:#14241A; text-decoration:none; font-weight:700;">{n["titulo"]}</a>' if link else n["titulo"]
            filas_html += f"""
            <div style="background:#D8DBD4; border-radius:8px; box-shadow:0 3px 6px rgba(0,0,0,0.3);
                 padding:10px 12px; margin-bottom:8px; width:100%; max-width:100%; overflow:hidden;
                 box-sizing:border-box; display:flex; align-items:flex-start; gap:10px;">
                <span style="flex-shrink:0; font-size:0.9rem; line-height:1.4;">🏈</span>
                <span style="flex:1; min-width:0; font-size:0.85rem; line-height:1.4; color:#14241A;
                     text-align:left; word-break:break-word; overflow-wrap:anywhere; white-space:normal;">{titulo_html}</span>
            </div>"""
        st.markdown(_sin_sangria(f'<div style="width:100%; max-width:100%; overflow:hidden;">{filas_html}</div>'), unsafe_allow_html=True)

    with col_principal:
        renderizar_noticias(principales)

    st.stop()


# ============================================================
# PANTALLA: DETALLE DE EQUIPO — calendario, roster y standing
# ============================================================
if st.session_state.pagina == "equipo_detalle":
    encabezado_sitio("inicio")
    equipo_sel = st.session_state.get("equipo_detalle", "KC")
    season_equipo = datetime.date.today().year

    if st.button("← Volver a Noticias"):
        st.session_state.pagina = "inicio"
        st.rerun()

    hero(
        '<span style="color:#F1F4F9;">NFL</span> '
        f'<span style="color:#BD4E1E;">{NOMBRES_EQUIPO.get(equipo_sel, equipo_sel)} ({equipo_sel})</span>',
    )
    st.image(logo_url(equipo_sel), width=90)

    st.subheader("Standing")
    try:
        standings_eq = standings_cacheados(season_equipo, api_key=API_SPORTS_KEY)
        fila_eq = standings_eq[standings_eq["Equipo"] == equipo_sel]
        if fila_eq.empty:
            st.info("No se encontró el standing de este equipo todavía.")
        else:
            st.dataframe(fila_eq, use_container_width=True, hide_index=True)
    except Exception as e:
        st.info(f"No se pudo cargar el standing: {e}")

    st.divider()
    st.subheader("Calendario de la temporada")
    try:
        calendario_eq = calendario_equipo_cacheado(equipo_sel, season_equipo)
        st.dataframe(calendario_eq, use_container_width=True, hide_index=True)
    except Exception as e:
        st.info(f"No se pudo cargar el calendario: {e}")

    st.divider()
    st.subheader("Roster")
    try:
        roster_eq = roster_equipo_cacheado(equipo_sel, season_equipo)
        st.dataframe(roster_eq, use_container_width=True, hide_index=True)
    except Exception as e:
        st.info(f"No se pudo cargar el roster: {e}")

    st.stop()


# ============================================================
# PANTALLA: LESIONES — reporte de lesiones de toda la liga
# ============================================================
if st.session_state.pagina == "lesiones":
    encabezado_sitio("lesiones")
    hero(
        '<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Injuries</span>',
        "Reporte de lesiones recientes de toda la liga.",
    )

    st.divider()
    with st.spinner("Cargando lesiones..."):
        lesiones = lesiones_liga_cacheadas(season=datetime.date.today().year, api_key=API_SPORTS_KEY)

    if lesiones and "error" in lesiones[0]:
        st.info(f"No se pudo cargar el reporte de lesiones: {lesiones[0]['error']}")
    elif not lesiones:
        st.info("No hay lesiones de importancia reportadas en este momento.")
    else:
        df_lesiones = pd.DataFrame(lesiones)
        df_lesiones["equipo"] = df_lesiones["equipo"].map(lambda a: NOMBRES_EQUIPO.get(a, a))
        columnas = [c for c in ["equipo", "jugador", "posicion", "estado", "detalle"] if c in df_lesiones.columns]
        st.dataframe(df_lesiones[columnas], use_container_width=True, hide_index=True)

    st.stop()


# ============================================================
# PANTALLA: ESTADÍSTICAS — tabla de posiciones de la liga
# ============================================================
if st.session_state.pagina == "estadisticas":
    encabezado_sitio("estadisticas")
    hero('<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Standings</span>')

    with st.container(key="selector_temporada"):
        anio_actual = _temporada_nfl_actual()
        anios_disponibles = list(range(anio_actual, 2014, -1))
        season_standings = st.selectbox(
            "Temporada", anios_disponibles,
            index=0, key="season_standings", label_visibility="collapsed",
        )
    with st.spinner("Cargando tabla de posiciones..."):
        try:
            standings = standings_cacheados(season_standings, api_key=API_SPORTS_KEY)
            if standings.empty:
                st.info("No se pudo cargar la tabla de posiciones.")
            else:
                # Si subes tu propio archivo de logo (con derecho de uso) a la
                # carpeta del repo, pon aquí la ruta o URL y se muestra al
                # centro entre AFC y NFC. Vacío = no se muestra nada ahí.
                LOGO_CENTRAL_URL = ""

                st.markdown(_sin_sangria("""
                <style>
                .banda-conf { padding: 12px; text-align: center; border-radius: 10px;
                    font-family: 'Barlow Condensed', sans-serif; font-weight: 700;
                    font-size: 1.65rem; color: white; margin-bottom: 10px; }
                .emblema-nfl { position: sticky; top: 40%; text-align: center; }
                .emblema-nfl img { max-width: 100%; }
                </style>
                """), unsafe_allow_html=True)

                if LOGO_CENTRAL_URL:
                    col_afc, col_centro, col_nfc = st.columns([5, 1, 5])
                else:
                    col_afc, col_nfc = st.columns(2)
                    col_centro = None

                with col_afc:
                    st.markdown('<div class="banda-conf" style="background:#C8102E;">AFC Football Conference</div>', unsafe_allow_html=True)
                    afc_df = standings[standings["Conferencia"] == "AFC"]
                    for div in sorted(afc_df["División"].unique()):
                        filas = afc_df[afc_df["División"] == div].sort_values("% Victorias", ascending=False)
                        st.markdown(tabla_division_html(div, filas, "#DB8F6E", "#C8102E"), unsafe_allow_html=True)

                if col_centro is not None:
                    with col_centro:
                        st.markdown(f'<div class="emblema-nfl"><img src="{LOGO_CENTRAL_URL}"></div>', unsafe_allow_html=True)

                with col_nfc:
                    st.markdown('<div class="banda-conf" style="background:#1D4E8F;">NFC Football Conference</div>', unsafe_allow_html=True)
                    nfc_df = standings[standings["Conferencia"] == "NFC"]
                    for div in sorted(nfc_df["División"].unique()):
                        filas = nfc_df[nfc_df["División"] == div].sort_values("% Victorias", ascending=False)
                        st.markdown(tabla_division_html(div, filas, "#AEC2E0", "#1D4E8F"), unsafe_allow_html=True)

                st.divider()
                hero('<span style="color:#C8102E;">AFC</span> <span style="color:#F1F4F9;">vs</span> <span style="color:#1D4E8F;">NFC</span>')

                agregado_div = agregar_standings_por_division(standings)
                agregado_conf = agregar_standings_por_conferencia(standings)

                col_afc2, col_nfc2 = st.columns(2)
                with col_afc2:
                    divs_afc = agregado_div[agregado_div["Conferencia"] == "AFC"].sort_values("% Victorias", ascending=False)
                    total_afc = agregado_conf[agregado_conf["Conferencia"] == "AFC"].iloc[0]
                    st.markdown(
                        tabla_conferencia_agregada_html("AFC", divs_afc, total_afc, "#C8102E", "#C8102E"),
                        unsafe_allow_html=True,
                    )
                with col_nfc2:
                    divs_nfc = agregado_div[agregado_div["Conferencia"] == "NFC"].sort_values("% Victorias", ascending=False)
                    total_nfc = agregado_conf[agregado_conf["Conferencia"] == "NFC"].iloc[0]
                    st.markdown(
                        tabla_conferencia_agregada_html("NFC", divs_nfc, total_nfc, "#1D4E8F", "#1D4E8F"),
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"No se pudo cargar la tabla de posiciones: {e}")

    st.stop()


# ============================================================
# PANTALLA: DETALLE DE UN PARTIDO (llegada desde el botón "Ver detalle
# completo" en una lista de partidos)
# ============================================================
if st.session_state.pagina == "detalle":
    encabezado_sitio("pronosticos")
    ctx = st.session_state.get("detalle_partido")
    if st.button("← Volver a pronósticos"):
        st.session_state.pagina = "pronosticos"
        st.rerun()

    if not ctx:
        st.warning("No hay ningún partido seleccionado.")
        st.stop()

    away, home, season, temp_hist = ctx["away"], ctx["home"], ctx["season"], ctx["temporadas_historicas"]
    hero(f"{nombre_equipo(away)} @ {nombre_equipo(home)}")

    with st.spinner("Cargando detalle..."):
        try:
            stats = stats_cacheadas(season, temp_hist)
        except Exception as e:
            st.error(f"No se pudieron obtener las estadísticas: {e}")
            st.stop()

        if away not in stats["team"].values or home not in stats["team"].values:
            st.error("Uno de los equipos no tiene datos para esta temporada todavía.")
            st.stop()
        avisar_temporadas_faltantes(stats)

        resultado, clima = ejecutar_comparacion(stats, away, home, home, True, True)

    mostrar_resultado(resultado, away, home, clima=clima, local=home, compacto=False)
    st.stop()


# ============================================================
# PANTALLA: FANTASY (en construcción)
# ============================================================
if st.session_state.pagina == "fantasy":
    encabezado_sitio("fantasy")
    hero(
        '<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Fantasy</span>',
        "Jugadores destacados de la temporada — por equipo y por posición.",
    )

    season_fantasy = datetime.date.today().year

    tab_equipo, tab_posicion = st.tabs(["🏟️ Por equipo", "⭐ Por posición"])

    with tab_equipo:
        st.caption(
            "El 'titular' de cada equipo se define como el jugador con más producción "
            "acumulada en su especialidad (pase para QB, carrera para RB, recepción para WR/TE) — "
            "no usa datos oficiales de lesiones, así que puede no reflejar al titular actual real."
        )
        with st.spinner("Cargando jugadores clave..."):
            try:
                jugadores_eq = jugadores_clave_cacheados(season_fantasy)
            except Exception as e:
                jugadores_eq = None
                st.info(f"No se pudieron cargar los jugadores por equipo: {e}")

        if jugadores_eq is not None and not jugadores_eq.empty:
            for _, fila in jugadores_eq.iterrows():
                with st.container(border=True):
                    col_logo, col_datos = st.columns([1, 5])
                    with col_logo:
                        st.image(logo_url(fila["team"]), width=44)
                        st.markdown(f"**{NOMBRES_EQUIPO.get(fila['team'], fila['team'])}**")
                    with col_datos:
                        cols_pos = st.columns(4)
                        etiquetas = [
                            ("QB1", "qb1_nombre", "qb1_yardas_pase_pg", "yd/partido"),
                            ("RB1", "rb1_nombre", "rb1_yardas_carrera_pg", "yd/partido"),
                            ("WR1", "wr1_nombre", "wr1_yardas_recepcion_pg", "yd/partido"),
                            ("TE1", "te1_nombre", "te1_yardas_recepcion_pg", "yd/partido"),
                        ]
                        for col, (pos, campo_nombre, campo_valor, unidad) in zip(cols_pos, etiquetas):
                            with col:
                                nombre_j = fila.get(campo_nombre) or "—"
                                valor_j = fila.get(campo_valor, 0)
                                st.metric(pos, nombre_j, f"{valor_j:.1f} {unidad}" if nombre_j != "—" else "")

    with tab_posicion:
        with st.spinner("Cargando líderes por posición..."):
            try:
                lideres = lideres_estadisticos_cacheados(season_fantasy, 10)
            except Exception as e:
                lideres = None
                st.info(f"No se pudieron cargar los líderes por posición: {e}")

        if lideres is not None:
            col_pase, col_carrera, col_recepcion = st.columns(3)
            with col_pase:
                st.markdown("**🏈 Mejores QB (yardas de pase)**")
                st.dataframe(lideres["pase"], use_container_width=True, hide_index=True)
            with col_carrera:
                st.markdown("**🏃 Mejores RB (yardas de carrera)**")
                st.dataframe(lideres["carrera"], use_container_width=True, hide_index=True)
            with col_recepcion:
                st.markdown("**🙌 Mejores WR/TE (yardas de recepción)**")
                st.dataframe(lideres["recepcion"], use_container_width=True, hide_index=True)

    st.stop()


# ============================================================
# PANTALLA: BLOG — sección nueva, contenido aún por definir
# ============================================================
if st.session_state.pagina == "blog":
    encabezado_sitio("blog")
    hero('<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Insider</span>')
    st.info(
        "Todavía no hay nada armado aquí — dime qué te gustaría ver "
        "(artículos de opinión, análisis a fondo, columnas de autor, etc.) "
        "y lo construimos."
    )
    st.stop()


# ============================================================
# PANTALLA: PRONÓSTICOS (lo que antes era la app completa)
# ============================================================
encabezado_sitio("pronosticos")
hero(
    '<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Predictions</span>',
    "Modelo de puntaje ponderado basado en estadísticas históricas, clima y mercado de apuestas.",
)

# --- Ajustes del modelo: desplegable, solo visible en esta sección (no en el sidebar global) ---
with st.expander("⚙️ Ajustes del modelo (temporadas históricas y pesos)"):
    st.subheader("Datos históricos")
    temporadas_historicas = st.slider(
        "Temporadas pasadas a combinar con la actual", 0, 4, 2,
        help="0 = usar solo la temporada seleccionada. 2 = combina esa temporada "
             "más las 2 anteriores completas, normalizado por partido — recomendado "
             "para pronosticar partidos que aún no se juegan, cuando la temporada "
             "actual todavía tiene pocos datos.",
    )

    st.divider()
    st.subheader("Ajustar pesos del modelo")
    pesos_editados = {}
    cols_pesos = st.columns(2)
    for i, (categoria, valor) in enumerate(WEIGHTS.items()):
        with cols_pesos[i % 2]:
            pesos_editados[categoria] = st.slider(categoria, 0, 5, valor)
    WEIGHTS.update(pesos_editados)

    st.divider()
    clima_ok = "✅" if OPENWEATHER_API_KEY != "TU_API_KEY_AQUI" else "⭕ (sin API key)"
    odds_ok = "✅" if ODDS_API_KEY != "TU_API_KEY_AQUI" else "⭕ (sin API key)"
    st.caption(f"Clima: {clima_ok}  |  Línea de apuestas: {odds_ok}")

# Clima y línea de apuestas se intentan SIEMPRE automáticamente. Si no hay
# API key configurada en comparador_nfl.py, simplemente se omiten sin error
# (ver OPENWEATHER_API_KEY / ODDS_API_KEY al inicio de ese archivo).
usar_clima = True
usar_odds = True

tab_individual, tab_proxima, tab_manual = st.tabs([
    "🆚 Partido individual", "🔮 Próximos partidos (auto)", "📅 Semana específica (manual)",
])

# ============================================================
# PESTAÑA 1 — Partido individual
# ============================================================
with tab_individual:
    col_a, col_b = st.columns(2)
    season_ind = col_a.number_input("Temporada", min_value=2015, max_value=2027, value=datetime.date.today().year, key="season_ind")
    equipo_a = col_b.selectbox("Equipo A", EQUIPOS, index=EQUIPOS.index("KC"), format_func=nombre_equipo)
    equipo_b = st.selectbox("Equipo B", EQUIPOS, index=EQUIPOS.index("BUF"), format_func=nombre_equipo)

    col_logo_a, col_logo_b = st.columns(2)
    col_logo_a.image(logo_url(equipo_a), width=64)
    col_logo_b.image(logo_url(equipo_b), width=64)

    local = st.radio(
        "¿Quién juega de local?",
        [equipo_a, equipo_b, "Sede neutral"],
        format_func=lambda x: nombre_equipo(x) if x != "Sede neutral" else x,
        horizontal=True,
    )
    local = None if local == "Sede neutral" else local

    ejecutar = st.button("🔎 Comparar equipos", type="primary", use_container_width=True)

    if equipo_a == equipo_b:
        st.warning("Selecciona dos equipos distintos.")
    elif ejecutar:
        with st.spinner(f"Descargando estadísticas de la temporada {season_ind}..."):
            try:
                stats = stats_cacheadas(season_ind, temporadas_historicas)
            except Exception as e:
                st.error(f"No se pudieron obtener las estadísticas: {e}")
                st.stop()

        if equipo_a not in stats["team"].values or equipo_b not in stats["team"].values:
            st.error("Uno de los equipos no tiene datos para esta temporada todavía.")
            st.stop()
        avisar_temporadas_faltantes(stats)

        with st.spinner("Calculando..."):
            resultado, clima = ejecutar_comparacion(stats, equipo_a, equipo_b, local, usar_clima, usar_odds)
        mostrar_resultado(resultado, equipo_a, equipo_b, clima=clima, local=local)
    else:
        st.info("Elige los equipos y presiona **Comparar equipos**.")

# ============================================================
# PESTAÑA 2 — Próximos partidos (automático: detecta qué falta por jugar)
# ============================================================
with tab_proxima:
    st.write(
        "Detecta automáticamente la próxima semana con partidos **sin jugar** "
        "y los pronostica usando las estadísticas acumuladas de los partidos "
        "ya jugados esta temporada."
    )
    season_auto = st.number_input(
        "Temporada", min_value=2015, max_value=2027,
        value=datetime.date.today().year, key="season_auto",
    )
    buscar_proxima = st.button("🔮 Pronosticar próxima semana", type="primary", use_container_width=True)
    if buscar_proxima:
        st.session_state.mostrar_proxima = True

    if st.session_state.get("mostrar_proxima"):
        with st.spinner("Buscando la próxima semana con partidos pendientes..."):
            try:
                partidos = obtener_proximos_partidos(season_auto)
                semana_detectada = int(partidos["week"].iloc[0])
            except Exception as e:
                st.error(f"No se pudo obtener el calendario: {e}")
                st.stop()

        rango_txt = (
            f"{season_auto - temporadas_historicas}-{season_auto}"
            if temporadas_historicas > 0 else str(season_auto)
        )
        with st.spinner(f"Descargando estadísticas ({rango_txt})..."):
            try:
                stats = stats_cacheadas(season_auto, temporadas_historicas)
            except Exception as e:
                st.error(f"No se pudieron obtener estadísticas ({rango_txt}). Detalle: {e}")
                st.stop()

        st.success(f"Semana {semana_detectada} — {len(partidos)} partidos por jugarse.")
        avisar_temporadas_faltantes(stats)
        st.divider()

        for _, partido in partidos.iterrows():
            away, home = partido["away_team"], partido["home_team"]
            fecha = partido.get("gameday", "")
            hora = partido.get("gametime", "")

            if away not in stats["team"].values or home not in stats["team"].values:
                st.warning(
                    f"{nombre_equipo(away)} @ {nombre_equipo(home)} — todavía no hay "
                    f"suficientes partidos jugados de alguno de los dos para comparar."
                )
                continue

            with st.container(border=True):
                col_logo_a, col_titulo, col_logo_b = st.columns([1, 3, 1])
                col_logo_a.image(logo_url(away), width=40)
                col_titulo.markdown(f"**{nombre_equipo(away)} @ {nombre_equipo(home)}**  \n{fecha} {hora}")
                col_logo_b.image(logo_url(home), width=40)
                try:
                    resultado, _ = ejecutar_comparacion(stats, away, home, home, usar_clima, usar_odds)
                    mostrar_resultado(
                        resultado, away, home, compacto=True,
                        boton_detalle_key=f"detalle_auto_{away}_{home}_{season_auto}",
                        contexto_detalle={
                            "away": away, "home": home,
                            "season": season_auto, "temporadas_historicas": temporadas_historicas,
                        },
                    )
                except Exception as e:
                    st.error(f"No se pudo comparar este partido: {e}")
    else:
        st.info("Presiona **Pronosticar próxima semana** para traer los partidos pendientes automáticamente.")

# ============================================================
# PESTAÑA 3 — Semana específica (manual, puede incluir partidos ya jugados)
# ============================================================
with tab_manual:
    st.write("Trae los partidos programados de una semana puntual (útil para revisar semanas pasadas).")
    col_a, col_b = st.columns(2)
    season_sem = col_a.number_input("Temporada", min_value=2015, max_value=2027, value=datetime.date.today().year, key="season_sem")
    week_sem = col_b.number_input("Semana", min_value=1, max_value=22, value=1, key="week_sem")

    cargar_semana = st.button("📅 Cargar y comparar semana", type="primary", use_container_width=True)
    if cargar_semana:
        st.session_state.mostrar_semana = True

    if st.session_state.get("mostrar_semana"):
        with st.spinner(f"Buscando calendario de la semana {week_sem}..."):
            try:
                partidos = obtener_calendario_semana(season_sem, week_sem)
            except Exception as e:
                st.error(f"No se pudo obtener el calendario: {e}")
                st.stop()

        with st.spinner(f"Descargando estadísticas de la temporada {season_sem}..."):
            try:
                stats = stats_cacheadas(season_sem, temporadas_historicas)
            except Exception as e:
                st.error(f"No se pudieron obtener las estadísticas: {e}")
                st.stop()

        st.success(f"{len(partidos)} partidos encontrados para la semana {week_sem}.")
        avisar_temporadas_faltantes(stats)
        st.divider()

        for _, partido in partidos.iterrows():
            away, home = partido["away_team"], partido["home_team"]
            fecha = partido.get("gameday", "")
            hora = partido.get("gametime", "")

            if away not in stats["team"].values or home not in stats["team"].values:
                st.warning(f"{nombre_equipo(away)} @ {nombre_equipo(home)} — sin datos suficientes todavía.")
                continue

            with st.container(border=True):
                col_logo_a, col_titulo, col_logo_b = st.columns([1, 3, 1])
                col_logo_a.image(logo_url(away), width=40)
                col_titulo.markdown(f"**{nombre_equipo(away)} @ {nombre_equipo(home)}**  \n{fecha} {hora}")
                col_logo_b.image(logo_url(home), width=40)
                try:
                    resultado, _ = ejecutar_comparacion(stats, away, home, home, usar_clima, usar_odds)
                    mostrar_resultado(
                        resultado, away, home, compacto=True,
                        boton_detalle_key=f"detalle_manual_{away}_{home}_{season_sem}_{week_sem}",
                        contexto_detalle={
                            "away": away, "home": home,
                            "season": season_sem, "temporadas_historicas": temporadas_historicas,
                        },
                    )
                except Exception as e:
                    st.error(f"No se pudo comparar este partido: {e}")
    else:
        st.info("Elige temporada y semana, luego presiona **Cargar y comparar semana**.")
