import os
import ssl
import time
import asyncio
import urllib.parse
import asyncpg
from app.config import IS_PRODUCTION, DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE

# guarda pool global de conexoes
_pool = None
_pool_lock = asyncio.Lock()
_ultima_tentativa_pool = 0.0
_ultimo_erro_pool = None
_RETRY_POOL_SEGUNDOS = 15


# corrige prefixo antigo do dsn
def _normalizar_dsn(dsn: str) -> str:
    """normaliza variantes antigas de DSN para formato PostgreSQL"""
    if not dsn:
        return dsn
    if dsn.startswith("postgres://"):
        return "postgresql://" + dsn[len("postgres://"):]
    return dsn


# monta dsn com vars separadas
def _construir_dsn_fallback() -> str | None:
    """gera DSN a partir de variaveis separadas quando DATABASE_URL nao existe"""
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    if not host or not user:
        return None

    password = os.getenv("DB_PASSWORD", "")
    port = os.getenv("DB_PORT", "5432")
    dbname = os.getenv("DB_NAME", "postgres")

    user_enc = urllib.parse.quote_plus(user)
    pass_enc = urllib.parse.quote_plus(password)
    if password:
        auth = f"{user_enc}:{pass_enc}"
    else:
        auth = user_enc

    return f"postgresql://{auth}@{host}:{port}/{dbname}"


# cria pool apenas uma vez
async def criar_pool():
    """cria o pool de conexoes assincronas ao PostgreSQL"""
    global _pool, _ultima_tentativa_pool, _ultimo_erro_pool

    if _pool is not None:
        return

    async with _pool_lock:
        if _pool is not None:
            return

        _ultima_tentativa_pool = time.monotonic()

        dsn = _normalizar_dsn(os.getenv("DATABASE_URL", ""))
        if not dsn:
            dsn = _construir_dsn_fallback()

        if not dsn:
            print("Aviso: DATABASE_URL nao definido. Endpoints dependentes de DB podem falhar.")
            _pool = None
            _ultimo_erro_pool = "DATABASE_URL nao definido"
            return

        # em producao ssl fica sempre ligado
        usar_ssl = os.getenv("DB_SSL", "true").strip().lower() in ("1", "true", "yes", "on")
        if IS_PRODUCTION and not usar_ssl:
            print("Aviso: DB_SSL=false em producao nao e permitido. A forcar SSL=true.")
            usar_ssl = True
        ssl_ctx = None
        if usar_ssl:
            ssl_ctx = ssl.create_default_context()

        try:
            _pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=DB_POOL_MIN_SIZE,
                max_size=DB_POOL_MAX_SIZE,
                command_timeout=30,
                ssl=ssl_ctx,
                server_settings={"application_name": "stcpe_core"},
            )
            _ultimo_erro_pool = None
            print("DB conectada: PostgreSQL")
        except Exception as e:
            _ultimo_erro_pool = str(e)
            print(f"Aviso: Nao foi possivel ligar a base de dados - {e}")
            _pool = None


async def garantir_pool():
    """tenta obter pool ativo e, se faltar, faz nova tentativa com cooldown"""
    global _ultima_tentativa_pool

    if _pool is not None:
        return _pool

    agora = time.monotonic()
    if (agora - _ultima_tentativa_pool) < _RETRY_POOL_SEGUNDOS:
        return None

    await criar_pool()
    return _pool


# fecha pool no shutdown da app
async def fechar_pool():
    """fecha o pool de conexoes"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# devolve pool para quem precisar
def obter_pool():
    """retorna o pool ativo"""
    return _pool


def obter_ultimo_erro_pool() -> str | None:
    """retorna a ultima mensagem de erro de ligacao ao pool"""
    return _ultimo_erro_pool
