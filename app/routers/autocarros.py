from fastapi import APIRouter, Query, HTTPException
from app.services import stcp_realtime

router = APIRouter(prefix="/api", tags=["Autocarros"])


@router.get("/autocarros")
async def obter_autocarros():
    await stcp_realtime.garantir_dados_recentes()
    dados = await stcp_realtime.listar_autocarros_api()
    feed = stcp_realtime.estado_feed()
    return {
        "total": len(dados),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "feed": feed,
        "dados": dados,
    }


@router.get("/autocarros/{linha}")
async def obter_autocarros_linha(linha: str, sentido: str = Query(None)):
    if sentido and sentido not in ("ida", "volta"):
        raise HTTPException(400, detail="Sentido deve ser 'ida' ou 'volta'.")

    await stcp_realtime.garantir_dados_recentes()

    linha_upper = linha.upper()
    dados = await stcp_realtime.listar_autocarros_api(linha=linha_upper, sentido=sentido)
    if not dados:
        raise HTTPException(404, detail=f"Nenhum autocarro ativo na linha '{linha_upper}'.")

    return {
        "linha": linha_upper,
        "total": len(dados),
        "ultima_atualizacao": stcp_realtime.ultima_atualizacao,
        "feed": stcp_realtime.estado_feed(),
        "dados": dados,
    }
