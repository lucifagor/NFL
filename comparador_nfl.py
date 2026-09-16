"""
Comparador de equipos NFL — modelo de pronóstico basado en puntaje ponderado
==============================================================================

Combina:
  - nfl_data_py: estadísticas históricas de equipo (ofensiva/defensiva) desde
    play-by-play público de nflverse.
  - ESPN API (no oficial): lesiones, roster y récord reciente.
  - OpenWeatherMap: clima esperado en el estadio (requiere API key gratuita).
  - The Odds API: línea de apuestas (spread) y movimiento (requiere API key,
    tiene plan gratuito limitado).

Instalación:
    pip install nfl_data_py pandas requests

API keys necesarias (variables al inicio de cada sección):
    OPENWEATHER_API_KEY  -> https://openweathermap.org/api (gratis, con límite)
    ODDS_API_KEY         -> https://the-odds-api.com (gratis, con límite)

Uso básico (al final del archivo, en `if __name__ == "__main__"`):
    python comparador_nfl.py

Este script automatiza ~35 de las 50 variables originales (estadísticas de
equipo, clima y línea de apuestas). Lo que queda como INPUT_MANUAL son
factores de juicio (motivación, "trap games", historial de entrenador vs
rival específico), difíciles de sacar de una API limpia.
"""

from __future__ import annotations  # compatibilidad con Python 3.9 (str | None, etc.)

import datetime
import math
import re
import pandas as pd
import requests
import json
import feedparser
from zoneinfo import ZoneInfo

try:
    import nfl_data_py as nfl
    NFL_DATA_PY_OK = True
except ImportError:
    NFL_DATA_PY_OK = False
    print("⚠️  nfl_data_py no está instalado. Ejecuta: pip install nfl_data_py")


# ---------------------------------------------------------------------------
# 1. PESOS DEL MODELO — ajusta estos valores según tu criterio
# ---------------------------------------------------------------------------
WEIGHTS = {
    "defensa_puntos_permitidos": 3,
    "defensa_yardas_permitidas": 2,
    "defensa_pase_permitido": 2,
    "defensa_run_permitido": 2,
    "defensa_turnovers_forzados": 3,
    "ataque_puntos": 3,
    "ataque_yardas_totales": 2,
    "ataque_pase": 2,
    "ataque_run": 2,
    "ataque_turnovers_cometidos": 3,
    "eficiencia_3er_down": 2,
    "eficiencia_zona_roja": 2,
    "qb_rating": 3,
    "forma_reciente": 3,
    "local_visitante": 2,
    "lesiones": 2,  # negativo si hay bajas clave
    "clima": 1,          # ventaja para el equipo acostumbrado a esas condiciones
    "linea_apuestas": 2,  # a favor del equipo favorito por el mercado
    "qb1_desempeno": 4,   # producción del quarterback titular (yardas+TD de pase, menos INT)
    "rb1_desempeno": 3,   # producción del corredor titular (yardas de carrera por partido)
    "wr1_desempeno": 3,   # producción del receptor abierto titular (yardas de recepción por partido)
    "te1_desempeno": 2,   # producción del ala cerrada titular (yardas de recepción por partido)
}

HOME_FIELD_BONUS = 1.5  # puntos extra fijos para el equipo local


