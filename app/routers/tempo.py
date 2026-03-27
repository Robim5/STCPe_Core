from fastapi import APIRouter, Query, HTTPException
from app.services import stcp_paragens, stcp_realtime, calculadora

router = APIRouter(prefix="/api", tags=["Tempo"])


@router.get("/tempo/{linha}/{codigo_paragem}")
async def tempo_chegada(
    linha: str,
    codigo_paragem: str,
    sentido: str = Query(...),
):
    if sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")

    linha_upper = linha.upper()
    codigo_upper = codigo_paragem.upper()

    # verificar se a paragem existe nesta linha e sentido
    resultado = stcp_paragens.encontrar_paragem_por_codigo(linha_upper, sentido, codigo_upper)
    if resultado is None:
        raise HTTPException(
            404,
            detail=f"Paragem '{codigo_upper}' nao encontrada na linha '{linha_upper}' sentido '{sentido}'.",
        )

    indice_destino, paragem_destino = resultado
    paragens_rota = stcp_paragens.todas_paragens[linha_upper][sentido]

    # buscar autocarros ativos nesta linha e sentido
    autocarros_linha = stcp_realtime.autocarros_por_linha.get(linha_upper, [])
    autocarros_sentido = [b for b in autocarros_linha if b["sentido"] == sentido]

    if not autocarros_sentido:
        return {
            "linha": linha_upper,
            "sentido": sentido,
            "paragem": {
                "codigo": paragem_destino["codigo"],
                "nome": paragem_destino["nome"],
                "lat": paragem_destino["lat"],
                "lon": paragem_destino["lon"],
            },
            "estimativas": [],
            "total_autocarros": 0,
            "mensagem": "Nenhum autocarro ativo nesta linha/sentido neste momento.",
        }

    estimativas = []

    for bus in autocarros_sentido:
        # encontrar em que ponto da rota o autocarro esta
        indice_bus, _ = calculadora.encontrar_paragem_mais_proxima(
            bus["lat"], bus["lon"], paragens_rota
        )

        # so interessa se ele estiver antes da paragem destino
        if indice_bus >= indice_destino:
            continue

        # distancia pela rota
        dist_rota = calculadora.calcular_distancia_rota(paragens_rota, indice_bus, indice_destino)

        # estimar tempo de chegada
        tempo_min = calculadora.estimar_tempo_chegada(dist_rota, bus["velocidade"])

        estimativas.append({
            "veiculo_id": bus["veiculo_id"],
            "tempo_estimado_min": tempo_min,
            "distancia_metros": dist_rota,
            "velocidade_atual": bus["velocidade"],
            "lat": bus["lat"],
            "lon": bus["lon"],
            "ultima_atualizacao": bus["ultima_atualizacao"],
        })

    # ordenar por tempo
    estimativas.sort(key=lambda x: x["tempo_estimado_min"])

    return {
        "linha": linha_upper,
        "sentido": sentido,
        "paragem": {
            "codigo": paragem_destino["codigo"],
            "nome": paragem_destino["nome"],
            "lat": paragem_destino["lat"],
            "lon": paragem_destino["lon"],
        },
        "estimativas": estimativas,
        "total_autocarros": len(estimativas),
    }
