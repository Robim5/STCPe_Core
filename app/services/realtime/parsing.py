from datetime import datetime, timezone

# mapeia sentido numerico para texto
SENTIDO_MAP = {0: "ida", 1: "volta"}
# idade maxima do gps valido
MAX_IDADE_DADOS_S = 180


# converte timestamp do feed para utc
def parse_obs_datetime(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# converte timestamp interno para datetime
def parse_iso_datetime(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# cria id quando feed nao manda
def gerar_id_fallback(linha: str, sentido_num: int | None, lon: float, lat: float, obs_dt_str: str, idx: int) -> str:
    sentido_txt = "x" if sentido_num is None else str(sentido_num)
    obs_txt = obs_dt_str or "sem_ts"
    return f"semid_{linha}_{sentido_txt}_{lat:.5f}_{lon:.5f}_{obs_txt}_{idx}"


# limpa e deduplica dados do feed
def processar_dados(dados_raw: list, max_idade_dados_s: int = MAX_IDADE_DADOS_S) -> tuple[list, dict]:
    agora = datetime.now(timezone.utc)
    veiculos_por_id = {}
    filtrados_stale = 0

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

            # descarta gps muito antigo
            obs_dt_str = veiculo.get("observationDateTime", {}).get("value", "")
            obs_dt = parse_obs_datetime(obs_dt_str)
            if obs_dt is not None:
                idade_s = (agora - obs_dt).total_seconds()
                if idade_s > max_idade_dados_s:
                    filtrados_stale += 1
                    continue

            lon, lat = coords[0], coords[1]
            sentido = SENTIDO_MAP.get(sentido_num, "desconhecido")

            raw_vid = veiculo.get("fleetVehicleId", {}).get("value", "")
            veiculo_id = raw_vid or gerar_id_fallback(linha, sentido_num, lon, lat, obs_dt_str, idx)

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
            }

            existente = veiculos_por_id.get(veiculo_id)
            obs_ref = obs_dt or agora
            if existente is None or obs_ref >= existente[0]:
                veiculos_por_id[veiculo_id] = (obs_ref, bus)

        except Exception:
            continue

    processados = [value[1] for value in veiculos_por_id.values()]

    # agrupa autocarros por linha
    por_linha = {}
    for bus in processados:
        por_linha.setdefault(bus["linha"], []).append(bus)

    if filtrados_stale > 0:
        print(f"Filtro fantasma: {filtrados_stale} autocarros removidos (GPS >3min obsoleto)")

    return processados, por_linha
