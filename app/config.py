import os

# detecao de ambiente de producao
IS_PRODUCTION = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PORT"))

# protecao por API Key
API_KEY = os.getenv("API_KEY")
