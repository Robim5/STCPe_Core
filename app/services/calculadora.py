import csv
import math
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from statistics import median

# pasta dos ficheiros GTFS
_PASTA_CSV = Path(__file__).resolve().parent.parent.parent / "dados" / "infoCVS"

# tempos programados do GTFS separados por periodo do dia
# (route_id, direction, periodo) -> {stop_code: median_cumulative_seconds}
_tempos_gtfs_periodo = {}
# fallback global (todas as viagens): (route_id, direction) -> {stop_code: median_cumulative_seconds}
_tempos_gtfs_global = {}

# fator de correcao estrada vs linha reta (urbano Porto)
_FATOR_ESTRADA = 1.35

# tempo medio de paragem por estacao intermediaria (segundos)
_TEMPO_PARAGEM_S = 25

# velocidade media efetiva de autocarro urbano (km/h) - inclui paragens, semaforos, transito
_VELOCIDADE_MEDIA_URBANA = 15.0


def _periodo_de_segundos(seg: int) -> str:
    """determina o periodo do dia com base em segundos desde meia-noite"""
    s = seg % 86400
    if s < 23400:       # 00:00 - 06:30
        return "madrugada"
    elif s < 34200:     # 06:30 - 09:30
        return "ponta_manha"
    elif s < 59400:     # 09:30 - 16:30
        return "dia"
    elif s < 70200:     # 16:30 - 19:30
        return "ponta_tarde"
    else:               # 19:30 - 24:00
        return "noite"


