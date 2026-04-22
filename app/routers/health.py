import os
from fastapi import APIRouter
from app.services import stcp_realtime, stcp_paragens
from app.database import obter_pool

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
async def health():
    await stcp_realtime.garantir_dados_recentes()

    url_configurada = bool(os.getenv("STCP_API_URL"))
    return {
        "estado": "online",
        "autocarros_ativos": len(stcp_realtime.autocarros_processados),
        "linhas_carregadas": len(stcp_paragens.todas_paragens),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "api_stcp_configurada": url_configurada,
    }


@router.get("/estatisticas")
async def estatisticas():
    await stcp_realtime.garantir_dados_recentes()

    pool = obter_pool()
    totais_db = {}
    if pool:
        async with pool.acquire() as conn:
            totais_db["total_paragens_db"] = await conn.fetchval("SELECT COUNT(*) FROM stops")
            totais_db["total_rotas"] = await conn.fetchval("SELECT COUNT(DISTINCT route_id) FROM routes")
            totais_db["autocarros_na_db"] = await conn.fetchval("SELECT COUNT(*) FROM veiculos")
    return {
        "autocarros_ativos": len(stcp_realtime.autocarros_processados),
        "linhas_com_autocarros": len(stcp_realtime.autocarros_por_linha),
        "linhas_carregadas": len(stcp_paragens.todas_paragens),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        **totais_db,
    }


@router.get("/internal/refresh")
async def refresh_manual():
    """endpoint interno para forcar refresh (ideal para Vercel Cron)"""
    await stcp_realtime.garantir_dados_recentes(force=True)
    return {
        "ok": True,
        "autocarros_ativos": len(stcp_realtime.autocarros_processados),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
    }
