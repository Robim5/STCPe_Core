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
  <img src="https://img.shields.io/badge/Deploy-Vercel-black?style=for-the-badge&logo=vercel&logoColor=white" alt="Vercel">
  <img src="https://img.shields.io/badge/DB-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase">
  <img src="https://img.shields.io/badge/Acesso-Privado%20🔒-red?style=for-the-badge" alt="Privado">
</p>

---

## Sobre o Núcleo STCPê

O **STCPê Core** é o backend centralizado do projeto STCPê, uma plataforma para consulta em tempo real dos autocarros da STCP (Sociedade de Transportes Colectivos do Porto).

Fornece dados de localização, estimativas de tempo de chegada e informações sobre paragens e linhas, prontos a ser consumidos por qualquer aplicação web ou móvel.

> _"Porque esperar pelo seu autocarro não deveria ser um mistério."_

---

## Funcionalidades

- **Localização em tempo real** -> sabe onde está cada autocarro, agora, com destino final e cor da linha
- **Tempo de chegada (ETA)** -> estimativas com base na rota real, não em linha reta
- **Desenho da rota** -> shape geográfico das linhas para desenhar num mapa
- **Todas as paragens** -> lista completa de paragens da STCP via base de dados
- **Paragens por linha** -> consulta as paragens de qualquer linha e sentido
- **Paragens próximas** -> encontra paragens à tua volta por GPS
- **Pesquisa por nome** -> procura qualquer paragem pelo nome
- **Info completa** -> todas as linhas que passam numa paragem, com sentidos e terminais
- **Dados de linhas** -> número, cor, município, origem e destino de cada linha
- **Estatísticas** -> resumo da rede (linhas, paragens, autocarros ativos)
- **Proteção por API Key** -> acesso controlado via header `X-API-Key`

---

## Tecnologias