# ---------------------------------------------------------------------------
# 2. DATOS DE EQUIPO VÍA nfl_data_py (estadísticas por temporada)
# ---------------------------------------------------------------------------
def _agregar_stats_equipo(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega play-by-play (de una o varias temporadas ya concatenadas) en
    estadísticas por equipo, normalizadas a PROMEDIO POR PARTIDO. Esto es
    lo que permite combinar temporadas completas con una temporada actual
    a medias sin que el tamaño de muestra distorsione la comparación.
    """
    if pbp is None or pbp.empty or "posteam" not in pbp.columns:
        raise ValueError("No hay datos jugada-por-jugada disponibles para las temporadas solicitadas.")

    # Puntos: sumamos el marcador FINAL de cada partido (no el máximo de
    # todo el rango de temporadas, que subestimaría equipos con muchos juegos).
    puntos_favor = (
        pbp.groupby(["posteam", "game_id"])["posteam_score_post"].max()
        .groupby("posteam").sum()
    )
    puntos_contra = (
        pbp.groupby(["defteam", "game_id"])["posteam_score_post"].max()
        .groupby("defteam").sum()
    )
    juegos_ataque = pbp.groupby("posteam")["game_id"].nunique()
    juegos_defensa = pbp.groupby("defteam")["game_id"].nunique()

    ataque = pbp.groupby("posteam").agg(
        yardas_pase=("passing_yards", "sum"),
        yardas_run=("rushing_yards", "sum"),
        turnovers_cometidos=("interception", "sum"),
        fumbles_perdidos=("fumble_lost", "sum"),
    )
    ataque["turnovers_cometidos"] += ataque["fumbles_perdidos"]
    ataque["puntos_ataque"] = puntos_favor
    ataque["juegos"] = juegos_ataque

    defensa = pbp.groupby("defteam").agg(
        yardas_pase_permitidas=("passing_yards", "sum"),
        yardas_run_permitidas=("rushing_yards", "sum"),
        turnovers_forzados=("interception", "sum"),
    )
    defensa["puntos_permitidos"] = puntos_contra
    defensa["juegos_def"] = juegos_defensa

    stats = ataque.join(defensa, how="outer").fillna(0)
    stats = stats.rename_axis("team").reset_index()

    # Normaliza a promedio por partido (usa "juegos" de ataque; si un equipo
    # solo tiene datos de defensa por algún hueco de datos, usa juegos_def).
    juegos = stats["juegos"].mask(stats["juegos"] == 0, stats["juegos_def"])
    juegos = juegos.mask(juegos == 0, 1)
    for col in [
        "puntos_ataque", "yardas_pase", "yardas_run", "turnovers_cometidos",
        "puntos_permitidos", "yardas_pase_permitidas", "yardas_run_permitidas",
        "turnovers_forzados",
    ]:
        stats[col] = stats[col] / juegos

    return stats.drop(columns=["fumbles_perdidos", "juegos", "juegos_def"], errors="ignore")


def obtener_stats_temporada(season: int) -> pd.DataFrame:
    """
    Descarga play-by-play de UNA temporada y agrega estadísticas ofensivas
    y defensivas por equipo (promedio por partido). Puede tardar ~30-60s la
    primera vez (cachea localmente después).
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    pbp = nfl.import_pbp_data([season], downcast=True)
    try:
        return _agregar_stats_equipo(pbp)
    except ValueError:
        raise ValueError(
            f"Todavía no hay suficientes datos jugada-por-jugada publicados "
            f"para la temporada {season} (puede ser que la temporada acabe "
            f"de empezar). Prueba con la temporada anterior mientras tanto."
        )


def obtener_stats_combinadas(season_actual: int, temporadas_historicas: int = 2) -> pd.DataFrame:
    """
    Combina estadísticas de las últimas `temporadas_historicas` temporadas
    COMPLETAS más lo que haya disponible de `season_actual` (aunque esté a
    medias), todo normalizado a promedio por partido para que sea comparable.

    Ej: obtener_stats_combinadas(2026, temporadas_historicas=2) usa
    2024, 2025 y lo que exista de 2026.

    Pide cada temporada POR SEPARADO — si una falla en descargar (típico de
    la temporada actual recién empezando), se descarta solo esa y se sigue
    con las demás, en vez de que una temporada rota tumbe todo el combinado.
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    temporadas = list(range(season_actual - temporadas_historicas, season_actual + 1))
    frames = []
    fallidas = []
    for t in temporadas:
        try:
            pbp_t = nfl.import_pbp_data([t], downcast=True)
            if pbp_t is not None and not pbp_t.empty and "posteam" in pbp_t.columns:
                frames.append(pbp_t)
            else:
                fallidas.append(t)
        except Exception:
            fallidas.append(t)

    if not frames:
        raise ValueError(f"No hay datos disponibles para ninguna de las temporadas {temporadas}.")

    pbp = pd.concat(frames, ignore_index=True)
    stats = _agregar_stats_equipo(pbp)
    stats.attrs["temporadas_usadas"] = [t for t in temporadas if t not in fallidas]
    stats.attrs["temporadas_faltantes"] = fallidas
    return stats


# ---------------------------------------------------------------------------
# 2a-bis. DESEMPEÑO DE JUGADORES CLAVE (QB1 / RB1 / WR1 / TE1) POR EQUIPO
# ---------------------------------------------------------------------------
def _stats_temporada_nflverse_directo(temporadas: list) -> pd.DataFrame:
    """
    Respaldo directo: descarga el archivo semanal de estadísticas de
    jugador que nflverse publica en GitHub (el mismo proyecto detrás de
    nfl_data_py) y lo agrega a nivel temporada nosotros mismos — sin
    pasar por nfl.import_seasonal_data(), que está fallando con error
    404 (probablemente apunta a una URL vieja que nflverse ya movió),
    mientras que el resto de funciones de nfl_data_py sí funcionan bien.

    Devuelve las mismas columnas base que import_seasonal_data(), para
    poder usarse como reemplazo directo donde se necesite.

    Aviso honesto: no confirmado en vivo — no tengo acceso a internet en
    este entorno de desarrollo. La URL viene de mi conocimiento general
    de cómo está organizado el repositorio de datos de nflverse
    (nflverse-data en GitHub), no de una prueba real contra el archivo.
    """
    url = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv.gz"
    semanal = pd.read_csv(url, compression="gzip", low_memory=False)

    if "season" not in semanal.columns:
        raise ValueError("El archivo de nflverse no tiene la columna 'season' esperada.")
    semanal = semanal[semanal["season"].isin(temporadas)]
    if semanal.empty:
        raise ValueError(f"No hay datos de jugadores para {temporadas} en el archivo de nflverse.")

    columna_equipo = "recent_team" if "recent_team" in semanal.columns else "team"
    columnas_sumar = [c for c in [
        "passing_yards", "passing_tds", "interceptions",
        "rushing_yards", "rushing_tds",
        "receiving_yards", "receiving_tds", "receptions",
        "fantasy_points", "fantasy_points_ppr",
    ] if c in semanal.columns]

    juegos = semanal.groupby("player_id")["week"].nunique().rename("games")

    agrupado = (
        semanal.groupby(["player_id", "player_name", "position", columna_equipo], dropna=False)[columnas_sumar]
        .sum().reset_index()
        .rename(columns={columna_equipo: "team"})
        .merge(juegos, on="player_id", how="left")
    )
    return agrupado


def obtener_jugadores_clave(season_actual: int, temporadas_historicas: int = 0) -> pd.DataFrame:
    """
    Identifica al jugador titular (el de mayor producción) en QB, RB, WR y
    TE de cada equipo, y devuelve sus estadísticas clave normalizadas a
    PROMEDIO POR PARTIDO — para usarlas como parámetros adicionales del
    modelo junto a las estadísticas de equipo.

    "Titular" se define de forma simple: el jugador de esa posición con más
    yardas de producción en su especialidad (pase para QB, carrera para RB,
    recepción para WR/TE) en el rango de temporadas pedido. No usa datos de
    lesiones/roster oficial, así que si un titular se lesionó a media
    temporada, puede seguir apareciendo como "titular" según su volumen
    acumulado — es una limitación conocida de este enfoque simple.

    Columnas devueltas (una fila por equipo):
        team, qb1_nombre, qb1_yardas_pase_pg, qb1_td_pase_pg, qb1_int_pg,
        rb1_nombre, rb1_yardas_carrera_pg, rb1_td_carrera_pg,
        wr1_nombre, wr1_yardas_recepcion_pg, wr1_td_recepcion_pg,
        te1_nombre, te1_yardas_recepcion_pg, te1_td_recepcion_pg
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    temporadas = (
        list(range(season_actual - temporadas_historicas, season_actual + 1))
        if temporadas_historicas > 0 else [season_actual]
    )

    # nfl.import_seasonal_data() está fallando con 404 en el entorno de
    # despliegue (para cualquier temporada, no solo la actual) — se
    # intenta primero por si acaso, y si falla, se cae al respaldo que
    # arma lo mismo descargando el archivo de nflverse directamente (ese
    # respaldo ya trae 'position'/'team' propios, así que no hace falta
    # cruzarlo con el roster después).
    uso_respaldo = False
    try:
        datos = nfl.import_seasonal_data(temporadas)
        if datos is None or datos.empty:
            raise ValueError("vacío")
    except Exception:
        try:
            datos = _stats_temporada_nflverse_directo(temporadas)
            uso_respaldo = True
        except Exception:
            # El archivo de nflverse existe pero puede no tener renglones
            # todavía para una temporada que apenas arrancó (se actualiza
            # con algo de retraso) — reintenta un año atrás.
            temporadas = [t - 1 for t in temporadas]
            try:
                datos = _stats_temporada_nflverse_directo(temporadas)
                uso_respaldo = True
            except Exception as e:
                raise ValueError(f"No hay estadísticas de jugadores disponibles para {temporadas}: {e}")

    if not uso_respaldo:
        try:
            roster = nfl.import_seasonal_rosters(temporadas)[["player_id", "player_name", "position", "team"]]
            roster = roster.drop_duplicates("player_id")
        except Exception as e:
            raise ValueError(f"No se pudo obtener el roster de jugadores: {e}")

        datos = datos.merge(roster, on="player_id", how="left")
        if "team" not in datos.columns or datos["team"].isna().all():
            raise ValueError("No se pudo cruzar jugadores con su equipo (roster incompleto).")

    columnas_deseadas = [
        "passing_yards", "passing_tds", "interceptions",
        "rushing_yards", "rushing_tds",
        "receiving_yards", "receiving_tds",
        "games",
    ]
    columnas_disponibles = [c for c in columnas_deseadas if c in datos.columns]
    if "games" not in columnas_disponibles:
        datos["games"] = 1  # fallback: si no viene "games", trata cada fila como 1 partido
        columnas_disponibles.append("games")

    agregado = (
        datos.groupby(["player_id", "player_name", "position", "team"])[columnas_disponibles]
        .sum().reset_index()
    )
    agregado["games"] = agregado["games"].replace(0, 1)

    def top_jugador(equipo_df: pd.DataFrame, posicion: str, columna_orden: str):
        sub = equipo_df[equipo_df["position"] == posicion]
        if sub.empty or columna_orden not in sub.columns:
            return None
        sub = sub.sort_values(columna_orden, ascending=False)
        return sub.iloc[0]

    filas = []
    for team in sorted(agregado["team"].dropna().unique()):
        equipo_df = agregado[agregado["team"] == team]
        fila = {"team": team}

        qb1 = top_jugador(equipo_df, "QB", "passing_yards")
        if qb1 is not None:
            juegos = qb1.get("games", 1) or 1
            fila["qb1_nombre"] = qb1.get("player_name")
            fila["qb1_yardas_pase_pg"] = qb1.get("passing_yards", 0) / juegos
            fila["qb1_td_pase_pg"] = qb1.get("passing_tds", 0) / juegos
            fila["qb1_int_pg"] = qb1.get("interceptions", 0) / juegos
        else:
            fila.update({"qb1_nombre": None, "qb1_yardas_pase_pg": 0.0, "qb1_td_pase_pg": 0.0, "qb1_int_pg": 0.0})

        rb1 = top_jugador(equipo_df, "RB", "rushing_yards")
        if rb1 is not None:
            juegos = rb1.get("games", 1) or 1
            fila["rb1_nombre"] = rb1.get("player_name")
            fila["rb1_yardas_carrera_pg"] = rb1.get("rushing_yards", 0) / juegos
            fila["rb1_td_carrera_pg"] = rb1.get("rushing_tds", 0) / juegos
        else:
            fila.update({"rb1_nombre": None, "rb1_yardas_carrera_pg": 0.0, "rb1_td_carrera_pg": 0.0})

        wr1 = top_jugador(equipo_df, "WR", "receiving_yards")
        if wr1 is not None:
            juegos = wr1.get("games", 1) or 1
            fila["wr1_nombre"] = wr1.get("player_name")
            fila["wr1_yardas_recepcion_pg"] = wr1.get("receiving_yards", 0) / juegos
            fila["wr1_td_recepcion_pg"] = wr1.get("receiving_tds", 0) / juegos
        else:
            fila.update({"wr1_nombre": None, "wr1_yardas_recepcion_pg": 0.0, "wr1_td_recepcion_pg": 0.0})

        te1 = top_jugador(equipo_df, "TE", "receiving_yards")
        if te1 is not None:
            juegos = te1.get("games", 1) or 1
            fila["te1_nombre"] = te1.get("player_name")
            fila["te1_yardas_recepcion_pg"] = te1.get("receiving_yards", 0) / juegos
            fila["te1_td_recepcion_pg"] = te1.get("receiving_tds", 0) / juegos
        else:
            fila.update({"te1_nombre": None, "te1_yardas_recepcion_pg": 0.0, "te1_td_recepcion_pg": 0.0})

        filas.append(fila)

    jugadores = pd.DataFrame(filas)

    # Puntajes compuestos simples (yardas + valor de TD, menos INT para el QB)
    # — el "20" es un equivalente aproximado de cuántas yardas vale un TD,
    # heurística común usada en scoring tipo fantasy football.
    jugadores["qb1_desempeno_score"] = (
        jugadores["qb1_yardas_pase_pg"] + jugadores["qb1_td_pase_pg"] * 20 - jugadores["qb1_int_pg"] * 25
    )
    jugadores["rb1_desempeno_score"] = jugadores["rb1_yardas_carrera_pg"] + jugadores["rb1_td_carrera_pg"] * 20
    jugadores["wr1_desempeno_score"] = jugadores["wr1_yardas_recepcion_pg"] + jugadores["wr1_td_recepcion_pg"] * 20
    jugadores["te1_desempeno_score"] = jugadores["te1_yardas_recepcion_pg"] + jugadores["te1_td_recepcion_pg"] * 20

    jugadores.attrs["temporada_usada"] = temporadas[-1]
    return jugadores


def combinar_stats_con_jugadores(stats: pd.DataFrame, jugadores: pd.DataFrame) -> pd.DataFrame:
    """Une el DataFrame de estadísticas de equipo con el de jugadores clave
    (por columna 'team'), rellenando con 0 los equipos sin datos de algún
    jugador para que el modelo no truene por valores faltantes."""
    combinado = stats.merge(jugadores, on="team", how="left")
    columnas_numericas = [c for c in jugadores.columns if c != "team" and not c.endswith("_nombre")]
    combinado[columnas_numericas] = combinado[columnas_numericas].fillna(0)
    combinado.attrs.update(stats.attrs)
    return combinado


# ---------------------------------------------------------------------------
# 2b. CALENDARIO DE PARTIDOS VÍA nfl_data_py
# ---------------------------------------------------------------------------
def obtener_calendario_semana(season: int, week: int) -> pd.DataFrame:
    """
    Devuelve los partidos programados de una semana específica de la
    temporada regular (away_team, home_team, fecha, hora).
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    sched = nfl.import_schedules([season])
    if sched is None or sched.empty:
        raise ValueError(f"No hay calendario disponible todavía para la temporada {season}.")

    partidos = sched[sched["week"] == week][
        ["away_team", "home_team", "gameday", "gametime", "game_type"]
    ].reset_index(drop=True)

    if partidos.empty:
        raise ValueError(f"No se encontraron partidos para la semana {week} de la temporada {season}.")

    return partidos


def obtener_proximos_partidos(season: int, week: int | None = None) -> pd.DataFrame:
    """
    Devuelve SOLO partidos que todavía no se han jugado (sin marcador final
    registrado en el calendario). Si week es None, detecta automáticamente
    la semana pendiente más próxima.
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    sched = nfl.import_schedules([season])
    if sched is None or sched.empty:
        raise ValueError(f"No hay calendario disponible todavía para la temporada {season}.")

    # Un partido "pendiente" es aquel sin marcador final registrado todavía.
    pendientes = sched[sched["home_score"].isna()]
    if pendientes.empty:
        raise ValueError(
            f"No quedan partidos pendientes por jugar en la temporada {season} "
            f"(o la temporada ya terminó)."
        )

    if week is None:
        week = int(pendientes["week"].min())

    partidos = pendientes[pendientes["week"] == week][
        ["away_team", "home_team", "gameday", "gametime", "game_type", "week"]
    ].reset_index(drop=True)

    if partidos.empty:
        raise ValueError(f"No se encontraron partidos pendientes para la semana {week}.")

    return partidos


# ---------------------------------------------------------------------------
# 3. DATOS COMPLEMENTARIOS VÍA ESPN API (récord reciente, lesiones)
#    Nota: esta API no es oficial de ESPN y puede cambiar sin aviso.
# ---------------------------------------------------------------------------
ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"

def obtener_record_espn(team_abbr: str) -> dict:
    """Devuelve récord actual y últimos resultados desde ESPN."""
    try:
        url = f"{ESPN_TEAMS_URL}/{team_abbr}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        record = data["team"].get("record", {}).get("items", [{}])[0]
        return {
            "wins": record.get("stats", [{}])[0].get("value", None),
            "raw": record,
        }
    except Exception as e:
        return {"error": str(e)}


def obtener_lesiones_espn(team_abbr: str) -> list:
    """Devuelve lista de jugadores lesionados reportados por ESPN, ya
    normalizada a una forma simple (nombre, posición, estado, detalle)."""
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_abbr}/injuries"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        crudo = r.json().get("injuries", [])

        normalizadas = []
        for item in crudo:
            atleta = item.get("athlete", {}) or {}
            detalle_txt = item.get("details", {}).get("detail", "") if isinstance(item.get("details"), dict) else ""
            if "coach's decision" in detalle_txt.lower() or "coaches decision" in detalle_txt.lower():
                continue
            normalizadas.append({
                "jugador": atleta.get("displayName", item.get("displayName", "?")),
                "posicion": atleta.get("position", {}).get("abbreviation", "?")
                    if isinstance(atleta.get("position"), dict) else "?",
                "estado": item.get("status", item.get("type", {}).get("description", "?")),
                "detalle": detalle_txt,
            })
        return normalizadas
    except Exception as e:
        return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# 3b. INFORMACIÓN GENERAL PARA LA PÁGINA DE INICIO (marcadores, tabla de
