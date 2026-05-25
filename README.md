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

Já **não** usa os JSON antigos de paragens (`dados/paragens/*.json`). O único JSON manual ativo é `dados/municipios_linhas.json` (filtros por município).

---

## Funcionalidades

| Área | Descrição |
|------|-----------|
| Tempo real | Autocarros ativos via feed STCP, com cache em memória |
| ETA | Tempo estimado até uma paragem (GTFS + GPS + margens calibradas) |
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
│   ├── main.py              # App FastAPI + frontend estático
│   ├── config.py            # Variáveis de ambiente
│   ├── database.py          # Pool PostgreSQL
│   ├── routers/             # Endpoints REST
│   ├── services/
│   │   ├── stcp_realtime.py # Feed STCP + memória
│   │   ├── stcp_paragens.py # Paragens/linhas (GTFS/DB)
│   │   └── calculadora.py   # ETA e distâncias
│   └── static/              # Frontend de testes
├── dados/
│   ├── gtfs/                # Ficheiros GTFS (.txt, no git)
│   └── municipios_linhas.json
├── scripts/
│   ├── load_supabase_data.py
│   └── refresh_supabase_gtfs.py
├── supabase/schema.sql
└── tests/test_api.py
```

---

## Dados e fontes

### GTFS (`dados/gtfs/`)

Coloca aqui os ficheiros standard:

- `routes.txt`
- `trips.txt`
- `stops.txt`
- `stop_times.txt`
- `shapes.txt`

Os `.txt` estão no `.gitignore` (não vão para o repositório). A pasta mantém-se com `.gitkeep`.

**Atualizar a base de dados:**

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..."
```

Validação sem escrever na DB:

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..." --dry-run-only
```

### Tempo real (STCP)

Define `STCP_API_URL` no `.env`. Os autocarros são processados em memória; a DB serve para cache e metadados GTFS, mas **não é obrigatória** para listar autocarros.

### Municípios (`dados/municipios_linhas.json`)

Único JSON manual — mapeia linhas a municípios para filtros futuros na API.

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
| 06:30 – 08:20 | manhã | Usa horários GTFS de `dia` (ainda não é ponta) |
| **08:20 – 09:30** | **ponta_manha** | Ponta estrita — horários GTFS de ponta |
| 09:30 – 16:30 | dia | |
| 16:30 – 17:15 | tarde | Usa horários de `dia` |
| **17:15 – 19:00** | **ponta_tarde** | Ponta estrita |
| 19:00 – 24:00 | noite | |

**Margens aplicadas** (sem duplicar o atraso já presente no GTFS de ponta):

- ~0,8 min base (GPS e variação operacional)
- Em ponta estrita: +0,4 min (GTFS) ou +1 min (cálculo por GPS)
- **+1 min** de alinhamento fino com horários oficiais STCP
- Teto: margem máxima de 30% do tempo base ou 2,5 min

A resposta inclui `tempo_estimado_min`, `tempo_base_min`, `margem_atraso_min`, `periodo`, `ponta_estrita` e `metodo_calculo` (`gtfs` ou `calculo`).

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
DATABASE_URL=postgresql://...   # recomendado para linhas/paragens/shapes
API_KEY=                        # opcional em local
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
- Frontend de testes: http://localhost:8000/ ou http://localhost:8000/frontend
- Health: http://localhost:8000/healthz

---

## Frontend de testes

Painel integrado para testar a API sem Postman.

1. Introduz **URL da API** e **API Key**
2. Escolhe um separador (Chegadas, Autocarros, Paragens, Linhas, Sistema)
3. Clica **Testar** num exemplo (ex.: «Ver quando o próximo 605 chega à Barca»)
4. Vê o resultado JSON em baixo

A configuração (URL e chave) guarda-se automaticamente no browser (`localStorage`).

Ficheiros: `app/static/` (`index.html`, `css/styles.css`, `js/` modular).

---

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `STCP_API_URL` | Sim* | URL do feed STCP em tempo real |
| `DATABASE_URL` | Recomendada | PostgreSQL (Supabase) |
| `API_KEY` | Produção | Protege endpoints `/api/*` |
| `CRON_SECRET` | Refresh interno | `Authorization: Bearer ...` em `/api/internal/refresh` |
| `ENABLE_BACKGROUND_POLLING` | Não | Polling contínuo do feed (Railway) |
| `STCP_REFRESH_INTERVAL_SECONDS` | Não | Mínimo entre refreshes por pedido (default 15) |
| `CORS_ALLOW_ORIGINS` | Produção | Origens permitidas, separadas por vírgula |

Ver `.env.example` para a lista completa.

---

## Deploy (Railway + Supabase)

1. Executar `supabase/schema.sql` no Supabase
2. Carregar GTFS com `scripts/refresh_supabase_gtfs.py`
3. Ligar o repositório ao Railway
4. Configurar variáveis de ambiente (`DATABASE_URL`, `STCP_API_URL`, `API_KEY`, etc.)
5. Validar `GET /healthz`

Guia detalhado: [docs/GUIA_RAILWAY_SUPABASE_PASSO_A_PASSO.md](docs/GUIA_RAILWAY_SUPABASE_PASSO_A_PASSO.md)

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
| GET | `/api/paragem/{codigo}/tempos` | Tempos estimados por linha na paragem |
| GET | `/api/tempo/{linha}/{codigo}` | ETA (`?sentido=ida\|volta` obrigatório) |
| GET | `/api/internal/refresh` | Forçar atualização do feed STCP |

---

## Testar a API

Script incluído:

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
