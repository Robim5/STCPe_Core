import asyncio
import httpx
import os
from datetime import datetime, timezone

from app.config import STCP_REFRESH_INTERVAL_SECONDS, STCP_BACKGROUND_INTERVAL_SECONDS
from app.database import garantir_pool
from app.services.realtime.parsing import parse_iso_datetime, processar_dados
from app.services.realtime.storage import (
    carregar_snapshot_veiculos,
    gravar_veiculos_db as gravar_veiculos_db_pool,
    inicializar_tabela_veiculos as inicializar_tabela_veiculos_pool,
)

# estado em memoria para respostas
memoria_autocarros = []  # bruto vindo do feed
autocarros_processados = []  # pronto para os endpoints
autocarros_por_linha = {}  # agrupado por linha
ultima_atualizacao = None
_feed_estado: dict = {}

# intervalo minimo para refresh sob pedido
_INTERVALO_REFRESH_S = STCP_REFRESH_INTERVAL_SECONDS

# intervalo do loop local continuo
_INTERVALO_BACKGROUND_S = STCP_BACKGROUND_INTERVAL_SECONDS

# lock evita refresh paralelo duplicado
_refresh_lock = asyncio.Lock()


# cria tabela de snapshot se faltar
async def inicializar_tabela_veiculos():
    pool = await garantir_pool()
    if not pool:
        return
    await inicializar_tabela_veiculos_pool(pool)


# grava snapshot atual na db
async def gravar_veiculos_db(processados: list):
    pool = await garantir_pool()
    if not pool:
        return
    await gravar_veiculos_db_pool(pool, processados)


# restaura cache da db para memoria
async def carregar_autocarros_da_db():
    global autocarros_processados, autocarros_por_linha, ultima_atualizacao

    pool = await garantir_pool()
    if not pool:
        return

    processados, por_linha, ultima_db = await carregar_snapshot_veiculos(pool)
    autocarros_processados = processados
    autocarros_por_linha = por_linha
    if ultima_db is not None:
        ultima_atualizacao = ultima_db


# verifica se cache ainda esta fresca
def _dados_em_memoria_recentes() -> bool:
    if not autocarros_processados or not ultima_atualizacao:
        return False

    ultima = parse_iso_datetime(ultima_atualizacao)
    if ultima is None:
        return False

    agora = datetime.now(timezone.utc)
    return (agora - ultima).total_seconds() <= _INTERVALO_REFRESH_S


# puxa feed stcp e atualiza cache
def estado_feed() -> dict:
    return dict(_feed_estado)


async def atualizar_autocarros_uma_vez() -> bool:
    """faz um refresh unico a partir da API STCP e persiste na DB"""
    global memoria_autocarros, autocarros_processados, autocarros_por_linha, ultima_atualizacao, _feed_estado

    url = os.getenv("STCP_API_URL")

    if not url:
        print("Aviso: STCP_API_URL nao definido no ambiente")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resposta = await client.get(url, headers={"Accept": "application/json"})

        if resposta.status_code != 200:
            print(f"Aviso: STCP respondeu com erro {resposta.status_code}. Body: {resposta.text[:200]}")
            return False

        dados = resposta.json()

        # tenta extrair lista do envelope
        if isinstance(dados, dict):
            for chave in ("results", "data", "entities", "value"):
                if chave in dados and isinstance(dados[chave], list):
                    dados = dados[chave]
                    break

        if not isinstance(dados, list):
            print(f"Aviso: Resposta inesperada (tipo: {type(dados).__name__}). Primeiros 200 chars: {str(dados)[:200]}")
            return False

        memoria_autocarros = dados
        autocarros_processados, autocarros_por_linha, _feed_estado = processar_dados(dados)
        ultima_atualizacao = datetime.now(timezone.utc).isoformat()
        await gravar_veiculos_db(autocarros_processados)
        modo = _feed_estado.get("modo", "tempo_real")
        print(
            f"Sucesso: {len(autocarros_processados)} autocarros processados de {len(dados)} entidades "
            f"({modo})."
        )
        return True

    except Exception as e:
        print(f"Erro: Falha ao obter dados da STCP - {e}")
        return False


