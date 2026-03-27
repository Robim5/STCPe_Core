"""
script de teste para todos os endpoints da STCPe Core API.
uso: python tests/test_api.py <BASE_URL>
exemplo: python tests/test_api.py https://stcpe-core.railway.app
"""

import sys
import httpx
import time

if len(sys.argv) < 2:
    print("uso: python tests/test_api.py <BASE_URL>")
    print("exemplo: python tests/test_api.py https://stcpe-core.railway.app")
    sys.exit(1)

BASE = sys.argv[1].rstrip("/")
API_KEY = sys.argv[2] if len(sys.argv) > 2 else ""

PASS = 0
FAIL = 0
WARN = 0


def header():
    h = {}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def test(nome: str, method: str, path: str, espera_status: int = 200, params: dict = None):
    global PASS, FAIL, WARN
    url = f"{BASE}{path}"
    try:
        inicio = time.time()
        r = httpx.request(method, url, headers=header(), params=params, timeout=15.0)
        duracao = round((time.time() - inicio) * 1000)
        status_ok = r.status_code == espera_status

        if status_ok:
            PASS += 1
            icone = "OK"
        else:
            FAIL += 1
            icone = "FAIL"

        print(f"[{icone}] {nome}")
        print(f"{method} {path} -> {r.status_code} ({duracao}ms)")

        if not status_ok:
            print(f"Esperado: {espera_status}, Recebido: {r.status_code}")
            try:
                print(f"Body: {r.text[:200]}")
            except Exception:
                pass

        # validar que resposta e JSON valido
        if status_ok and r.status_code == 200:
            try:
                data = r.json()
                return data
            except Exception:
                WARN += 1
                print(f"[WARN] Resposta nao e JSON valido")
                return None

        return None

    except httpx.TimeoutException:
        FAIL += 1
        print(f"[FAIL] {nome}")
        print(f"{method} {path} -> TIMEOUT (>15s)")
        return None
    except Exception as e:
        FAIL += 1
        print(f"[FAIL] {nome}")
        print(f"{method} {path} -> ERRO: {e}")
        return None


