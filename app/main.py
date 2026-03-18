from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from app import stcp_realtime
from app import stcp_paragens
from app import calculadora


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("A iniciar nucleo...")
    stcp_paragens.carregar_paragens()
    asyncio.create_task(stcp_realtime.atualizar_autocarros())
    yield
    print("A encerrar nucleo...")


app = FastAPI(title="STCPe Core API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# health
@app.get("/api/health")
async def health():
    import os
    url_configurada = bool(os.getenv("STCP_API_URL"))
    return {
        "estado": "online",
        "autocarros_ativos": len(stcp_realtime.autocarros_processados),
        "linhas_carregadas": len(stcp_paragens.todas_paragens),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "api_stcp_configurada": url_configurada,
    }


# autocarros
@app.get("/api/autocarros/todos")
async def obter_autocarros():
    return {
        "total_ativos": len(stcp_realtime.autocarros_processados),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "dados": stcp_realtime.autocarros_processados,
    }


# linhas e paragens
@app.get("/api/linhas")
async def listar_linhas():
    return {"linhas": stcp_paragens.obter_info_linhas()}


@app.get("/api/linhas/{linha}/paragens")
async def paragens_da_linha(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")

    resultado = stcp_paragens.obter_paragens_linha(linha.upper(), sentido)
    if resultado is None:
        raise HTTPException(404, detail=f"Linha '{linha}' ou sentido '{sentido}' nao encontrado.")
    return {"linha": linha.upper(), "paragens": resultado}


# posição dos autocarros por linha
@app.get("/api/autocarro/{linha}/posicao")
async def posicao_autocarro(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")

    linha_upper = linha.upper()
    autocarros = stcp_realtime.autocarros_por_linha.get(linha_upper, [])

    if sentido:
        autocarros = [b for b in autocarros if b["sentido"] == sentido]

    if not autocarros:
        raise HTTPException(404, detail=f"Nenhum autocarro ativo na linha '{linha_upper}'.")
    return {
        "linha": linha_upper,
        "total": len(autocarros),
        "autocarros": autocarros,
    }


# paragens proximas
@app.get("/api/paragens/proximas")
async def paragens_proximas(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    raio: float = Query(500, ge=50, le=2000),
):
    resultados = stcp_paragens.encontrar_paragens_proximas(lat, lon, raio)
    return {"total": len(resultados), "paragens": resultados}


# tempo estimado de chegada
@app.get("/api/tempo/{linha}/{codigo_paragem}")
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


# pesquisa de paragens por nome
@app.get("/api/paragens/pesquisa")
async def pesquisar_paragens(nome: str = Query(..., min_length=2)):
    resultados = stcp_paragens.pesquisar_paragens_por_nome(nome)
    return {"total": len(resultados), "paragens": resultados}


# info completa de uma paragem (todas as linhas que passam la)
@app.get("/api/paragem/{codigo}/info")
async def info_paragem(codigo: str):
    paragem_info, linhas = stcp_paragens.obter_linhas_na_paragem(codigo)
    if paragem_info is None:
        raise HTTPException(404, detail=f"Paragem '{codigo}' nao encontrada.")
    return {
        "paragem": paragem_info,
        "linhas": linhas,
        "total_linhas": len(linhas),
    }


# todos os autocarros a caminho de uma paragem (todas as linhas)
@app.get("/api/paragem/{codigo}/tempos")
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