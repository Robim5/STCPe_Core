from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio

from app.config import IS_PRODUCTION, API_KEY
from app import database
from app.services import stcp_realtime, stcp_paragens, calculadora
from app.routers import health, autocarros, linhas, paragens, tempo


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("A iniciar nucleo...")
    await database.criar_pool()
    await stcp_realtime.inicializar_tabela_veiculos()
    stcp_paragens.carregar_paragens()
    calculadora.carregar_tempos_gtfs()
    asyncio.create_task(stcp_realtime.atualizar_autocarros())
    yield
    print("A encerrar nucleo...")
    await database.fechar_pool()


app = FastAPI(
    title="STCPe Core API",
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def verificar_api_key(request: Request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        chave = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if chave != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "API Key invalida ou em falta."})
    return await call_next(request)


# registar routers
app.include_router(health.router)
app.include_router(autocarros.router)
app.include_router(linhas.router)
app.include_router(paragens.router)
app.include_router(tempo.router)