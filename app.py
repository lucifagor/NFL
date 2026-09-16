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
import re
import pandas as pd
import datetime
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

from comparador_nfl import (
    obtener_stats_temporada,
    obtener_stats_combinadas,
    obtener_jugadores_clave,
    obtener_lideres_estadisticos,
    obtener_ranking_fantasy,
    obtener_ranking_fantasy_espn,
    POSICIONES_CON_FANTASY,
    POSICIONES_SIN_FANTASY,
    POSICIONES_ESPN,
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
    obtener_lesiones_espn,
    obtener_posiciones_liga,
    obtener_lesiones_equipo_api_sports,
    _APODOS_NFL,
    obtener_standings,
    obtener_standings_api_sports,
    obtener_marcadores_actuales,
    obtener_calendario_equipo,
    obtener_roster_equipo,
    _DIVISIONES_NFL,
    obtener_marcadores_api_sports,
    obtener_semana_actual_api_sports,
    obtener_marcadores_semana_api_sports,
    obtener_marcadores_semana,
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

from insider_content import (
    cargar_columnas_manuales,
    CATEGORIAS_LABEL,
    render_grid_teasers,
    render_articulo_completo,
    render_lista_archivo,
)

# Insider siempre muestra como máximo esta cantidad de notas en la grilla
# principal (5 filas de 2 columnas); el resto queda accesible desde el
# botón "Notas anteriores" al final de la página.
INSIDER_NOTAS_RECIENTES = 10

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
    div[class*="st-key-selector_lesiones"] { max-width: 260px; margin-bottom: 10px; }
    /* Navegación de semana en Scores — botones ◀/▶ pegados a los lados
       del título "WEEK N", en vez del selector desplegable anterior. */
    div[class*="st-key-nav_semana_scores"] { max-width: 320px; margin: 0 auto 6px auto; }
    div[class*="st-key-nav_semana_scores"] [data-testid="stHorizontalBlock"] { align-items: center; }
    div[class*="st-key-nav_semana_scores"] button {
        font-size: 1.4rem; font-weight: 800; line-height: 1; padding: 0.35rem 0;
    }

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


# Etiquetas en español para el periodo de un partido en vivo — cubre tanto
# el número de cuarto que da ESPN (1-4, 5 = tiempo extra) como los códigos
# cortos tipo "Q1"/"HT"/"OT" que da API-Sports.
_ETIQUETAS_PERIODO_NUM = {1: "1er cuarto", 2: "2do cuarto", 3: "3er cuarto", 4: "4to cuarto", 5: "Tiempo extra"}
_ETIQUETAS_PERIODO_COD = {
    "Q1": "1er cuarto", "Q2": "2do cuarto", "Q3": "3er cuarto", "Q4": "4to cuarto",
    "OT": "Tiempo extra", "HT": "Medio tiempo", "1H": "1ra mitad", "2H": "2da mitad",
}


def _texto_periodo_en_vivo(p: dict) -> str:
    """Texto para un partido EN VIVO — cuarto/periodo + minuto restante
    (ej. '2do cuarto · 7:45'), en vez de la hora programada y el estadio."""
    periodo = p.get("periodo")
    if isinstance(periodo, int):
        etiqueta = _ETIQUETAS_PERIODO_NUM.get(periodo, f"Cuarto {periodo}")
    else:
        etiqueta = _ETIQUETAS_PERIODO_COD.get(str(periodo).upper(), str(periodo) if periodo else "En vivo")
    reloj = p.get("reloj", "")
    return f"{etiqueta} · {reloj}" if reloj else etiqueta


def ticker_marcadores(partidos: list, standings: pd.DataFrame = None):
    """Renderiza el ticker horizontal de marcadores estilo NFL.com.
    Si el partido no se ha jugado, en vez de '-' muestra el récord
    ganados-perdidos de cada equipo en la temporada (ej. 3-4). Si el
    partido está EN VIVO, muestra el cuarto y el minuto de juego en vez
    de la hora programada y el estadio."""
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
        elif p.get("en_vivo"):
            linea1 = _texto_periodo_en_vivo(p)
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
# El logo oficial del Super Bowl cambia de diseño cada año y no hay una
# URL pública estable para "el logo de este año" — se usa en su lugar
# el escudo genérico de la NFL (mismo CDN de ESPN que ya usan los logos
# de equipo) para el centro del bracket de Playoff Picture.
LOGO_SUPER_BOWL_URL = "https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png"


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
    ("scores", "Scores"),
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


@st.fragment(run_every="60s")
def _ticker_con_auto_refresco():
    """Este pedazo de la página se vuelve a ejecutar solo cada 60
    segundos (sin recargar ni perder el resto de la pantalla), así que
    los resultados se actualizan sin que el usuario tenga que hacer
    nada. El caché de marcadores_cacheados dura 5 min, así que en la
    práctica los datos nuevos llegan cada vez que la API los actualiza."""
    with st.spinner("Cargando marcadores..."):
        partidos_ticker = marcadores_cacheados(datetime.date.today().year, api_key=API_SPORTS_KEY)
        try:
            standings_ticker = standings_cacheados(datetime.date.today().year, api_key=API_SPORTS_KEY)
        except Exception:
            standings_ticker = None
    ticker_marcadores(partidos_ticker, standings_ticker)


def encabezado_sitio(activo: str):
    """Encabezado compartido por TODA la app: franja de campo, resultados
    de la semana, menú de navegación, y la fila de logos de equipo — se
    ve igual arriba de cualquier pantalla en la que estés."""
    franja_campo()
    _ticker_con_auto_refresco()
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

# Color primario de cada equipo — se usa como fondo de cada mitad de la
# fila en la pantalla Scores (ver tabla_semana_scores_html), imitando el
# gráfico de "resultados de la semana" estilo NFL.com/ESPN.
_COLORES_EQUIPO = {
    "ARI": "#97233F", "ATL": "#A71930", "BAL": "#241773", "BUF": "#00338D",
    "CAR": "#0085CA", "CHI": "#0B162A", "CIN": "#FB4F14", "CLE": "#311D00",
    "DAL": "#041E42", "DEN": "#FB4F14", "DET": "#0076B6", "GB": "#203731",
    "HOU": "#03202F", "IND": "#002C5F", "JAX": "#101820", "KC": "#E31837",
    "LA": "#003594", "LAC": "#0080C6", "LV": "#000000", "MIA": "#008E97",
    "MIN": "#4F2683", "NE": "#0B162A", "NO": "#9F8958", "NYG": "#0B2265",
    "NYJ": "#125740", "PHI": "#004C54", "PIT": "#FFB612", "SEA": "#002244",
    "SF": "#AA0000", "TB": "#D50A0A", "TEN": "#4B92DB", "WAS": "#5A1414",
}
# Equipos cuyo color primario es muy claro — el texto/logo necesitan un
# texto oscuro encima en vez de blanco para mantenerse legibles.
_EQUIPOS_TEXTO_OSCURO = {"PIT"}


def nombre_equipo(abbr: str) -> str:
    return f"{NOMBRES_EQUIPO.get(abbr, abbr)} ({abbr})"


def tabla_division_html(nombre_division: str, filas: pd.DataFrame, color_header: str, color_borde: str) -> str:
    """Genera una tabla de una división usando divs (CSS Grid) en vez de
    <table> — así la línea punteada entre equipos es un border-bottom de
    div normal, el mismo mecanismo confiable que ya usa el marco de
    color exterior, en vez de bordes de celda con border-collapse (poco
    confiable entre navegadores). Fondo blanco uniforme, encabezados
    grandes en negritas, texto negro. Incluye G/P/E/%/PF/PC/Loc./Vis./Racha."""
    BLANCO = "#FFFFFF"
    NEGRO = "#14241A"
    PUNTEADO = "1.5px dotted #8B9187"
    tiene_extra = "PF" in filas.columns

    columnas_extra = " 48px 48px 48px 48px 74px" if tiene_extra else ""
    grid_cols = f"42px 175px 46px 46px 46px 72px{columnas_extra}"

    def _celda(contenido, extra_estilo=""):
        return f'<div style="text-align:center; color:{NEGRO}; {extra_estilo}">{contenido}</div>'

    encabezado_extra = ""
    if tiene_extra:
        for c in ["PF", "PC", "Loc.", "Vis."]:
            encabezado_extra += _celda(c, "font-weight:700; font-size:0.95rem;")
        encabezado_extra += _celda("Racha", "font-weight:700; font-size:0.95rem; padding-right:10px;")

    filas_html = ""
    for _, row in filas.iterrows():
        pct = row["% Victorias"] / 100
        pct_txt = "-" if row["V"] == 0 else f"{pct:.3f}".lstrip("0")
        extra_html = ""
        if tiene_extra:
            extra_html = (
                _celda(row.get("PF", ""), "font-size:0.85rem;")
                + _celda(row.get("PC", ""), "font-size:0.85rem;")
                + _celda(row.get("Loc", ""), "font-size:0.85rem;")
                + _celda(row.get("Vis", ""), "font-size:0.85rem;")
                + _celda(row.get("Racha", ""), "font-size:0.85rem; padding-right:10px;")
            )
        filas_html += f"""
        <div style="display:grid; grid-template-columns:{grid_cols}; align-items:center;
             background:{BLANCO}; border-bottom:{PUNTEADO}; padding:6px 0;">
            <div style="text-align:center;"><img src="{logo_url(row['Equipo'])}" width="24" style="vertical-align:middle;"></div>
            <div style="padding:0 10px; font-weight:700; color:{NEGRO}; white-space:nowrap; font-size:1rem;">{NOMBRES_COMPLETOS.get(row['Equipo'], row['Equipo'])}</div>
            {_celda(row['V'])}
            {_celda(row['D'])}
            {_celda(row['E'])}
            {_celda(pct_txt, "font-weight:600;")}
            {extra_html}
        </div>"""

    return _sin_sangria(f"""
    <div style="border:3px solid {color_borde}; border-radius:12px; overflow-x:auto; overflow-y:hidden; margin-bottom:20px; max-width:100%; background:{BLANCO};">
        <div style="display:grid; grid-template-columns:{grid_cols}; align-items:center;
             background:{BLANCO}; padding:8px 0;">
            <div style="grid-column:1 / span 2; padding:0 10px; color:{NEGRO}; font-weight:700; white-space:nowrap;
                font-family:'Barlow Condensed',sans-serif; font-size:1.15rem;">{nombre_division}</div>
            {_celda("G", "font-weight:700; font-size:0.95rem;")}
            {_celda("P", "font-weight:700; font-size:0.95rem;")}
            {_celda("E", "font-weight:700; font-size:0.95rem;")}
            {_celda(".PCT", "font-weight:700; font-size:0.95rem;")}
            {encabezado_extra}
        </div>
        {filas_html}
    </div>
    """)


def agregar_standings_por_division(standings: pd.DataFrame) -> pd.DataFrame:
    """Suma el récord de los equipos de cada división — un renglón por
    división en vez de uno por equipo."""
    cols_sum = [c for c in ["V", "D", "E", "PF", "PC"] if c in standings.columns]
    agg = standings.groupby(["Conferencia", "División"], as_index=False)[cols_sum].sum()
    agg["% Victorias"] = agg.apply(
        lambda r: round((r["V"] + 0.5 * r["E"]) / (r["V"] + r["D"] + r["E"]) * 100, 1)
        if (r["V"] + r["D"] + r["E"]) > 0 else 0.0,
        axis=1,
    )
    return agg


def agregar_standings_por_conferencia(standings: pd.DataFrame) -> pd.DataFrame:
    """Suma el récord de TODOS los equipos de la conferencia — un
    renglón único con el total de las 4 divisiones."""
    cols_sum = [c for c in ["V", "D", "E", "PF", "PC"] if c in standings.columns]
    agg = standings.groupby(["Conferencia"], as_index=False)[cols_sum].sum()
    agg["% Victorias"] = agg.apply(
        lambda r: round((r["V"] + 0.5 * r["E"]) / (r["V"] + r["D"] + r["E"]) * 100, 1)
        if (r["V"] + r["D"] + r["E"]) > 0 else 0.0,
        axis=1,
    )
    return agg


def tabla_conferencia_agregada_html(nombre_conferencia: str, filas_division: pd.DataFrame,
                                      fila_total: pd.Series, color_borde: str, color_nombre: str) -> str:
    """Tabla de comparación por división dentro de una conferencia — cada
    renglón es una división completa (suma de sus 4 equipos), y al final
    un renglón de TOTAL con la suma de toda la conferencia. Usa divs
    (CSS Grid) en vez de <table>, igual que tabla_division_html, para
    que la línea punteada sea un border-bottom de div confiable."""
    BLANCO = "#FFFFFF"
    NEGRO = "#14241A"
    PUNTEADO = "1.5px dotted #8B9187"
    tiene_extra = "PF" in filas_division.columns

    columnas_extra = " 56px 56px" if tiene_extra else ""
    grid_cols = f"42px 175px 46px 46px 46px 72px{columnas_extra}"

    def _celda(contenido, extra_estilo=""):
        return f'<div style="text-align:center; color:{NEGRO}; {extra_estilo}">{contenido}</div>'

    def _fila(nombre, row, es_total=False):
        pct = row["% Victorias"] / 100
        total_juegos = row["V"] + row["D"] + row["E"]
        pct_txt = "-" if total_juegos == 0 else f"{pct:.3f}".lstrip("0")
        peso = "800" if es_total else "700"
        borde = "" if es_total else f"border-bottom:{PUNTEADO};"
        extra_html = ""
        if tiene_extra:
            extra_html = (
                _celda(int(row.get("PF", 0)), f"font-size:0.85rem; font-weight:{peso};")
                + _celda(int(row.get("PC", 0)), f"font-size:0.85rem; font-weight:{peso}; padding-right:14px;")
            )
        return f"""
        <div style="display:grid; grid-template-columns:{grid_cols}; align-items:center;
             background:{BLANCO}; {borde} padding:6px 0;">
            <div style="grid-column:1 / span 2; padding:0 10px; font-weight:{peso}; color:{NEGRO}; white-space:nowrap; font-size:1rem;">{nombre}</div>
            {_celda(int(row['V']), f"font-weight:{peso};")}
            {_celda(int(row['D']), f"font-weight:{peso};")}
            {_celda(int(row['E']), f"font-weight:{peso};")}
            {_celda(pct_txt, f"font-weight:{peso};")}
            {extra_html}
        </div>"""

    filas_html = "".join(_fila(row["División"], row) for _, row in filas_division.iterrows())
    filas_html += _fila(f"Total {nombre_conferencia}", fila_total, es_total=True)

    encabezado_extra = ""
    if tiene_extra:
        encabezado_extra = (
            _celda("PF", "font-weight:700; font-size:0.95rem;")
            + _celda("PC", "font-weight:700; font-size:0.95rem; padding-right:14px;")
        )

    return _sin_sangria(f"""
    <div style="border:3px solid {color_borde}; border-radius:12px; overflow-x:auto; overflow-y:hidden; margin-bottom:20px; max-width:100%; background:{BLANCO};">
        <div style="display:grid; grid-template-columns:{grid_cols}; align-items:center; background:{BLANCO}; padding:8px 0;">
            <div style="grid-column:1 / span 2; padding:0 10px; white-space:nowrap;">
                <span style="background:{color_nombre}; color:#FFFFFF; font-weight:700; padding:4px 12px;
                    border-radius:6px; font-family:'Barlow Condensed',sans-serif; font-size:1.15rem; display:inline-block;">{nombre_conferencia}</span>
            </div>
            {_celda("G", "font-weight:700; font-size:0.95rem;")}
            {_celda("P", "font-weight:700; font-size:0.95rem;")}
            {_celda("E", "font-weight:700; font-size:0.95rem;")}
            {_celda(".PCT", "font-weight:700; font-size:0.95rem;")}
            {encabezado_extra}
        </div>
        {filas_html}
    </div>
    """)


def calcular_playoff_picture(standings: pd.DataFrame) -> dict:
    """A partir de la tabla de posiciones actual, arma el 'playoff
    picture' de cada conferencia: los 4 líderes de división (seeds 1-4,
    ordenados por % de victorias) y los 3 mejores comodines restantes
    (seeds 5-7), más el primer equipo que se queda fuera de la foto.
    Se recalcula cada vez que se llama — así se va moviendo solo
    conforme se juegan más partidos, sin que haya que tocar nada.

    Desempate simplificado: % de victorias y, si empatan, diferencial
    de puntos (PF-PC). No son los criterios de desempate oficiales
    completos de la NFL (que incluyen resultado entre los propios
    equipos, récord divisional/de conferencia, etc.), así que en casos
    muy cerrados el orden real de la liga puede diferir un poco."""
    resultado = {}
    for conf in ("AFC", "NFC"):
        conf_df = standings[standings["Conferencia"] == conf].copy()
        if conf_df.empty:
            resultado[conf] = {"clasificados": [], "primer_fuera": None}
            continue

        conf_df["_diff"] = conf_df["PF"] - conf_df["PC"]
        conf_df = conf_df.sort_values(["% Victorias", "_diff"], ascending=[False, False]).reset_index(drop=True)

        lideres = conf_df.groupby("División", sort=False).head(1)
        lideres = lideres.sort_values(["% Victorias", "_diff"], ascending=[False, False]).reset_index(drop=True)

        resto = conf_df[~conf_df["Equipo"].isin(lideres["Equipo"])].reset_index(drop=True)
        comodines = resto.head(3)
        primer_fuera = resto.iloc[3] if len(resto) > 3 else None

        def _registro(fila):
            txt = f"{int(fila['V'])}-{int(fila['D'])}"
            if fila.get("E", 0):
                txt += f"-{int(fila['E'])}"
            return txt

        clasificados = []
        for i, fila in lideres.iterrows():
            clasificados.append({
                "seed": i + 1, "equipo": fila["Equipo"], "tipo": "División",
                "division": fila["División"], "registro": _registro(fila),
            })
        for i, fila in comodines.iterrows():
            clasificados.append({
                "seed": len(lideres) + i + 1, "equipo": fila["Equipo"], "tipo": "Wild Card",
                "division": fila["División"], "registro": _registro(fila),
            })

        resultado[conf] = {
            "clasificados": clasificados,
            "primer_fuera": (
                {"equipo": primer_fuera["Equipo"], "division": primer_fuera["División"], "registro": _registro(primer_fuera)}
                if primer_fuera is not None else None
            ),
        }
    return resultado


def _titulo_columna_bracket_html(texto: str, color: str) -> str:
    """Encabezado de una columna del bracket, enmarcado en un cuadro del
    color de la conferencia — todas las columnas de un mismo lado
    (Wild Card, Divisional, Campeón) comparten el mismo color y el
    mismo estilo de cuadro, en vez de solo texto de color suelto."""
    return f"""
    <div style="border:2px solid {color}; border-radius:8px; padding:6px 6px; margin-bottom:8px;
         background:#FFFFFF; color:{color}; font-family:'Barlow Condensed',sans-serif; font-weight:800;
         font-size:0.72rem; text-align:center; white-space:nowrap; letter-spacing:0.02em;">{texto}</div>"""


def _caja_bracket_html(item: dict = None, color_borde: str = "#8B9187", vacio_texto: str = "") -> str:
    """Una casilla de la gráfica de bracket: con equipo (seed + logo +
    una etiqueta de si clasificó como campeón de División o como Wild
    Card) si ya se conoce, o vacía/punteada si esa ronda todavía no se
    define."""
    if item is None:
        return f"""
        <div style="background:#F1F3EF; border:2px dashed #C9CDC5; border-radius:10px; height:56px;
             display:flex; align-items:center; justify-content:center; color:#5C6B57; font-size:0.62rem;
             font-family:'Barlow Condensed',sans-serif; letter-spacing:0.05em; text-transform:uppercase;">{vacio_texto}</div>"""

    es_division = item.get("tipo") == "División"
    etiqueta = "DIV" if es_division else "WC"
    fondo_etiqueta = color_borde if es_division else "#FFFFFF"
    texto_etiqueta = "#FFFFFF" if es_division else color_borde

    return f"""
    <div style="background:#FFFFFF; border:2px solid {color_borde}; border-radius:10px; height:56px;
         display:flex; align-items:center; gap:7px; padding:0 10px;">
        <span style="font-family:'Barlow Condensed',sans-serif; font-weight:800; font-size:1.15rem;
             color:{color_borde}; width:20px; text-align:center; flex-shrink:0;">{item['seed']}</span>
        <img src="{logo_url(item['equipo'])}" style="width:34px; height:34px; object-fit:contain; flex-shrink:0;">
        <span style="color:#14241A; font-weight:800; font-size:0.95rem; text-transform:uppercase; white-space:nowrap;
             overflow:hidden; text-overflow:ellipsis; flex:1; min-width:0;">{item['equipo']}</span>
        <span style="background:{fondo_etiqueta}; color:{texto_etiqueta}; border:1px solid {color_borde};
             border-radius:5px; font-size:0.64rem; font-weight:800; padding:3px 5px; flex-shrink:0;
             font-family:'Barlow Condensed',sans-serif; letter-spacing:0.03em;">{etiqueta}</span>
    </div>"""


def bracket_visual_html(picture: dict) -> str:
    """Gráfica tipo 'bracket' de playoffs: ronda de Wild Card con los 7
    clasificados de cada conferencia (el 1 con 'bye') y casillas vacías
    para las rondas siguientes (Divisional, Campeón de Conferencia y
    Super Bowl), que se van llenando solas conforme avanza la
    postemporada real."""
    afc = {c["seed"]: c for c in picture.get("AFC", {}).get("clasificados", [])}
    nfc = {c["seed"]: c for c in picture.get("NFC", {}).get("clasificados", [])}
    COLOR_AFC, COLOR_NFC = "#C8102E", "#1D4E8F"

    def _columna_wc(mapa, color):
        cajas = [_caja_bracket_html(mapa.get(1), color)]
        for a, b in [(2, 7), (3, 6), (4, 5)]:
            cajas.append(_caja_bracket_html(mapa.get(a), color))
            cajas.append(_caja_bracket_html(mapa.get(b), color))
        return "".join(f'<div style="margin-bottom:9px;">{c}</div>' for c in cajas)

    def _columna_vacia(n, alto_extra=0):
        return "".join(
            f'<div style="margin-bottom:{6 + alto_extra}px;">{_caja_bracket_html(None, vacio_texto="POR DEFINIR")}</div>'
            for _ in range(n)
        )

    COLOR_SB = "#BD4E1E"

    return _sin_sangria(f"""
    <div style="background:#FFFFFF; border-radius:12px; padding:16px; margin-bottom:20px; overflow-x:auto;">
        <div style="display:flex; gap:12px; min-width:1080px; align-items:stretch; justify-content:center;">
            <div style="width:210px;">
                {_titulo_columna_bracket_html("AFC · WILD CARD", COLOR_AFC)}
                {_columna_wc(afc, COLOR_AFC)}
            </div>
            <div style="width:110px; display:flex; flex-direction:column; justify-content:center;">
                {_titulo_columna_bracket_html("DIVISIONAL", COLOR_AFC)}
                {_columna_vacia(2, alto_extra=48)}
            </div>
            <div style="width:110px; display:flex; flex-direction:column; justify-content:center;">
                {_titulo_columna_bracket_html("CAMPEÓN AFC", COLOR_AFC)}
                {_columna_vacia(1)}
            </div>
            <div style="width:110px; display:flex; flex-direction:column; justify-content:center; align-items:center;">
                {_titulo_columna_bracket_html("SUPER BOWL", COLOR_SB)}
                <img src="{LOGO_SUPER_BOWL_URL}" style="width:48px; height:48px; object-fit:contain; margin-top:4px;">
            </div>
            <div style="width:110px; display:flex; flex-direction:column; justify-content:center;">
                {_titulo_columna_bracket_html("CAMPEÓN NFC", COLOR_NFC)}
                {_columna_vacia(1)}
            </div>
            <div style="width:110px; display:flex; flex-direction:column; justify-content:center;">
                {_titulo_columna_bracket_html("DIVISIONAL", COLOR_NFC)}
                {_columna_vacia(2, alto_extra=48)}
            </div>
            <div style="width:210px;">
                {_titulo_columna_bracket_html("NFC · WILD CARD", COLOR_NFC)}
                {_columna_wc(nfc, COLOR_NFC)}
            </div>
        </div>
        <div style="display:flex; justify-content:center; gap:16px; margin-top:14px;">
            <span style="display:flex; align-items:center; gap:6px; color:#5C6B57; font-size:0.72rem;
                 font-family:'Barlow Condensed',sans-serif;">
                <span style="background:#8B9187; color:#FFFFFF; border-radius:4px; font-size:0.58rem; font-weight:800;
                     padding:3px 5px;">DIV</span> Campeón de división
            </span>
            <span style="display:flex; align-items:center; gap:6px; color:#5C6B57; font-size:0.72rem;
                 font-family:'Barlow Condensed',sans-serif;">
                <span style="background:#FFFFFF; color:#8B9187; border:1px solid #8B9187; border-radius:4px;
                     font-size:0.58rem; font-weight:800; padding:3px 5px;">WC</span> Wild Card
            </span>
        </div>
    </div>
    """)


def tabla_playoff_conferencia_html(nombre_conferencia: str, picture_conf: dict, color_borde: str) -> str:
    """Cuadro resumen de la conferencia para el 'playoff picture':
    campeones de división (seeds 1-4) y comodines/Wild Card (seeds
    5-7), con el primer equipo fuera de la foto como referencia — mismo
    lenguaje visual que las tablas de Standings (tarjeta blanca, borde
    de color, separador punteado)."""
    BLANCO = "#FFFFFF"
    NEGRO = "#14241A"
    GRIS = "#5C6B57"
    PUNTEADO = "1.5px dotted #8B9187"

    def _fila(item, es_ultimo=False):
        borde = "" if es_ultimo else f"border-bottom:{PUNTEADO};"
        etiqueta = "Campeón de división" if item["tipo"] == "División" else "Wild Card"
        return f"""
        <div style="display:flex; align-items:center; gap:12px; padding:8px 10px; {borde}">
            <span style="font-family:'Barlow Condensed',sans-serif; font-weight:800; font-size:1.2rem;
                 color:{color_borde}; width:20px; text-align:center; flex-shrink:0;">{item['seed']}</span>
            <img src="{logo_url(item['equipo'])}" width="28" style="flex-shrink:0;">
            <div style="flex:1; min-width:0;">
                <div style="color:{NEGRO}; font-weight:700; font-size:0.95rem; white-space:nowrap;
                     overflow:hidden; text-overflow:ellipsis;">{NOMBRES_COMPLETOS.get(item['equipo'], item['equipo'])}</div>
                <div style="color:{GRIS}; font-size:0.72rem;">{etiqueta} · {item['division']}</div>
            </div>
            <div style="color:{NEGRO}; font-weight:700; font-size:0.9rem; flex-shrink:0;">{item['registro']}</div>
        </div>"""

    clasificados = picture_conf.get("clasificados", [])
    primer_fuera = picture_conf.get("primer_fuera")
    filas_html = "".join(
        _fila(item, es_ultimo=(i == len(clasificados) - 1 and not primer_fuera))
        for i, item in enumerate(clasificados)
    )

    pie_html = ""
    if primer_fuera:
        pie_html = f"""
        <div style="padding:8px 10px; background:#F1F3EF;">
            <div style="color:{GRIS}; font-size:0.68rem; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px;">
                Primero fuera de la foto</div>
            <div style="display:flex; align-items:center; gap:10px;">
                <img src="{logo_url(primer_fuera['equipo'])}" width="22">
                <span style="color:{NEGRO}; font-weight:600; font-size:0.85rem;">{NOMBRES_COMPLETOS.get(primer_fuera['equipo'], primer_fuera['equipo'])}</span>
                <span style="color:{GRIS}; font-size:0.8rem; margin-left:auto;">{primer_fuera['registro']}</span>
            </div>
        </div>"""

    return _sin_sangria(f"""
    <div style="border:3px solid {color_borde}; border-radius:12px; overflow:hidden; margin-bottom:20px; background:{BLANCO};">
        <div style="background:{color_borde}; padding:10px; text-align:center;">
            <span style="font-family:'Barlow Condensed',sans-serif; font-weight:800; font-size:1.3rem;
                 color:#FFFFFF; letter-spacing:0.05em;">{nombre_conferencia}</span>
        </div>
        {filas_html}
        {pie_html}
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


@st.cache_data(show_spinner=False, ttl=1800)
def ranking_fantasy_cacheado(season: int, posicion: str = None, top_n: int = 50):
    return obtener_ranking_fantasy(season, posicion, top_n)


@st.cache_data(show_spinner=False, ttl=1800)
def ranking_fantasy_espn_cacheado(season: int, posicion_espn: str, top_n: int = 50):
    return obtener_ranking_fantasy_espn(season, posicion_espn, top_n)


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
def lesiones_equipo_cacheadas(team_abbr: str):
    """Lesiones de un solo equipo (para el desplegable de Injuries)."""
    return obtener_lesiones_espn(team_abbr)


@st.cache_data(show_spinner=False, ttl=3600)
def posiciones_liga_cacheadas(season: int):
    return obtener_posiciones_liga(season)


@st.cache_data(show_spinner=False, ttl=300)
def lesiones_equipo_api_sports_cacheadas(team_abbr: str, season: int, api_key: str):
    return obtener_lesiones_equipo_api_sports(api_key, season, team_abbr)


def lesiones_equipo_con_respaldo(team_abbr: str, season: int, api_key: str) -> list:
    """Si hay API key, consulta ese equipo específico directo en
    API-Sports (misma fuente confiable que 'Toda la liga', sin el
    recorte por fecha que podía dejar fuera a un equipo con lesiones
    menos recientes). Si no hay API key, o falla, usa el endpoint de
    ESPN por equipo; y si ese también viene vacío, cae a filtrar el
    listado completo de la liga por ese equipo."""
    if api_key:
        try:
            resultado = lesiones_equipo_api_sports_cacheadas(team_abbr, season, api_key)
            if resultado:
                return resultado
        except Exception:
            pass

    directo = lesiones_equipo_cacheadas(team_abbr)
    if directo and "error" not in directo[0]:
        return [dict(l, equipo=team_abbr) for l in directo]

    liga = lesiones_liga_cacheadas(limite=300, season=season, api_key=api_key)
    if liga and "error" not in liga[0]:
        return [l for l in liga if l.get("equipo") == team_abbr]
    return []


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


@st.cache_data(show_spinner=False, ttl=60)
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
            "en_vivo": p.get("en_vivo", False),
            "periodo": p.get("periodo"),
            "reloj": p.get("reloj", ""),
            "fecha": p.get("fecha", ""), "hora": "", "timestamp": None, "estadio": "", "ciudad": "",
        }
        for p in crudo
    ]


@st.cache_data(show_spinner=False, ttl=300)
def semana_actual_cacheada(season: int, api_key: str = "") -> int:
    """Número de semana a preseleccionar en Scores — misma lógica de
    corte (6am del día siguiente al último partido) que usa el ticker de
    marcadores. Sin API-Sports, usa la próxima semana con partidos
    pendientes como mejor estimado; si la temporada ya terminó, se queda
    en la semana 18."""
    if api_key:
        try:
            return obtener_semana_actual_api_sports(api_key, season)
        except Exception:
            pass
    try:
        return int(obtener_proximos_partidos(season)["week"].iloc[0])
    except Exception:
        return 18


@st.cache_data(show_spinner=False, ttl=1800)
def marcadores_semana_cacheados(season: int, week: int, api_key: str = ""):
    """Partidos (jugados o pendientes) de una semana ESPECÍFICA, para la
    pantalla Scores. API-Sports si hay key (incluye estado en vivo); si
    no, o si falla, respaldo con el calendario de nfl_data_py."""
    if api_key:
        try:
            return obtener_marcadores_semana_api_sports(api_key, season, week)
        except Exception:
            pass
    return obtener_marcadores_semana(season, week)


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


def _fila_score_semana(p: dict) -> str:
    """Una fila de la pantalla Scores: fondo blanco neutro de ambos lados
    (sin el color de cada equipo, que hacía ilegibles algunos logos),
    marcador o fecha/hora si el partido todavía no se juega, y
    "FINAL"/estado al centro."""
    away, home = p["away_abbr"], p["home_abbr"]
    NEGRO = "#14241A"
    ACENTO = "#BD4E1E"

    jugado = p["estado"] in ("FT", "AOT")
    if jugado:
        centro = "FINAL" if p["estado"] == "FT" else "FINAL (OT)"
        score_away = p.get("away_score") if p.get("away_score") is not None else "-"
        score_home = p.get("home_score") if p.get("home_score") is not None else "-"
    elif p.get("en_vivo"):
        centro = _texto_periodo_en_vivo(p)
        score_away = p.get("away_score") if p.get("away_score") is not None else "-"
        score_home = p.get("home_score") if p.get("home_score") is not None else "-"
    else:
        centro = _fecha_hora_local(p) or "Por jugarse"
        score_away = "-"
        score_home = "-"

    return f"""
    <div style="display:flex; align-items:stretch; justify-content:center; border-radius:12px; overflow:hidden;
         margin-bottom:16px; border:2px solid #E3E6E1; min-height:100px; max-width:900px;
         margin-left:auto; margin-right:auto;">
        <div style="flex:0 1 380px; background:#FFFFFF; display:flex; align-items:center;
             padding:0 16px; min-width:0;">
            <img src="{logo_url(away)}" style="width:48px; height:48px; object-fit:contain; flex-shrink:0; margin-right:12px;">
            <span style="color:{NEGRO}; font-weight:800; font-size:1.48rem;
                 min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                 text-transform:uppercase;">{NOMBRES_EQUIPO.get(away, away)}</span>
            <span style="color:{ACENTO}; font-weight:800; font-size:2rem; flex-shrink:0; margin-left:auto;
                 padding-left:16px;">{score_away}</span>
        </div>
        <div style="flex:0 0 auto; background:#F1F3EF; color:{NEGRO}; font-weight:700; font-size:1.36rem;
             display:flex; align-items:center; justify-content:center; padding:0 16px; text-align:center;
             min-width:136px; white-space:normal; line-height:1.2; border-left:2px solid #E3E6E1;
             border-right:2px solid #E3E6E1;">{centro}</div>
        <div style="flex:0 1 380px; background:#FFFFFF; display:flex; align-items:center;
             padding:0 16px; min-width:0;">
            <span style="color:{ACENTO}; font-weight:800; font-size:2rem; flex-shrink:0; margin-right:auto;
                 padding-right:12px;">{score_home}</span>
            <span style="color:{NEGRO}; font-weight:800; font-size:1.48rem;
                 min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                 text-transform:uppercase; margin-right:16px;">{NOMBRES_EQUIPO.get(home, home)}</span>
            <img src="{logo_url(home)}" style="width:48px; height:48px; object-fit:contain; flex-shrink:0;">
        </div>
    </div>"""


def tabla_semana_scores_html(partidos: list) -> str:
    """Bloque de resultados de la semana: una fila por partido (ver
    _fila_score_semana). El título "WEEK N" y la navegación entre
    semanas se muestran aparte, con controles nativos de Streamlit
    (ver pantalla Scores) para poder reaccionar a los botones ◀/▶."""
    filas = "".join(_fila_score_semana(p) for p in partidos)
    return _sin_sangria(f"""
    <div style="background:#FFFFFF; border-radius:16px; padding:20px 20px 6px 20px; margin-bottom:16px;
         max-width:940px; margin-left:auto; margin-right:auto; box-shadow:0 3px 10px rgba(0,0,0,0.25);">
        {filas}
    </div>
    """)


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

# Cada tarjeta teaser de Insider es un hipervínculo real (?articulo=ID) a
# la pantalla de artículo completo — mismo patrón que equipos y partidos.
if st.query_params.get("articulo"):
    st.session_state.articulo_detalle = st.query_params["articulo"]
    st.session_state.pagina = "articulo_detalle"
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
    hero('<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Injuries</span>')

    season_lesiones = datetime.date.today().year

    with st.spinner("Cargando lesiones..."):
        if st.session_state.get("equipo_lesiones", "Toda la liga") == "Toda la liga":
            lesiones = lesiones_liga_cacheadas(season=season_lesiones, api_key=API_SPORTS_KEY)
            lesiones = lesiones[:10] if lesiones and "error" not in lesiones[0] else lesiones
        else:
            lesiones = lesiones_equipo_con_respaldo(
                st.session_state.get("equipo_lesiones"), season_lesiones, API_SPORTS_KEY,
            )

        # Respaldo de posición: si la fuente de lesiones no la trae, se
        # busca por nombre en el roster completo de la liga (nfl_data_py).
        posiciones_respaldo = posiciones_liga_cacheadas(season_lesiones)

    col_tabla, col_noticias = st.columns([2.4, 1], gap="medium")

    with col_tabla:
        with st.container(key="selector_lesiones"):
            equipos_por_apodo = sorted(EQUIPOS, key=lambda a: _APODOS_NFL.get(a, a))
            equipo_filtro = st.selectbox(
                "Equipo", ["Toda la liga"] + equipos_por_apodo,
                format_func=lambda a: "Toda la liga" if a == "Toda la liga" else f"{NOMBRES_COMPLETOS.get(a, a)}",
                key="equipo_lesiones", label_visibility="collapsed",
            )

        muestra_equipo = equipo_filtro == "Toda la liga"

        if lesiones and "error" in lesiones[0]:
            st.info(f"No se pudo cargar el reporte de lesiones: {lesiones[0]['error']}")
        else:
            if equipo_filtro != "Toda la liga":
                st.markdown(_sin_sangria(f"""
                <div style="display:flex; align-items:center; gap:8px; margin-bottom:10px;">
                    <img src="{logo_url(equipo_filtro)}" width="26">
                    <span style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:1.2rem; color:#F1F4F9;">
                        {NOMBRES_EQUIPO.get(equipo_filtro, equipo_filtro)}</span>
                </div>
                """), unsafe_allow_html=True)
            else:
                st.markdown(_sin_sangria(f"""
                <div style="display:flex; align-items:center; gap:8px; margin-bottom:10px;">
                    <img src="{LOGO_ESCUDO_URL}" width="26">
                    <span style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:1.2rem; color:#F1F4F9;">NFL</span>
                </div>
                """), unsafe_allow_html=True)

            col_foto = "44px " if muestra_equipo else ""
            filas_html = ""
            # Siempre se muestran al menos 10 espacios — si hay menos
            # lesionados, se rellena con filas vacías del mismo diseño;
            # si hay más de 10, la caja simplemente crece.
            total_filas = max(len(lesiones), 10)
            for i in range(total_filas):
                fondo = "#FFFFFF" if i % 2 == 0 else "#F1F2EE"
                l = lesiones[i] if i < len(lesiones) else None

                if l is None:
                    filas_html += f"""
                    <div style="display:grid; grid-template-columns:{col_foto}{'40px ' if muestra_equipo else ''}1fr 55px 120px 2fr;
                         gap:10px; align-items:center; background:{fondo}; padding:10px 8px; min-height:20px;">
                        <div></div><div></div><div></div><div></div><div></div>
                    </div>"""
                    continue

                estado = l.get("estado", "") or ""
                e_min = estado.lower()
                if "quest" in e_min or "doubt" in e_min:
                    color_punto = "#E8A33D"
                elif "probable" in e_min or "active" in e_min:
                    color_punto = "#5CB85C"
                else:
                    color_punto = "#D9534F"

                celda_equipo = ""
                if muestra_equipo:
                    abbr = l.get("equipo", "")
                    celda_equipo = f'<div style="text-align:center;"><img src="{logo_url(abbr)}" width="20"></div>'

                # Rostro del jugador — solo si la fuente de datos lo trae
                # (API-Sports a veces incluye foto directa del jugador).
                celda_foto = ""
                if muestra_equipo:
                    foto = l.get("foto", "")
                    celda_foto = (
                        f'<div style="text-align:center;"><img src="{foto}" width="32" height="32" '
                        f'style="border-radius:50%; object-fit:cover;"></div>' if foto
                        else '<div></div>'
                    )

                posicion_txt = l.get("posicion", "") or posiciones_respaldo.get(l.get("jugador", ""), "") or "—"

                filas_html += f"""
                <div style="display:grid; grid-template-columns:{col_foto}{'40px ' if muestra_equipo else ''}1fr 55px 120px 2fr;
                     gap:10px; align-items:center; background:{fondo}; padding:10px 8px;">
                    {celda_foto}
                    {celda_equipo}
                    <div style="color:#1B5FBF; font-weight:600; font-size:0.92rem;">{l.get('jugador', '?')}</div>
                    <div style="color:#5A5A5A; font-size:0.85rem;">{posicion_txt}</div>
                    <div style="font-size:0.85rem; color:#14241A;"><span style="color:{color_punto};">●</span> {estado}</div>
                    <div style="color:#5A5A5A; font-size:0.82rem;">{l.get('detalle', '')}</div>
                </div>"""

            encabezado_cols = f"{col_foto}{'40px ' if muestra_equipo else ''}1fr 55px 120px 2fr"
            encabezado_celda_foto = '<div></div>' if muestra_equipo else ''
            encabezado_celda_equipo = '<div></div>' if muestra_equipo else ''
            st.markdown(_sin_sangria(f"""
            <div style="background:#FFFFFF; border-radius:10px; overflow:hidden; box-shadow:0 4px 10px rgba(0,0,0,0.3);">
                <div style="display:grid; grid-template-columns:{encabezado_cols}; gap:10px; padding:8px 8px;
                     border-bottom:2px solid #E4E6E1; font-size:0.75rem; font-weight:700; color:#7A7A7A; text-transform:uppercase;">
                    {encabezado_celda_foto}
                    {encabezado_celda_equipo}
                    <div>Name</div><div>Pos</div><div>Status</div><div>Comment</div>
                </div>
                {filas_html}
            </div>
            """), unsafe_allow_html=True)

            # Otras ausencias que no son lesión (suspensiones, motivos
            # personales, etc.) — no vienen del reporte oficial de
            # lesiones, así que se buscan por palabra clave en las
            # noticias (del equipo si hay uno elegido, si no de la liga).
            # Es un listado de titulares, no datos estructurados como la
            # tabla de arriba.
            palabras_ausencia = [
                "suspend", "suspension", "suspendido", "suspensión",
                "banned", "released", "cut by", "personal reasons",
                "not with the team", "away from the team",
            ]

            def _es_de_ausencia(n):
                texto = f"{n.get('titulo', '')} {n.get('descripcion', '')}".lower()
                return any(p in texto for p in palabras_ausencia)

            noticias_ausencia_fuente = noticias_cacheadas(30)
            if not (noticias_ausencia_fuente and "error" in noticias_ausencia_fuente[0]):
                if muestra_equipo:
                    ausencias = [n for n in noticias_ausencia_fuente if _es_de_ausencia(n)][:5]
                else:
                    apodo = _APODOS_NFL.get(equipo_filtro, "").lower()
                    ausencias = [
                        n for n in noticias_ausencia_fuente
                        if _es_de_ausencia(n) and apodo in f"{n.get('titulo', '')} {n.get('descripcion', '')}".lower()
                    ][:5]

                if ausencias:
                    st.markdown(_sin_sangria("""
                    <p style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:1rem;
                       color:#F1F4F9; margin:16px 0 8px 0;">Otras ausencias (no por lesión)</p>
                    """), unsafe_allow_html=True)
                    filas_ausencia = ""
                    for n in ausencias:
                        link = n.get("link", "")
                        filas_ausencia += f"""
                        <a href="{link}" style="text-decoration:none;">
                        <div style="background:#FFFFFF; border-radius:8px; box-shadow:0 3px 6px rgba(0,0,0,0.3);
                             padding:8px 10px; margin-bottom:6px;">
                            <span style="color:#14241A; font-size:0.85rem; font-weight:600;">{n['titulo']}</span>
                        </div>
                        </a>"""
                    st.markdown(_sin_sangria(f'<div>{filas_ausencia}</div>'), unsafe_allow_html=True)

    with col_noticias:
        # Espaciador para que "Injury News" quede a la misma altura que
        # el título con logo (equipo o "NFL") — ahora siempre existe ese
        # encabezado, así que el espaciador es el mismo en ambos casos.
        st.markdown('<div style="height:70px;"></div>', unsafe_allow_html=True)
        st.markdown(_sin_sangria("""
        <p style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:1.2rem;
           color:#F1F4F9; margin:0 0 10px 0;">Injury News</p>
        """), unsafe_allow_html=True)
        with st.spinner("Cargando noticias..."):
            noticias_todas = noticias_cacheadas(30)

        palabras_lesion = [
            "injury", "injured", "hurt", "out for", "sidelined", "ir ", "injured reserve",
            "surgery", "return", "recovery", "recovering", "questionable", "doubtful",
            "ruled out", "torn", "sprain", "fracture", "concussion", "acl", "achilles",
            "lesión", "lesionado", "cirugía", "recuperación", "baja",
        ]

        def _es_de_lesion(n):
            texto = f"{n.get('titulo', '')} {n.get('descripcion', '')}".lower()
            return any(p in texto for p in palabras_lesion)

        if noticias_todas and "error" in noticias_todas[0]:
            noticias_mini = []
        else:
            noticias_mini = [n for n in noticias_todas if _es_de_lesion(n)][:6]

        if not noticias_mini:
            st.caption("No hay noticias de lesiones en este momento.")
        else:
            filas_noticias = ""
            for n in noticias_mini:
                link = n.get("link", "")
                img_html = f'<img src="{n["imagen"]}" style="width:56px; height:56px; object-fit:cover; border-radius:6px; flex-shrink:0;">' if n.get("imagen") else ""
                filas_noticias += f"""
                <a href="{link}" style="text-decoration:none;">
                <div style="display:flex; gap:10px; background:#FFFFFF; border-radius:8px;
                     box-shadow:0 3px 6px rgba(0,0,0,0.3); padding:8px; margin-bottom:8px;">
                    {img_html}
                    <span style="color:#14241A; font-size:0.8rem; font-weight:600; line-height:1.3;">{n['titulo']}</span>
                </div>
                </a>"""
            st.markdown(_sin_sangria(f'<div>{filas_noticias}</div>'), unsafe_allow_html=True)

    st.stop()


# ============================================================
# PANTALLA: SCORES — resultados (o calendario, si no se han jugado) de
# la semana que el usuario elija, con diseño tipo "resumen semanal" de
# marcadores finales.
# ============================================================
if st.session_state.pagina == "scores":
    encabezado_sitio("scores")
    hero('<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Scores</span>')

    season_scores = _temporada_nfl_actual()

    try:
        semana_default = semana_actual_cacheada(season_scores, API_SPORTS_KEY)
    except Exception:
        semana_default = 1
    semana_default = min(max(int(semana_default), 1), 18)

    if "semana_scores_num" not in st.session_state:
        st.session_state.semana_scores_num = semana_default

    with st.container(key="nav_semana_scores"):
        col_izq, col_centro, col_der = st.columns([1, 2, 1])
        with col_izq:
            if st.button("◀", key="semana_scores_prev", use_container_width=True):
                st.session_state.semana_scores_num = max(1, st.session_state.semana_scores_num - 1)
        with col_der:
            if st.button("▶", key="semana_scores_next", use_container_width=True):
                st.session_state.semana_scores_num = min(18, st.session_state.semana_scores_num + 1)
        week_scores = st.session_state.semana_scores_num
        with col_centro:
            st.markdown(_sin_sangria(f"""
            <div style="text-align:center;">
                <div style="font-family:'Barlow Condensed',sans-serif; font-weight:800; font-size:2rem;
                     color:#F1F4F9; line-height:1;">WEEK {week_scores}</div>
                <div style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:0.9rem;
                     color:#BD4E1E; letter-spacing:0.08em; margin-top:2px;">RESULTADOS</div>
            </div>
            """), unsafe_allow_html=True)

    with st.spinner("Cargando resultados..."):
        try:
            partidos_semana = marcadores_semana_cacheados(season_scores, week_scores, API_SPORTS_KEY)
        except Exception as e:
            partidos_semana = []
            st.error(f"No se pudieron cargar los resultados de la semana {week_scores}: {e}")

    if not partidos_semana:
        st.info("No se encontraron partidos para esta semana.")
    else:
        st.markdown(tabla_semana_scores_html(partidos_semana), unsafe_allow_html=True)

    st.stop()


# ============================================================
# PANTALLA: ESTADÍSTICAS — tabla de posiciones de la liga
# ============================================================
if st.session_state.pagina == "estadisticas":
    encabezado_sitio("estadisticas")
    hero('<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Standings</span>')

    if st.button("Escenario de Playoffs", key="ir_a_playoffs", type="primary"):
        st.session_state.pagina = "playoffs"
        st.rerun()

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

                # Orden fijo Este / Norte / Oeste / Sur (no por % de victorias).
                def _orden_division(nombre_div: str) -> int:
                    for palabra, num in [("Este", 0), ("Norte", 1), ("Oeste", 2), ("Sur", 3)]:
                        if palabra in str(nombre_div):
                            return num
                    return 99

                agregado_div["_orden"] = agregado_div["División"].apply(_orden_division)
                agregado_div = agregado_div.sort_values("_orden", kind="mergesort").reset_index(drop=True)

                col_afc2, col_nfc2 = st.columns(2)
                with col_afc2:
                    divs_afc = agregado_div[agregado_div["Conferencia"] == "AFC"]
                    total_afc = agregado_conf[agregado_conf["Conferencia"] == "AFC"].iloc[0]
                    st.markdown(
                        tabla_conferencia_agregada_html("AFC", divs_afc, total_afc, "#C8102E", "#C8102E"),
                        unsafe_allow_html=True,
                    )
                with col_nfc2:
                    divs_nfc = agregado_div[agregado_div["Conferencia"] == "NFC"]
                    total_nfc = agregado_conf[agregado_conf["Conferencia"] == "NFC"].iloc[0]
                    st.markdown(
                        tabla_conferencia_agregada_html("NFC", divs_nfc, total_nfc, "#1D4E8F", "#1D4E8F"),
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"No se pudo cargar la tabla de posiciones: {e}")

    st.stop()


# ============================================================
# PANTALLA: PLAYOFF PICTURE — quién clasificaría a playoffs (campeones
# de división y wild cards de cada conferencia) según la tabla de
# posiciones actual. Se recalcula solo cada vez que se entra a esta
# pantalla, así que se va moviendo conforme se juegan más partidos —
# no hay que actualizar nada a mano.
# ============================================================
if st.session_state.pagina == "playoffs":
    encabezado_sitio("estadisticas")

    if st.button("← Volver a Standings"):
        st.session_state.pagina = "estadisticas"
        st.rerun()

    hero('<span style="color:#F1F4F9;">PLAYOFF</span> <span style="color:#BD4E1E;">PICTURE</span>')

    season_playoffs = _temporada_nfl_actual()
    standings_po = None
    with st.spinner("Calculando escenario de playoffs..."):
        try:
            standings_po = standings_cacheados(season_playoffs, api_key=API_SPORTS_KEY)
        except Exception as e:
            st.error(f"No se pudo cargar la tabla de posiciones: {e}")

    if standings_po is None or standings_po.empty:
        st.info("Todavía no hay suficientes partidos jugados para calcular el escenario de playoffs.")
    else:
        picture = calcular_playoff_picture(standings_po)

        st.markdown(bracket_visual_html(picture), unsafe_allow_html=True)

        col_afc_po, col_nfc_po = st.columns(2)
        with col_afc_po:
            st.markdown(tabla_playoff_conferencia_html("AFC", picture.get("AFC", {}), "#C8102E"), unsafe_allow_html=True)
        with col_nfc_po:
            st.markdown(tabla_playoff_conferencia_html("NFC", picture.get("NFC", {}), "#1D4E8F"), unsafe_allow_html=True)

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
    hero('<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Fantasy</span>')

    season_fantasy = datetime.date.today().year

    tab_ranking, tab_equipo, tab_posicion = st.tabs(["Ranking de puntos", "Por equipo", "Por posición"])

    with tab_ranking:
        posiciones_todas = POSICIONES_CON_FANTASY + ["K", "DST"] + POSICIONES_SIN_FANTASY
        col_pos, col_aire = st.columns([2, 3])
        with col_pos:
            posicion_sel = st.selectbox(
                "Posición", ["Todas"] + posiciones_todas, key="posicion_ranking_fantasy",
            )

        if posicion_sel in POSICIONES_SIN_FANTASY or posicion_sel in ("K", "DST"):
            motivo = (
                "el endpoint de fantasy de ESPN que intentamos usar para esta posición ya no "
                "responde sin sesión iniciada (nos redirige a la página de login)"
                if posicion_sel in ("K", "DST") else
                "es una posición de liga IDP (jugador defensivo individual), un formato que "
                "la mayoría de las ligas no usa, y ni siquiera el catálogo default de ESPN la trae"
            )
            st.info(
                f"Todavía no tenemos una fuente de puntos de fantasy para {posicion_sel} — {motivo}. "
                "En vez de inventar un número, lo dejamos vacío hasta conectar una fuente real."
            )
        else:
            with st.spinner("Cargando ranking de fantasy..."):
                try:
                    filtro_pos = None if posicion_sel == "Todas" else posicion_sel
                    ranking = ranking_fantasy_cacheado(season_fantasy, filtro_pos, 50)
                    col_usada = ranking.attrs.get("columna_usada", "fantasy_points_ppr")
                    temporada_usada = ranking.attrs.get("temporada_usada", season_fantasy)
                    aviso_temporada = (
                        f" (la {season_fantasy} todavía no tiene datos publicados, "
                        f"mostrando {temporada_usada})" if temporada_usada != season_fantasy else ""
                    )
                    st.caption(
                        f"Puntos calculados por nflverse ({'PPR' if 'ppr' in col_usada else 'estándar'}) "
                        f"para QB/RB/WR/TE — no incluye K/DST/IDP.{aviso_temporada}"
                    )
                    st.dataframe(ranking, use_container_width=True, hide_index=True)
                except Exception as e:
                    st.info(f"No se pudo cargar el ranking de fantasy: {e}")

    with tab_equipo:
        st.caption(
            "El 'titular' de cada equipo se define como el jugador con más producción "
            "acumulada en su especialidad (pase para QB, carrera para RB, recepción para WR/TE) — "
            "no usa datos oficiales de lesiones, así que puede no reflejar al titular actual real."
        )
        with st.spinner("Cargando jugadores clave..."):
            try:
                jugadores_eq = jugadores_clave_cacheados(season_fantasy)
                temporada_usada_eq = jugadores_eq.attrs.get("temporada_usada", season_fantasy)
                if temporada_usada_eq != season_fantasy:
                    st.caption(
                        f"La temporada {season_fantasy} todavía no tiene datos publicados — "
                        f"mostrando {temporada_usada_eq}."
                    )
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
# PANTALLA: INSIDER — notas periodísticas propias (independiente de
# Fantasy: aquí NO hay reportes automáticos ni datos de tu roster, solo
# las notas/columnas que tú escribes en insider_articles/).
# ============================================================
if st.session_state.pagina == "blog":
    encabezado_sitio("blog")
    hero(
        '<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Insider</span>',
    )

    with st.spinner("Cargando Insider..."):
        articulos = cargar_columnas_manuales()

    if not articulos:
        st.info(
            "Todavía no hay notas publicadas. Agrega un archivo `.md` dentro de "
            "`insider_articles/` (ver `insider_articles/_LEEME.md`) y súbelo a tu repo — "
            "aparecerá aquí automáticamente."
        )
    else:
        categorias_presentes = sorted(
            {a.get("categoria") for a in articulos if a.get("categoria")},
            key=lambda c: list(CATEGORIAS_LABEL).index(c) if c in CATEGORIAS_LABEL else 99,
        )
        if len(categorias_presentes) > 1:
            etiquetas = ["Todas"] + [CATEGORIAS_LABEL.get(c, c) for c in categorias_presentes]
            filtro = st.radio("Filtrar", etiquetas, horizontal=True, label_visibility="collapsed")
            if filtro != "Todas":
                categoria_filtro = next(c for c in categorias_presentes if CATEGORIAS_LABEL.get(c, c) == filtro)
                articulos = [a for a in articulos if a.get("categoria") == categoria_filtro]

        # La grilla principal siempre muestra como máximo las 10 notas más
        # recientes (5 filas de 2) — el resto se archiva y se accede con el
        # botón de abajo, para que Insider no crezca sin límite en pantalla.
        recientes = articulos[:INSIDER_NOTAS_RECIENTES]
        anteriores = articulos[INSIDER_NOTAS_RECIENTES:]

        render_grid_teasers(recientes)

        if anteriores:
            st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)
            if st.button(f"📜 Notas anteriores ({len(anteriores)})", use_container_width=True):
                st.session_state.insider_archivo_ids = [a["id"] for a in anteriores]
                st.session_state.pagina = "blog_archivo"
                st.rerun()

    st.stop()


# ============================================================
# PANTALLA: INSIDER — NOTAS ANTERIORES (archivo de notas que ya salieron
# de la grilla principal por antigüedad; solo título, primera frase y
# fecha, sin foto ni tarjeta — se accede desde el botón al fondo de
# Insider).
# ============================================================
if st.session_state.pagina == "blog_archivo":
    encabezado_sitio("blog")

    if st.button("← Volver a Insider"):
        st.session_state.pagina = "blog"
        st.rerun()

    hero(
        '<span style="color:#F1F4F9;">NFL</span> <span style="color:#BD4E1E;">Insider</span>',
        "Notas anteriores",
    )

    with st.spinner("Cargando notas anteriores..."):
        todos = cargar_columnas_manuales()

    ids_archivo = st.session_state.get("insider_archivo_ids", [])
    por_id = {a["id"]: a for a in todos}
    anteriores = [por_id[i] for i in ids_archivo if i in por_id]

    render_lista_archivo(anteriores)

    st.stop()


# ============================================================
# PANTALLA: ARTÍCULO COMPLETO DE INSIDER (llegada desde una tarjeta
# teaser de la grilla de Insider)
# ============================================================
if st.session_state.pagina == "articulo_detalle":
    encabezado_sitio("blog")

    if st.button("← Volver a Insider"):
        st.session_state.pagina = "blog"
        st.rerun()

    articulo_id = st.session_state.get("articulo_detalle")

    with st.spinner("Cargando artículo..."):
        articulos = cargar_columnas_manuales()

    art = next((a for a in articulos if a.get("id") == articulo_id), None)
    if not art:
        st.warning("No se encontró esa nota — puede que ya no esté disponible.")
        st.stop()

    render_articulo_completo(art)
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
