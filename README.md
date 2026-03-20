<p align="center">
  <img src="logo.png" alt="STCPe Logo" width="90%"/>
</p>

<h1 align="center">STCPê Core</h1>

<p align="center">
  O núcleo que move o STCPê -> autocarros do Porto.
</p>

<p align="center">
  <a href="https://web-production-60c4d.up.railway.app/docs#/"><img src="https://img.shields.io/badge/API%20Docs-Swagger-85EA2D?style=for-the-badge&logo=swagger&logoColor=black" alt="API Docs"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/Licença-AGPL--3.0-blue?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white" alt="Railway">
</p>

---

## Sobre o Núcleo STCPê

O **STCPê Core** é o backend centralizado do projeto STCPê, uma plataforma para consulta em tempo real dos autocarros da STCP (Sociedade de Transportes Colectivos do Porto).

Fornece dados de localização, estimativas de tempo de chegada e informações sobre paragens e linhas, prontos a ser consumidos por qualquer aplicação web ou móvel.

> _"Porque esperar pelo seu autocarro não deveria ser um mistério."_

---

## Funcionalidades

- **Localização em tempo real** -> sabe onde está cada autocarro, agora
- **Tempo de chegada (ETA)** -> estimativas com base na rota real, não em linha reta
- **Paragens próximas** -> encontra paragens à tua volta por GPS
- **Pesquisa por nome** -> procura qualquer paragem pelo nome
- **Info completa** -> todas as linhas que passam numa paragem, com sentidos e terminais
- **Dados de linhas** -> origem, destino e percurso de cada linha

---

## Tecnologias

| Componente | Tecnologia |
|---|---|
| Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Servidor | [Uvicorn](https://www.uvicorn.org/) |
| HTTP Client | [httpx](https://www.python-httpx.org/) |
| Configuração | [python-dotenv](https://pypi.org/project/python-dotenv/) |
| Deploy | [Railway](https://railway.app/) |

---

## Estrutura do Projeto

```
STCPe_Core/
├── app/
│   ├── __init__.py            # Package Python
│   ├── main.py                # Endpoints da API (FastAPI)
│   ├── stcp_realtime.py       # Polling e processamento de dados em tempo real
│   ├── stcp_paragens.py       # Gestão de paragens e pesquisa
│   └── calculadora.py         # Cálculos de distância (Haversine) e ETA
├── dados/
│   ├── municipios_linhas.json # Mapa linha -> municipio
│   └── paragens/              # Ficheiros JSON com dados de todas as paragens
│       ├── 200tos.json
│       ├── 300tos.json
│       ├── ...
│       └── Zc.json
├── Procfile                   # Configuração de deploy (Railway)
├── requirements.txt           # Dependências Python
└── README.md
```

---

## Endpoints da API

### Estado do Serviço

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/health` | Estado do serviço, autocarros ativos e linhas carregadas |

### Autocarros

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/autocarros/todos` | Todos os autocarros ativos com posição e velocidade |
| `GET` | `/api/autocarro/{linha}/posicao` | Posição dos autocarros de uma linha específica |

**Parâmetros opcionais:** `sentido` -> filtrar por `ida` ou `volta`

### Linhas e Paragens

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/linhas` | Lista de todas as linhas com `cor`, `municipio`, origem e destino |
| `GET` | `/api/linhas/{linha}/paragens` | Paragens de uma linha (filtrável por sentido) |

`GET /api/linhas` inclui por linha:
- `linha`
- `cor` (`azul`, `amarelo`, `verde`, `vermelho`, `roxo`, `laranja`, `preto`)
- `municipio`
- `sentidos` (`ida`/`volta` com `origem`, `destino`, `total_paragens`)

### Paragens

| Método | Endpoint | Descrição |
|---|---|---|
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

# configurar variável de ambiente
# criar ficheiro .env na raiz com:
# STCP_API_URL=<url_da_api_stcp>

# iniciar o servidor
uvicorn app.main:app --reload
```

O servidor fica disponível em `http://localhost:8000`.

A documentação interativa (Swagger UI) fica acessível em `http://localhost:8000/docs`.

---

## Deploy

O projeto está configurado para deploy no [Railway](https://railway.app/) através do `Procfile`.

1. Ligar o repositório GitHub ao Railway
2. Adicionar a variável de ambiente `STCP_API_URL` nas definições do projeto
3. O deploy é feito automaticamente a cada push

---

## Notas Técnicas

- Os dados de autocarros são atualizados a cada **5 segundos** via polling à API da STCP
- As coordenadas seguem o formato **GeoJSON** (`[longitude, latitude]`)
- O cálculo de ETA usa a **distância pela rota** (soma dos segmentos entre paragens) e não a distância em linha reta
- Quando um autocarro está parado, é usada uma velocidade mínima de **12 km/h** para a estimativa
- O campo `sentido` mapeia: `0 → ida`, `1 → volta`

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
