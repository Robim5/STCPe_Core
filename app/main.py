from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import os
import aiomysql
from app import database
from app import stcp_realtime
from app import stcp_paragens
from app import calculadora

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
        SELECT route_id, direction_id, trip_headsign
        FROM trips
        GROUP BY route_id, direction_id
    ) t ON t.route_id = r.route_id
        AND t.direction_id = CASE v.sentido
            WHEN 'ida'   THEN 0
            WHEN 'volta' THEN 1
            ELSE -1
        END
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("A iniciar nucleo...")
    await database.criar_pool()
    await stcp_realtime.inicializar_tabela_veiculos()
    stcp_paragens.carregar_paragens()
    asyncio.create_task(stcp_realtime.atualizar_autocarros())
    yield
    print("A encerrar nucleo...")
    await database.fechar_pool()


# esconder docs em produção (só disponíveis localmente)
_is_production = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PORT"))

app = FastAPI(
    title="STCPe Core API",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# protecao por API Key (se API_KEY estiver definida no .env)
_API_KEY = os.getenv("API_KEY")

@app.middleware("http")
async def verificar_api_key(request: Request, call_next):
    if _API_KEY and request.url.path.startswith("/api/"):
        chave = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if chave != _API_KEY:
            return JSONResponse(status_code=401, content={"detail": "API Key invalida ou em falta."})
    return await call_next(request)


# health
@app.get("/api/health")
async def health():
    url_configurada = bool(os.getenv("STCP_API_URL"))
    return {
        "estado": "online",
        "autocarros_ativos": len(stcp_realtime.autocarros_processados),
        "linhas_carregadas": len(stcp_paragens.todas_paragens),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "api_stcp_configurada": url_configurada,
    }


# estatisticas gerais da rede
@app.get("/api/estatisticas")
async def estatisticas():
    pool = database.obter_pool()
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


# autocarros em tempo real (dados enriquecidos via DB)
@app.get("/api/autocarros")
async def obter_autocarros():
    pool = database.obter_pool()
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


@app.get("/api/autocarros/{linha}")
async def obter_autocarros_linha(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")
    pool = database.obter_pool()
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


# shape / desenho geografico da rota (para mapas)
@app.get("/api/linhas/{linha}/shape")
async def shape_da_linha(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")
    pool = database.obter_pool()
    if not pool:
        raise HTTPException(503, detail="Base de dados indisponivel.")
    linha_upper = linha.upper()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            if sentido:
                direction = 0 if sentido == "ida" else 1
                await cur.execute("""
                    SELECT DISTINCT s.shape_id, s.shape_pt_lat, s.shape_pt_lon, s.shape_pt_sequence
                    FROM shapes s
                    JOIN trips t ON t.shape_id = s.shape_id
                    JOIN routes r ON r.route_id = t.route_id
                    WHERE r.route_short_name = %s AND t.direction_id = %s
                    ORDER BY s.shape_id, s.shape_pt_sequence
                """, (linha_upper, direction))
            else:
                await cur.execute("""
                    SELECT DISTINCT s.shape_id, s.shape_pt_lat, s.shape_pt_lon, s.shape_pt_sequence
                    FROM shapes s
                    JOIN trips t ON t.shape_id = s.shape_id
                    JOIN routes r ON r.route_id = t.route_id
                    WHERE r.route_short_name = %s
                    ORDER BY s.shape_id, s.shape_pt_sequence
                """, (linha_upper,))
            rows = await cur.fetchall()
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


# todas as paragens da STCP (da base de dados)
@app.get("/api/paragens")
async def listar_todas_paragens():
    pool = database.obter_pool()
    if not pool:
        raise HTTPException(503, detail="Base de dados indisponivel.")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops ORDER BY stop_name"
            )
            rows = await cur.fetchall()
    return {"total": len(rows), "paragens": rows}


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