#     posiciones, líderes estadísticos) — combina ESPN (tiempo real) con
#     nfl_data_py (líderes de temporada).
# ---------------------------------------------------------------------------
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_STANDINGS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/standings"
ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"
ESPN_LEAGUE_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"

# ESPN usa códigos de logo distintos a los de nflverse solo para estos dos.
_LOGO_ESPECIALES = {"LA": "lar", "WAS": "wsh"}


def logo_url(abbr: str) -> str:
    """URL del logo oficial del equipo (CDN público de ESPN)."""
    codigo = _LOGO_ESPECIALES.get(abbr, abbr).lower()
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{codigo}.png"


def obtener_noticias_nfl(limite: int = 10) -> list:
    """Devuelve las noticias más recientes de la NFL (titular, resumen,
    imagen y liga al artículo completo) — no separadas por equipo."""
    try:
        r = requests.get(ESPN_NEWS_URL, params={"limit": limite}, timeout=15)
        r.raise_for_status()
        data = r.json()

        noticias = []
        for art in data.get("articles", [])[:limite]:
            imagen = None
            imgs = art.get("images") or []
            if imgs:
                imagen = imgs[0].get("url")
            noticias.append({
                "titulo": art.get("headline", "?"),
                "descripcion": art.get("description", ""),
                "imagen": imagen,
                "link": (art.get("links") or {}).get("web", {}).get("href", ""),
                "fecha": art.get("published", ""),
            })
        return noticias
    except Exception as e:
        return [{"error": str(e)}]


FUENTES_RSS_NFL = {
    "NBC Sports": "https://www.nbcsports.com/nfl.atom",
    "Yahoo Sports": "https://sports.yahoo.com/nfl/rss/",
}


def obtener_noticias_rss(fuente_url: str, limite: int = 10) -> list:
    """
    Trae noticias de un feed RSS/Atom estándar (NBC, Yahoo, etc.) usando
    feedparser — el formato RSS lleva ~20 años estable, así que es más
    confiable que las APIs JSON no documentadas.
    """
    try:
        feed = feedparser.parse(fuente_url)
        if getattr(feed, "bozo", False) and not feed.entries:
            return [{"error": str(feed.get("bozo_exception", "No se pudo leer el feed"))}]

        noticias = []
        for entry in feed.entries[:limite]:
            imagen = None
            media = entry.get("media_content") or []
            if media:
                imagen = media[0].get("url")
            if not imagen:
                for enlace in entry.get("links", []):
                    if str(enlace.get("type", "")).startswith("image"):
                        imagen = enlace.get("href")
                        break

            noticias.append({
                "titulo": entry.get("title", "?"),
                "descripcion": re.sub("<[^<]+?>", "", entry.get("summary", ""))[:220],
                "imagen": imagen,
                "link": entry.get("link", ""),
                "fecha": entry.get("published", entry.get("updated", "")),
            })
        return noticias
    except Exception as e:
        return [{"error": str(e)}]


def _normalizar_titulo(titulo: str) -> str:
    """Reduce un titular a solo letras/números en minúscula, para poder
    comparar si dos notas de fuentes distintas son la misma historia."""
    return re.sub(r"[^a-z0-9]+", "", titulo.lower())


def obtener_noticias_combinadas(limite_por_fuente: int = 10) -> list:
    """
    Combina noticias de ESPN + NBC Sports + Yahoo Sports en una sola
    lista, quitando duplicados (misma historia reportada por más de una
    fuente) comparando el titular normalizado.
    """
    fuentes = [
        ("ESPN", lambda: obtener_noticias_nfl(limite_por_fuente)),
        ("NBC Sports", lambda: obtener_noticias_rss(FUENTES_RSS_NFL["NBC Sports"], limite_por_fuente)),
        ("Yahoo Sports", lambda: obtener_noticias_rss(FUENTES_RSS_NFL["Yahoo Sports"], limite_por_fuente)),
    ]

    combinadas = []
    titulos_vistos = set()

    for nombre_fuente, obtener in fuentes:
        try:
            items = obtener()
        except Exception:
            continue
        if not items or "error" in items[0]:
            continue
        for n in items:
            clave = _normalizar_titulo(n.get("titulo", ""))
            if not clave or clave in titulos_vistos:
                continue
            titulos_vistos.add(clave)
            n["fuente"] = nombre_fuente
            combinadas.append(n)

    return combinadas


def obtener_noticias_equipo(team_abbr: str, limite: int = 10) -> list:
    """
    Noticias específicas de un equipo. Intenta primero un endpoint de
    ESPN por equipo (mismo patrón que el de lesiones por equipo, que sí
    funciona) — si falla, no existe, o no trae nada, cae a filtrar las
    noticias generales de la liga por el apodo del equipo.
    """
    # Intento 1: endpoint de noticias por equipo (no verificado en vivo,
    # sigue el mismo patrón que /teams/{abbr}/injuries).
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_abbr}/news"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        articulos = data.get("articles") or data.get("feed") or []

        noticias = []
        for art in articulos[:limite]:
            imagen = None
            imgs = art.get("images") or []
            if imgs:
                imagen = imgs[0].get("url")
            noticias.append({
                "titulo": art.get("headline", "?"),
                "descripcion": art.get("description", ""),
                "imagen": imagen,
                "link": (art.get("links") or {}).get("web", {}).get("href", ""),
                "fecha": art.get("published", ""),
            })
        if noticias:
            return noticias
    except Exception:
        pass

    # Respaldo: filtra las noticias generales de la liga por apodo del equipo.
    apodo = _APODOS_NFL.get(team_abbr, team_abbr).lower()
    generales = obtener_noticias_nfl(30)
    if generales and "error" in generales[0]:
        return []
    filtradas = [
        n for n in generales
        if apodo in n.get("titulo", "").lower() or apodo in n.get("descripcion", "").lower()
    ]
    return filtradas[:limite]


_EQUIPOS_LIGA = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LA", "LAC", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
]

# Estados que NO cuentan como lesión real (jugador sano/disponible) — se
# excluyen del reporte para que solo queden bajas de importancia.
_ESTADOS_IRRELEVANTES = {"active", "healthy", "available"}


def obtener_lesiones_liga(limite: int = 25) -> list:
    """
    Devuelve las lesiones RECIENTES y de IMPORTANCIA de toda la liga (no
    jugadores sanos/activos), en una sola lista sin separar por equipo.

    Consulta el endpoint de lesiones de cada equipo por separado (en
    paralelo) y descarta cualquier entrada cuyo estado sea "Active" /
    "Healthy" — esas no son lesiones reales, son solo el estado normal
    del roster que a veces incluye ese endpoint.
    """
    import concurrent.futures

    def _lesiones_de_equipo(abbr: str) -> list:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{abbr}/injuries"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            crudo = r.json().get("injuries", [])
            filas = []
            for item in crudo:
                atleta = item.get("athlete", {}) or {}
                posicion = atleta.get("position")
                estado = item.get("status") or (item.get("type") or {}).get("description", "?")
                if str(estado).strip().lower() in _ESTADOS_IRRELEVANTES:
                    continue
                detalle_txt = (item.get("details") or {}).get("detail", "") if isinstance(item.get("details"), dict) else ""
                if "coach's decision" in detalle_txt.lower() or "coaches decision" in detalle_txt.lower():
                    continue
                filas.append({
                    "equipo": abbr,
                    "jugador": atleta.get("displayName", "?"),
                    "posicion": posicion.get("abbreviation", "?") if isinstance(posicion, dict) else "?",
                    "estado": estado,
                    "detalle": detalle_txt,
                    "fecha": item.get("date", ""),
                })
            return filas
        except Exception:
            return []

    try:
        resultado = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            for filas in executor.map(_lesiones_de_equipo, _EQUIPOS_LIGA):
                resultado.extend(filas)

        # Más recientes primero cuando hay fecha disponible.
        resultado.sort(key=lambda x: x.get("fecha") or "", reverse=True)
        return resultado[:limite]
    except Exception as e:
        return [{"error": str(e)}]


