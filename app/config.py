import os
from dotenv import load_dotenv


# carrega .env local sem sobrescrever variaveis ja definidas no ambiente
load_dotenv(override=False)


def _bool_env(nome: str, default: bool) -> bool:
	raw = os.getenv(nome)
	if raw is None:
		return default
	return raw.strip().lower() in ("1", "true", "yes", "on")


def _int_env(nome: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
	raw = os.getenv(nome)
	try:
		valor = int(raw) if raw is not None and raw.strip() else default
	except ValueError:
		valor = default

	if min_value is not None and valor < min_value:
		valor = min_value
	if max_value is not None and valor > max_value:
		valor = max_value
	return valor


def _list_env(nome: str, default: list[str]) -> list[str]:
	raw = os.getenv(nome)
	if raw is None:
		return default
	itens = [p.strip() for p in raw.split(",") if p.strip()]
	return itens or default


# detecao de ambiente
IS_RAILWAY = bool(
	os.getenv("RAILWAY_ENVIRONMENT")
	or os.getenv("RAILWAY_ENVIRONMENT_NAME")
	or os.getenv("RAILWAY_PROJECT_ID")
)
IS_SERVERLESS = _bool_env("IS_SERVERLESS", False)

# permite override por variavel de ambiente
IS_PRODUCTION = _bool_env("IS_PRODUCTION", IS_RAILWAY or IS_SERVERLESS)

# polling interno desligado por defeito (menos CPU/rede no Railway); usar cron em /api/internal/refresh
# em serverless nunca ativar loop infinito
_default_background_polling = False
ENABLE_BACKGROUND_POLLING = _bool_env(
	"ENABLE_BACKGROUND_POLLING",
	_default_background_polling and not IS_SERVERLESS,
)

# protecao por API Key
API_KEY = (os.getenv("API_KEY") or "").strip() or None

# por defeito, em producao exige API_KEY para endpoints /api/* (exceto fluxo interno com CRON_SECRET)
REQUIRE_API_KEY_IN_PRODUCTION = _bool_env("REQUIRE_API_KEY_IN_PRODUCTION", True)

# opcionalmente permitir query param ?api_key=... (é menos seguro, porque pode aparecer em logs)
ALLOW_API_KEY_QUERY_PARAM = _bool_env("ALLOW_API_KEY_QUERY_PARAM", False)

# autenticacao opcional para scheduler externo (Authorization: Bearer <CRON_SECRET>)
CRON_SECRET = (os.getenv("CRON_SECRET") or "").strip() or None


def modo_refresh_realtime() -> str:
	"""como o feed STCP e mantido fresco: background | cron | on_demand"""
	if IS_SERVERLESS or not ENABLE_BACKGROUND_POLLING:
		return "cron" if CRON_SECRET else "on_demand"
	return "background"

# CORS: em producao, negar por omissao e exigir configuracao explicita
_cors_default = ["*"] if not IS_PRODUCTION else []
CORS_ALLOW_ORIGINS = _list_env("CORS_ALLOW_ORIGINS", _cors_default)

# seguranca HTTP basica
SECURITY_HEADERS_ENABLED = _bool_env("SECURITY_HEADERS_ENABLED", True)

# rate limit simples por IP (mitiga brute force e consumo excessivo)
RATE_LIMIT_ENABLED = _bool_env("RATE_LIMIT_ENABLED", IS_PRODUCTION)
RATE_LIMIT_REQUESTS = _int_env("RATE_LIMIT_REQUESTS", 120, min_value=20)
RATE_LIMIT_WINDOW_SECONDS = _int_env("RATE_LIMIT_WINDOW_SECONDS", 60, min_value=10)

# frequencias de refresh com piso de 10s para evitar carga excessiva acidental
STCP_REFRESH_INTERVAL_SECONDS = _int_env("STCP_REFRESH_INTERVAL_SECONDS", 30, min_value=10)
STCP_BACKGROUND_INTERVAL_SECONDS = _int_env("STCP_BACKGROUND_INTERVAL_SECONDS", 30, min_value=10)

# TTL de Cache-Control para respostas publicas (segundos); reduz re-fetches dos clientes
CACHE_TTL_REALTIME = _int_env("CACHE_TTL_REALTIME", 15, min_value=5)
CACHE_TTL_STATIC = _int_env("CACHE_TTL_STATIC", 300, min_value=30)

# limites de conexoes ao PostgreSQL (reduz risco de estourar quota no Supabase)
_db_pool_min = _int_env("DB_POOL_MIN_SIZE", 1, min_value=1, max_value=20)
_db_pool_max = _int_env("DB_POOL_MAX_SIZE", 3, min_value=1, max_value=30)
if _db_pool_min > _db_pool_max:
	_db_pool_min = _db_pool_max
DB_POOL_MIN_SIZE = _db_pool_min
DB_POOL_MAX_SIZE = _db_pool_max