def _parse_time(t: str) -> int:
    """converte HH:MM:SS para total de segundos"""
    parts = t.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def carregar_tempos_gtfs():
    """
    carrega os tempos programados do GTFS (stop_times.csv + trips.csv)
    separa viagens por periodo do dia (madrugada, ponta manha, dia, ponta tarde, noite)
    para que as estimativas reflitam o transito real de cada periodo
    """
    global _tempos_gtfs_periodo, _tempos_gtfs_global

    trips_file = _PASTA_CSV / "trips.csv"
    stop_times_file = _PASTA_CSV / "stop_times.csv"

    if not trips_file.exists() or not stop_times_file.exists():
        print("Aviso: Ficheiros GTFS nao encontrados. ETA usara calculo por distancia.")
        return

    # trip_id -> (route_id, direction_id)
    trip_route = {}
    with open(trips_file, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trip_route[row["trip_id"]] = (row["route_id"], int(row["direction_id"]))

    # agrupar stop_times por trip
    trip_stops = defaultdict(list)
    with open(stop_times_file, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trip_stops[row["trip_id"]].append(row)

    # colecionar tempos acumulados por (rota, sentido, periodo) e globalmente
    acum_periodo = defaultdict(lambda: defaultdict(list))
    acum_global = defaultdict(lambda: defaultdict(list))

    for tid, stops in trip_stops.items():
        if tid not in trip_route:
            continue

        route, direction = trip_route[tid]
        stops.sort(key=lambda x: int(x["stop_sequence"]))

        if not stops:
            continue

        base_time = _parse_time(stops[0]["departure_time"])
        periodo = _periodo_de_segundos(base_time)

        for s in stops:
            arr = _parse_time(s["arrival_time"])
            cumulativo = arr - base_time
            # filtrar anomalias (tempos negativos ou superiores a 3h)
            if 0 <= cumulativo <= 10800:
                acum_periodo[(route, direction, periodo)][s["stop_id"]].append(cumulativo)
                acum_global[(route, direction)][s["stop_id"]].append(cumulativo)

    # mediana por periodo (min 3 viagens para ser representativo)
    for key, stops_dict in acum_periodo.items():
        _tempos_gtfs_periodo[key] = {}
        for stop_code, times in stops_dict.items():
            if len(times) >= 3:
                _tempos_gtfs_periodo[key][stop_code] = median(times)

    # mediana global (fallback)
    for key, stops_dict in acum_global.items():
        _tempos_gtfs_global[key] = {}
        for stop_code, times in stops_dict.items():
            _tempos_gtfs_global[key][stop_code] = median(times)

    n_periodo = len(_tempos_gtfs_periodo)
    n_global = len(_tempos_gtfs_global)
    print(f"GTFS: {n_global} rotas globais + {n_periodo} rotas por periodo carregadas.")


def _procurar_codigo_gtfs(tempos: dict, codigo: str):
    """
    tenta encontrar o tempo acumulado para um codigo de paragem
    primeiro tenta match exato, depois tenta match pela base do codigo
    (ex: MCBL no JSON pode corresponder a MCBL3 no GTFS)
    """
    # match exato
    if codigo in tempos:
        return tempos[codigo]

    # match por base (remover digitos finais)
    base = codigo.rstrip("0123456789")
    if not base:
        return None

    for gtfs_code, tempo in tempos.items():
        if gtfs_code.rstrip("0123456789") == base:
            return tempo

    return None


def calcular_distancia(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    calcula a distancia entre dois pontos geograficos usando a formula de Haversine
     lat1, lon1: coordenadas do ponto 1
     lat2, lon2: coordenadas do ponto 2
    """
    R = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(R * c, 1)


def calcular_distancia_rota(
    paragens: list, indice_inicio: int, indice_fim: int
) -> float:
    """
    calcula a distancia pela rota
    basicamente a soma dos segmentos entre paragens consecutivas
    """
    if indice_inicio >= indice_fim:
        return 0.0

    distancia_total = 0.0
    for i in range(indice_inicio, indice_fim):
        p1 = paragens[i]
        p2 = paragens[i + 1]
        distancia_total += calcular_distancia(
            p1["lat"], p1["lon"], p2["lat"], p2["lon"]
        )

    return round(distancia_total, 1)


def encontrar_paragem_mais_proxima(lat: float, lon: float, paragens: list) -> tuple:
    """
    encontra a paragem mais proxima de um ponto
    retorna indice, distancia_metros
    """
    menor_dist = float("inf")
    indice = -1

    for i, p in enumerate(paragens):
        dist = calcular_distancia(lat, lon, p["lat"], p["lon"])
        if dist < menor_dist:
            menor_dist = dist
            indice = i

    return indice, round(menor_dist, 1)


def estimar_tempo_chegada(distancia_metros: float, velocidade_kmh: float) -> float:
    """
    LEGADO - calculo simples por distancia/velocidade
    mantido para compatibilidade mas nao deve ser usado diretamente
    """
    velocidade = max(velocidade_kmh, 12.0)
    velocidade_ms = velocidade * 1000 / 3600
    tempo_segundos = distancia_metros / velocidade_ms
    return round(tempo_segundos / 60, 1)


def estimar_tempo_chegada_v2(
    linha: str,
    sentido: str,
    paragens_rota: list,
    indice_bus: int,
    indice_destino: int,
    velocidade_atual: float,
) -> tuple:
    """
    estima o tempo de chegada usando tempos programados do GTFS quando disponiveis
    com fallback para calculo melhorado por distancia

    usa tempos especificos do periodo do dia (ponta manha/tarde, dia, noite, madrugada)
    para estimativas mais realistas conforme o transito tipico

    retorna (tempo_minutos, distancia_metros, metodo)
    metodo: 'gtfs' se usou tempos programados, 'calculo' se usou fallback
    """
    direction = 0 if sentido == "ida" else 1

    # distancia para incluir na resposta (corrigida com fator estrada)
    dist_reta = calcular_distancia_rota(paragens_rota, indice_bus, indice_destino)
    dist_estimada = round(dist_reta * _FATOR_ESTRADA, 1)

    code_bus = paragens_rota[indice_bus]["codigo"]
    code_dest = paragens_rota[indice_destino]["codigo"]

    # determinar periodo atual do dia
    agora = datetime.now()
    seg_dia = agora.hour * 3600 + agora.minute * 60 + agora.second
    periodo = _periodo_de_segundos(seg_dia)

    # tentar GTFS com tempos especificos do periodo
    key_periodo = (linha, direction, periodo)
    tempos = _tempos_gtfs_periodo.get(key_periodo)
    if tempos:
        t_bus = _procurar_codigo_gtfs(tempos, code_bus)
        t_dest = _procurar_codigo_gtfs(tempos, code_dest)
        if t_bus is not None and t_dest is not None:
            delta = t_dest - t_bus
            if delta > 0:
                return round(delta / 60.0, 1), dist_estimada, "gtfs"

    # fallback: GTFS global (todas as viagens)
    key_global = (linha, direction)
    tempos = _tempos_gtfs_global.get(key_global)
    if tempos:
        t_bus = _procurar_codigo_gtfs(tempos, code_bus)
        t_dest = _procurar_codigo_gtfs(tempos, code_dest)
        if t_bus is not None and t_dest is not None:
            delta = t_dest - t_bus
            if delta > 0:
                return round(delta / 60.0, 1), dist_estimada, "gtfs"

    # fallback: calculo melhorado por distancia
    num_paragens_entre = max(0, indice_destino - indice_bus - 1)
    tempo_paragens_s = num_paragens_entre * _TEMPO_PARAGEM_S

    velocidade_ms = _VELOCIDADE_MEDIA_URBANA * 1000 / 3600
    tempo_viagem_s = dist_estimada / velocidade_ms

    tempo_total_s = tempo_viagem_s + tempo_paragens_s
    tempo_min = round(tempo_total_s / 60.0, 1)

    return tempo_min, dist_estimada, "calculo"
