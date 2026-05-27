<p align="center">
  <img src="logo.png" alt="STCPe Logo" width="90%"/>
</p>

<h1 align="center">STCPê Core</h1>

<p align="center">
  O núcleo que move o STCPê -> autocarros do Porto.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/Licença-AGPL--3.0-blue?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white" alt="Railway">
  <img src="https://img.shields.io/badge/DB-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase">
  <img src="https://img.shields.io/badge/Acesso-Privado-red?style=for-the-badge" alt="Privado">
</p>

---

## Sobre

O **STCPê Core** é a API central do projeto STCPê para consulta de autocarros da STCP em tempo real.

A arquitetura foi simplificada para depender sobretudo de:

1. **API STCP em tempo real** (`STCP_API_URL`) -> posição dos autocarros
2. **Dados GTFS** (`dados/gtfs/*.txt`) -> rotas, paragens, horários e shapes
3. **PostgreSQL / Supabase** (opcional mas recomendado) -> persistência GTFS, enriquecimento de metadados e cache de veículos

Já **não** usa os JSON antigos de paragens (`dados/paragens/*.json`). O único JSON manual ativo é `dados/municipios_linhas.json` (município e cor por linha em `/api/linhas`).

---

## Funcionalidades

| Área | Descrição |
|------|-----------|
| Tempo real | Autocarros ativos via feed STCP, com cache em memória |
| ETA | Tempo estimado até uma paragem (GTFS + GPS + margens calibradas) |
| Horário programado | Próxima passagem GTFS na paragem, mesmo sem autocarro GPS a caminho |
| Linhas | Lista de linhas, paragens por sentido, shapes |
| Paragens | Listagem, pesquisa por nome, paragens próximas, tempos por paragem |
| GTFS | Atualização da base de dados a partir de ficheiros `.txt` |
| Frontend | Painel web integrado para testar endpoints com exemplos práticos |
| Segurança | API Key, rate limit, headers HTTP, refresh interno protegido |

---

## Stack