# Etiquetas en español para el periodo de un partido en vivo — se usan
# tanto con el número de cuarto que da ESPN (1-4, 5 = tiempo extra) como
# con los códigos cortos tipo "Q1"/"HT"/"OT" que da API-Sports.
_ETIQUETAS_PERIODO_NUM = {1: "1er cuarto", 2: "2do cuarto", 3: "3er cuarto", 4: "4to cuarto", 5: "Tiempo extra"}
_ETIQUETAS_PERIODO_COD = {
    "Q1": "1er cuarto", "Q2": "2do cuarto", "Q3": "3er cuarto", "Q4": "4to cuarto",
    "OT": "Tiempo extra", "HT": "Medio tiempo", "1H": "1ra mitad", "2H": "2da mitad",
}
# Códigos/estados que indican que el partido está EN VIVO ahora mismo (ni
# programado/sin empezar ni ya terminado).
_CODIGOS_EN_VIVO = {"Q1", "Q2", "Q3", "Q4", "OT", "HT", "1H", "2H"}


def obtener_marcadores_actuales() -> list:
    """
    Devuelve los partidos de la semana actual según ESPN (en vivo, próximos
    o recién terminados), con marcador, estado y equipos. Si el partido
    está en vivo, incluye también el cuarto/periodo y el reloj de juego
    (minuto restante) para poder mostrarlo en vez de la hora programada.
    """
    try:
        r = requests.get(ESPN_SCOREBOARD_URL, timeout=10)
        r.raise_for_status()
        data = r.json()

        partidos = []
        for ev in data.get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            competidores = comp.get("competitors", [])
            home = next((c for c in competidores if c.get("homeAway") == "home"), {})
            away = next((c for c in competidores if c.get("homeAway") == "away"), {})
            status_obj = comp.get("status", {}) or {}
            tipo = status_obj.get("type", {}) or {}
            estado = tipo.get("description", "?")

            partidos.append({
                "away_nombre": (away.get("team") or {}).get("displayName", "?"),
                "away_abbr": (away.get("team") or {}).get("abbreviation", "?"),
                "away_score": away.get("score", "-"),
                "home_nombre": (home.get("team") or {}).get("displayName", "?"),
                "home_abbr": (home.get("team") or {}).get("abbreviation", "?"),
                "home_score": home.get("score", "-"),
                "estado": estado,
                "en_vivo": tipo.get("state") == "in",
                "periodo": status_obj.get("period"),
                "reloj": status_obj.get("displayClock", "") or "",
                "fecha": ev.get("date", ""),
            })
        # Primero los que faltan por jugar, y hasta el final los que ya
        # terminaron (ESPN ya entrega los eventos en orden cronológico
        # dentro de la jornada, así que solo hace falta reagrupar).
        partidos.sort(key=lambda p: 1 if "final" in p["estado"].lower() else 0)
        return partidos
    except Exception as e:
        return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# 3c. API-SPORTS (api-sports.io) — cuenta de pago del usuario, datos
#     oficiales de NFL: standings, lesiones. La API key NUNCA se hardcodea
#     aquí — se recibe como parámetro desde app.py, que la lee de
#     st.secrets (privado, no se sube a GitHub).
# ---------------------------------------------------------------------------
API_SPORTS_BASE_URL = "https://v1.american-football.api-sports.io"
API_SPORTS_LEAGUE_NFL = 1

# Zona horaria usada para decidir cuándo una jornada deja de mostrarse como
# "actual" (ver _semana_actual_por_corte) — la misma que usa el resto de la
# app para mostrar horarios locales (America/Cancun).
ZONA_CORTE_SEMANA = "America/Cancun"

# Apodo de cada equipo, usado para cruzar el nombre completo que devuelve
# API-Sports (ej. "Kansas City Chiefs") con nuestra abreviatura (KC) sin
# depender de que sus códigos de equipo coincidan con los de nflverse.
_APODOS_NFL = {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills",
    "CAR": "Panthers", "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns",
    "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
    "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs",
    "LA": "Rams", "LAC": "Chargers", "LV": "Raiders", "MIA": "Dolphins",
    "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
    "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks",
    "SF": "49ers", "TB": "Buccaneers", "TEN": "Titans", "WAS": "Commanders",
}


def _abbr_desde_nombre_api_sports(nombre_equipo: str) -> str:
    """Traduce 'Kansas City Chiefs' -> 'KC' usando el apodo. Si no encuentra
    coincidencia, regresa el nombre tal cual (mejor mostrar algo que nada)."""
    for abbr, apodo in _APODOS_NFL.items():
        if apodo.lower() in nombre_equipo.lower():
            return abbr
    return nombre_equipo


