import httpx
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

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


async def atualizar_autocarros():
    global memoria_autocarros, autocarros_processados, autocarros_por_linha, ultima_atualizacao
    url = os.getenv("STCP_API_URL")

    if not url:
        print("Erro: STCP_API_URL nao definido no .env")
        return

    async with httpx.AsyncClient() as client:
        while True:
            try:
                resposta = await client.get(url, headers={"Accept": "application/json"})

                if resposta.status_code == 200:
                    memoria_autocarros = resposta.json()
                    autocarros_processados, autocarros_por_linha = processar_dados(memoria_autocarros)
                    ultima_atualizacao = datetime.now(timezone.utc).isoformat()
                    print(f"Sucesso: {len(autocarros_processados)} autocarros processados.")
                else:
                    print(f"Aviso: STCP respondeu com erro {resposta.status_code}.")

            except Exception as e:
                print(f"Erro: Falha ao obter dados da STCP - {e}")

            await asyncio.sleep(5)
