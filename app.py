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

st.set_page_config(page_title="Comparador NFL", page_icon="🏈", layout="centered")


def inyectar_estilos():
    """Capa visual del sitio — tipografía condensada tipo marcador de
    estadio para títulos, Inter para el resto, acento dorado único
    (evita el look genérico de plantilla)."""
    st.markdown("""
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
        background: #FFB627;
        color: #0B0F1A;
        border: none;
        font-weight: 600;
        border-radius: 6px;
    }
    [data-testid="stButton"] button[kind="primary"]:hover {
        background: #FFC659;
        color: #0B0F1A;
    }
    [data-testid="stButton"] button:not([kind="primary"]) {
        border-radius: 6px;
        border: 1px solid #2A3348;
    }

    /* Métricas con el tono condensado del marcador */
    [data-testid="stMetricValue"] {
        font-family: 'Barlow Condensed', sans-serif;
        font-weight: 700;
    }
    [data-testid="stMetricLabel"] { color: #8B96AC; }

    /* Tabs: subrayado dorado en la pestaña activa */
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: #FFB627 !important;
        border-bottom-color: #FFB627 !important;
    }

    /* Barra de progreso (probabilidad) en dorado */
    [data-testid="stProgress"] > div > div > div {
        background-color: #FFB627 !important;
    }

    /* Sidebar con borde sutil */
    [data-testid="stSidebar"] { border-right: 1px solid #2A3348; }
    </style>
    """, unsafe_allow_html=True)


def hero(titulo: str, subtitulo: str = ""):
    """Encabezado con el mismo tono condensado en toda la app, con una
    barra de acento — más deliberado que un st.title suelto."""
    st.markdown(f"""
    <div style="border-left: 4px solid #FFB627; padding-left: 16px; margin-bottom: 8px;">
        <h1 style="margin: 0; font-size: 2.4rem;">{titulo}</h1>
        {f'<p style="color: #8B96AC; margin-top: 4px;">{subtitulo}</p>' if subtitulo else ''}
    </div>
    """, unsafe_allow_html=True)


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


def nombre_equipo(abbr: str) -> str:
    return f"{NOMBRES_EQUIPO.get(abbr, abbr)} ({abbr})"


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
    hero("🏈 NFL — Noticias", "Lo último de la liga, antes de ver los pronósticos.")

    if st.button("🔮 Ver pronósticos", type="primary", use_container_width=True):
        st.session_state.pagina = "pronosticos"
        st.rerun()

    if st.button("📊 Estadísticas (tabla de posiciones)", use_container_width=True):
        st.session_state.pagina = "estadisticas"
        st.rerun()

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
    if st.button("← Volver a inicio"):
        st.session_state.pagina = "inicio"
        st.rerun()

    hero("📊 Tabla de posiciones")
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
                standings = standings.copy()
                standings["Logo"] = standings["Equipo"].map(logo_url)
                standings["Equipo"] = standings["Equipo"].map(lambda a: NOMBRES_EQUIPO.get(a, a))

                if API_SPORTS_KEY and "PF" in standings.columns:
                    st.caption("📡 Datos oficiales en tiempo real vía API-Sports")

                columnas_orden = ["Logo", "Equipo", "V", "D", "E"]
                config_columnas = {
                    "Logo": st.column_config.ImageColumn("", width="small"),
                    "Equipo": st.column_config.TextColumn("Equipo", width="medium"),
                    "V": st.column_config.NumberColumn("V", width="small"),
                    "D": st.column_config.NumberColumn("D", width="small"),
                    "E": st.column_config.NumberColumn("E", width="small"),
                }
                if "PF" in standings.columns:
                    columnas_orden += ["PF", "PC"]
                    config_columnas["PF"] = st.column_config.NumberColumn("PF", width="small", help="Puntos a favor")
                    config_columnas["PC"] = st.column_config.NumberColumn("PC", width="small", help="Puntos en contra")
                if "Racha" in standings.columns:
                    columnas_orden.append("Racha")
                    config_columnas["Racha"] = st.column_config.TextColumn("Racha", width="small")
                columnas_orden.append("% Victorias")
                config_columnas["% Victorias"] = st.column_config.ProgressColumn(
                    "% Victorias", min_value=0, max_value=100, format="%.0f%%",
                )

                for conf in sorted(standings["Conferencia"].unique()):
                    st.subheader(conf)
                    conf_df = standings[standings["Conferencia"] == conf]
                    for div in sorted(conf_df["División"].unique()):
                        st.markdown(f"**{div}**")
                        st.dataframe(
                            conf_df[conf_df["División"] == div][columnas_orden],
                            use_container_width=True, hide_index=True,
                            column_config=config_columnas,
                        )
        except Exception as e:
            st.error(f"No se pudo cargar la tabla de posiciones: {e}")

    st.stop()


# ============================================================
# PANTALLA: DETALLE DE UN PARTIDO (llegada desde el botón "Ver detalle
# completo" en una lista de partidos)
# ============================================================
if st.session_state.pagina == "detalle":
    ctx = st.session_state.get("detalle_partido")
    if st.button("← Volver a pronósticos"):
        st.session_state.pagina = "pronosticos"
        st.rerun()

    if not ctx:
        st.warning("No hay ningún partido seleccionado.")
        st.stop()

    away, home, season, temp_hist = ctx["away"], ctx["home"], ctx["season"], ctx["temporadas_historicas"]
    hero(f"🔍 {nombre_equipo(away)} @ {nombre_equipo(home)}")

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
# PANTALLA: PRONÓSTICOS (lo que antes era la app completa)
# ============================================================
if st.button("← Volver a inicio"):
    st.session_state.pagina = "inicio"
    st.rerun()

hero("🏈 Comparador de equipos NFL", "Modelo de puntaje ponderado basado en estadísticas históricas, clima y mercado de apuestas.")

# --- Barra lateral: pesos del modelo (compartidos por las tres pestañas) ---
with st.sidebar:
    st.header("Datos históricos")
    temporadas_historicas = st.slider(
        "Temporadas pasadas a combinar con la actual", 0, 4, 2,
        help="0 = usar solo la temporada seleccionada. 2 = combina esa temporada "
             "más las 2 anteriores completas, normalizado por partido — recomendado "
             "para pronosticar partidos que aún no se juegan, cuando la temporada "
             "actual todavía tiene pocos datos.",
    )

    st.divider()
    st.header("Ajustar pesos del modelo")
    pesos_editados = {}
    for categoria, valor in WEIGHTS.items():
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
