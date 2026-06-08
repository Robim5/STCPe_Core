from datetime import datetime, timezone

from app.config import STCP_MAX_GPS_AGE_SECONDS, STCP_INCLUIR_GPS_OBSOLETO

# mapeia sentido numerico para texto
SENTIDO_MAP = {0: "ida", 1: "volta"}


# converte timestamp do feed para utc
def parse_obs_datetime(dt_str: str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


# converte timestamp interno para datetime
def parse_iso_datetime(dt_str: str):
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


# cria id quando feed nao manda
def gerar_id_fallback(linha: str, sentido_num: int | None, lon: float, lat: float, obs_dt_str: str, idx: int) -> str:
    sentido_txt = "x" if sentido_num is None else str(sentido_num)
    obs_txt = obs_dt_str or "sem_ts"
    return f"semid_{linha}_{sentido_txt}_{lat:.5f}_{lon:.5f}_{obs_txt}_{idx}"


def _processar_viagens(
    dados_raw: list,
    agora: datetime,
    max_idade_dados_s: int | None,
) -> tuple[list, dict, dict]:
    veiculos_por_id = {}
    filtrados_stale = 0
    entidades_validas = 0
    idades_gps: list[float] = []

    for idx, veiculo in enumerate(dados_raw):
        try:
            anotacoes = veiculo.get("annotations", {}).get("value", [])

            linha = None
            sentido_num = None

            for anotacao in anotacoes:
                if anotacao.startswith("stcp:route:"):
                    linha = anotacao.replace("stcp:route:", "").upper()
                elif anotacao.startswith("stcp:sentido:"):
                    try:
                        sentido_num = int(anotacao.replace("stcp:sentido:", ""))
                    except ValueError:
                        pass

            if not linha:
                continue

            coords = veiculo.get("location", {}).get("value", {}).get("coordinates", [])
            if len(coords) < 2:
                continue

            entidades_validas += 1

            obs_dt_str = veiculo.get("observationDateTime", {}).get("value", "")
            obs_dt = parse_obs_datetime(obs_dt_str)
            idade_s = None
            if obs_dt is not None:
                idade_s = (agora - obs_dt).total_seconds()
                idades_gps.append(idade_s)
                if max_idade_dados_s is not None and idade_s > max_idade_dados_s:
                    filtrados_stale += 1
                    continue

            lon, lat = coords[0], coords[1]
            sentido = SENTIDO_MAP.get(sentido_num, "desconhecido")

            raw_vid = veiculo.get("fleetVehicleId", {}).get("value", "")
            veiculo_id = raw_vid or gerar_id_fallback(linha, sentido_num, lon, lat, obs_dt_str, idx)

            gps_fresco = (
                idade_s is not None
                and max_idade_dados_s is not None
                and idade_s <= max_idade_dados_s
            ) or (max_idade_dados_s is None and idade_s is not None and idade_s <= STCP_MAX_GPS_AGE_SECONDS)

            bus = {
                "veiculo_id": veiculo_id,
                "linha": linha,
                "sentido": sentido,
                "sentido_num": sentido_num,
                "lat": lat,
                "lon": lon,
                "velocidade": veiculo.get("speed", {}).get("value", 0),
                "bearing": veiculo.get("bearing", {}).get("value", 0),
                "ultima_atualizacao": obs_dt_str or agora.isoformat(),
                "gps_fresco": gps_fresco,
                "idade_gps_segundos": round(idade_s, 1) if idade_s is not None else None,
            }

            existente = veiculos_por_id.get(veiculo_id)
            obs_ref = obs_dt or agora
            if existente is None or obs_ref >= existente[0]:
                veiculos_por_id[veiculo_id] = (obs_ref, bus)

        except Exception:
            continue

    processados = [value[1] for value in veiculos_por_id.values()]

    por_linha = {}
    for bus in processados:
        por_linha.setdefault(bus["linha"], []).append(bus)

    stats = {
        "entidades_recebidas": len(dados_raw),
        "entidades_validas": entidades_validas,
        "filtrados_stale": filtrados_stale,
        "gps_fresco": False,
        "modo": "tempo_real",
        "idade_gps_max_segundos": round(max(idades_gps), 1) if idades_gps else None,
        "idade_gps_min_segundos": round(min(idades_gps), 1) if idades_gps else None,
        "aviso": None,
    }

    return processados, por_linha, stats


# limpa e deduplica dados do feed
def processar_dados(
    dados_raw: list,
    max_idade_dados_s: int | None = None,
    incluir_obsoleto: bool | None = None,
) -> tuple[list, dict, dict]:
    if max_idade_dados_s is None:
        max_idade_dados_s = STCP_MAX_GPS_AGE_SECONDS
    if incluir_obsoleto is None:
        incluir_obsoleto = STCP_INCLUIR_GPS_OBSOLETO

    agora = datetime.now(timezone.utc)
    processados, por_linha, stats = _processar_viagens(dados_raw, agora, max_idade_dados_s)

    if processados:
        stats["gps_fresco"] = all(bus.get("gps_fresco") for bus in processados)
        if stats["filtrados_stale"] > 0:
            print(
                f"Filtro fantasma: {stats['filtrados_stale']} autocarros removidos "
                f"(GPS >{max_idade_dados_s}s obsoleto)"
            )
        return processados, por_linha, stats

    if not incluir_obsoleto or stats["entidades_validas"] == 0:
        if stats["filtrados_stale"] > 0:
            print(
                f"Filtro fantasma: {stats['filtrados_stale']} autocarros removidos "
                f"(GPS >{max_idade_dados_s}s obsoleto)"
            )
        return processados, por_linha, stats

    # feed STCP so com GPS antigo: fallback para nao devolver lista vazia
    processados, por_linha, stats_obsoleto = _processar_viagens(dados_raw, agora, max_idade_dados_s=None)
    for bus in processados:
        bus["gps_fresco"] = False

    stats_obsoleto["gps_fresco"] = False
    stats_obsoleto["modo"] = "obsoleto"
    stats_obsoleto["aviso"] = (
        "GPS do feed STCP esta obsoleto; posicoes podem nao refletir a localizacao atual."
    )
    print(
        f"Aviso: feed STCP sem GPS fresco (>{max_idade_dados_s}s). "
        f"A devolver {len(processados)} autocarros em modo obsoleto."
    )
    return processados, por_linha, stats_obsoleto
