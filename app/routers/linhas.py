from fastapi import APIRouter, Query, HTTPException
from app.database import garantir_pool
from app.services import stcp_paragens

router = APIRouter(prefix="/api", tags=["Linhas"])


@router.get("/linhas")
async def listar_linhas():
    return {"linhas": stcp_paragens.obter_info_linhas()}


@router.get("/linhas/{linha}/paragens")
async def paragens_da_linha(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")

    resultado = stcp_paragens.obter_paragens_linha(linha.upper(), sentido)
    if resultado is None:
        raise HTTPException(404, detail=f"Linha '{linha}' ou sentido '{sentido}' nao encontrado.")
    return {"linha": linha.upper(), "paragens": resultado}


@router.get("/linhas/{linha}/shape")
async def shape_da_linha(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")
    pool = await garantir_pool()
    if not pool:
        raise HTTPException(503, detail="Base de dados indisponivel.")

    linha_upper = linha.upper()
    async with pool.acquire() as conn:
        if sentido:
            direction = 0 if sentido == "ida" else 1
            rows = await conn.fetch(
                """
                SELECT DISTINCT s.shape_id, s.shape_pt_lat, s.shape_pt_lon, s.shape_pt_sequence
                FROM shapes s
                JOIN trips t ON t.shape_id = s.shape_id
                JOIN routes r ON r.route_id = t.route_id
                WHERE r.route_short_name = $1 AND t.direction_id = $2
                ORDER BY s.shape_id, s.shape_pt_sequence
                """,
                linha_upper,
                direction,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT DISTINCT s.shape_id, s.shape_pt_lat, s.shape_pt_lon, s.shape_pt_sequence
                FROM shapes s
                JOIN trips t ON t.shape_id = s.shape_id
                JOIN routes r ON r.route_id = t.route_id
                WHERE r.route_short_name = $1
                ORDER BY s.shape_id, s.shape_pt_sequence
                """,
                linha_upper,
            )

    if not rows:
        raise HTTPException(404, detail=f"Shape da linha '{linha_upper}' nao encontrado.")

    # agrupar por shape_id
    shapes = {}
    for r in rows:
        sid = r["shape_id"]
        if sid not in shapes:
            shapes[sid] = []
        shapes[sid].append({"lat": r["shape_pt_lat"], "lon": r["shape_pt_lon"]})
    return {"linha": linha_upper, "shapes": shapes}
