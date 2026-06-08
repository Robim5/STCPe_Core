from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import asyncio
import hmac
from collections import deque
from time import monotonic
from pathlib import Path

from app.config import (
    IS_PRODUCTION,
    API_KEY,
    IS_SERVERLESS,
    ENABLE_BACKGROUND_POLLING,
    modo_refresh_realtime,
    CRON_SECRET,
    CORS_ALLOW_ORIGINS,
    ALLOW_API_KEY_QUERY_PARAM,
    REQUIRE_API_KEY_IN_PRODUCTION,
    SECURITY_HEADERS_ENABLED,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    CACHE_TTL_REALTIME,
    CACHE_TTL_STATIC,
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
        if not chave:
            for nome, valor in request.query_params.items():
                if nome.lower() == "api_key":
                    chave = valor
                    break

    if not chave:
        return False

    return hmac.compare_digest(chave, API_KEY)


# arranca recursos e fecha limpo
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("A iniciar nucleo...")
    await database.criar_pool()
    await stcp_realtime.inicializar_tabela_veiculos()
    await stcp_paragens.carregar_paragens()
    calculadora.carregar_tempos_gtfs()
    calculadora.carregar_horarios_programados()

    modo = modo_refresh_realtime()
    print(f"Refresh tempo real: {modo}")

    tarefa_realtime = None
    if ENABLE_BACKGROUND_POLLING and not IS_SERVERLESS:
        tarefa_realtime = asyncio.create_task(stcp_realtime.loop_atualizacao_continua())
    else:
        # sem loop infinito: arranque + cron externo (/api/internal/refresh) ou refresh por pedido
        await stcp_realtime.garantir_dados_recentes(force=True)
        if modo == "cron":
            print(
                "Agenda GET /api/internal/refresh a cada 15-30s (ex.: cron-job.org) "
                "com Authorization: Bearer <CRON_SECRET>"
            )
        elif modo == "on_demand":
            print(
                "Aviso: sem CRON_SECRET nem polling; dados STCP so atualizam quando um endpoint pede."
            )

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

app.add_middleware(GZipMiddleware, minimum_size=500)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.mount("/frontend/static", StaticFiles(directory=str(_STATIC_DIR)), name="frontend_static_legacy")


@app.get("/", include_in_schema=False)
async def frontend_home():
    # aqui deixamos o front sempre a mao
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/frontend", include_in_schema=False)
async def frontend_alias():
    # rota alternativa para partilhar facil
    return FileResponse(_STATIC_DIR / "index.html")


# healthcheck tecnico para a plataforma (sem auth)
@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}

# cors para chamadas de browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# Cache-Control automatico por tipo de rota (reduz re-fetches e custo de CPU)
_REALTIME_PREFIXES = ("/api/autocarros", "/api/tempo/", "/api/health", "/api/paragem/")
_STATIC_PREFIXES = ("/api/linhas", "/api/paragens", "/api/estatisticas")


@app.middleware("http")
async def adicionar_cache_control(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path

    if "Cache-Control" not in response.headers and path.startswith("/api/"):
        if path == "/api/internal/refresh":
            response.headers["Cache-Control"] = "no-store"
        elif any(path.startswith(p) for p in _REALTIME_PREFIXES):
            response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL_REALTIME}"
        elif any(path.startswith(p) for p in _STATIC_PREFIXES):
            response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL_STATIC}"

    return response


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

    if RATE_LIMIT_ENABLED and path.startswith("/api/") and path != "/api/internal/refresh":
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