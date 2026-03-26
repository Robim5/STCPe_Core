import httpx
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from app.database import obter_pool

# carrega os segredos obscuros
load_dotenv()

# dados na ram
memoria_autocarros = [] # dados brutos da STCP
autocarros_processados = [] # dados limpos e organizados
autocarros_por_linha = {} # indexados por linha (ex: {"600": [...], "200": [...]})
ultima_atualizacao = None

# mapeamento sentido STCP onde 0 = ida e 1 = volta
SENTIDO_MAP = {0: "ida", 1: "volta"}

def processar_dados(dados_raw: list) -> tuple:
    """
    processa dados brutos da API STCP
    extrai info relevante e indexa por linha
    """
    processados = []
    por_linha = {}

    for veiculo in dados_raw:
        try:
            anotacoes = veiculo.get("annotations", {}).get("value", [])

            linha = None
            sentido_num = None

            for a in anotacoes:
                if a.startswith("stcp:route:"):
                    linha = a.replace("stcp:route:", "").upper()
                elif a.startswith("stcp:sentido:"):
                    try:
                        sentido_num = int(a.replace("stcp:sentido:", ""))
                    except ValueError:
                        pass

            if not linha:
                continue

            # coodenadas geojson é [longitude, latitude]
            coords = veiculo.get("location", {}).get("value", {}).get("coordinates", [])
            if len(coords) < 2:
                continue

            lon, lat = coords[0], coords[1]
            sentido = SENTIDO_MAP.get(sentido_num, "desconhecido")

            bus = {
                "veiculo_id": veiculo.get("fleetVehicleId", {}).get("value", ""),
                "linha": linha,
                "sentido": sentido,
                "sentido_num": sentido_num,
                "lat": lat,
                "lon": lon,
                "velocidade": veiculo.get("speed", {}).get("value", 0),
                "bearing": veiculo.get("bearing", {}).get("value", 0),
                "ultima_atualizacao": veiculo.get("observationDateTime", {}).get("value", ""),
            }

            processados.append(bus)

            if linha not in por_linha:
                por_linha[linha] = []
            por_linha[linha].append(bus)

        except Exception:
            continue

    return processados, por_linha


async def inicializar_tabela_veiculos():
    """cria a tabela veiculos se nao existir"""
    pool = obter_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS veiculos (
                    id_veiculo VARCHAR(100) PRIMARY KEY,
                    linha VARCHAR(10) NOT NULL,
                    sentido VARCHAR(20) NOT NULL,
                    latitude DOUBLE NOT NULL,
                    longitude DOUBLE NOT NULL,
                    velocidade DOUBLE DEFAULT 0,
                    bearing DOUBLE DEFAULT 0,
                    timestamp VARCHAR(50),
                    INDEX idx_linha (linha)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
    print("Tabela 'veiculos' pronta.")


async def gravar_veiculos_db(processados: list):
    """grava os veiculos processados na base de dados"""
    pool = obter_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                await cur.execute("DELETE FROM veiculos")
                if processados:
                    sql = """
                        INSERT INTO veiculos
                            (id_veiculo, linha, sentido, latitude, longitude, velocidade, bearing, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    dados = [
                        (
                            b["veiculo_id"], b["linha"], b["sentido"],
                            b["lat"], b["lon"], b["velocidade"],
                            b["bearing"], b["ultima_atualizacao"],
                        )
                        for b in processados
                    ]
                    await cur.executemany(sql, dados)
                await conn.commit()
    except Exception as e:
        print(f"Erro ao gravar veiculos na DB: {e}")


async def atualizar_autocarros():
    global memoria_autocarros, autocarros_processados, autocarros_por_linha, ultima_atualizacao
    url = os.getenv("STCP_API_URL")

    if not url:
        print("Erro: STCP_API_URL nao definido no .env")
        return

    print(f"Polling STCP em: {url[:40]}...")

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                resposta = await client.get(url, headers={"Accept": "application/json"})

                if resposta.status_code == 200:
                    dados = resposta.json()

                    # se a resposta vier dentro de um objeto, extrair a lista
                    if isinstance(dados, dict):
                        # tentar chaves comuns de APIs NGSI-LD
                        for chave in ("results", "data", "entities", "value"):
                            if chave in dados and isinstance(dados[chave], list):
                                dados = dados[chave]
                                break

                    if isinstance(dados, list):
                        memoria_autocarros = dados
                        autocarros_processados, autocarros_por_linha = processar_dados(dados)
                        ultima_atualizacao = datetime.now(timezone.utc).isoformat()
                        await gravar_veiculos_db(autocarros_processados)
                        print(f"Sucesso: {len(autocarros_processados)} autocarros processados de {len(dados)} entidades.")
                    else:
                        print(f"Aviso: Resposta inesperada (tipo: {type(dados).__name__}). Primeiros 200 chars: {str(dados)[:200]}")
                else:
                    print(f"Aviso: STCP respondeu com erro {resposta.status_code}. Body: {resposta.text[:200]}")

            except Exception as e:
                print(f"Erro: Falha ao obter dados da STCP - {e}")

            await asyncio.sleep(5)