| Componente | Tecnologia |
|---|---|
| Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Servidor | [Uvicorn](https://www.uvicorn.org/) |
| Base de Dados | PostgreSQL ([Supabase](https://supabase.com/), via [asyncpg](https://github.com/MagicStack/asyncpg)) |
| HTTP Client | [httpx](https://www.python-httpx.org/) |
| Configuração | [python-dotenv](https://pypi.org/project/python-dotenv/) |
| Deploy | [Vercel](https://vercel.com/) |

---

## Estrutura do Projeto

```
STCPe_Core/
├── app/
│   ├── __init__.py                # Package Python
│   ├── main.py                    # App FastAPI, middleware e lifespan
│   ├── config.py                  # Configurações e variáveis de ambiente
│   ├── database.py                # Pool assíncrono de conexões MySQL
│   ├── routers/                   # Endpoints organizados por domínio
│   │   ├── __init__.py
│   │   ├── health.py              # /api/health, /api/estatisticas
│   │   ├── autocarros.py          # /api/autocarros
│   │   ├── linhas.py              # /api/linhas, paragens de linha, shapes
│   │   ├── paragens.py            # /api/paragens, pesquisa, info, tempos
│   │   └── tempo.py               # /api/tempo (ETA)
│   └── services/                  # Lógica de negócio
│       ├── __init__.py
│       ├── calculadora.py         # Cálculos de distância (Haversine) e ETA (GTFS)
│       ├── stcp_paragens.py       # Gestão de paragens e pesquisa
│       └── stcp_realtime.py       # Polling e processamento em tempo real
├── dados/
│   ├── municipios_linhas.json     # Mapa linha -> municipio
│   ├── infoCVS/                   # Dados GTFS estáticos da STCP
│   │   ├── routes.csv
│   │   ├── shapes.csv
│   │   ├── stop_times.csv
│   │   ├── stops.csv
│   │   └── trips.csv
│   └── paragens/                  # Ficheiros JSON com dados de todas as paragens
│       ├── 200tos.json
│       ├── 300tos.json
│       ├── ...
│       └── Zc.json
├── tests/
│   └── test_api.py                # Testes automatizados dos endpoints
├── .env                           # Variáveis de ambiente (não vai para o Git)
├── Procfile                       # Configuração de deploy (Railway)
├── requirements.txt               # Dependências Python
└── README.md
```

---

## Endpoints da API

### Estado do Serviço

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/health` | Estado do serviço, autocarros ativos e linhas carregadas |
| `GET` | `/api/estatisticas` | Resumo geral da rede (totais de linhas, paragens, autocarros) |

### Autocarros

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/autocarros` | Todos os autocarros ativos com posição, velocidade, cor da linha e destino final |
| `GET` | `/api/autocarros/{linha}` | Autocarros de uma linha específica (ex: `/api/autocarros/600`) |

**Parâmetros opcionais:** `sentido` -> filtrar por `ida` ou `volta`

Cada autocarro inclui dados enriquecidos via base de dados:
- `nome_rota` -> nome completo da rota (ex: "Cordoaria - Castêlo da Maia")
- `cor_linha` -> cor hex da linha (ex: "#00FF00")
- `destino` -> destino final (trip_headsign, ex: "Castêlo da Maia")

### Linhas e Paragens

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/linhas` | Lista de todas as linhas com `cor`, `municipio`, origem e destino |
| `GET` | `/api/linhas/{linha}/paragens` | Paragens de uma linha (filtrável por sentido) |
| `GET` | `/api/linhas/{linha}/shape` | Desenho geográfico da rota (coordenadas para mapa) |

`GET /api/linhas` inclui por linha:
- `linha`
- `cor` (`azul`, `amarelo`, `verde`, `vermelho`, `roxo`, `laranja`, `preto`)
- `municipio`
- `sentidos` (`ida`/`volta` com `origem`, `destino`, `total_paragens`)

### Paragens

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/paragens` | Todas as paragens da STCP (da base de dados) |
| `GET` | `/api/paragens/proximas` | Paragens próximas a um ponto GPS |
| `GET` | `/api/paragens/pesquisa` | Pesquisa de paragens por nome |
| `GET` | `/api/paragem/{codigo}/info` | Informação de uma paragem e linhas que passam |
| `GET` | `/api/paragem/{codigo}/tempos` | Todos os autocarros a caminho de uma paragem |

### Tempo de Chegada

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/tempo/{linha}/{codigo_paragem}` | ETA dos autocarros de uma linha para uma paragem |

**Parâmetros obrigatórios:** `sentido` -> `ida` ou `volta`

---

## Exemplos de Utilização

### Paragens próximas a Av. Aliados

```
GET /api/paragens/proximas?lat=41.1480&lon=-8.6111&raio=500
```

### Pesquisar paragens com "maia"

```
GET /api/paragens/pesquisa?nome=maia
```

### Tempo de chegada do 600 para a Trindade (ida)

```
GET /api/tempo/600/TRD1?sentido=ida
```

### Todos os autocarros a caminho do Fórum da Maia

```
GET /api/paragem/FOR1/tempos
```

### Shape da linha 600 (ida) para desenhar num mapa

```
GET /api/linhas/600/shape?sentido=ida
```

### Estatísticas gerais da rede

```
GET /api/estatisticas
```

---

## Instalação Local

### Pré-requisitos

- Python 3.10+
- Acesso à API da STCP (URL privada)

### Passos

```bash
# clonar o repositório
git clone https://github.com/Robim5/STCPe_Core.git
cd STCPe_Core

# criar ambiente virtual
python -m venv .venv

# ativar ambiente virtual
# windows:
.venv\Scripts\activate
# winux/macOS:
source .venv/bin/activate

# instalar dependências
pip install -r requirements.txt

# configurar variáveis de ambiente
# criar ficheiro .env na raiz com:
# STCP_API_URL=<url_da_api_stcp>
# DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db>
# DB_SSL=true
# DB_POOL_MIN_SIZE=1
# DB_POOL_MAX_SIZE=5
# API_KEY=<chave_opcional>
# CRON_SECRET=<segredo_para_cron_vercel>
# REQUIRE_API_KEY_IN_PRODUCTION=true
# ALLOW_API_KEY_QUERY_PARAM=false
# CORS_ALLOW_ORIGINS=https://teu-frontend.com
# RATE_LIMIT_ENABLED=true
# RATE_LIMIT_REQUESTS=120
# RATE_LIMIT_WINDOW_SECONDS=60

# iniciar o servidor
uvicorn app.main:app --reload
```

O servidor fica disponível em `http://localhost:8000`.

A documentação interativa (Swagger UI) fica acessível em `http://localhost:8000/docs`.

---

## Deploy

O projeto está configurado para deploy no [Vercel](https://vercel.com/) + [Supabase](https://supabase.com/).

Ficheiros principais de deploy/migração:

- `vercel.json` -> rotas e cron job (`/api/internal/refresh`)
- `api/index.py` -> entrypoint ASGI para Vercel
- `supabase/schema.sql` -> schema PostgreSQL
- `scripts/load_supabase_data.py` -> carga dos CSV GTFS para a base de dados

Resumo rápido:

1. Criar projeto no Supabase
2. Executar `supabase/schema.sql`
3. (Opcional) Validar CSV: `python scripts/load_supabase_data.py --dry-run`
4. Correr `python scripts/load_supabase_data.py` com `DATABASE_URL`
5. Ligar o repositório ao Vercel
6. Adicionar variáveis de ambiente:
   - `STCP_API_URL` -> URL da API da STCP
  - `DATABASE_URL` -> ligação PostgreSQL da Supabase
  - `DB_SSL=true`
  - `DB_POOL_MIN_SIZE=1`
  - `DB_POOL_MAX_SIZE=5`
   - `API_KEY` -> chave secreta para proteger os endpoints (opcional mas recomendado)
  - `CRON_SECRET` -> protege chamadas do Vercel Cron (recomendado)
  - `REQUIRE_API_KEY_IN_PRODUCTION=true`
  - `ALLOW_API_KEY_QUERY_PARAM=false`
  - `RATE_LIMIT_ENABLED=true`
7. O deploy é feito automaticamente a cada push

---

## Notas Técnicas

- Em ambiente local (com `ENABLE_BACKGROUND_POLLING=true`), os dados de autocarros podem ser atualizados em polling contínuo
- O intervalo do polling contínuo local é configurável por `STCP_BACKGROUND_INTERVAL_SECONDS` (default: 10s)
- Em produção serverless, os dados são atualizados sob procura + cron e gravados na tabela `veiculos` (PostgreSQL), cruzando com tabelas GTFS (`routes`, `trips`) para enriquecer a resposta com destino e cor da linha
- As coordenadas seguem o formato **GeoJSON** (`[longitude, latitude]`)
- O cálculo de ETA usa **tempos programados GTFS por período do dia** (madrugada, ponta manhã, dia, ponta tarde, noite) — a mediana dos horários oficiais da STCP entre paragens é calculada separadamente para cada período, refletindo o trânsito típico de cada altura do dia. Fallback: mediana global de todos os horários, depois distância corrigida (×1.35 fator estrada) + 25s/paragem + velocidade média urbana de 15 km/h
- A resposta do endpoint `/api/tempo` inclui o campo `metodo_calculo` (`gtfs` ou `calculo`) para indicar qual método foi usado
- O campo `sentido` mapeia: `0 → ida`, `1 → volta`

### Base de Dados

Tabelas GTFS estáticas (importadas uma vez):
- `routes` -> linhas (id, nome, cor)
- `stops` -> paragens (id, nome, coordenadas)
- `trips` -> viagens (destino final por sentido)
- `stop_times` -> horários por paragem
- `shapes` -> desenho geográfico das rotas

Tabela dinâmica (atualização contínua local configurável; default 10s):
- `veiculos` -> posição em tempo real dos autocarros

---

## Segurança

Esta API é de **acesso privado**. O repositório e o URL de produção não são públicos.

- **API Key**: Em produção, com `REQUIRE_API_KEY_IN_PRODUCTION=true`, os endpoints `/api/*` exigem `API_KEY`; sem configuração, respondem `503` (fail-closed)
- **Header preferido**: autenticação por `X-API-Key`; query param `?api_key=` está desativado por default (`ALLOW_API_KEY_QUERY_PARAM=false`)
- **Cron protegido**: `/api/internal/refresh` exige `CRON_SECRET` por Bearer token; sem segredo o endpoint interno é bloqueado
- **Rate limiting**: limite básico por IP (`RATE_LIMIT_*`) para mitigar brute force e abuso de consumo
- **Headers de segurança**: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` e `HSTS` em produção
- **Repositório**: Privado no GitHub
- **Docs**: Swagger UI e ReDoc desativados em produção (disponíveis apenas localmente em `http://localhost:8000/docs`)
- **Apenas leitura**: A API só aceita `GET` -- não expõe nenhuma operação de escrita
- **Sem dados sensíveis**: Credenciais da DB e URL da STCP ficam no `.env` (excluído do Git)

---

## Licença

Licenciado sob a [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).

Podes usar, estudar e modificar o código livremente, desde que:

- Mantenhas o código aberto e com a mesma licença
- Dês crédito ao autor original
- Partilhes quaisquer alterações, **mesmo que o uses apenas como serviço (API)**

---

<p align="center">
  Feito com ❤️ e muito ☕ no Porto por <a href="https://github.com/Robim5">Robim5</a>
</p>