def _api_sports_get(api_key: str, endpoint: str, params: dict) -> dict:
    """Llamada genérica a API-Sports con manejo de errores consistente."""
    if not api_key:
        raise ValueError("Falta la API key de API-Sports (configúrala en Streamlit Secrets).")
    r = requests.get(
        f"{API_SPORTS_BASE_URL}{endpoint}",
        headers={"x-apisports-key": api_key},
        params=params, timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise ValueError(f"API-Sports respondió con error: {data['errors']}")
    return data


def obtener_standings_api_sports(api_key: str, season: int) -> pd.DataFrame:
    """
    Tabla de posiciones oficial vía API-Sports — incluye conferencia,
    división, récord, puntos a favor/en contra y racha actual. Requiere
    tu API key de api-sports.io (cuenta de pago del usuario).
    """
    data = _api_sports_get(api_key, "/standings", {"league": API_SPORTS_LEAGUE_NFL, "season": season})

    filas = []
    for item in data.get("response", []):
        nombre_api = (item.get("team") or {}).get("name", "?")
        abbr = _abbr_desde_nombre_api_sports(nombre_api)
        puntos = item.get("points") or {}
        v, d, e = item.get("won", 0) or 0, item.get("lost", 0) or 0, item.get("ties", 0) or 0
        total = v + d + e

        # Récord local/visitante — el nombre exacto del campo puede variar
        # según la respuesta de API-Sports; si no viene, cae a "0-0" en
        # vez de tronar.
        records = item.get("records") or {}
        home_rec = records.get("home") or {}
        away_rec = records.get("away") or {}
        loc_txt = f"{home_rec.get('won', 0)}-{home_rec.get('lost', 0)}" if home_rec else "0-0"
        vis_txt = f"{away_rec.get('won', 0)}-{away_rec.get('lost', 0)}" if away_rec else "0-0"

        filas.append({
            "Conferencia": "AFC" if "American" in (item.get("conference") or "") else "NFC",
            "División": item.get("division", "?"),
            "Equipo": abbr,
            "V": v, "D": d, "E": e,
            "PF": puntos.get("for", 0), "PC": puntos.get("against", 0),
            "Loc": loc_txt, "Vis": vis_txt,
            "Racha": item.get("streak", "") or "",
            "% Victorias": round((v + 0.5 * e) / total * 100, 1) if total else 0.0,
        })

    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values(["Conferencia", "División", "% Victorias"], ascending=[True, True, False]).reset_index(drop=True)
    return df


def obtener_equipos_api_sports(api_key: str, season: int) -> dict:
    """Devuelve {abbr: id_api_sports} para poder consultar /injuries por equipo."""
    data = _api_sports_get(api_key, "/teams", {"league": API_SPORTS_LEAGUE_NFL, "season": season})
    mapeo = {}
    for item in data.get("response", []):
        nombre = item.get("name", "")
        abbr = _abbr_desde_nombre_api_sports(nombre)
        if item.get("id") is not None:
            mapeo[abbr] = item["id"]
    return mapeo


def _juegos_temporada_regular_api_sports(api_key: str, season: int) -> list:
    """Trae TODOS los juegos de temporada regular de la temporada (1 sola
    consulta), sin filtrar todavía por semana — usado tanto para detectar
    la semana 'actual' como para traer una semana puntual en Scores."""
    data = _api_sports_get(api_key, "/games", {"league": API_SPORTS_LEAGUE_NFL, "season": season})
    juegos = data.get("response", [])
    # Solo temporada regular — descarta pretemporada (por eso salían
    # combinaciones raras de equipos con "Final" fuera de lugar).
    return [j for j in juegos if "regular" in ((j.get("game") or {}).get("stage") or "").lower()]


def _fecha_juego_api_sports(j: dict, respaldo: datetime.date = None) -> datetime.date:
    """Fecha (solo día) del juego, a partir del campo crudo de API-Sports."""
    try:
        return datetime.date.fromisoformat(j["game"]["date"]["date"])
    except Exception:
        return respaldo or datetime.date.today()


def _semana_numero_api_sports(j: dict):
    """Número de semana de un juego crudo de API-Sports, normalizado a int
    — API-Sports a veces manda este campo como número (3) y a veces como
    texto ("3" o "Week 3"), así que hay que extraer el número siempre de
    la misma forma en vez de comparar el valor crudo directamente (eso
    causaba que el selector de semana en Scores nunca encontrara partidos,
    y que preseleccionar la semana 'actual' tronara al forzar int())."""
    semana = (j.get("game") or {}).get("week")
    if semana is None:
        return None
    if isinstance(semana, int):
        return semana
    coincidencia = re.search(r"\d+", str(semana))
    return int(coincidencia.group()) if coincidencia else None


def _semanas_min_max(juegos: list) -> dict:
    """{numero_semana: {"min": date, "max": date}} — el rango de fechas
    (primer y último partido) de cada jornada, a partir de la lista cruda
    de juegos de API-Sports (ya filtrada a temporada regular)."""
    semanas = {}
    for j in juegos:
        semana = _semana_numero_api_sports(j)
        if semana is None:
            continue
        f = _fecha_juego_api_sports(j)
        if semana not in semanas:
            semanas[semana] = {"min": f, "max": f}
        else:
            semanas[semana]["min"] = min(semanas[semana]["min"], f)
            semanas[semana]["max"] = max(semanas[semana]["max"], f)
    return semanas


def _semana_actual_por_corte(semanas: dict, ahora: datetime.datetime) -> int:
    """
    La jornada 'actual' es la primera (en orden cronológico) cuyo CORTE
    todavía no se ha cumplido. El corte de una jornada son las 6:00 am
    (hora de ZONA_CORTE_SEMANA) del día siguiente a la fecha de su ÚLTIMO
    partido — antes de ese momento se sigue mostrando esa jornada (aunque
    ya hayan terminado todos sus partidos); justo al llegar el corte, se
    salta automáticamente a la siguiente jornada con sus propios partidos
    y horarios. Si ya se cumplió el corte de todas las jornadas conocidas,
    se queda en la última (temporada terminada / nada más que mostrar).
    """
    orden = sorted(semanas.keys(), key=lambda s: semanas[s]["min"])
    if not orden:
        raise ValueError("No hay semanas para evaluar.")

    semana_actual = orden[-1]
    for semana in orden:
        corte = datetime.datetime.combine(
            semanas[semana]["max"] + datetime.timedelta(days=1),
            datetime.time(6, 0),
            tzinfo=ahora.tzinfo,
        )
        if ahora < corte:
            semana_actual = semana
            break
    return semana_actual


def _formatear_partido_api_sports(j: dict) -> dict:
    """Normaliza un juego crudo de API-Sports (/games) a nuestro formato
    común de partido — compartido entre el ticker de la semana 'actual' y
    la pantalla Scores (que pide una semana puntual)."""
    home = (j.get("teams") or {}).get("home") or {}
    away = (j.get("teams") or {}).get("away") or {}
    scores = j.get("scores") or {}
    status_obj = (j.get("game") or {}).get("status") or {}
    estado = status_obj.get("short", "NS")
    venue = (j.get("game") or {}).get("venue") or {}
    # El nombre del campo del reloj en vivo varía entre proveedores —
    # se intentan las variantes más comunes en vez de asumir una sola.
    reloj = status_obj.get("timer") or status_obj.get("clock") or ""
    return {
        "away_abbr": _abbr_desde_nombre_api_sports(away.get("name", "")),
        "home_abbr": _abbr_desde_nombre_api_sports(home.get("name", "")),
        "away_score": (scores.get("away") or {}).get("total"),
        "home_score": (scores.get("home") or {}).get("total"),
        "estado": estado,
        "en_vivo": estado in _CODIGOS_EN_VIVO,
        "periodo": estado,
        "reloj": reloj,
        "fecha": (j.get("game") or {}).get("date", {}).get("date", ""),
        "hora": (j.get("game") or {}).get("date", {}).get("time", ""),
        "timestamp": (j.get("game") or {}).get("date", {}).get("timestamp"),
        "estadio": venue.get("name", ""),
        "ciudad": venue.get("city", ""),
        "semana": _semana_numero_api_sports(j),
    }


def obtener_marcadores_api_sports(api_key: str, season: int) -> list:
    """
    Marcadores de la jornada (semana) actual vía API-Sports. Se queda en
    una jornada hasta las 6:00 am (hora de America/Cancun) del día
    siguiente a su último partido — justo en ese momento salta sola a la
    próxima jornada, con sus propios partidos y horarios. Trae toda la
    temporada en 1 sola consulta y filtra en memoria, para no gastar
    cuota pidiendo semana por semana.

    Si un partido está en vivo, incluye también el cuarto/periodo
    (código corto como "Q2"/"HT"/"OT") y el reloj de juego, cuando la
    API lo trae, para poder mostrar el minuto del partido en vez de la
    hora programada y el estadio.
    """
    juegos = _juegos_temporada_regular_api_sports(api_key, season)
    if not juegos:
        return []

    ahora = datetime.datetime.now(ZoneInfo(ZONA_CORTE_SEMANA))
    semanas = _semanas_min_max(juegos)
    semana_actual = _semana_actual_por_corte(semanas, ahora)

    de_esta_semana = [j for j in juegos if _semana_numero_api_sports(j) == semana_actual]

    def _terminado(j):
        estado = ((j.get("game") or {}).get("status") or {}).get("short", "NS")
        return 1 if estado in ("FT", "AOT") else 0

    # Primero los que faltan por jugar (en orden cronológico), y hasta el
    # final los que ya terminaron.
    de_esta_semana.sort(key=lambda j: (_terminado(j), _fecha_juego_api_sports(j, ahora.date())))

    return [_formatear_partido_api_sports(j) for j in de_esta_semana]


def _lesiones_equipo_api_sports_raw(api_key: str, team_id, abbr: str) -> list:
    """Lesiones de UN equipo directo desde API-Sports (sin combinar con
    otros equipos ni recortar por fecha) — se usa tanto para el listado
    de toda la liga como para el filtro por equipo específico, así
    ambos usan la misma fuente confiable sin que un equipo con lesiones
    'menos recientes' que las de otros quede fuera al truncar.

    Filtra las entradas que son 'Coach's Decision' (jugador sano, fuera
    por decisión técnica/estrategia) — no es una lesión ni una
    suspensión, así que no debe aparecer en el reporte de lesiones."""
    data = _api_sports_get(api_key, "/injuries", {"team": team_id})
    filas = []
    for lesion in data.get("response", []):
        descripcion = lesion.get("description", "") or ""
        if "coach's decision" in descripcion.lower() or "coaches decision" in descripcion.lower():
            continue
        jugador = lesion.get("player") or {}
        filas.append({
            "equipo": abbr,
            "jugador": jugador.get("name", "?"),
            "posicion": jugador.get("position", "") or jugador.get("pos", "") or "",
            "foto": jugador.get("photo", "") or jugador.get("image", "") or "",
            "estado": lesion.get("status", "?"),
            "detalle": descripcion,
            "fecha": lesion.get("date", "") or "",
        })
    return filas


def obtener_lesiones_equipo_api_sports(api_key: str, season: int, team_abbr: str) -> list:
    """Lesiones de un solo equipo específico, vía API-Sports — no pasa
    por el recorte de 'toda la liga', así que no se pierde ningún
    jugador de ese equipo aunque otros equipos tengan lesiones más
    recientes."""
    equipos = obtener_equipos_api_sports(api_key, season)
    if not equipos or team_abbr not in equipos:
        raise ValueError(f"No se encontró el equipo {team_abbr} en el catálogo de API-Sports.")
    team_id = equipos[team_abbr]
    filas = _lesiones_equipo_api_sports_raw(api_key, team_id, team_abbr)
    filas.sort(key=lambda x: x.get("fecha") or "", reverse=True)
    return filas


def obtener_lesiones_liga_api_sports(api_key: str, season: int, limite: int = 30) -> list:
    """
    Lesiones recientes de toda la liga vía API-Sports (más confiable que
    scrapear ESPN equipo por equipo). Consume 1 request por equipo (32
    en total) más 1 para el catálogo de equipos — cuidado con el límite
    diario en el plan gratuito (100/día).
    """
    import concurrent.futures

    equipos = obtener_equipos_api_sports(api_key, season)
    if not equipos:
        raise ValueError("No se pudo obtener el catálogo de equipos de API-Sports.")

    def _lesiones_de_equipo(item):
        abbr, team_id = item
        try:
            return _lesiones_equipo_api_sports_raw(api_key, team_id, abbr)
        except Exception:
            return []

    resultado = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for filas in executor.map(_lesiones_de_equipo, equipos.items()):
            resultado.extend(filas)

    resultado.sort(key=lambda x: x.get("fecha") or "", reverse=True)
    return resultado[:limite]


def obtener_semana_actual_api_sports(api_key: str, season: int) -> int:
    """Número de la jornada que se considera 'actual' ahora mismo (misma
    lógica de corte de las 6am que usa el ticker de marcadores) — se usa
    para preseleccionar la semana en la pantalla Scores."""
    juegos = _juegos_temporada_regular_api_sports(api_key, season)
    if not juegos:
        raise ValueError(f"No hay partidos de temporada regular para {season} todavía.")
    ahora = datetime.datetime.now(ZoneInfo(ZONA_CORTE_SEMANA))
    semanas = _semanas_min_max(juegos)
    return _semana_actual_por_corte(semanas, ahora)


def obtener_marcadores_semana_api_sports(api_key: str, season: int, week: int) -> list:
    """
    Partidos (ya jugados, en vivo, o pendientes) de una semana ESPECÍFICA
    vía API-Sports — a diferencia de obtener_marcadores_api_sports(), no
    detecta ninguna semana "actual": trae exactamente la que se le pida.
    Se usa en la pantalla Scores, donde el usuario elige la semana con un
    selector. Si la semana todavía no se jugó, los partidos vienen con
    estado "NS" (Not Started) y sin marcador.
    """
    juegos = _juegos_temporada_regular_api_sports(api_key, season)
    de_la_semana = [j for j in juegos if _semana_numero_api_sports(j) == week]
    if not de_la_semana:
        return []

    de_la_semana.sort(key=lambda j: _fecha_juego_api_sports(j))
    return [_formatear_partido_api_sports(j) for j in de_la_semana]


def obtener_marcadores_semana(season: int, week: int) -> list:
    """
    Respaldo SIN API-Sports para la pantalla Scores — usa el calendario de
    nfl_data_py, que ya trae el marcador final de cada partido una vez
    jugado (y NaN si todavía no se juega). No incluye estado en vivo (esa
    granularidad solo la dan ESPN/API-Sports), pero alcanza para ver
    resultados de semanas pasadas o el calendario de una semana futura.
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    sched = nfl.import_schedules([season])
    if sched is None or sched.empty:
        raise ValueError(f"No hay calendario disponible todavía para la temporada {season}.")

    partidos = sched[sched["week"] == week]
    if partidos.empty:
        raise ValueError(f"No se encontraron partidos para la semana {week} de la temporada {season}.")

    resultado = []
    for _, p in partidos.iterrows():
        jugado = pd.notna(p.get("home_score")) and pd.notna(p.get("away_score"))
        resultado.append({
            "away_abbr": p["away_team"],
            "home_abbr": p["home_team"],
            "away_score": int(p["away_score"]) if jugado else None,
            "home_score": int(p["home_score"]) if jugado else None,
            "estado": "FT" if jugado else "NS",
            "en_vivo": False,
            "periodo": None,
            "reloj": "",
            "fecha": p.get("gameday", ""),
            "hora": p.get("gametime", ""),
            "timestamp": None,
            "estadio": "",
            "ciudad": "",
            "semana": week,
        })
    return resultado


_DIVISIONES_NFL = {
    "BUF": ("AFC", "AFC Este"), "MIA": ("AFC", "AFC Este"), "NE": ("AFC", "AFC Este"), "NYJ": ("AFC", "AFC Este"),
    "BAL": ("AFC", "AFC Norte"), "CIN": ("AFC", "AFC Norte"), "CLE": ("AFC", "AFC Norte"), "PIT": ("AFC", "AFC Norte"),
    "HOU": ("AFC", "AFC Sur"), "IND": ("AFC", "AFC Sur"), "JAX": ("AFC", "AFC Sur"), "TEN": ("AFC", "AFC Sur"),
    "DEN": ("AFC", "AFC Oeste"), "KC": ("AFC", "AFC Oeste"), "LV": ("AFC", "AFC Oeste"), "LAC": ("AFC", "AFC Oeste"),
    "DAL": ("NFC", "NFC Este"), "NYG": ("NFC", "NFC Este"), "PHI": ("NFC", "NFC Este"), "WAS": ("NFC", "NFC Este"),
    "CHI": ("NFC", "NFC Norte"), "DET": ("NFC", "NFC Norte"), "GB": ("NFC", "NFC Norte"), "MIN": ("NFC", "NFC Norte"),
    "ATL": ("NFC", "NFC Sur"), "CAR": ("NFC", "NFC Sur"), "NO": ("NFC", "NFC Sur"), "TB": ("NFC", "NFC Sur"),
    "ARI": ("NFC", "NFC Oeste"), "LA": ("NFC", "NFC Oeste"), "SF": ("NFC", "NFC Oeste"), "SEA": ("NFC", "NFC Oeste"),
}


def _calcular_racha(resultados: list) -> str:
    """A partir de una lista cronológica de 'V'/'D'/'E', arma el texto de
    racha actual (ej. 'W3', 'L1') igual que el formato de API-Sports."""
    if not resultados:
        return ""
    ultimo = resultados[-1]
    conteo = 0
    for r in reversed(resultados):
        if r == ultimo:
            conteo += 1
        else:
            break
    letra = {"V": "W", "D": "L", "E": "T"}.get(ultimo, "")
    return f"{letra}{conteo}"


def obtener_standings(season: int) -> pd.DataFrame:
    """
    Calcula la tabla de posiciones (V-D-E por equipo) a partir de los
    resultados de partidos YA JUGADOS de la temporada, usando el calendario
    de nfl_data_py — no depende de ninguna API externa no documentada.
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    sched = nfl.import_schedules([season])
    if sched is None or sched.empty:
        raise ValueError(f"No hay calendario disponible todavía para la temporada {season}.")

    jugados = sched[sched["home_score"].notna() & sched["away_score"].notna()]
    if jugados.empty:
        raise ValueError(f"Todavía no se ha jugado ningún partido en la temporada {season}.")
    jugados = jugados.sort_values(["week"])  # orden cronológico, para calcular la racha

    def _registro_vacio():
        return {"V": 0, "D": 0, "E": 0, "PF": 0, "PC": 0,
                "loc_v": 0, "loc_d": 0, "loc_e": 0,
                "vis_v": 0, "vis_d": 0, "vis_e": 0, "resultados": []}

    registros = {equipo: _registro_vacio() for equipo in _DIVISIONES_NFL}
    for _, partido in jugados.iterrows():
        home, away = partido["home_team"], partido["away_team"]
        hs, aw = partido["home_score"], partido["away_score"]
        for equipo in (home, away):
            registros.setdefault(equipo, _registro_vacio())

        registros[home]["PF"] += hs
        registros[home]["PC"] += aw
        registros[away]["PF"] += aw
        registros[away]["PC"] += hs

        if hs > aw:
            registros[home]["V"] += 1
            registros[home]["loc_v"] += 1
            registros[home]["resultados"].append("V")
            registros[away]["D"] += 1
            registros[away]["vis_d"] += 1
            registros[away]["resultados"].append("D")
        elif aw > hs:
            registros[away]["V"] += 1
            registros[away]["vis_v"] += 1
            registros[away]["resultados"].append("V")
            registros[home]["D"] += 1
            registros[home]["loc_d"] += 1
            registros[home]["resultados"].append("D")
        else:
            registros[home]["E"] += 1
            registros[home]["loc_e"] += 1
            registros[home]["resultados"].append("E")
            registros[away]["E"] += 1
            registros[away]["vis_e"] += 1
            registros[away]["resultados"].append("E")

    filas = []
    for equipo, rec in registros.items():
        total = rec["V"] + rec["D"] + rec["E"]
        conferencia, division = _DIVISIONES_NFL.get(equipo, ("?", "?"))
        filas.append({
            "Conferencia": conferencia,
            "División": division,
            "Equipo": equipo,
            "V": rec["V"], "D": rec["D"], "E": rec["E"],
            "PF": int(rec["PF"]), "PC": int(rec["PC"]),
            "Loc": f"{rec['loc_v']}-{rec['loc_d']}", "Vis": f"{rec['vis_v']}-{rec['vis_d']}",
            "Racha": _calcular_racha(rec["resultados"]),
            "% Victorias": round((rec["V"] + 0.5 * rec["E"]) / total * 100, 1) if total else 0.0,
        })

    df = pd.DataFrame(filas)
    if not df.empty:
        df = df.sort_values(["Conferencia", "División", "% Victorias"], ascending=[True, True, False]).reset_index(drop=True)
    return df


def obtener_calendario_equipo(team_abbr: str, season: int) -> pd.DataFrame:
    """
    Calendario completo de un equipo en la temporada — todos sus
    partidos (jugados y por jugar), rival, si es local/visitante, y
    marcador cuando ya se jugó. Usa nfl_data_py (mismo dato confiable
    que ya usamos para standings/próximos partidos).
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    sched = nfl.import_schedules([season])
    if sched is None or sched.empty:
        raise ValueError(f"No hay calendario disponible todavía para la temporada {season}.")

    del_equipo = sched[(sched["home_team"] == team_abbr) | (sched["away_team"] == team_abbr)].copy()
    if del_equipo.empty:
        raise ValueError(f"No se encontraron partidos de {team_abbr} en la temporada {season}.")

    filas = []
    for _, p in del_equipo.sort_values("week").iterrows():
        es_local = p["home_team"] == team_abbr
        rival = p["away_team"] if es_local else p["home_team"]
        propio_score = p["home_score"] if es_local else p["away_score"]
        rival_score = p["away_score"] if es_local else p["home_score"]
        jugado = pd.notna(propio_score) and pd.notna(rival_score)

        resultado = "-"
        if jugado:
            if propio_score > rival_score:
                resultado = f"W {int(propio_score)}-{int(rival_score)}"
            elif propio_score < rival_score:
                resultado = f"L {int(propio_score)}-{int(rival_score)}"
            else:
                resultado = f"E {int(propio_score)}-{int(rival_score)}"

        filas.append({
            "Semana": p.get("week", "?"),
            "Rival": rival,
            "Sede": "vs" if es_local else "@",
            "Fecha": p.get("gameday", ""),
            "Resultado": resultado,
        })

    return pd.DataFrame(filas)


def obtener_posiciones_liga(season: int) -> dict:
    """
    Diccionario {nombre del jugador: posición} de toda la liga, usando
    el roster de nfl_data_py — se usa como respaldo cuando la fuente de
    lesiones no trae la posición del jugador."""
    if not NFL_DATA_PY_OK:
        return {}
    try:
        roster = nfl.import_seasonal_rosters([season])
        if roster is None or roster.empty or "player_name" not in roster.columns:
            return {}
        return dict(zip(roster["player_name"], roster.get("position", "")))
    except Exception:
        return {}


def obtener_roster_equipo(team_abbr: str, season: int) -> pd.DataFrame:
    """
    Plantilla de un equipo para la temporada — nombre, posición y
    número, usando el roster de nfl_data_py.
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    roster = nfl.import_seasonal_rosters([season])
    if roster is None or roster.empty:
        raise ValueError(f"No hay roster disponible todavía para la temporada {season}.")

    del_equipo = roster[roster["team"] == team_abbr]
    if del_equipo.empty:
        raise ValueError(f"No se encontró roster de {team_abbr} para la temporada {season}.")

    columnas_deseadas = ["player_name", "position", "jersey_number"]
    columnas_disponibles = [c for c in columnas_deseadas if c in del_equipo.columns]
    resultado = del_equipo[columnas_disponibles].drop_duplicates().rename(columns={
        "player_name": "Jugador", "position": "Posición", "jersey_number": "Número",
    })
    if "Posición" in resultado.columns:
        resultado = resultado.sort_values("Posición")
    return resultado.reset_index(drop=True)


POSICIONES_CON_FANTASY = ["QB", "RB", "WR", "TE"]
POSICIONES_SIN_FANTASY = ["DL", "LB", "DB"]  # IDP — la mayoría de ligas no las usa, sin fuente conectada
POSICIONES_ESPN = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "K": 5, "DST": 16}  # ID de posición interno de ESPN

