import csv
import math
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from statistics import median

# pasta dos ficheiros GTFS
_PASTA_GTFS = Path(__file__).resolve().parent.parent.parent / "dados" / "gtfs"

# tempos programados do GTFS separados por periodo do dia
# (route_id, direction, periodo) -> {stop_code: median_cumulative_seconds}
_tempos_gtfs_periodo = {}
# fallback global (todas as viagens): (route_id, direction) -> {stop_code: median_cumulative_seconds}
_tempos_gtfs_global = {}
# horarios de passagem por paragem: (linha, direction, stop_id)
_horarios_programados = {}

# fator de correcao estrada vs linha reta (urbano Porto)
_FATOR_ESTRADA = 1.35

# tempo medio de paragem por estacao intermediaria (segundos)
_TEMPO_PARAGEM_S = 25

# velocidade media efetiva de autocarro urbano (km/h) - inclui paragens, semaforos, transito
_VELOCIDADE_MEDIA_URBANA = 15.0

# margem leve sempre (gps e variacao operacional)
_BUFFER_BASE_MIN = 0.8
# extra so em ponta ESTRITA e so no fallback por gps
_BUFFER_PONTA_CALCULO_MIN = 1.0
# extra minimo em ponta estrita quando ja vem do gtfs (horario ja e lento)
_BUFFER_PONTA_GTFS_MIN = 0.4
# teto da margem: no maximo 30% do tempo base ou 2.5 min
_MARGEM_MAX_RATIO = 0.30
_MARGEM_MAX_MIN = 2.5
# fator leve no fallback gps em ponta estrita
_FATOR_PONTA_CALCULO = 1.06
# ajuste fino para alinhar com horario oficial stcp (+1 min)
_BUFFER_ALINHAMENTO_MIN = 1.0


def _segundos_agora() -> int:
    agora = datetime.now()
    return agora.hour * 3600 + agora.minute * 60 + agora.second


def periodo_para_eta() -> dict:
    """
    periodo para estimativa em tempo real (diferente do bucket ao carregar gtfs)

    ponta estrita manha: 08:20-09:30 (como referiste)
    fora disso de manha usa horarios 'dia' para nao inflacionar
    """
    s = _segundos_agora()

    if s < 6 * 3600 + 30 * 60:
        return {"periodo": "madrugada", "periodo_gtfs": "madrugada", "ponta_estrita": False}
    if s < 8 * 3600 + 20 * 60:
        return {"periodo": "manha", "periodo_gtfs": "dia", "ponta_estrita": False}
    if s < 9 * 3600 + 30 * 60:
        return {"periodo": "ponta_manha", "periodo_gtfs": "ponta_manha", "ponta_estrita": True}
    if s < 16 * 3600 + 30 * 60:
        return {"periodo": "dia", "periodo_gtfs": "dia", "ponta_estrita": False}
    if s < 17 * 3600 + 15 * 60:
        return {"periodo": "tarde", "periodo_gtfs": "dia", "ponta_estrita": False}
    if s < 19 * 3600:
        return {"periodo": "ponta_tarde", "periodo_gtfs": "ponta_tarde", "ponta_estrita": True}
    return {"periodo": "noite", "periodo_gtfs": "noite", "ponta_estrita": False}


def periodo_atual() -> str:
    return periodo_para_eta()["periodo"]


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


def _formatar_hora(segundos: int) -> str:
    """formata segundos (mod 24h) para HH:MM"""
    s = segundos % 86400
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h:02d}:{m:02d}"


def _codigos_correspondem(codigo_a: str, codigo_b: str) -> bool:
    if codigo_a == codigo_b:
        return True
    base_a = codigo_a.rstrip("0123456789")
    base_b = codigo_b.rstrip("0123456789")
    return bool(base_a and base_a == base_b)


def carregar_tempos_gtfs():
    """
    carrega os tempos programados do GTFS (stop_times.txt + trips.txt)
    separa viagens por periodo do dia (madrugada, ponta manha, dia, ponta tarde, noite)
    para que as estimativas reflitam o transito real de cada periodo
    """
    global _tempos_gtfs_periodo, _tempos_gtfs_global

    trips_file = _PASTA_GTFS / "trips.txt"
    stop_times_file = _PASTA_GTFS / "stop_times.txt"

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