| Componente | Tecnologia |
|----------|------------|
| Framework API | [FastAPI](https://fastapi.tiangolo.com/) |
| Servidor ASGI | [Uvicorn](https://www.uvicorn.org/) |
| Base de dados | [PostgreSQL](https://www.postgresql.org/) via [Supabase](https://supabase.com/) |
| Driver DB | [asyncpg](https://github.com/MagicStack/asyncpg) |
| Deploy | [Railway](https://railway.com/) |
| Frontend tester | HTML/CSS/JS modular em `app/static/` |

---

## Estrutura do projeto

```
STCPe_Core/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── routers/
│   ├── services/
│   │   ├── stcp_realtime.py
│   │   ├── stcp_paragens.py
│   │   ├── calculadora.py
│   │   └── realtime/
│   └── static/
├── dados/gtfs/
├── scripts/
│   ├── load_supabase_data.py
│   └── refresh_supabase_gtfs.py
├── supabase/schema.sql
└── tests/test_api.py
```

---

## Dados e fontes

### GTFS (`dados/gtfs/`)

Coloca aqui os ficheiros standard: `routes.txt`, `trips.txt`, `stops.txt`, `stop_times.txt`, `shapes.txt`.

Os `.txt` estão no `.gitignore`. A pasta mantém-se com `.gitkeep`.

**Atualizar a base de dados:**

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..."
```

Validação sem escrever na DB:

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..." --dry-run-only
```

> **Nota deploy:** paragens/shapes vêm da DB; **ETA e horários programados** leem os `.txt` em `dados/gtfs/` no servidor. Só ter GTFS na Supabase não chega — os ficheiros têm de existir no container Railway.

### Tempo real (STCP)

Define `STCP_API_URL` no `.env`. Os autocarros são processados em memória; a DB serve para cache e metadados GTFS.

### Municípios (`dados/municipios_linhas.json`)

Mapeia linhas a municípios. Aparece em `GET /api/linhas` como `municipio` e `cor`.

---

## Tempo real vs programado

| `tipo` | Quando |
|--------|--------|
| `tempo_real` | Autocarro na linha/sentido, antes da paragem, a ≤500 m da rota |
| `programado` | Sem autocarro útil no GPS; usa próximo horário do GTFS (`metodo_calculo: gtfs_horario`) |

**Integração:** muitas paragens têm vários códigos (ex. Barca: `BVIS1`, `BVIS2`). Usa o código certo por sentido, ou `/api/paragens/pesquisa?nome=Barca`. Para uma linha: `GET /api/tempo/605/BVIS1?sentido=ida`. Header: `X-API-Key`.

---

## Cálculo de chegada (ETA)

A lógica está em `app/services/calculadora.py` (`estimar_tempo_chegada_v2`).

**Ordem de cálculo:**

1. **GTFS por período** — mediana dos `stop_times` para o período do dia
2. **GTFS global** — fallback se faltar dados do período
3. **GPS** — distância na rota + velocidade do autocarro

**Períodos para estimativa em tempo real:**

| Hora | Período | Notas |
|------|---------|-------|
| 00:00 – 06:30 | madrugada | |
| 06:30 – 08:20 | manhã | Usa horários GTFS de `dia` |
| **08:20 – 09:30** | **ponta_manha** | Ponta estrita |
| 09:30 – 16:30 | dia | |
| 16:30 – 17:15 | tarde | Usa horários de `dia` |
| **17:15 – 19:00** | **ponta_tarde** | Ponta estrita |
| 19:00 – 24:00 | noite | |

**Margens:** ~0,8 min base; +0,4 min (GTFS) ou +1 min (GPS) em ponta; +1 min alinhamento STCP; teto 30% ou 2,5 min.

---

## Arranque rápido (local)

1. Clonar e criar ambiente virtual.

```bash
git clone https://github.com/Robim5/STCPe_Core.git
cd STCPe_Core
python -m venv .venv
```

2. Ativar ambiente virtual.

- Windows (PowerShell): `.venv\Scripts\activate`
- Linux/macOS: `source .venv/bin/activate`

3. Instalar dependências.

```bash
pip install -r requirements.txt
```

4. Criar `.env` a partir de `.env.example` e preencher pelo menos:

```env
STCP_API_URL=https://...
DATABASE_URL=postgresql://...
API_KEY=
```

5. Colocar ficheiros GTFS em `dados/gtfs/` e (opcional) carregar na DB:

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..." --yes
```

6. Arrancar a API.

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Frontend: http://localhost:8000/ ou http://localhost:8000/frontend
- OpenAPI (só dev): http://localhost:8000/docs
- Health: http://localhost:8000/healthz

---

## Frontend de testes

Painel integrado para testar a API sem Postman.

1. Introduz **URL da API** e **API Key**
2. Escolhe um separador (Chegadas, Autocarros, Paragens, Linhas, Sistema)
3. Clica **Testar** num exemplo (ex.: próximo 605 na Barca — código `BVIS1`)
4. Vê o resultado JSON em baixo

---

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `STCP_API_URL` | Sim* | URL do feed STCP em tempo real |
| `DATABASE_URL` | Recomendada | PostgreSQL (Supabase) |
| `API_KEY` | Produção | Protege endpoints `/api/*` |
| `CRON_SECRET` | Refresh interno | `Authorization: Bearer ...` em `/api/internal/refresh` |
| `ENABLE_BACKGROUND_POLLING` | Não | Polling contínuo do feed (Railway) |
| `STCP_REFRESH_INTERVAL_SECONDS` | Não | Mínimo entre refreshes (default 15) |
| `CORS_ALLOW_ORIGINS` | Produção | Origens permitidas, separadas por vírgula |
| `DB_SSL`, `DB_SSL_CA_FILE` | Supabase | Ver `.env.example` e `certs/prod-ca-2021.crt` |

Ver `.env.example` para a lista completa.

---

## Deploy (Railway + Supabase)

1. Executar `supabase/schema.sql` no Supabase
2. Carregar GTFS com `scripts/refresh_supabase_gtfs.py`
3. Ligar o repositório ao Railway
4. Configurar variáveis (`DATABASE_URL`, `STCP_API_URL`, `API_KEY`, `CORS_ALLOW_ORIGINS`, etc.)
5. Garantir ficheiros GTFS em `dados/gtfs/` no deploy
6. Validar `GET /healthz`

---

## Segurança

- Autenticação por `X-API-Key` nos endpoints `/api/*` (quando `API_KEY` está definida)
- `/api/internal/refresh` protegido por `CRON_SECRET` ou `API_KEY`
- Rate limiting por IP em produção
- Headers HTTP de segurança ativos
- Documentação OpenAPI (`/docs`) desativada em produção

---

## Endpoints principais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/healthz` | Healthcheck simples (sem auth) |
| GET | `/api/health` | Estado da API e dados carregados |
| GET | `/api/estatisticas` | Contagens (rotas, paragens, autocarros) |
| GET | `/api/autocarros` | Todos os autocarros em tempo real |
| GET | `/api/autocarros/{linha}` | Autocarros de uma linha (`?sentido=ida\|volta`) |
| GET | `/api/linhas` | Lista de linhas e terminais |
| GET | `/api/linhas/{linha}/paragens` | Paragens da linha |
| GET | `/api/linhas/{linha}/shape` | Coordenadas do percurso |
| GET | `/api/paragens` | Todas as paragens (DB) |
| GET | `/api/paragens/proximas` | `?lat=&lon=&raio=` |
| GET | `/api/paragens/pesquisa` | `?nome=` (mín. 2 caracteres) |
| GET | `/api/paragem/{codigo}/info` | Linhas que passam na paragem |
| GET | `/api/paragem/{codigo}/tempos` | Tempo real + programado por linha |
| GET | `/api/tempo/{linha}/{codigo}` | ETA; inclui `horario_programado` se vazio |
| GET | `/api/internal/refresh` | Forçar atualização do feed STCP |

---

## Testar a API

```bash
python tests/test_api.py http://localhost:8000
python tests/test_api.py https://a-tua-api.railway.app A_TUA_API_KEY
```

---

## Licença

Licenciado sob [AGPL-3.0](LICENSE).

---

<p align="center">
  Feito com muito café no Porto por <a href="https://github.com/Robim5">Robim5</a>
</p>
