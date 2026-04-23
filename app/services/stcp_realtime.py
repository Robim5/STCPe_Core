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
async def atualizar_autocarros_uma_vez() -> bool:
    """faz um refresh unico a partir da API STCP e persiste na DB"""
    global memoria_autocarros, autocarros_processados, autocarros_por_linha, ultima_atualizacao

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
        autocarros_processados, autocarros_por_linha = processar_dados(dados)
        ultima_atualizacao = datetime.now(timezone.utc).isoformat()
        await gravar_veiculos_db(autocarros_processados)
        print(f"Sucesso: {len(autocarros_processados)} autocarros processados de {len(dados)} entidades.")
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


