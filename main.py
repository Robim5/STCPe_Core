from fastapi import FastAPI
import asyncio
import stcp_realtime

app = FastAPI(title = "Núcleo Avançado STCP")

@app.on_event("startup")
async def iniciar_server():
    print("Iniciando o servidor e a atualização dos dados da STCP...")
    asyncio.create_task(stcp_realtime.atualizar_autocarros())

@app.get("/api/autocarros/todos")
async def obter_autocarros():
    return {
        "total_ativos": len(stcp_realtime.memoria_autocarros),
        "dados": stcp_realtime.memoria_autocarros
    }