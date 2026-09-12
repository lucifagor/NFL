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

from comparador_nfl import (
    obtener_stats_temporada,
    obtener_stats_combinadas,
    obtener_jugadores_clave,
    combinar_stats_con_jugadores,
    obtener_calendario_semana,
    obtener_proximos_partidos,
    obtener_clima_estadio,
    obtener_lineas_apuestas,
    obtener_noticias_nfl,
    obtener_lesiones_liga,
    obtener_lesiones_liga_api_sports,
    obtener_standings,
    obtener_standings_api_sports,
    obtener_marcadores_actuales,
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
        background: #F2994A;
        color: #14241A;
        border: none;
        font-weight: 600;
        border-radius: 6px;
    }
    [data-testid="stButton"] button[kind="primary"]:hover {
        background: #F5AD6E;
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
        color: #F2994A !important;
        border-bottom-color: #F2994A !important;
    }

    /* Barra de progreso (probabilidad) en dorado */
    [data-testid="stProgress"] > div > div > div {
        background-color: #F2994A !important;
    }

    /* Sidebar con borde sutil */
    [data-testid="stSidebar"] { border-right: 1px solid #26402F; }

    /* Franja de "campo cortado" — línea de yarda diagonal repetida */
    .franja-campo {
        height: 10px;
        background: repeating-linear-gradient(
            -45deg, #1F6B3A, #1F6B3A 10px, #2A8449 10px, #2A8449 20px
        );
        border-bottom: 2px solid #F2994A;
        margin: -1rem -1rem 1rem -1rem;
    }

    /* Ticker de marcadores — scroll horizontal */
    .ticker-marcadores {
        display: flex; gap: 10px; overflow-x: auto; padding: 4px 2px 12px 2px;
        margin-bottom: 12px; scrollbar-width: thin;
    }
    .ticker-juego {
        flex: 0 0 auto; background: #E9EBE8; border: 1px solid #D2D6D0;
        border-radius: 6px; padding: 8px 14px; min-width: 170px; max-width: 210px;
    }
    .ticker-equipo { display:flex; align-items:center; justify-content:space-between; gap:8px; }
    .ticker-equipo img { width:20px; height:20px; }
    .ticker-abbr { font-weight:700; font-size:0.85rem; color:#14241A; }
    .ticker-score { font-weight:700; font-size:0.85rem; color:#C97A2E; }
    .ticker-estado { font-size:0.7rem; color:#1F241E; text-align:center; margin-top:4px; line-height:1.3; white-space:normal; }
    .ticker-estadio { font-size:0.65rem; color:#5B6B60; text-align:center; margin-top:1px; line-height:1.3; white-space:normal; }
    </style>
    """), unsafe_allow_html=True)


def franja_campo():
    """Franja decorativa delgada tipo línea de yarda cortada, arriba de todo."""
    st.markdown('<div class="franja-campo"></div>', unsafe_allow_html=True)


_MESES_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
             7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


def _fecha_corta(fecha_iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(fecha_iso)
        return f"{d.day} {_MESES_ES[d.month]}"
    except Exception:
        return fecha_iso


def ticker_marcadores(partidos: list):
    """Renderiza el ticker horizontal de marcadores estilo NFL.com."""
    if not partidos:
        return
    tarjetas = ""
    for p in partidos:
        away_score = p["away_score"] if p["away_score"] is not None else "-"
        home_score = p["home_score"] if p["home_score"] is not None else "-"
        if p["estado"] in ("FT", "AOT"):
            linea1 = "Final" if p["estado"] == "FT" else "Final (OT)"
            linea2 = ""
        else:
            fecha_hora = " · ".join(x for x in [_fecha_corta(p["fecha"]) if p.get("fecha") else "", p.get("hora", "")] if x)
            linea1 = fecha_hora or "Por confirmar"
            linea2 = p.get("estadio", "")
        tarjetas += f"""
        <div class="ticker-juego">
            <div class="ticker-equipo">
                <img src="{logo_url(p['away_abbr'])}"><span class="ticker-abbr">{p['away_abbr']}</span>
                <span class="ticker-score">{away_score}</span>
            </div>
            <div class="ticker-equipo">
                <img src="{logo_url(p['home_abbr'])}"><span class="ticker-abbr">{p['home_abbr']}</span>
                <span class="ticker-score">{home_score}</span>
            </div>
            <div class="ticker-estado">{linea1}</div>
            {f'<div class="ticker-estadio">{linea2}</div>' if linea2 else ''}
        </div>"""
    st.markdown(_sin_sangria(f'<div class="ticker-marcadores">{tarjetas}</div>'), unsafe_allow_html=True)


def hero(titulo: str, subtitulo: str = ""):
    """Encabezado con el mismo tono condensado en toda la app, con una
    barra de acento — más deliberado que un st.title suelto."""
    st.markdown(_sin_sangria(f"""
    <div style="border-left: 4px solid #F2994A; padding-left: 16px; margin-bottom: 8px;">
        <h1 style="margin: 0; font-size: 2.4rem;">{titulo}</h1>
        {f'<p style="color: #9CB3A3; margin-top: 4px;">{subtitulo}</p>' if subtitulo else ''}
    </div>
    """), unsafe_allow_html=True)


def _escudo_svg(tamano: int = 40) -> str:
    """Escudo con 'W' — diseño geométrico original propio (no es el logo
    de la NFL ni de ningún equipo), para que la marca sea de NFLWarriors
    sin usar marcas registradas de terceros."""
    return f"""<svg width="{tamano}" height="{int(tamano*1.1)}" viewBox="0 0 44 48" xmlns="http://www.w3.org/2000/svg">
        <path d="M22 2 L42 9 L42 22 C42 34 33 43 22 46 C11 43 2 34 2 22 L2 9 Z"
              fill="#1C3324" stroke="#F2994A" stroke-width="2.5"/>
        <text x="22" y="33" font-family="'Barlow Condensed', sans-serif" font-weight="700"
              font-size="24" fill="#F2994A" text-anchor="middle">W</text>
    </svg>"""


def marca_completa():
    """Lockup completo de la marca — logo + wordmark + tagline. Se usa una
    sola vez, en la pantalla de Inicio."""
    st.markdown(_sin_sangria(f"""
    <div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">
        {_escudo_svg(52)}
        <div>
            <div style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:2.1rem; line-height:1; letter-spacing:0.01em;">
                <span style="color:#F1F4F9;">NFL</span> <span style="color:#F2994A;">WARRIORS</span>
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
            <span style="color:#F1F4F9;">NFL</span> <span style="color:#F2994A;">WARRIORS</span>
        </div>
    </div>
    """), unsafe_allow_html=True)


_SECCIONES_NAV = [
    ("inicio", "Noticias"),
    ("estadisticas", "Standings"),
    ("pronosticos", "Pronósticos"),
    ("fantasy", "Fantasy"),
]


def barra_navegacion(activo: str):
    """Menú horizontal tipo NFL.com — logo a la izquierda, secciones a la
    derecha. La sección activa se muestra resaltada (botón dorado); el
    resto, como link discreto."""
    st.markdown(_sin_sangria("""
    <style>
    .nav-marca { display:flex; align-items:center; gap:10px; height:100%; }
    </style>
    """), unsafe_allow_html=True)

    col_marca, col_nav = st.columns([2, 5])
    with col_marca:
        st.markdown(_sin_sangria(f"""
        <div class="nav-marca">
            {_escudo_svg(30)}
            <div style="font-family:'Barlow Condensed',sans-serif; font-weight:700; font-size:1.25rem;">
                <span style="color:#F1F4F9;">NFL</span> <span style="color:#F2994A;">WARRIORS</span>
            </div>
        </div>
        """), unsafe_allow_html=True)

    with col_nav:
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

    st.markdown('<hr style="border-color:#26402F; margin-top:0;">', unsafe_allow_html=True)


def encabezado_sitio(activo: str):
    """Encabezado compartido por TODA la app: franja de campo, menú de
    navegación, y el ticker de marcadores de la semana actual — se ve
    igual arriba de cualquier pantalla en la que estés."""
    franja_campo()
    barra_navegacion(activo)
    with st.spinner("Cargando marcadores..."):
        partidos_ticker = marcadores_cacheados(datetime.date.today().year, api_key=API_SPORTS_KEY)
    ticker_marcadores(partidos_ticker)


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
    """Genera una tabla de una división al estilo gráfico de transmisión
    deportiva: sub-encabezado en tono claro, filas oscuras, borde de color
    alrededor de toda la división (calcado del formato de referencia)."""
    filas_html = ""
    for _, row in filas.iterrows():
        pct = row["% Victorias"] / 100
        pct_txt = "-" if row["V"] == 0 else f"{pct:.3f}".lstrip("0")
        filas_html += f"""
        <tr>
            <td style="padding:6px 6px; background:#14241A;"><img src="{logo_url(row['Equipo'])}" width="24" style="vertical-align:middle;"></td>
            <td style="padding:8px 10px; font-weight:700; color:#F5F7FA; white-space:nowrap; background:#14241A; font-size:1rem;">{NOMBRES_COMPLETOS.get(row['Equipo'], row['Equipo'])}</td>
            <td style="text-align:center; color:#E4E8EF; background:#14241A; white-space:nowrap;">{row['V']}</td>
            <td style="text-align:center; color:#E4E8EF; background:#14241A; white-space:nowrap;">{row['D']}</td>
            <td style="text-align:center; color:#E4E8EF; background:#14241A; white-space:nowrap;">{row['E']}</td>
            <td style="text-align:center; color:#E4E8EF; font-weight:600; background:#14241A; white-space:nowrap;">{pct_txt}</td>
        </tr>"""

    return _sin_sangria(f"""
    <div style="border:3px solid {color_borde}; border-radius:4px; overflow:hidden; margin-bottom:20px; min-width:420px;">
    <table style="width:100%; border-collapse:collapse; font-family:'Inter',sans-serif; table-layout:fixed;">
        <colgroup>
            <col style="width:42px;"><col><col style="width:46px;">
            <col style="width:46px;"><col style="width:46px;"><col style="width:72px;">
        </colgroup>
        <tr style="background:{color_header};">
            <td colspan="2" style="padding:8px 10px; color:white; font-weight:700; white-space:nowrap;
                font-family:'Barlow Condensed',sans-serif; font-size:1.1rem;">{nombre_division}</td>
            <td style="text-align:center; color:white; font-weight:700; font-size:0.8rem; white-space:nowrap;">G</td>
            <td style="text-align:center; color:white; font-weight:700; font-size:0.8rem; white-space:nowrap;">P</td>
            <td style="text-align:center; color:white; font-weight:700; font-size:0.8rem; white-space:nowrap;">E</td>
            <td style="text-align:center; color:white; font-weight:700; font-size:0.8rem; white-space:nowrap;">.PCT</td>
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
def noticias_cacheadas(limite: int = 10):
    return obtener_noticias_nfl(limite)


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
            "fecha": p.get("fecha", ""), "hora": "", "estadio": "",
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

if not NFL_DATA_PY_OK:
    st.error("nfl_data_py no está instalado en este entorno. Ejecuta: pip install nfl_data_py")
    st.stop()


# ============================================================
# PANTALLA: INICIO — solo noticias y lesiones recientes de la liga
# ============================================================
if st.session_state.pagina == "inicio":
    encabezado_sitio("inicio")
    marca_completa()

    st.divider()
    hero("Noticias", "Lo último de la liga, antes de ver los pronósticos.")

    st.divider()
    st.subheader("📰 Noticias recientes")
    with st.spinner("Cargando noticias..."):
        noticias = noticias_cacheadas()

    if noticias and "error" in noticias[0]:
        st.info(f"No se pudieron cargar las noticias: {noticias[0]['error']}")
    elif not noticias:
        st.info("No hay noticias disponibles en este momento.")
    else:
        for n in noticias:
            with st.container(border=True):
                if n.get("imagen"):
                    col_img, col_txt = st.columns([1, 2])
                    col_img.image(n["imagen"], use_container_width=True)
                    with col_txt:
                        st.markdown(f"**{n['titulo']}**")
                        st.write(n.get("descripcion", ""))
                        if n.get("link"):
                            st.markdown(f"[Leer más]({n['link']})")
                else:
                    st.markdown(f"**{n['titulo']}**")
                    st.write(n.get("descripcion", ""))
                    if n.get("link"):
                        st.markdown(f"[Leer más]({n['link']})")

    st.divider()
    st.subheader("🤕 Lesiones recientes (toda la liga)")
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
    hero("Tabla de posiciones")
    season_standings = st.number_input(
        "Temporada", min_value=2015, max_value=2027,
        value=datetime.date.today().year, key="season_standings",
    )
    with st.spinner("Cargando tabla de posiciones..."):
        try:
            standings = standings_cacheados(season_standings, api_key=API_SPORTS_KEY)
            if standings.empty:
                st.info("No se pudo cargar la tabla de posiciones.")
            else:
                if API_SPORTS_KEY and "PF" in standings.columns:
                    st.caption("📡 Datos oficiales en tiempo real vía API-Sports")

                # Si subes tu propio archivo de logo (con derecho de uso) a la
                # carpeta del repo, pon aquí la ruta o URL y se muestra al
                # centro entre AFC y NFC. Vacío = no se muestra nada ahí.
                LOGO_CENTRAL_URL = ""

                st.markdown(_sin_sangria("""
                <style>
                .banda-conf { padding: 12px; text-align: center;
                    font-family: 'Barlow Condensed', sans-serif; font-weight: 700;
                    font-size: 1.5rem; color: white; margin-bottom: 10px; }
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
    hero("Fantasy", "Próximamente.")
    st.info(
        "Todavía no hay nada armado aquí — dime qué te gustaría ver "
        "(ligas, draft, waiver wire, proyecciones semanales, tu roster, etc.) "
        "y lo construimos."
    )
    st.stop()


# ============================================================
# PANTALLA: PRONÓSTICOS (lo que antes era la app completa)
# ============================================================
encabezado_sitio("pronosticos")
hero("Comparador de equipos", "Modelo de puntaje ponderado basado en estadísticas históricas, clima y mercado de apuestas.")

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
