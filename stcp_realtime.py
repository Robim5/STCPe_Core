import httpx
import asyncio 
import os
from dotenv import load_dotenv

# carrega os segredos obscuros
load_dotenv()

# vive na memoria ram (é a nossa base de dados)
memoria_autocarros = []

async def atualizar_autocarros():
    global memoria_autocarros
    url = os.getenv("STCP_API_URL")
    
    if not url:
        print("Error: O link da API da STCP não está no ficheiro .env.")
        return
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resposta = await client.get(url, headers={'Accept': 'application/json'})
                
                if resposta.status_code == 200:
                    memoria_autocarros = resposta.json()
                    print(f"Sucesso: {len(memoria_autocarros)} autocarros guardados na RAM!.")
                else:
                    print(f"Aviso: A STCP respondeu com erro {resposta.status_code}.")
            
            except Exception as e:
                print(f"Erro: Falha ao obter dados da STCP - {e}")
            
            await asyncio.sleep(5)  # espera 5 segundos ate att