_EQUIPOS_ESPN_ID = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LA", 15: "MIA", 16: "MIN",
    17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}


def obtener_ranking_fantasy_espn(season: int, posicion_espn: str, top_n: int = 50) -> pd.DataFrame:
    """
    Ranking de K o DST por puntos de fantasy, vía el endpoint no oficial
    de ESPN Fantasy Football (el mismo que usa su app — 'kona_player_info').
    Es la única fuente que tenemos con puntos reales para estas dos
    posiciones, ya que nflverse no las incluye. No confirmado en vivo
    (sin acceso a internet en este entorno de desarrollo) — el formato
    exacto de la respuesta viene de documentación de la comunidad, no
    de documentación oficial de ESPN.
    """
    position_id = POSICIONES_ESPN.get(posicion_espn)
    if position_id is None:
        raise ValueError(f"Posición no soportada por este endpoint: {posicion_espn}")

    url = f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3"
    filtro = {
        "players": {
            "filterSlotIds": {"value": [position_id]},
            "sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 1, "value": f"{season}"},
            "limit": top_n,
        }
    }
    headers = {"x-fantasy-filter": json.dumps(filtro)}
    r = requests.get(url, headers=headers, params={"view": "kona_player_info"}, timeout=15)
    r.raise_for_status()
    data = r.json()

    filas = []
    for item in data.get("players", []):
        jugador = item.get("player") or {}
        equipo_id = jugador.get("proTeamId")
        puntos = None
        for stat in jugador.get("stats", []) or []:
            if stat.get("seasonId") == season and stat.get("statSourceId") == 0:
                puntos = stat.get("appliedTotal")
                break
        filas.append({
            "Jugador": jugador.get("fullName", "?"),
            "Equipo": _EQUIPOS_ESPN_ID.get(equipo_id, "?"),
            "Posición": posicion_espn,
            "Puntos": puntos if puntos is not None else 0.0,
        })

    resultado = pd.DataFrame(filas).sort_values("Puntos", ascending=False).reset_index(drop=True)
    return resultado.head(top_n)



