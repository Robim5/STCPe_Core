# cria tabela e indices de apoio
async def inicializar_tabela_veiculos(pool):
    if not pool:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS veiculos (
                id_veiculo TEXT PRIMARY KEY,
                linha TEXT NOT NULL,
                sentido TEXT NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                velocidade DOUBLE PRECISION DEFAULT 0,
                bearing DOUBLE PRECISION DEFAULT 0,
                timestamp TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_veiculos_linha ON veiculos (linha)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_veiculos_updated_at ON veiculos (updated_at)")

    print("Tabela 'veiculos' pronta.")


# troca snapshot antigo pelo atual
async def gravar_veiculos_db(pool, processados: list):
    if not pool:
        return

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("TRUNCATE TABLE veiculos")
                if processados:
                    sql = """
                        INSERT INTO veiculos
                            (id_veiculo, linha, sentido, latitude, longitude, velocidade, bearing, timestamp, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    """
                    dados = [
                        (
                            bus["veiculo_id"],
                            bus["linha"],
                            bus["sentido"],
                            bus["lat"],
                            bus["lon"],
                            bus["velocidade"],
                            bus["bearing"],
                            bus["ultima_atualizacao"],
                        )
                        for bus in processados
                    ]
                    await conn.executemany(sql, dados)
    except Exception as erro:
        print(f"Erro ao gravar veiculos na DB: {erro}")


# le snapshot para repor memoria
async def carregar_snapshot_veiculos(pool) -> tuple[list, dict, str | None]:
    if not pool:
        return [], {}, None

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                id_veiculo,
                linha,
                sentido,
                latitude,
                longitude,
                velocidade,
                bearing,
                timestamp,
                updated_at
            FROM veiculos
            """
        )

    processados = []
    por_linha = {}
    max_updated_at = None

    for row in rows:
        bus = {
            "veiculo_id": row["id_veiculo"],
            "linha": row["linha"],
            "sentido": row["sentido"],
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
            "velocidade": float(row["velocidade"] or 0),
            "bearing": float(row["bearing"] or 0),
            "ultima_atualizacao": row["timestamp"] or "",
        }
        processados.append(bus)
        por_linha.setdefault(bus["linha"], []).append(bus)

        updated_at = row["updated_at"]
        if updated_at is not None and (max_updated_at is None or updated_at > max_updated_at):
            max_updated_at = updated_at

    # calcula ultima atualizacao do snapshot
    ultima = max_updated_at.isoformat() if max_updated_at is not None else None
    return processados, por_linha, ultima