# evita refresh repetido em concorrencia
async def garantir_dados_recentes(force: bool = False):
    """garante dados frescos em memoria; em falha usa fallback do snapshot na DB"""
    if not force and _dados_em_memoria_recentes():
        return

    async with _refresh_lock:
        if not force and _dados_em_memoria_recentes():
            return

        sucesso = await atualizar_autocarros_uma_vez()
        if not sucesso:
            await carregar_autocarros_da_db()


def _bus_para_resposta_api(bus: dict) -> dict:
    # formato igual ao que a api devolve via sql
    return {
        "id_veiculo": bus["veiculo_id"],
        "linha": bus["linha"],
        "sentido": bus["sentido"],
        "latitude": bus["lat"],
        "longitude": bus["lon"],
        "velocidade": bus.get("velocidade", 0),
        "bearing": bus.get("bearing", 0),
        "timestamp": bus.get("ultima_atualizacao"),
        "gps_fresco": bus.get("gps_fresco"),
        "idade_gps_segundos": bus.get("idade_gps_segundos"),
        "nome_rota": None,
        "cor_linha": None,
        "destino": None,
    }


def _filtrar_autocarros_memoria(linha: str | None = None, sentido: str | None = None) -> list[dict]:
    lista = autocarros_processados
    if linha:
        linha_upper = linha.upper()
        lista = [b for b in lista if b["linha"] == linha_upper]
    if sentido:
        lista = [b for b in lista if b["sentido"] == sentido]
    return [_bus_para_resposta_api(b) for b in lista]


async def _enriquecer_metadados_gtfs(pool, dados: list[dict]) -> list[dict]:
    if not dados or not pool:
        return dados

    linhas = list({d["linha"] for d in dados})
    sentido_map = {"ida": 0, "volta": 1}

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    r.route_short_name AS linha,
                    r.route_long_name AS nome_rota,
                    r.route_color AS route_color,
                    t.direction_id,
                    MIN(t.trip_headsign) AS destino
                FROM routes r
                LEFT JOIN trips t ON t.route_id = r.route_id
                WHERE r.route_short_name = ANY($1::text[])
                GROUP BY r.route_short_name, r.route_long_name, r.route_color, t.direction_id
                """,
                linhas,
            )
    except Exception as e:
        print(f"Aviso: nao foi possivel enriquecer autocarros com GTFS - {e}")
        return dados

    meta = {}
    for row in rows:
        chave = (row["linha"], row["direction_id"])
        cor = row["route_color"]
        meta[chave] = {
            "nome_rota": row["nome_rota"],
            "cor_linha": f"#{cor}" if cor else None,
            "destino": row["destino"],
        }

    for item in dados:
        direction = sentido_map.get(item["sentido"])
        extra = meta.get((item["linha"], direction))
        if extra:
            item["nome_rota"] = extra["nome_rota"]
            item["cor_linha"] = extra["cor_linha"]
            item["destino"] = extra["destino"]

    return dados


async def listar_autocarros_api(linha: str | None = None, sentido: str | None = None) -> list[dict]:
    # memoria primeiro a db so enriquece metadados
    dados = _filtrar_autocarros_memoria(linha, sentido)
    pool = await garantir_pool()
    if pool:
        dados = await _enriquecer_metadados_gtfs(pool, dados)
    return dados


# loop continuo para ambientes com worker persistente
async def loop_atualizacao_continua():
    """polling continuo apenas quando ENABLE_BACKGROUND_POLLING=true"""
    url = os.getenv("STCP_API_URL")
    if url:
        print(f"Polling STCP continuo em: {url[:40]}...")

    while True:
        try:
            await garantir_dados_recentes(force=True)
        except Exception as e:
            print(f"Erro no ciclo de atualizacao continua: {e}")
        await asyncio.sleep(_INTERVALO_BACKGROUND_S)


