from fastapi import APIRouter, Query, HTTPException
import aiomysql
from app.database import obter_pool
from app.services import stcp_paragens, stcp_realtime, calculadora

router = APIRouter(prefix="/api", tags=["Paragens"])


@router.get("/paragens")
async def listar_todas_paragens():
    pool = obter_pool()
    if not pool:
        raise HTTPException(503, detail="Base de dados indisponivel.")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops ORDER BY stop_name"
            )
            rows = await cur.fetchall()
    return {"total": len(rows), "paragens": rows}


@router.get("/paragens/proximas")
async def paragens_proximas(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    raio: float = Query(500, ge=50, le=2000),
):
    resultados = stcp_paragens.encontrar_paragens_proximas(lat, lon, raio)
    return {"total": len(resultados), "paragens": resultados}


@router.get("/paragens/pesquisa")
async def pesquisar_paragens(nome: str = Query(..., min_length=2)):
    resultados = stcp_paragens.pesquisar_paragens_por_nome(nome)
    return {"total": len(resultados), "paragens": resultados}


@router.get("/paragem/{codigo}/info")
async def info_paragem(codigo: str):
    paragem_info, linhas = stcp_paragens.obter_linhas_na_paragem(codigo)
    if paragem_info is None:
        raise HTTPException(404, detail=f"Paragem '{codigo}' nao encontrada.")
    return {
        "paragem": paragem_info,
        "linhas": linhas,
        "total_linhas": len(linhas),
    }


@router.get("/paragem/{codigo}/tempos")
async def tempos_paragem(codigo: str):
    paragem_info, linhas_na_paragem = stcp_paragens.obter_linhas_na_paragem(codigo)
    if paragem_info is None:
        raise HTTPException(404, detail=f"Paragem '{codigo}' nao encontrada.")

    todos_tempos = []

    for entrada in linhas_na_paragem:
        linha = entrada["linha"]
        sentido = entrada["sentido"]

        resultado = stcp_paragens.encontrar_paragem_por_codigo(linha, sentido, codigo)
        if resultado is None:
            continue

        indice_destino, _ = resultado
        paragens_rota = stcp_paragens.todas_paragens[linha][sentido]

        autocarros_linha = stcp_realtime.autocarros_por_linha.get(linha, [])
        autocarros_sentido = [b for b in autocarros_linha if b["sentido"] == sentido]

        for bus in autocarros_sentido:
            indice_bus, _ = calculadora.encontrar_paragem_mais_proxima(
                bus["lat"], bus["lon"], paragens_rota
            )

            if indice_bus >= indice_destino:
                continue

            dist_rota = calculadora.calcular_distancia_rota(paragens_rota, indice_bus, indice_destino)
            tempo_min = calculadora.estimar_tempo_chegada(dist_rota, bus["velocidade"])

            todos_tempos.append({
                "linha": linha,
                "sentido": sentido,
                "origem": entrada["origem"],
                "destino": entrada["destino"],
                "veiculo_id": bus["veiculo_id"],
                "tempo_estimado_min": tempo_min,
                "distancia_metros": dist_rota,
                "velocidade_atual": bus["velocidade"],
                "lat": bus["lat"],
                "lon": bus["lon"],
            })

    todos_tempos.sort(key=lambda x: x["tempo_estimado_min"])

    return {
        "paragem": paragem_info,
        "tempos": todos_tempos,
        "total": len(todos_tempos),
    }
