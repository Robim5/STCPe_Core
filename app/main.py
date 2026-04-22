from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import hmac
from collections import deque
from time import monotonic

from app.config import (
    IS_PRODUCTION,
    API_KEY,
    IS_VERCEL,
    ENABLE_BACKGROUND_POLLING,
    CRON_SECRET,
    CORS_ALLOW_ORIGINS,
    ALLOW_API_KEY_QUERY_PARAM,
    REQUIRE_API_KEY_IN_PRODUCTION,
    SECURITY_HEADERS_ENABLED,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)
from app import database
from app.services import stcp_realtime, stcp_paragens, calculadora
from app.routers import health, autocarros, linhas, paragens, tempo


_rate_limit_por_ip: dict[str, deque[float]] = {}


# tira ip real do pedido
def _obter_ip_cliente(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "desconhecido"


# controla pedidos por janela
def _excedeu_rate_limit(ip: str) -> bool:
    agora = monotonic()
    limite_janela = agora - RATE_LIMIT_WINDOW_SECONDS
    fila = _rate_limit_por_ip.setdefault(ip, deque())

    while fila and fila[0] < limite_janela:
        fila.popleft()

    if len(fila) >= RATE_LIMIT_REQUESTS:
        return True

    fila.append(agora)

    # poda cache para evitar crescer demais
    if len(_rate_limit_por_ip) > 10000:
        for chave, registos in list(_rate_limit_por_ip.items()):
            while registos and registos[0] < limite_janela:
                registos.popleft()
            if not registos:
                _rate_limit_por_ip.pop(chave, None)

    return False


# valida chave sem vazar timing
def _api_key_valida(request: Request) -> bool:
    if not API_KEY:
        return False

    chave = request.headers.get("X-API-Key")
    if ALLOW_API_KEY_QUERY_PARAM:
        chave = chave or request.query_params.get("api_key")

    if not chave:
        return False

    return hmac.compare_digest(chave, API_KEY)


# arranca recursos e fecha limpo
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("A iniciar nucleo...")
    await database.criar_pool()
    await stcp_realtime.inicializar_tabela_veiculos()
    stcp_paragens.carregar_paragens()
    calculadora.carregar_tempos_gtfs()

    tarefa_realtime = None
    if ENABLE_BACKGROUND_POLLING and not IS_VERCEL:
        tarefa_realtime = asyncio.create_task(stcp_realtime.loop_atualizacao_continua())
    else:
        # serverless sem loop infinito ativo
        await stcp_realtime.garantir_dados_recentes(force=True)

    app.state.realtime_task = tarefa_realtime

    yield

    print("A encerrar nucleo...")

    tarefa_realtime = getattr(app.state, "realtime_task", None)
    if tarefa_realtime:
        tarefa_realtime.cancel()
        try:
            await tarefa_realtime
        except asyncio.CancelledError:
            pass

    await database.fechar_pool()


# cria app e liga ciclo de vida
app = FastAPI(
    title="STCPe Core API",
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

# cors para chamadas de browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# mete headers extra de seguranca
@app.middleware("http")
async def adicionar_headers_seguranca(request: Request, call_next):
    response = await call_next(request)

    if SECURITY_HEADERS_ENABLED:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if IS_PRODUCTION:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    return response


# valida cron api key e limite
@app.middleware("http")
async def verificar_api_key(request: Request, call_next):
    path = request.url.path

    if RATE_LIMIT_ENABLED and path.startswith("/api/"):
        ip = _obter_ip_cliente(request)
        if _excedeu_rate_limit(ip):
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
                content={"detail": "Demasiados pedidos. Tenta novamente em instantes."},
            )

    if path == "/api/internal/refresh":
        if CRON_SECRET:
            auth = request.headers.get("Authorization", "")
            if hmac.compare_digest(auth, f"Bearer {CRON_SECRET}"):
                return await call_next(request)
            return JSONResponse(status_code=401, content={"detail": "CRON_SECRET invalido ou em falta."})

        if API_KEY:
            if _api_key_valida(request):
                return await call_next(request)
            return JSONResponse(status_code=401, content={"detail": "API Key invalida ou em falta."})

        return JSONResponse(
            status_code=503,
            content={"detail": "Endpoint interno sem segredo configurado. Define CRON_SECRET."},
        )

    if path.startswith("/api/"):
        if IS_PRODUCTION and REQUIRE_API_KEY_IN_PRODUCTION and not API_KEY:
            return JSONResponse(
                status_code=503,
                content={"detail": "API_KEY obrigatoria em producao e nao configurada."},
            )

        if API_KEY and not _api_key_valida(request):
            return JSONResponse(status_code=401, content={"detail": "API Key invalida ou em falta."})

    return await call_next(request)


# liga rotas da api
app.include_router(health.router)
app.include_router(autocarros.router)
app.include_router(linhas.router)
app.include_router(paragens.router)
app.include_router(tempo.router)