def main():
    print("=" * 60)
    print("STCPe Core API - Testes de Endpoints")
    print(f"URL: {BASE}")
    print(f"API Key: {'***' + API_KEY[-4:] if API_KEY else '(sem chave)'}")
    print("=" * 60)

    # health
    print("\n[Health & Estatisticas]")
    data = test("Health check", "GET", "/api/health")
    if data:
        print(f"-> estado={data.get('estado')}, autocarros={data.get('autocarros_ativos')}, linhas={data.get('linhas_carregadas')}")

    data = test("Estatisticas", "GET", "/api/estatisticas")
    if data:
        print(f"-> rotas={data.get('total_rotas')}, paragens_db={data.get('total_paragens_db')}")

    # autocarros
    print("\n[Autocarros - Tempo Real]")
    data = test("Todos os autocarros", "GET", "/api/autocarros")
    if data:
        total = data.get("total", 0)
        print(f"-> {total} autocarros ativos")
        # guardar uma linha para testes seguintes
        if data.get("dados") and len(data["dados"]) > 0:
            primeira_linha = data["dados"][0].get("linha", "600")
        else:
            primeira_linha = "600"
    else:
        primeira_linha = "600"

    data = test(f"Autocarros da linha {primeira_linha}", "GET", f"/api/autocarros/{primeira_linha}")
    if data:
        print(f"-> {data.get('total', 0)} autocarros na linha {primeira_linha}")

    data = test(f"Autocarros linha {primeira_linha} ida", "GET", f"/api/autocarros/{primeira_linha}", params={"sentido": "ida"})

    test("Sentido invalido (400)", "GET", f"/api/autocarros/{primeira_linha}", espera_status=400, params={"sentido": "xyz"})

    # linhas
    print("\n[Linhas & Paragens de Linha]")
    data = test("Listar linhas", "GET", "/api/linhas")
    if data and data.get("linhas"):
        total_linhas = len(data["linhas"])
        print(f"-> {total_linhas} linhas")
        linha_teste = data["linhas"][0].get("linha", "200")
    else:
        linha_teste = "200"

    data = test(f"Paragens da linha {linha_teste}", "GET", f"/api/linhas/{linha_teste}/paragens")
    if data and data.get("paragens"):
        # contar paragens
        total_p = 0
        for sentido, lista in data["paragens"].items():
            total_p += len(lista)
        print(f"-> {total_p} paragens")

    data = test(f"Paragens da linha {linha_teste} (ida)", "GET", f"/api/linhas/{linha_teste}/paragens", params={"sentido": "ida"})

    test("Linha inexistente (404)", "GET", "/api/linhas/XYZ999/paragens", espera_status=404)

    # shapes
    print("\n[Shapes - Desenho de Rotas]")
    data = test(f"Shape da linha {linha_teste}", "GET", f"/api/linhas/{linha_teste}/shape")
    if data and data.get("shapes"):
        print(f"-> {len(data['shapes'])} shape(s)")

    data = test(f"Shape da linha {linha_teste} (ida)", "GET", f"/api/linhas/{linha_teste}/shape", params={"sentido": "ida"})

    # paragens
    print("\n[Paragens]")
    data = test("Todas as paragens (DB)", "GET", "/api/paragens")
    if data:
        print(f"-> {data.get('total', 0)} paragens")

    data = test("Paragens proximas (Porto centro)", "GET", "/api/paragens/proximas", params={"lat": 41.1496, "lon": -8.6110, "raio": 500})
    if data:
        print(f"-> {data.get('total', 0)} paragens num raio de 500m")
        if data.get("paragens") and len(data["paragens"]) > 0:
            paragem_teste = data["paragens"][0]
            codigo_paragem = paragem_teste.get("codigo", "")
            linha_paragem = paragem_teste.get("linha", "")
            sentido_paragem = paragem_teste.get("sentido", "ida")
            print(f"-> paragem mais proxima: {paragem_teste.get('nome')} ({codigo_paragem})")
        else:
            codigo_paragem = ""
            linha_paragem = ""
            sentido_paragem = "ida"
    else:
        codigo_paragem = ""
        linha_paragem = ""
        sentido_paragem = "ida"

    test("Paragens proximas sem coords (422)", "GET", "/api/paragens/proximas", espera_status=422)

    data = test("Pesquisa paragens 'bolhao'", "GET", "/api/paragens/pesquisa", params={"nome": "bolhao"})
    if data:
        print(f"-> {data.get('total', 0)} resultados")

    test("Pesquisa muito curta (422)", "GET", "/api/paragens/pesquisa", espera_status=422, params={"nome": "a"})

    # paragens
    print("\n[Info Paragem & Tempos]")
    if codigo_paragem:
        data = test(f"Info paragem {codigo_paragem}", "GET", f"/api/paragem/{codigo_paragem}/info")
        if data:
            print(f"-> {data.get('total_linhas', 0)} linhas passam nesta paragem")

        data = test(f"Tempos paragem {codigo_paragem}", "GET", f"/api/paragem/{codigo_paragem}/tempos")
        if data:
            print(f"-> {data.get('total', 0)} autocarros a caminho")
    else:
        print("  [SKIP] Sem paragem de teste disponivel")

    test("Paragem inexistente (404)", "GET", "/api/paragem/XXXXX/info", espera_status=404)

    # tempo chegada
    print("\n[Tempo Estimado de Chegada]")
    if codigo_paragem and linha_paragem:
        data = test(
            f"ETA linha {linha_paragem} paragem {codigo_paragem}",
            "GET",
            f"/api/tempo/{linha_paragem}/{codigo_paragem}",
            params={"sentido": sentido_paragem},
        )
        if data:
            print(f"       -> {data.get('total_autocarros', 0)} autocarros estimados")
            if data.get("estimativas"):
                melhor = data["estimativas"][0]
                print(f"-> proximo: {melhor.get('tempo_estimado_min')} min ({melhor.get('distancia_metros')}m)")
    else:
        print("  [SKIP] Sem dados de paragem/linha para testar ETA")

    test("ETA sem sentido (422)", "GET", f"/api/tempo/600/TEST1", espera_status=422)
    test("ETA sentido invalido (400)", "GET", f"/api/tempo/600/TEST1", espera_status=400, params={"sentido": "xyz"})

    # seguranca
    print("\n[Seguranca]")
    # testar acesso sem API key (se a API tem proteção)
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=10.0)
        if r.status_code == 401:
            print(f"  [OK] API protegida - acesso sem chave retorna 401")
            PASS_HACK = True
        else:
            print(f"  [INFO] API acessivel sem chave (status {r.status_code})")
            PASS_HACK = False
    except Exception as e:
        print(f"  [WARN] Nao foi possivel testar sem chave: {e}")
        PASS_HACK = False

    # resumo
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTADOS: {PASS}/{total} testes OK")
    if FAIL > 0:
        print(f"FALHAS: {FAIL}")
    if WARN > 0:
        print(f"AVISOS: {WARN}")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
