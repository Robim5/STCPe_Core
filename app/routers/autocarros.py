from fastapi import APIRouter, Query, HTTPException
import aiomysql
from app.database import obter_pool
from app.services import stcp_realtime

router = APIRouter(prefix="/api", tags=["Autocarros"])

# query principal que cruza veiculos em tempo real com rotas e destinos GTFS
QUERY_AUTOCARROS = """
    SELECT
        v.id_veiculo,
        v.linha,
        v.sentido,
        v.latitude,
        v.longitude,
        v.velocidade,
        v.bearing,
        v.timestamp,
        r.route_long_name  AS nome_rota,
        CONCAT('#', COALESCE(r.route_color, '808080')) AS cor_linha,
        t.trip_headsign    AS destino
    FROM veiculos v
    LEFT JOIN routes r
        ON r.route_short_name = v.linha
    LEFT JOIN (
        SELECT route_id, direction_id, MIN(trip_headsign) AS trip_headsign
        FROM trips
        GROUP BY route_id, direction_id
    ) t ON t.route_id = r.route_id
        AND t.direction_id = CASE v.sentido
            WHEN 'ida'   THEN 0
            WHEN 'volta' THEN 1
            ELSE -1
        END
"""


@router.get("/autocarros")
async def obter_autocarros():
    pool = obter_pool()
    if not pool:
        raise HTTPException(503, detail="Base de dados indisponivel.")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(QUERY_AUTOCARROS)
            rows = await cur.fetchall()
    return {
        "total": len(rows),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "dados": rows,
    }


@router.get("/autocarros/{linha}")
async def obter_autocarros_linha(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")
    pool = obter_pool()
    if not pool:
        raise HTTPException(503, detail="Base de dados indisponivel.")
    linha_upper = linha.upper()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            if sentido:
                await cur.execute(
                    QUERY_AUTOCARROS + " WHERE v.linha = %s AND v.sentido = %s",
                    (linha_upper, sentido),
                )
            else:
                await cur.execute(
                    QUERY_AUTOCARROS + " WHERE v.linha = %s",
                    (linha_upper,),
                )
            rows = await cur.fetchall()
    if not rows:
        raise HTTPException(404, detail=f"Nenhum autocarro ativo na linha '{linha_upper}'.")
    return {
        "linha": linha_upper,
        "total": len(rows),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "dados": rows,
    }
