# Guia Passo a Passo - Railway + Supabase

Este documento e o tutorial completo para configurar, atualizar e validar o STCPe Core em Railway + Supabase.

## 1) Pre-requisitos

- conta no GitHub
- conta no Railway
- conta no Supabase
- Python 3.10+
- repositório STCPe_Core clonado

## 2) Preparar base no Supabase (primeira vez)

### 2.1 Criar projeto

1. Entrar no Supabase
2. Criar projeto novo
3. Guardar os dados de ligacao da base

### 2.2 Criar schema

1. Abrir SQL Editor
2. Executar o ficheiro `supabase/schema.sql`

## 3) Carregar GTFS no Supabase

### 3.1 Atualizar CSV

Substituir os CSV em `dados/infoCVS`:

Site GTFS oficial da STCP: https://opendata.porto.digital/dataset/horarios-paragens-e-rotas-em-formato-gtfs-stcp

- routes.csv
- trips.csv
- stops.csv
- stop_times.csv
- shapes.csv

### 3.2 Validar sem escrever na base

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..." --dry-run-only
```

### 3.3 Limpar e recarregar GTFS

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..."
```

Quando pedir confirmacao, escrever:

`ATUALIZAR`

Opcional, sem confirmacao interativa:

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..." --yes
```

## 4) Deploy no Railway

### 4.1 Criar servico

1. Entrar no Railway
2. New Project
3. Deploy from GitHub Repo
4. Selecionar `STCPe_Core`

### 4.2 Confirmar runtime

O projeto usa:

- `Procfile`
- `railway.json`

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Healthcheck tecnico:

- endpoint: `/healthz`

### 4.3 Configurar variaveis no Railway

Configurar no painel Variables:

- STCP_API_URL
- DATABASE_URL
- DB_SSL=true
- DB_SSL_CA_FILE=certs/prod-ca-2021.crt (recomendado, mantem validacao SSL completa do certificado Supabase)
- DB_POOL_MIN_SIZE=1
- DB_POOL_MAX_SIZE=5
- ENABLE_BACKGROUND_POLLING=true
- STCP_BACKGROUND_INTERVAL_SECONDS=10
- STCP_REFRESH_INTERVAL_SECONDS=15
- API_KEY (recomendado)
- REQUIRE_API_KEY_IN_PRODUCTION=true
- ALLOW_API_KEY_QUERY_PARAM=false
- CRON_SECRET (recomendado)
- RATE_LIMIT_ENABLED=true
- RATE_LIMIT_REQUESTS=120
- RATE_LIMIT_WINDOW_SECONDS=60
- SECURITY_HEADERS_ENABLED=true
- CORS_ALLOW_ORIGINS=https://teu-frontend.com

## 5) Validar deploy

### 5.1 Healthcheck tecnico

```bash
curl "https://TEU-DOMINIO/healthz"
```

Esperado:

- 200 OK
- body com `{\"ok\": true}`

### 5.2 API protegida

Sem API key (em producao protegida):

```bash
curl "https://TEU-DOMINIO/api/health"
```

Com API key:

```bash
curl -H "X-API-Key: TUA_CHAVE" "https://TEU-DOMINIO/api/health"
```

### 5.3 Teste automatizado dos endpoints

```bash
python tests/test_api.py https://TEU-DOMINIO TUA_CHAVE
```

## 6) Rotina sempre que GTFS mudar

1. Substituir CSV em `dados/infoCVS`
2. Validar com `--dry-run-only`
3. Recarregar base com `refresh_supabase_gtfs.py`
4. Fazer commit/push dos CSV novos
5. Confirmar novo deploy no Railway
6. Validar `/healthz` e endpoints principais

## 7) Troubleshooting rapido

### 7.1 Railway unhealthy

- confirmar `/healthz`
- verificar logs do Railway

### 7.2 Erro de DB

- confirmar string de ligacao
- confirmar SSL ativo
- confirmar schema aplicado

Se o log mostrar `[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain`:

- definir `DB_SSL_CA_FILE=certs/prod-ca-2021.crt` (o ficheiro ja vem no repo, em `certs/`)
- alternativa menos segura: `DB_SSL_VERIFY=false` (mantem encriptacao mas nao valida o certificado)

### 7.3 401 nos endpoints

- esperado se API_KEY ativa
- enviar header `X-API-Key`

### 7.4 Sem dados de tempo real

- confirmar STCP_API_URL
- verificar logs por timeout/erro no feed

## 8) Checklist final

- deploy Railway em estado Success
- `/healthz` a responder 200
- `/api/health` a responder com API key
- GTFS atualizado na base
- CSV GTFS atualizados no repositório