def carregar_horarios_programados():
    """ carrega horarios de passagem (stop_times) para o proximo autocarro programado na paragem, mesmo sem veiculo GPS a caminho """
    global _horarios_programados

    routes_file = _PASTA_GTFS / "routes.txt"
    trips_file = _PASTA_GTFS / "trips.txt"
    stops_file = _PASTA_GTFS / "stops.txt"
    stop_times_file = _PASTA_GTFS / "stop_times.txt"

    if not all(f.exists() for f in (routes_file, trips_file, stops_file, stop_times_file)):
        print("Aviso: Ficheiros GTFS incompletos. Horarios programados indisponiveis.")
        _horarios_programados = {}
        return

    route_short = {}
    with open(routes_file, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            route_id = (row.get("route_id") or "").strip()
            short = (row.get("route_short_name") or "").strip().upper()
            if route_id and short:
                route_short[route_id] = short

    stop_codigo = {}
    with open(stops_file, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stop_id = (row.get("stop_id") or "").strip()
            if not stop_id:
                continue
            code = (row.get("stop_code") or "").strip().upper() or stop_id.upper()
            stop_codigo[stop_id] = code

    trip_meta = {}
    with open(trips_file, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trip_id = (row.get("trip_id") or "").strip()
            route_id = (row.get("route_id") or "").strip()
            if not trip_id or route_id not in route_short:
                continue
            try:
                direction = int((row.get("direction_id") or "0").strip())
            except ValueError:
                direction = 0
            trip_meta[trip_id] = (route_short[route_id], direction)

    horarios = defaultdict(list)
    with open(stop_times_file, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            trip_id = (row.get("trip_id") or "").strip()
            stop_id = (row.get("stop_id") or "").strip()
            arrival = (row.get("arrival_time") or row.get("departure_time") or "").strip()
            if trip_id not in trip_meta or not stop_id or not arrival:
                continue
            linha, direction = trip_meta[trip_id]
            codigo = stop_codigo.get(stop_id, stop_id.upper())
            horarios[(linha, direction, codigo)].append(_parse_time(arrival))

    _horarios_programados = {k: sorted(set(v)) for k, v in horarios.items() if v}
    print(f"GTFS: horarios programados para {len(_horarios_programados)} paragens.")


def _horarios_para_codigo(linha: str, direction: int, codigo: str) -> list[int]:
    codigo_u = codigo.upper()
    candidatos = []
    for (l, d, stop_code), horas in _horarios_programados.items():
        if l != linha or d != direction:
            continue
        if _codigos_correspondem(stop_code, codigo_u):
            candidatos.extend(horas)
    return candidatos


def _segundos_ate_proximo_horario(horarios: list[int], agora: int) -> tuple[int, int] | None:
    if not horarios:
        return None

    melhor_delta = None
    melhor_hora = None

    for h in horarios:
        opcoes = [h]
        if h < 86400:
            opcoes.append(h + 86400)

        for t in opcoes:
            delta = (t - agora) if t >= agora else (t + 86400) - agora
            if melhor_delta is None or delta < melhor_delta:
                melhor_delta = delta
                melhor_hora = t % 86400

    if melhor_delta is None:
        return None
    return melhor_delta, melhor_hora


def proximo_horario_programado(linha: str, sentido: str, codigo: str) -> dict | None:
    """proxima passagem programada GTFS na paragem (independente de GPS ativo)"""
    if not _horarios_programados:
        return None

    direction = 0 if sentido == "ida" else 1
    horarios = _horarios_para_codigo(linha.upper(), direction, codigo)
    if not horarios:
        return None

    resultado = _segundos_ate_proximo_horario(horarios, _segundos_agora())
    if resultado is None:
        return None

    delta_s, hora_s = resultado
    info = periodo_para_eta()
    minutos = round(delta_s / 60.0, 1)

    return {
        "tipo": "programado",
        "horario_chegada": _formatar_hora(hora_s),
        "tempo_estimado_min": minutos,
        "tempo_base_min": minutos,
        "margem_atraso_min": 0.0,
        "periodo": info["periodo"],
        "ponta_estrita": info["ponta_estrita"],
        "metodo_calculo": "gtfs_horario",
        "distancia_metros": None,
        "velocidade_atual": None,
    }


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


def _calcular_margem_chegada(tempo_base_min: float, metodo: str, ponta_estrita: bool, periodo: str) -> dict:
    # evita dupla contagem: gtfs em ponta ja traz viagens lentas da janela 8:20-9:30
    buffer_base = _BUFFER_BASE_MIN
    buffer_ponta = 0.0
    if ponta_estrita:
        if metodo == "gtfs":
            buffer_ponta = _BUFFER_PONTA_GTFS_MIN
        else:
            buffer_ponta = _BUFFER_PONTA_CALCULO_MIN

    buffer_bruto = buffer_base + buffer_ponta
    teto = min(max(tempo_base_min, 0.5) * _MARGEM_MAX_RATIO, _MARGEM_MAX_MIN)
    buffer_total = round(min(buffer_bruto, teto), 1)

    return {
        "periodo": periodo,
        "ponta_estrita": ponta_estrita,
        "buffer_base_min": buffer_base,
        "buffer_ponta_min": buffer_ponta,
        "margem_min": buffer_total,
    }


def _finalizar_estimativa(tempo_base_min: float, info_periodo: dict, metodo: str) -> dict:
    margem = _calcular_margem_chegada(
        tempo_base_min,
        metodo,
        info_periodo["ponta_estrita"],
        info_periodo["periodo"],
    )
    tempo_base = round(max(0.0, tempo_base_min), 1)
    margem_total = round(margem["margem_min"] + _BUFFER_ALINHAMENTO_MIN, 1)
    tempo_final = round(tempo_base + margem_total, 1)
    return {
        "tempo_estimado_min": tempo_final,
        "tempo_base_min": tempo_base,
        "buffer_alinhamento_min": _BUFFER_ALINHAMENTO_MIN,
        **margem,
        "margem_min": margem_total,
    }


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
    """calculo simples por distancia/velocidade + margem de atraso """
    velocidade = max(velocidade_kmh, 12.0)
    velocidade_ms = velocidade * 1000 / 3600
    tempo_segundos = distancia_metros / velocidade_ms
    tempo_base = tempo_segundos / 60.0
    info = periodo_para_eta()
    if info["ponta_estrita"]:
        tempo_base *= _FATOR_PONTA_CALCULO
    return _finalizar_estimativa(tempo_base, info, "calculo")["tempo_estimado_min"]


def estimar_tempo_chegada_v2(
    linha: str,
    sentido: str,
    paragens_rota: list,
    indice_bus: int,
    indice_destino: int,
    velocidade_atual: float,
) -> dict:
    """
    estima chegada a uma paragem
    1) gtfs do periodo certo (ponta estrita so 8:20-9:30 e 17:15-19:00)
    2) fallback gtfs global
    3) fallback gps
    margem pequena sem duplicar atraso ja presente no gtfs de ponta
    """
    direction = 0 if sentido == "ida" else 1
    info = periodo_para_eta()
    periodo_gtfs = info["periodo_gtfs"]

    dist_reta = calcular_distancia_rota(paragens_rota, indice_bus, indice_destino)
    dist_estimada = round(dist_reta * _FATOR_ESTRADA, 1)

    code_bus = paragens_rota[indice_bus]["codigo"]
    code_dest = paragens_rota[indice_destino]["codigo"]

    def _resultado_gtfs(delta_segundos: float) -> dict:
        tempo_base = delta_segundos / 60.0
        out = _finalizar_estimativa(tempo_base, info, "gtfs")
        out["distancia_metros"] = dist_estimada
        out["metodo_calculo"] = "gtfs"
        return out

    key_periodo = (linha, direction, periodo_gtfs)
    tempos = _tempos_gtfs_periodo.get(key_periodo)
    if tempos:
        t_bus = _procurar_codigo_gtfs(tempos, code_bus)
        t_dest = _procurar_codigo_gtfs(tempos, code_dest)
        if t_bus is not None and t_dest is not None:
            delta = t_dest - t_bus
            if delta > 0:
                return _resultado_gtfs(delta)

    key_global = (linha, direction)
    tempos = _tempos_gtfs_global.get(key_global)
    if tempos:
        t_bus = _procurar_codigo_gtfs(tempos, code_bus)
        t_dest = _procurar_codigo_gtfs(tempos, code_dest)
        if t_bus is not None and t_dest is not None:
            delta = t_dest - t_bus
            if delta > 0:
                return _resultado_gtfs(delta)

    num_paragens_entre = max(0, indice_destino - indice_bus - 1)
    tempo_paragens_s = num_paragens_entre * _TEMPO_PARAGEM_S

    velocidade = max(velocidade_atual or 0, _VELOCIDADE_MEDIA_URBANA * 0.8)
    velocidade = min(velocidade, 45.0)
    if info["ponta_estrita"]:
        velocidade *= 0.94

    velocidade_ms = velocidade * 1000 / 3600
    tempo_viagem_s = dist_estimada / velocidade_ms
    tempo_total_s = tempo_viagem_s + tempo_paragens_s
    if info["ponta_estrita"]:
        tempo_total_s *= _FATOR_PONTA_CALCULO

    out = _finalizar_estimativa(tempo_total_s / 60.0, info, "calculo")
    out["distancia_metros"] = dist_estimada
    out["metodo_calculo"] = "calculo"
    return out