def obtener_ranking_fantasy(season: int, posicion: str = None, top_n: int = 50) -> pd.DataFrame:
    """
    Ranking de jugadores por puntos de fantasy de la temporada, usando
    la columna de puntos ya calculada por nflverse (fantasy_points_ppr
    si está disponible, si no fantasy_points normal). Solo cubre
    QB/RB/WR/TE — nflverse no incluye puntos de fantasy para K/DST
    (usan otra lógica de puntuación) ni para posiciones defensivas
    individuales (eso es para ligas IDP, un formato distinto).

    Si la temporada pedida todavía no tiene su archivo de datos
    publicado en nflverse (típico apenas arranca la temporada — da
    error 404), cae automáticamente a la temporada anterior y lo avisa
    en el resultado (stats.attrs["temporada_usada"]).
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    temporada_usada = season
    uso_respaldo = False
    try:
        datos = nfl.import_seasonal_data([season])
        if datos is None or datos.empty:
            raise ValueError("vacío")
    except Exception:
        # nfl.import_seasonal_data() está fallando con 404 de raíz — se
        # cae al respaldo que descarga el archivo de nflverse a mano. Si
        # tampoco tiene renglones para esta temporada (típico apenas
        # arranca, el archivo se actualiza con un poco de retraso),
        # reintenta con la temporada anterior.
        try:
            datos = _stats_temporada_nflverse_directo([season])
            uso_respaldo = True
        except Exception:
            temporada_usada = season - 1
            try:
                datos = _stats_temporada_nflverse_directo([temporada_usada])
                uso_respaldo = True
            except Exception as e:
                raise ValueError(f"No hay estadísticas de jugadores disponibles ni para {season} ni para {temporada_usada}: {e}")

    columna_puntos = None
    for candidata in ["fantasy_points_ppr", "fantasy_points"]:
        if candidata in datos.columns:
            columna_puntos = candidata
            break
    if columna_puntos is None:
        raise ValueError("Esta fuente no trae puntos de fantasy precalculados.")

    if not uso_respaldo:
        roster = nfl.import_seasonal_rosters([temporada_usada])[["player_id", "player_name", "position", "team"]].drop_duplicates("player_id")
        datos = datos.merge(roster, on="player_id", how="left")

    if posicion:
        datos = datos[datos["position"] == posicion]

    resultado = (
        datos[["player_name", "team", "position", columna_puntos]]
        .dropna(subset=[columna_puntos])
        .sort_values(columna_puntos, ascending=False)
        .head(top_n)
        .rename(columns={"player_name": "Jugador", "team": "Equipo", "position": "Posición", columna_puntos: "Puntos"})
        .reset_index(drop=True)
    )
    resultado.attrs["columna_usada"] = columna_puntos
    resultado.attrs["temporada_usada"] = temporada_usada
    return resultado


def obtener_lideres_estadisticos(season: int, top_n: int = 5) -> dict:
    """
    Devuelve los líderes de la temporada en yardas de pase, carrera y
    recepción, usando datos agregados por jugador de nfl_data_py.
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    uso_respaldo = False
    try:
        datos = nfl.import_seasonal_data([season])
        if datos is None or datos.empty:
            raise ValueError("vacío")
    except Exception:
        try:
            datos = _stats_temporada_nflverse_directo([season])
            uso_respaldo = True
        except Exception:
            try:
                datos = _stats_temporada_nflverse_directo([season - 1])
                uso_respaldo = True
            except Exception as e:
                raise ValueError(f"No hay estadísticas de jugadores disponibles ni para {season} ni para {season - 1}: {e}")

    if not uso_respaldo:
        jugadores = nfl.import_seasonal_rosters([season])[["player_id", "player_name", "team"]].drop_duplicates("player_id")
        datos = datos.merge(jugadores, on="player_id", how="left")

    def top(col):
        if col not in datos.columns:
            return pd.DataFrame()
        return (
            datos[["player_name", "team", col]]
            .dropna(subset=[col])
            .sort_values(col, ascending=False)
            .head(top_n)
        )

    return {
        "pase": top("passing_yards"),
        "carrera": top("rushing_yards"),
        "recepcion": top("receiving_yards"),
    }


# ---------------------------------------------------------------------------
# 4. CLIMA VÍA OpenWeatherMap
#    Regístrate gratis en https://openweathermap.org/api para tu API key.
# ---------------------------------------------------------------------------
OPENWEATHER_API_KEY = "TU_API_KEY_AQUI"

# Coordenadas de estadios (completa/ajusta según necesites; solo ejemplos).
# Los equipos con techo cerrado (indoor) no necesitan pronóstico de viento/lluvia.
ESTADIOS = {
    "KC":  {"lat": 39.0489, "lon": -94.4839, "techo": False},
    "BUF": {"lat": 42.7738, "lon": -78.7870, "techo": False},
    "GB":  {"lat": 44.5013, "lon": -88.0622, "techo": False},
    "MIA": {"lat": 25.9580, "lon": -80.2389, "techo": False},
    "DAL": {"lat": 32.7473, "lon": -97.0945, "techo": True},
    "LV":  {"lat": 36.0909, "lon": -115.1833, "techo": True},
    "NO":  {"lat": 29.9511, "lon": -90.0812, "techo": True},
    # agrega el resto de los 32 equipos según los necesites
}


