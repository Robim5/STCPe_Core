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

Foi desenhada para correr em **Railway** com base de dados **Supabase (PostgreSQL)**.

---

## Funcionalidades

- autocarros em tempo real
- estimativas de chegada (ETA)
- linhas, paragens e shapes de rota
- pesquisa de paragens e paragens próximas
- endpoint interno de refresh protegido

---

## Stack

| Componente | Tecnologia |
|---|---|
| Framework API | [FastAPI](https://fastapi.tiangolo.com/) |
| Servidor ASGI | [Uvicorn](https://www.uvicorn.org/) |
| Base de Dados | [PostgreSQL](https://www.postgresql.org/) via [Supabase](https://supabase.com/) |
| Driver DB | [asyncpg](https://github.com/MagicStack/asyncpg) |
| Deploy | [Railway](https://railway.com/) |

---

## Arranque Rapido (Local)

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

4. Criar `.env` a partir de `.env.example` e preencher variáveis obrigatórias.

5. Arrancar a API.

```bash
uvicorn app.main:app --reload
```

API local: http://localhost:8000

---

## Deploy (Railway + Supabase)

Resumo:

1. Garantir schema e dados GTFS no Supabase.
2. Ligar o repositório ao Railway.
3. Configurar variáveis de ambiente no Railway.
4. Fazer deploy e validar `/healthz`.

Guia detalhado completo:

- [docs/GUIA_RAILWAY_SUPABASE_PASSO_A_PASSO.md](docs/GUIA_RAILWAY_SUPABASE_PASSO_A_PASSO.md)

---

## Atualizar GTFS

Quando os CSV GTFS mudarem, usa:

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..."
```

Validação apenas:

```bash
python scripts/refresh_supabase_gtfs.py --database-url "postgresql://..." --dry-run-only
```

Importante:

- atualiza os CSV em `dados/infoCVS`
- faz commit/push dos novos CSV para manter o runtime sincronizado com a base

---

## Segurança

- autenticação por `X-API-Key` nos endpoints `/api/*` (quando configurada)
- endpoint interno `/api/internal/refresh` protegido por `CRON_SECRET`
- rate limiting por IP
- headers HTTP de segurança ativos
- docs OpenAPI desativadas em produção

---

## Endpoints Principais

| Método | Endpoint |
|---|---|
| GET | /healthz |
| GET | /api/health |
| GET | /api/autocarros |
| GET | /api/linhas |
| GET | /api/paragens |
| GET | /api/tempo/{linha}/{codigo_paragem} |
| GET | /api/internal/refresh |

---

## Licença

Licenciado sob [AGPL-3.0](LICENSE).

---

<p align="center">
  Feito com muito cafe no Porto por <a href="https://github.com/Robim5">Robim5</a>
</p>
