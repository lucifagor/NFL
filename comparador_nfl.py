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

import math
import pandas as pd
import requests

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
            normalizadas.append({
                "jugador": atleta.get("displayName", item.get("displayName", "?")),
                "posicion": atleta.get("position", {}).get("abbreviation", "?")
                    if isinstance(atleta.get("position"), dict) else "?",
                "estado": item.get("status", item.get("type", {}).get("description", "?")),
                "detalle": item.get("details", {}).get("detail", "") if isinstance(item.get("details"), dict) else "",
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
        r = requests.get(ESPN_NEWS_URL, timeout=15)
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
                filas.append({
                    "equipo": abbr,
                    "jugador": atleta.get("displayName", "?"),
                    "posicion": posicion.get("abbreviation", "?") if isinstance(posicion, dict) else "?",
                    "estado": estado,
                    "detalle": (item.get("details") or {}).get("detail", "") if isinstance(item.get("details"), dict) else "",
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


def obtener_marcadores_actuales() -> list:
    """
    Devuelve los partidos de la semana actual según ESPN (en vivo, próximos
    o recién terminados), con marcador, estado y equipos.
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
            estado = comp.get("status", {}).get("type", {}).get("description", "?")

            partidos.append({
                "away_nombre": (away.get("team") or {}).get("displayName", "?"),
                "away_abbr": (away.get("team") or {}).get("abbreviation", "?"),
                "away_score": away.get("score", "-"),
                "home_nombre": (home.get("team") or {}).get("displayName", "?"),
                "home_abbr": (home.get("team") or {}).get("abbreviation", "?"),
                "home_score": home.get("score", "-"),
                "estado": estado,
                "fecha": ev.get("date", ""),
            })
        return partidos
    except Exception as e:
        return [{"error": str(e)}]


def obtener_standings() -> pd.DataFrame:
    """Devuelve la tabla de posiciones actual (equipo, victorias, derrotas,
    empates, división) según ESPN."""
    try:
        r = requests.get(ESPN_STANDINGS_URL, timeout=10)
        r.raise_for_status()
        data = r.json()

        filas = []
        for conferencia in data.get("children", []):
            nombre_conf = conferencia.get("name", "")
            for entrada in conferencia.get("standings", {}).get("entries", []):
                equipo = entrada.get("team", {})
                stats = {s.get("name"): s.get("value") for s in entrada.get("stats", [])}
                filas.append({
                    "Conferencia": nombre_conf,
                    "Equipo": equipo.get("displayName", "?"),
                    "Abbr": equipo.get("abbreviation", "?"),
                    "V": int(stats.get("wins", 0)),
                    "D": int(stats.get("losses", 0)),
                    "E": int(stats.get("ties", 0)),
                    "% Victorias": round(stats.get("winPercent", 0) * 100, 1),
                })
        df = pd.DataFrame(filas)
        if not df.empty:
            df = df.sort_values(["Conferencia", "% Victorias"], ascending=[True, False]).reset_index(drop=True)
        return df
    except Exception as e:
        raise ValueError(f"No se pudo obtener la tabla de posiciones: {e}")


def obtener_lideres_estadisticos(season: int, top_n: int = 5) -> dict:
    """
    Devuelve los líderes de la temporada en yardas de pase, carrera y
    recepción, usando datos agregados por jugador de nfl_data_py.
    """
    if not NFL_DATA_PY_OK:
        raise RuntimeError("nfl_data_py no disponible")

    datos = nfl.import_seasonal_data([season])
    if datos is None or datos.empty:
        raise ValueError(f"No hay estadísticas de jugadores disponibles para {season} todavía.")

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
def comparar_equipos(stats: pd.DataFrame, equipo_a: str, equipo_b: str,
                      local: str = None, favorito_mercado: str = None,
                      clima_local: dict = None) -> dict:
    """
    Compara dos equipos usando WEIGHTS y devuelve el puntaje total de cada uno
    más el desglose por categoría.

    favorito_mercado: resultado de favorito_segun_mercado() — suma puntos
        de "linea_apuestas" al equipo que el mercado favorece.
    clima_local: resultado de obtener_clima_estadio() para el equipo local —
        si hay viento fuerte (>25 km/h) o lluvia, favorece ligeramente al
        equipo con más peso en el ataque terrestre (proxy simple).
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

    for peso_key, columna, menor_es_mejor in comparaciones:
        peso = WEIGHTS.get(peso_key, 0)
        val_a, val_b = a[columna], b[columna]
        if menor_es_mejor:
            ganador = equipo_a if val_a < val_b else equipo_b
        else:
            ganador = equipo_a if val_a > val_b else equipo_b
        puntaje[ganador] += peso
        desglose.append((peso_key, equipo_a, val_a, equipo_b, val_b, ganador, peso))

    if local:
        puntaje[local] += HOME_FIELD_BONUS
        desglose.append(("local", local, "N/A", "-", "-", local, HOME_FIELD_BONUS))

    if favorito_mercado and favorito_mercado in puntaje:
        peso = WEIGHTS.get("linea_apuestas", 0)
        puntaje[favorito_mercado] += peso
        desglose.append(("linea_apuestas", equipo_a, "-", equipo_b, "-", favorito_mercado, peso))

    if clima_local and not clima_local.get("techo_cerrado") and not clima_local.get("error"):
        condiciones_dificiles = clima_local.get("viento_kmh", 0) > 25 or clima_local.get("lluvia")
        if condiciones_dificiles:
            # Proxy simple: favorece a quien tiene más yardas por tierra (ataque más "clima-resistente")
            peso = WEIGHTS.get("clima", 0)
            ganador_clima = equipo_a if a["yardas_run"] > b["yardas_run"] else equipo_b
            puntaje[ganador_clima] += peso
            desglose.append(("clima", equipo_a, a["yardas_run"], equipo_b, b["yardas_run"], ganador_clima, peso))

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
    for cat, ea, va, eb, vb, ganador, peso in resultado["desglose"]:
        print(f"{cat:35s} | {ea}: {va!s:>10} | {eb}: {vb!s:>10} | +{peso} → {ganador}")

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