def obtener_clima_estadio(team_abbr: str, api_key: str = OPENWEATHER_API_KEY) -> dict:
    """
    Devuelve pronóstico actual (temperatura, viento, lluvia) para el estadio
    del equipo local. Si el estadio tiene techo, regresa condiciones neutras.
    """
    if api_key == "TU_API_KEY_AQUI":
        return {"error": "OPENWEATHER_API_KEY no configurada"}

    info = ESTADIOS.get(team_abbr)
    if not info:
        return {"error": f"Sin coordenadas registradas para {team_abbr}"}
    if info["techo"]:
        return {"techo_cerrado": True, "temp_c": 21, "viento_kmh": 0, "lluvia": False}

    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"lat": info["lat"], "lon": info["lon"], "appid": api_key, "units": "metric"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return {
            "techo_cerrado": False,
            "temp_c": data["main"]["temp"],
            "viento_kmh": round(data["wind"]["speed"] * 3.6, 1),
            "lluvia": "rain" in data,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# 5. LÍNEA DE APUESTAS VÍA The Odds API
#    Regístrate gratis en https://the-odds-api.com para tu API key.
# ---------------------------------------------------------------------------
ODDS_API_KEY = "TU_API_KEY_AQUI"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"


def obtener_lineas_apuestas(api_key: str = ODDS_API_KEY, region: str = "us") -> pd.DataFrame:
    """
    Devuelve un DataFrame con spreads y totals de todas las casas de apuestas
    disponibles para los partidos próximos. Filtra luego por los equipos que
    te interesen.
    """
    if api_key == "TU_API_KEY_AQUI":
        return pd.DataFrame()

    try:
        params = {"apiKey": api_key, "regions": region, "markets": "spreads,totals"}
        r = requests.get(ODDS_API_URL, params=params, timeout=10)
        r.raise_for_status()
        eventos = r.json()

        filas = []
        for ev in eventos:
            for casa in ev.get("bookmakers", []):
                for mercado in casa.get("markets", []):
                    for outcome in mercado.get("outcomes", []):
                        filas.append({
                            "partido": f"{ev['away_team']} @ {ev['home_team']}",
                            "casa": casa["title"],
                            "mercado": mercado["key"],
                            "equipo": outcome["name"],
                            "valor": outcome.get("point"),
                            "precio": outcome.get("price"),
                        })
        return pd.DataFrame(filas)
    except Exception as e:
        print(f"Error al obtener líneas: {e}")
        return pd.DataFrame()


def favorito_segun_mercado(odds_df: pd.DataFrame, equipo_a: str, equipo_b: str) -> str | None:
    """
    A partir del DataFrame de obtener_lineas_apuestas, determina qué equipo
    es favorito (spread negativo = favorito) usando el consenso (promedio)
    entre casas de apuestas.
    """
    if odds_df.empty:
        return None
    spreads = odds_df[
        (odds_df["mercado"] == "spreads") &
        (odds_df["equipo"].isin([equipo_a, equipo_b]))
    ]
    if spreads.empty:
        return None
    promedio = spreads.groupby("equipo")["valor"].mean()
    return promedio.idxmin()  # el spread más negativo es el favorito


# ---------------------------------------------------------------------------
# 6. SISTEMA DE PUNTAJE COMPARATIVO
# ---------------------------------------------------------------------------
def _score_1_a_10(valor: float, minimo: float, maximo: float, invertir: bool = False) -> float:
    """
    Convierte un valor a una calificación de 1 a 10 según dónde cae entre
    el mínimo y el máximo de TODA LA LIGA para esa métrica (1 = el peor
    equipo de la liga en esa métrica, 10 = el mejor). invertir=True para
    métricas donde un valor más bajo es mejor (ej. puntos permitidos).
    """
    if maximo == minimo:
        return 5.5  # todos los equipos empatados en esa métrica
    pct = (valor - minimo) / (maximo - minimo)
    if invertir:
        pct = 1 - pct
    pct = min(max(pct, 0.0), 1.0)
    return 1 + 9 * pct


def comparar_equipos(stats: pd.DataFrame, equipo_a: str, equipo_b: str,
                      local: str = None, favorito_mercado: str = None,
                      clima_local: dict = None) -> dict:
    """
    Compara dos equipos usando WEIGHTS y devuelve el puntaje total de cada
    uno más el desglose por categoría.

    A diferencia de un esquema "el que va mejor se lleva todos los puntos",
    cada equipo recibe una calificación de 1 a 10 en cada métrica según su
    posición relativa a TODA LA LIGA (no solo contra el rival), y los
    puntos de esa categoría se reparten proporcionalmente a esa
    calificación. Así un equipo apenas mejor que otro se refleja como
    apenas mejor, no como si arrasara en la categoría.

    favorito_mercado: resultado de favorito_segun_mercado() — suma puntos
        de "linea_apuestas" al equipo que el mercado favorece.
    clima_local: resultado de obtener_clima_estadio() para el equipo local —
        si hay viento fuerte (>25 km/h) o lluvia, favorece ligeramente al
        equipo con más peso en el ataque terrestre (proxy simple).

    Nota: localía, clima y línea de apuestas siguen siendo bonos de
    contexto (no son estadísticas de rendimiento de todo el año), así que
    se mantienen como antes — van completos a un solo equipo, no se
    reparten en escala 1-10.
    """
    a = stats[stats["team"] == equipo_a].iloc[0]
    b = stats[stats["team"] == equipo_b].iloc[0]

    puntaje = {equipo_a: 0.0, equipo_b: 0.0}
    desglose = []

    comparaciones = [
        ("defensa_puntos_permitidos", "puntos_permitidos", True),   # menor es mejor
        ("defensa_pase_permitido", "yardas_pase_permitidas", True),
        ("defensa_run_permitido", "yardas_run_permitidas", True),
        ("defensa_turnovers_forzados", "turnovers_forzados", False),  # mayor es mejor
        ("ataque_puntos", "puntos_ataque", False),
        ("ataque_pase", "yardas_pase", False),
        ("ataque_run", "yardas_run", False),
        ("ataque_turnovers_cometidos", "turnovers_cometidos", True),  # menor es mejor
    ]

    # Las columnas de jugadores clave solo se agregan a la comparación si
    # están presentes en `stats` (es decir, si se combinó con
    # combinar_stats_con_jugadores() antes de llamar a esta función).
    comparaciones_jugadores = [
        ("qb1_desempeno", "qb1_desempeno_score", False),
        ("rb1_desempeno", "rb1_desempeno_score", False),
        ("wr1_desempeno", "wr1_desempeno_score", False),
        ("te1_desempeno", "te1_desempeno_score", False),
    ]
    for peso_key, columna, menor_es_mejor in comparaciones_jugadores:
        if columna in stats.columns:
            comparaciones.append((peso_key, columna, menor_es_mejor))

    for peso_key, columna, menor_es_mejor in comparaciones:
        peso = WEIGHTS.get(peso_key, 0)
        val_a, val_b = a[columna], b[columna]
        minimo, maximo = stats[columna].min(), stats[columna].max()

        score_a = _score_1_a_10(val_a, minimo, maximo, invertir=menor_es_mejor)
        score_b = _score_1_a_10(val_b, minimo, maximo, invertir=menor_es_mejor)

        pts_a = peso * score_a / 10
        pts_b = peso * score_b / 10
        puntaje[equipo_a] += pts_a
        puntaje[equipo_b] += pts_b

        # Para categorías de jugador clave (qb1/rb1/wr1/te1), muestra el
        # nombre del jugador junto al valor si la columna existe.
        prefijo_nombre = columna.replace("_desempeno_score", "_nombre")
        etiqueta_a = val_a
        etiqueta_b = val_b
        if prefijo_nombre in stats.columns:
            nombre_a, nombre_b = a.get(prefijo_nombre), b.get(prefijo_nombre)
            if nombre_a:
                etiqueta_a = f"{val_a:.1f} ({nombre_a})"
            if nombre_b:
                etiqueta_b = f"{val_b:.1f} ({nombre_b})"

        desglose.append({
            "categoria": peso_key, "peso": peso,
            "equipo_a": equipo_a, "valor_a": etiqueta_a, "score_a": round(score_a, 1), "puntos_a": round(pts_a, 2),
            "equipo_b": equipo_b, "valor_b": etiqueta_b, "score_b": round(score_b, 1), "puntos_b": round(pts_b, 2),
        })

    if local:
        pts_a = HOME_FIELD_BONUS if local == equipo_a else 0.0
        pts_b = HOME_FIELD_BONUS if local == equipo_b else 0.0
        puntaje[local] += HOME_FIELD_BONUS
        desglose.append({
            "categoria": "local", "peso": HOME_FIELD_BONUS,
            "equipo_a": equipo_a, "valor_a": "local" if local == equipo_a else "visitante",
            "score_a": "-", "puntos_a": round(pts_a, 2),
            "equipo_b": equipo_b, "valor_b": "local" if local == equipo_b else "visitante",
            "score_b": "-", "puntos_b": round(pts_b, 2),
        })

    if favorito_mercado and favorito_mercado in puntaje:
        peso = WEIGHTS.get("linea_apuestas", 0)
        pts_a = peso if favorito_mercado == equipo_a else 0.0
        pts_b = peso if favorito_mercado == equipo_b else 0.0
        puntaje[favorito_mercado] += peso
        desglose.append({
            "categoria": "linea_apuestas", "peso": peso,
            "equipo_a": equipo_a, "valor_a": "favorito" if favorito_mercado == equipo_a else "-",
            "score_a": "-", "puntos_a": round(pts_a, 2),
            "equipo_b": equipo_b, "valor_b": "favorito" if favorito_mercado == equipo_b else "-",
            "score_b": "-", "puntos_b": round(pts_b, 2),
        })

    if clima_local and not clima_local.get("techo_cerrado") and not clima_local.get("error"):
        condiciones_dificiles = clima_local.get("viento_kmh", 0) > 25 or clima_local.get("lluvia")
        if condiciones_dificiles:
            # Proxy simple: favorece a quien tiene más yardas por tierra (ataque más "clima-resistente")
            peso = WEIGHTS.get("clima", 0)
            ganador_clima = equipo_a if a["yardas_run"] > b["yardas_run"] else equipo_b
            pts_a = peso if ganador_clima == equipo_a else 0.0
            pts_b = peso if ganador_clima == equipo_b else 0.0
            puntaje[ganador_clima] += peso
            desglose.append({
                "categoria": "clima", "peso": peso,
                "equipo_a": equipo_a, "valor_a": round(a["yardas_run"], 1), "score_a": "-", "puntos_a": round(pts_a, 2),
                "equipo_b": equipo_b, "valor_b": round(b["yardas_run"], 1), "score_b": "-", "puntos_b": round(pts_b, 2),
            })

    return {"puntaje": puntaje, "desglose": desglose}


def probabilidad_victoria(
    puntaje: dict, equipo_a: str, equipo_b: str, max_posible: float, techo: float = 0.85,
) -> dict:
    """
    Convierte la diferencia de puntaje en una probabilidad de victoria (%)
    usando una curva logística, calibrada para que aunque un equipo gane
    TODAS las categorías, la probabilidad tope en `techo` (85% por default)
    en vez de dispararse a un irreal 99-100% — el fútbol americano siempre
    tiene incertidumbre.
    """
    diff = puntaje[equipo_a] - puntaje[equipo_b]
    if max_posible <= 0:
        return {equipo_a: 0.5, equipo_b: 0.5}

    k = math.log(techo / (1 - techo)) / max_posible
    p_a = 1 / (1 + math.exp(-k * diff))
    return {equipo_a: p_a, equipo_b: 1 - p_a}


def imprimir_resultado(resultado: dict, equipo_a: str, equipo_b: str):
    print("\n=== DESGLOSE POR CATEGORÍA ===")
    for fila in resultado["desglose"]:
        print(
            f"{fila['categoria']:30s} | "
            f"{fila['equipo_a']}: {fila['valor_a']!s:>10} (score {fila['score_a']}) → +{fila['puntos_a']:.2f} | "
            f"{fila['equipo_b']}: {fila['valor_b']!s:>10} (score {fila['score_b']}) → +{fila['puntos_b']:.2f}"
        )

    print("\n=== PUNTAJE TOTAL ===")
    total = resultado["puntaje"]
    for eq, pts in total.items():
        print(f"{eq}: {pts}")

    ganador = max(total, key=total.get)
    diferencia = abs(total[equipo_a] - total[equipo_b])
    max_posible = sum(WEIGHTS.values()) + HOME_FIELD_BONUS
    confianza = round((diferencia / max_posible) * 100, 1)
    print(f"\n🏆 Pronóstico: {ganador} (confianza relativa: {confianza}%)")


# ---------------------------------------------------------------------------
# 7. EJECUCIÓN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    SEASON = 2025          # temporada a analizar
    EQUIPO_A = "KC"        # abreviatura estilo nflverse (KC, BUF, SF, DAL, etc.)
    EQUIPO_B = "BUF"
    LOCAL = "BUF"           # quién juega en casa (o None)

    if not NFL_DATA_PY_OK:
        print("Instala nfl_data_py para correr el modelo: pip install nfl_data_py")
    else:
        stats = obtener_stats_temporada(SEASON)

        # --- Clima (solo si configuraste OPENWEATHER_API_KEY) ---
        clima = None
        if OPENWEATHER_API_KEY != "TU_API_KEY_AQUI":
            clima = obtener_clima_estadio(LOCAL)

        # --- Línea de apuestas (solo si configuraste ODDS_API_KEY) ---
        favorito = None
        if ODDS_API_KEY != "TU_API_KEY_AQUI":
            odds_df = obtener_lineas_apuestas()
            favorito = favorito_segun_mercado(odds_df, EQUIPO_A, EQUIPO_B)

        resultado = comparar_equipos(
            stats, EQUIPO_A, EQUIPO_B,
            local=LOCAL, favorito_mercado=favorito, clima_local=clima,
        )
        imprimir_resultado(resultado, EQUIPO_A, EQUIPO_B)

    # Ejemplo de datos complementarios (lesiones/récord vía ESPN):
    # print(obtener_lesiones_espn(EQUIPO_A))
    # print(obtener_record_espn(EQUIPO_A))
