import os
import aiomysql

_pool = None


async def criar_pool():
    """cria o pool de conexoes assincronas ao MySQL"""
    global _pool
    try:
        _pool = await aiomysql.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            db=os.getenv("DB_NAME", "real_time_data"),
            minsize=1,
            maxsize=10,
            autocommit=True,
            charset="utf8mb4",
        )
        print(f"DB conectada: {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}")
    except Exception as e:
        print(f"Aviso: Nao foi possivel ligar a base de dados - {e}")
        _pool = None


async def fechar_pool():
    """fecha o pool de conexoes"""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()


def obter_pool():
    """retorna o pool ativo"""
    return _pool
