import csv
import math
from pathlib import Path
from collections import defaultdict
from statistics import median

# pasta dos ficheiros GTFS
_PASTA_CSV = Path(__file__).resolve().parent.parent.parent / "dados" / "infoCVS"

# tempos programados do GTFS: (route_id, direction) -> {stop_code: cumulative_median_seconds}
_tempos_gtfs = {}

# fator de correcao estrada vs linha reta (urbano Porto)
_FATOR_ESTRADA = 1.35

# tempo medio de paragem por estacao intermediaria (segundos)
_TEMPO_PARAGEM_S = 25

# velocidade media efetiva de autocarro urbano (km/h) - inclui paragens, semaforos, transito
_VELOCIDADE_MEDIA_URBANA = 15.0


def _parse_time(t: str) -> int:
    """converte HH:MM:SS para total de segundos"""
    parts = t.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def carregar_tempos_gtfs():
    """
    carrega os tempos programados do GTFS (stop_times.csv + trips.csv)
    para cada (rota, sentido) guarda {codigo_paragem: mediana_segundos_acumulados}
    """
    global _tempos_gtfs

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

    # para cada (rota, sentido), colecionar tempos acumulados por paragem
    acumulados = defaultdict(lambda: defaultdict(list))

    for tid, stops in trip_stops.items():
        if tid not in trip_route:
            continue

        route, direction = trip_route[tid]
        stops.sort(key=lambda x: int(x["stop_sequence"]))

        if not stops:
            continue

        base_time = _parse_time(stops[0]["departure_time"])

        for s in stops:
            arr = _parse_time(s["arrival_time"])
            cumulativo = arr - base_time
            # filtrar anomalias (tempos negativos ou superiores a 3h)
            if 0 <= cumulativo <= 10800:
                acumulados[(route, direction)][s["stop_id"]].append(cumulativo)

    # calcular a mediana para cada paragem
    for key, stops_dict in acumulados.items():
        _tempos_gtfs[key] = {}
        for stop_code, times in stops_dict.items():
            _tempos_gtfs[key][stop_code] = median(times)

    print(f"GTFS: {len(_tempos_gtfs)} rotas com tempos programados carregados.")


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

    retorna (tempo_minutos, distancia_metros, metodo)
    metodo: 'gtfs' se usou tempos programados, 'calculo' se usou fallback
    """
    direction = 0 if sentido == "ida" else 1
    key = (linha, direction)

    # distancia para incluir na resposta (corrigida com fator estrada)
    dist_reta = calcular_distancia_rota(paragens_rota, indice_bus, indice_destino)
    dist_estimada = round(dist_reta * _FATOR_ESTRADA, 1)

    # tentar metodo GTFS
    if key in _tempos_gtfs:
        tempos = _tempos_gtfs[key]

        code_bus = paragens_rota[indice_bus]["codigo"]
        code_dest = paragens_rota[indice_destino]["codigo"]

        t_bus = _procurar_codigo_gtfs(tempos, code_bus)
        t_dest = _procurar_codigo_gtfs(tempos, code_dest)

        if t_bus is not None and t_dest is not None:
            tempo_programado_s = t_dest - t_bus
            if tempo_programado_s > 0:
                tempo_min = round(tempo_programado_s / 60.0, 1)
                return tempo_min, dist_estimada, "gtfs"

    # fallback: calculo melhorado por distancia
    num_paragens_entre = max(0, indice_destino - indice_bus - 1)
    tempo_paragens_s = num_paragens_entre * _TEMPO_PARAGEM_S

    velocidade_ms = _VELOCIDADE_MEDIA_URBANA * 1000 / 3600
    tempo_viagem_s = dist_estimada / velocidade_ms

    tempo_total_s = tempo_viagem_s + tempo_paragens_s
    tempo_min = round(tempo_total_s / 60.0, 1)

    return tempo_min, dist_estimada, "calculo"
