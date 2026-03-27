import os
from fastapi import APIRouter
from app.services import stcp_realtime, stcp_paragens
from app.database import obter_pool

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
async def health():
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
    pool = obter_pool()
    totais_db = {}
    if pool:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM stops")
                totais_db["total_paragens_db"] = (await cur.fetchone())[0]
                await cur.execute("SELECT COUNT(DISTINCT route_id) FROM routes")
                totais_db["total_rotas"] = (await cur.fetchone())[0]
                await cur.execute("SELECT COUNT(*) FROM veiculos")
                totais_db["autocarros_na_db"] = (await cur.fetchone())[0]
    return {
        "autocarros_ativos": len(stcp_realtime.autocarros_processados),
        "linhas_com_autocarros": len(stcp_realtime.autocarros_por_linha),
        "linhas_carregadas": len(stcp_paragens.todas_paragens),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        **totais_db,
    }
