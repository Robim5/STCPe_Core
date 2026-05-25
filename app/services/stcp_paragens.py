import csv
import json
from pathlib import Path
from app.database import garantir_pool
from app.services import calculadora

_RAIZ = Path(__file__).resolve().parent.parent.parent
_GTFS_DIR = _RAIZ / "dados" / "gtfs"
_FICHEIRO_MUNICIPIOS = Path(__file__).resolve().parent.parent.parent / "dados" / "municipios_linhas.json"
_MUNICIPIOS_POR_LINHA = {}
todas_paragens = {}


def _sentido_txt(direction_id: int | None) -> str:
    return "ida" if direction_id == 0 else "volta"


def _ler_tsv(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    with caminho.open("r", encoding="utf-8-sig", newline="") as ficheiro:
        return list(csv.DictReader(ficheiro))


def carregar_municipios_linhas():
    global _MUNICIPIOS_POR_LINHA

    if not _FICHEIRO_MUNICIPIOS.exists():
        print(f"Aviso: O ficheiro '{_FICHEIRO_MUNICIPIOS}' nao existe.")
        _MUNICIPIOS_POR_LINHA = {}
        return

    try:
        with open(_FICHEIRO_MUNICIPIOS, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _MUNICIPIOS_POR_LINHA = {str(k).upper(): v for k, v in dados.items()}
    except Exception as e:
        print(f"Erro ao carregar municipios por linha: {e}")
        _MUNICIPIOS_POR_LINHA = {}


def obter_cor_linha(linha: str):
    linha_upper = linha.upper()

    if linha_upper.endswith("M"):
        return "preto"

    if linha_upper == "ZC":
        return "azul"

    if linha_upper.isdigit():
        numero = int(linha_upper)
        if 200 <= numero <= 404:
            return "azul"
        if 500 <= numero <= 508:
            return "amarelo"
        if 600 <= numero <= 604:
            return "verde"
        if 700 <= numero <= 707:
            return "vermelho"
        if 800 <= numero <= 806:
            return "roxo"
        if 900 <= numero <= 907:
            return "laranja"

    return None


def obter_municipio_linha(linha: str):
    return _MUNICIPIOS_POR_LINHA.get(linha.upper())


async def _carregar_paragens_da_db() -> dict:
    pool = await garantir_pool()
    if not pool:
        return {}

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH trips_rank AS (
                SELECT
                    r.route_short_name AS linha,
                    t.direction_id AS direction_id,
                    t.trip_id AS trip_id,
                    COUNT(*) AS total_paragens,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.route_short_name, t.direction_id
                        ORDER BY COUNT(*) DESC, t.trip_id
                    ) AS rn
                FROM routes r
                JOIN trips t ON t.route_id = r.route_id
                JOIN stop_times st ON st.trip_id = t.trip_id
                WHERE r.route_short_name IS NOT NULL
                    AND t.direction_id IN (0, 1)
                GROUP BY r.route_short_name, t.direction_id, t.trip_id
            )
            SELECT
                tr.linha,
                tr.direction_id,
                st.stop_sequence,
                COALESCE(s.stop_code, s.stop_id) AS codigo,
                s.stop_name,
                s.stop_lat,
                s.stop_lon
            FROM trips_rank tr
            JOIN stop_times st ON st.trip_id = tr.trip_id
            JOIN stops s ON s.stop_id = st.stop_id
            WHERE tr.rn = 1
            ORDER BY tr.linha, tr.direction_id, st.stop_sequence
            """
        )

    por_linha = {}
    for row in rows:
        linha = (row["linha"] or "").upper().strip()
        if not linha:
            continue
        sentido = _sentido_txt(row["direction_id"])
        por_linha.setdefault(linha, {"ida": [], "volta": []})[sentido].append(
            {
                "codigo": str(row["codigo"]).upper(),
                "nome": row["stop_name"],
                "lat": float(row["stop_lat"]),
                "lon": float(row["stop_lon"]),
            }
        )
    return {linha: sentidos for linha, sentidos in por_linha.items() if sentidos["ida"] or sentidos["volta"]}


def _carregar_paragens_de_gtfs_local() -> dict:
    routes = _ler_tsv(_GTFS_DIR / "routes.txt")
    trips = _ler_tsv(_GTFS_DIR / "trips.txt")
    stop_times = _ler_tsv(_GTFS_DIR / "stop_times.txt")
    stops = _ler_tsv(_GTFS_DIR / "stops.txt")

    if not (routes and trips and stop_times and stops):
        return {}

    route_short_by_id = {}
    for rota in routes:
        route_id = (rota.get("route_id") or "").strip()
        short_name = (rota.get("route_short_name") or "").strip().upper()
        if route_id and short_name:
            route_short_by_id[route_id] = short_name

    stop_by_id = {}
    for stop in stops:
        stop_id = (stop.get("stop_id") or "").strip()
        if not stop_id:
            continue
        try:
            lat = float(stop.get("stop_lat") or "")
            lon = float(stop.get("stop_lon") or "")
        except ValueError:
            continue
        stop_by_id[stop_id] = {
            "codigo": ((stop.get("stop_code") or "").strip() or stop_id).upper(),
            "nome": (stop.get("stop_name") or "").strip() or stop_id,
            "lat": lat,
            "lon": lon,
        }

    trip_meta = {}
    for trip in trips:
        trip_id = (trip.get("trip_id") or "").strip()
        route_id = (trip.get("route_id") or "").strip()
        if not trip_id or route_id not in route_short_by_id:
            continue
        try:
            direction_id = int((trip.get("direction_id") or "0").strip())
        except ValueError:
            direction_id = 0
        trip_meta[trip_id] = (route_short_by_id[route_id], _sentido_txt(direction_id))

    stops_by_trip = {}
    for row in stop_times:
        trip_id = (row.get("trip_id") or "").strip()
        stop_id = (row.get("stop_id") or "").strip()
        if trip_id not in trip_meta or stop_id not in stop_by_id:
            continue
        try:
            sequence = int((row.get("stop_sequence") or "").strip())
        except ValueError:
            continue
        stops_by_trip.setdefault(trip_id, []).append((sequence, stop_id))

    melhores = {}
    for trip_id, paragens_trip in stops_by_trip.items():
        linha, sentido = trip_meta[trip_id]
        chave = (linha, sentido)
        ordenadas = [stop_by_id[stop_id] for _, stop_id in sorted(paragens_trip)]
        if not ordenadas:
            continue
        atual = melhores.get(chave)
        if atual is None or len(ordenadas) > len(atual):
            melhores[chave] = ordenadas

    por_linha = {}
    for (linha, sentido), paragens in melhores.items():
        por_linha.setdefault(linha, {"ida": [], "volta": []})[sentido] = paragens
    return {linha: sentidos for linha, sentidos in por_linha.items() if sentidos["ida"] or sentidos["volta"]}


async def carregar_paragens():
    global todas_paragens

    carregar_municipios_linhas()
    # primeiro tenta o que ja foi carregado na db
    dados_db = await _carregar_paragens_da_db()
    if dados_db:
        todas_paragens = dados_db
        print(f"Paragens carregadas da DB para {len(todas_paragens)} linhas")
        return

    # fallback local para desenvolvimento sem db
    dados_local = _carregar_paragens_de_gtfs_local()
    if dados_local:
        todas_paragens = dados_local
        print(f"Paragens carregadas de GTFS local para {len(todas_paragens)} linhas")
        return

    todas_paragens = {}
    print("Aviso: sem dados de paragens na DB e sem GTFS local")


def obter_linhas():
    """
    retorna lista de todas as linhas disponiveis
    """
    return sorted(todas_paragens.keys())


def obter_paragens_linha(linha: str, sentido: str = None):
    """
    retorna as paragens de uma linha
    se sentido especificado
    filtra por sentido (ida/volta)
    """
    dados_linha = todas_paragens.get(linha)
    if not dados_linha:
        return None

    if sentido:
        paragens = dados_linha.get(sentido)
        if paragens is None:
            return None
        return {sentido: paragens}

    return dados_linha


def encontrar_paragem_por_codigo(linha: str, sentido: str, codigo: str):
    """
    encontra paragem pelo codigo numa linha e sentido
    retorna indice e paragem ou None
    """
    dados_linha = todas_paragens.get(linha)
    if not dados_linha:
        return None

    paragens = dados_linha.get(sentido, [])
    for i, p in enumerate(paragens):
        if p["codigo"].upper() == codigo.upper():
            return i, p

    return None


def encontrar_paragens_proximas(lat: float, lon: float, raio_metros: float = 500):
    """
    encontra todas as paragens dentro de um raio de um ponto de todas as linhas
    """
    resultados = []
    vistos = set()

    for linha, sentidos in todas_paragens.items():
        for sentido, paragens in sentidos.items():
            for p in paragens:
                chave = (p["codigo"], linha, sentido)
                if chave in vistos:
                    continue
                dist = calculadora.calcular_distancia(lat, lon, p["lat"], p["lon"])
                if dist <= raio_metros:
                    vistos.add(chave)
                    resultados.append({
                        "linha": linha,
                        "sentido": sentido,
                        "codigo": p["codigo"],
                        "nome": p["nome"],
                        "lat": p["lat"],
                        "lon": p["lon"],
                        "distancia_metros": dist,
                    })

    resultados.sort(key=lambda x: x["distancia_metros"])
    return resultados


def pesquisar_paragens_por_nome(nome: str):
    """
    pesquisa paragens pelo nome (parcial, case-insensitive)
    retorna lista de paragens unicas com todas as linhas que passam la
    """
    nome_lower = nome.lower()
    paragens_encontradas = {}

    for linha, sentidos in todas_paragens.items():
        for sentido, paragens in sentidos.items():
            for p in paragens:
                if nome_lower in p["nome"].lower():
                    codigo = p["codigo"]
                    if codigo not in paragens_encontradas:
                        paragens_encontradas[codigo] = {
                            "codigo": codigo,
                            "nome": p["nome"],
                            "lat": p["lat"],
                            "lon": p["lon"],
                            "linhas": [],
                        }
                    # evitar duplicar a mesma linha+sentido
                    entrada_linha = {"linha": linha, "sentido": sentido}
                    if entrada_linha not in paragens_encontradas[codigo]["linhas"]:
                        paragens_encontradas[codigo]["linhas"].append(entrada_linha)

    return list(paragens_encontradas.values())


def obter_linhas_na_paragem(codigo: str):
    """
    dado um codigo de paragem, retorna todas as linhas e sentidos que passam la
    com info do terminal (primeira e ultima paragem da rota)
    """
    codigo_upper = codigo.upper()
    resultados = []
    paragem_info = None

    for linha, sentidos in todas_paragens.items():
        for sentido, paragens in sentidos.items():
            for p in paragens:
                if p["codigo"].upper() == codigo_upper:
                    if paragem_info is None:
                        paragem_info = {
                            "codigo": p["codigo"],
                            "nome": p["nome"],
                            "lat": p["lat"],
                            "lon": p["lon"],
                        }
                    primeira = paragens[0]
                    ultima = paragens[-1]
                    resultados.append({
                        "linha": linha,
                        "sentido": sentido,
                        "origem": primeira["nome"],
                        "destino": ultima["nome"],
                    })
                    break

    return paragem_info, resultados


def obter_info_linhas():
    """
    retorna lista de linhas com info dos terminais (origem -> destino) para cada sentido
    """
    info = []
    for linha in sorted(todas_paragens.keys()):
        sentidos = todas_paragens[linha]
        dados_linha = {
            "linha": linha,
            "cor": obter_cor_linha(linha),
            "municipio": obter_municipio_linha(linha),
            "sentidos": {},
        }
        for sentido, paragens in sentidos.items():
            if paragens:
                dados_linha["sentidos"][sentido] = {
                    "origem": paragens[0]["nome"],
                    "destino": paragens[-1]["nome"],
                    "total_paragens": len(paragens),
                }
        info.append(dados_linha)
    return info
