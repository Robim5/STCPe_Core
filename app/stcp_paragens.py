import json
from pathlib import Path
from app import calculadora

todas_paragens = {}

_PASTA_PARAGENS = Path(__file__).resolve().parent.parent / "dados" / "paragens"
_FICHEIRO_MUNICIPIOS = Path(__file__).resolve().parent.parent / "dados" / "municipios_linhas.json"
_MUNICIPIOS_POR_LINHA = {}


def carregar_municipios_linhas():
    global _MUNICIPIOS_POR_LINHA

    if not _FICHEIRO_MUNICIPIOS.exists():
        print(f"Aviso: O ficheiro '{_FICHEIRO_MUNICIPIOS}' nao existe.")
        _MUNICIPIOS_POR_LINHA = {}
        return

    try:
        with open(_FICHEIRO_MUNICIPIOS, "r", encoding="utf-8") as f:
            dados = json.load(f)
            _MUNICIPIOS_POR_LINHA = {str(k).upper(): v for k, v in dados.items()}
    except Exception as e:
        print(f"Erro ao carregar municipios por linha: {e}")
        _MUNICIPIOS_POR_LINHA = {}


def obter_cor_linha(linha: str):
    linha_upper = linha.upper()

    if linha_upper.endswith("M"):
        return "preto"

    if linha_upper == "ZC":
        return "azul"

    if linha_upper.isdigit():
        numero = int(linha_upper)
        if 200 <= numero <= 404:
            return "azul"
        if 500 <= numero <= 508:
            return "amarelo"
        if 600 <= numero <= 604:
            return "verde"
        if 700 <= numero <= 707:
            return "vermelho"
        if 800 <= numero <= 806:
            return "roxo"
        if 900 <= numero <= 907:
            return "laranja"

    return None


def obter_municipio_linha(linha: str):
    return _MUNICIPIOS_POR_LINHA.get(linha.upper())


def carregar_paragens():
    global todas_paragens

    carregar_municipios_linhas()

    if not _PASTA_PARAGENS.exists():
        print(f"Erro: A pasta '{_PASTA_PARAGENS}' nao existe.")
        return

    for ficheiro in sorted(_PASTA_PARAGENS.glob("*.json")):
        try:
            with open(ficheiro, "r", encoding="utf-8") as f:
                dados = json.load(f)
                todas_paragens.update(dados)
            print(f"Lido: {ficheiro.name}")
        except Exception as e:
            print(f"Erro ao carregar {ficheiro}: {e}")


def obter_linhas():
    """
    retorna lista de todas as linhas disponiveis
    """
    return sorted(todas_paragens.keys())


def obter_paragens_linha(linha: str, sentido: str = None):
    """
    retorna as paragens de uma linha
    se sentido especificado
    filtra por sentido (ida/volta)
    """
    dados_linha = todas_paragens.get(linha)
    if not dados_linha:
        return None

    if sentido:
        paragens = dados_linha.get(sentido)
        if paragens is None:
            return None
        return {sentido: paragens}

    return dados_linha


def encontrar_paragem_por_codigo(linha: str, sentido: str, codigo: str):
    """
    encontra paragem pelo codigo numa linha e sentido 
    retorna indice e paragem ou None
    """
    dados_linha = todas_paragens.get(linha)
    if not dados_linha:
        return None

    paragens = dados_linha.get(sentido, [])
    for i, p in enumerate(paragens):
        if p["codigo"].upper() == codigo.upper():
            return i, p

    return None


def encontrar_paragens_proximas(lat: float, lon: float, raio_metros: float = 500):
    """
    encontra todas as paragens dentro de um raio de um ponto de todas as linhas
    """
    resultados = []
    vistos = set()

    for linha, sentidos in todas_paragens.items():
        for sentido, paragens in sentidos.items():
            for p in paragens:
                chave = (p["codigo"], linha, sentido)
                if chave in vistos:
                    continue
                dist = calculadora.calcular_distancia(lat, lon, p["lat"], p["lon"])
                if dist <= raio_metros:
                    vistos.add(chave)
                    resultados.append({
                        "linha": linha,
                        "sentido": sentido,
                        "codigo": p["codigo"],
                        "nome": p["nome"],
                        "lat": p["lat"],
                        "lon": p["lon"],
                        "distancia_metros": dist,
                    })

    resultados.sort(key=lambda x: x["distancia_metros"])
    return resultados


def pesquisar_paragens_por_nome(nome: str):
    """
    pesquisa paragens pelo nome (parcial, case-insensitive)
    retorna lista de paragens unicas com todas as linhas que passam la
    """
    nome_lower = nome.lower()
    paragens_encontradas = {}

    for linha, sentidos in todas_paragens.items():
        for sentido, paragens in sentidos.items():
            for p in paragens:
                if nome_lower in p["nome"].lower():
                    codigo = p["codigo"]
                    if codigo not in paragens_encontradas:
                        paragens_encontradas[codigo] = {
                            "codigo": codigo,
                            "nome": p["nome"],
                            "lat": p["lat"],
                            "lon": p["lon"],
                            "linhas": [],
                        }
                    # evitar duplicar a mesma linha+sentido
                    entrada_linha = {"linha": linha, "sentido": sentido}
                    if entrada_linha not in paragens_encontradas[codigo]["linhas"]:
                        paragens_encontradas[codigo]["linhas"].append(entrada_linha)

    return list(paragens_encontradas.values())


def obter_linhas_na_paragem(codigo: str):
    """
    dado um codigo de paragem, retorna todas as linhas e sentidos que passam la
    com info do terminal (primeira e ultima paragem da rota)
    """
    codigo_upper = codigo.upper()
    resultados = []
    paragem_info = None

    for linha, sentidos in todas_paragens.items():
        for sentido, paragens in sentidos.items():
            for p in paragens:
                if p["codigo"].upper() == codigo_upper:
                    if paragem_info is None:
                        paragem_info = {
                            "codigo": p["codigo"],
                            "nome": p["nome"],
                            "lat": p["lat"],
                            "lon": p["lon"],
                        }
                    primeira = paragens[0]
                    ultima = paragens[-1]
                    resultados.append({
                        "linha": linha,
                        "sentido": sentido,
                        "origem": primeira["nome"],
                        "destino": ultima["nome"],
                    })
                    break

    return paragem_info, resultados


def obter_info_linhas():
    """
    retorna lista de linhas com info dos terminais (origem -> destino) para cada sentido
    """
    info = []
    for linha in sorted(todas_paragens.keys()):
        sentidos = todas_paragens[linha]
        dados_linha = {
            "linha": linha,
            "cor": obter_cor_linha(linha),
            "municipio": obter_municipio_linha(linha),
            "sentidos": {},
        }
        for sentido, paragens in sentidos.items():
            if paragens:
                dados_linha["sentidos"][sentido] = {
                    "origem": paragens[0]["nome"],
                    "destino": paragens[-1]["nome"],
                    "total_paragens": len(paragens),
                }
        info.append(dados_linha)
    return info