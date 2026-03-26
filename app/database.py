import os
import aiomysql

_pool = None


async def criar_pool():
    """cria o pool de conexoes assincronas ao MySQL"""
    global _pool
    _pool = await aiomysql.create_pool(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        db=os.getenv("DB_NAME", "real_time_data"),
        minsize=2,
        maxsize=10,
        autocommit=True,
        charset="utf8mb4",
    )


async def fechar_pool():
    """fecha o pool de conexoes"""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()


def obter_pool():
    """retorna o pool ativo"""
    return _pool
