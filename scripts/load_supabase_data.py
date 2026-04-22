import argparse
import asyncio
import csv
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
GTFS_DIR = ROOT_DIR / "dados" / "infoCVS"
SCHEMA_FILE = ROOT_DIR / "supabase" / "schema.sql"


def parse_int(value: str):
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_float(value: str):
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def transform_route(row: dict):
    route_id = (row.get("route_id") or "").strip()
    route_short_name = (row.get("route_short_name") or "").strip()
    if not route_id or not route_short_name:
        return None

    return (
        (row.get("agency_id") or "").strip() or None,
        route_id,
        route_short_name,
        parse_int(row.get("route_type")),
        (row.get("route_long_name") or "").strip() or None,
        (row.get("route_url") or "").strip() or None,
        (row.get("route_color") or "").strip() or None,
        (row.get("route_text_color") or "").strip() or None,
        parse_int(row.get("route_sort_order")),
    )


def transform_trip(row: dict):
    trip_id = (row.get("trip_id") or "").strip()
    route_id = (row.get("route_id") or "").strip()
    if not trip_id or not route_id:
        return None

    return (
        route_id,
        (row.get("service_id") or "").strip() or None,
        trip_id,
        (row.get("trip_headsign") or "").strip() or None,
        parse_int(row.get("wheelchair_accessible")),
        (row.get("block_id") or "").strip() or None,
        parse_int(row.get("direction_id")),
        (row.get("shape_id") or "").strip() or None,
    )


def transform_stop(row: dict):
    stop_id = (row.get("stop_id") or "").strip()
    stop_name = (row.get("stop_name") or "").strip()
    lat = parse_float(row.get("stop_lat"))
    lon = parse_float(row.get("stop_lon"))

    # Ignora linhas tecnicamente invalidas (ex: stop_id='.' ou coordenadas nao numericas).
    if not stop_id or stop_id == "." or lat is None or lon is None:
        return None

    if not stop_name:
        stop_name = stop_id

    return (
        stop_id,
        (row.get("stop_code") or "").strip() or None,
        stop_name,
        lat,
        lon,
        (row.get("zone_id") or "").strip() or None,
        (row.get("stop_url") or "").strip() or None,
    )


def transform_stop_time(row: dict):
    trip_id = (row.get("trip_id") or "").strip()
    stop_id = (row.get("stop_id") or "").strip()
    arrival_time = (row.get("arrival_time") or "").strip()
    departure_time = (row.get("departure_time") or "").strip()
    stop_sequence = parse_int(row.get("stop_sequence"))

    if not trip_id or not stop_id or not arrival_time or not departure_time or stop_sequence is None:
        return None

    return (
        trip_id,
        arrival_time,
        departure_time,
        stop_id,
        stop_sequence,
        parse_int(row.get("timepoint")),
        parse_float(row.get("shape_dist_traveled")),
    )


def transform_shape(row: dict):
    shape_id = (row.get("shape_id") or "").strip()
    lat = parse_float(row.get("shape_pt_lat"))
    lon = parse_float(row.get("shape_pt_lon"))
    seq = parse_int(row.get("shape_pt_sequence"))

    if not shape_id or lat is None or lon is None or seq is None:
        return None

    return (
        shape_id,
        lat,
        lon,
        parse_float(row.get("shape_dist_traveled")),
        seq,
    )


def inspect_csv_file(file_path: Path, transform):
    total = 0
    valid = 0
    skipped = 0

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if transform(row) is None:
                skipped += 1
            else:
                valid += 1

    return total, valid, skipped


def run_dry_run():
    required_files = {
        "routes": (GTFS_DIR / "routes.csv", transform_route),
        "trips": (GTFS_DIR / "trips.csv", transform_trip),
        "stops": (GTFS_DIR / "stops.csv", transform_stop),
        "shapes": (GTFS_DIR / "shapes.csv", transform_shape),
        "stop_times": (GTFS_DIR / "stop_times.csv", transform_stop_time),
    }

    for table_name, (file_path, transform) in required_files.items():
        if not file_path.exists():
            raise FileNotFoundError(f"Ficheiro GTFS em falta: {file_path}")

        total, valid, skipped = inspect_csv_file(file_path, transform)
        print(f"{table_name}: total={total}, validos={valid}, ignorados={skipped}")


async def copy_csv_to_table(
    conn,
    file_path: Path,
    table_name: str,
    columns: tuple[str, ...],
    transform,
    chunk_size: int = 20000,
):
    inserted = 0
    skipped = 0
    buffer = []

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = transform(row)
            if record is None:
                skipped += 1
                continue

            buffer.append(record)
            if len(buffer) >= chunk_size:
                await conn.copy_records_to_table(table_name, records=buffer, columns=columns)
                inserted += len(buffer)
                buffer.clear()

    if buffer:
        await conn.copy_records_to_table(table_name, records=buffer, columns=columns)
        inserted += len(buffer)

    print(f"{table_name}: inseridos={inserted}, ignorados={skipped}")


async def run(database_url: str):
    import asyncpg

    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Schema SQL nao encontrado: {SCHEMA_FILE}")

    required_files = [
        GTFS_DIR / "routes.csv",
        GTFS_DIR / "trips.csv",
        GTFS_DIR / "stops.csv",
        GTFS_DIR / "stop_times.csv",
        GTFS_DIR / "shapes.csv",
    ]
    for file in required_files:
        if not file.exists():
            raise FileNotFoundError(f"Ficheiro GTFS em falta: {file}")

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    try:
        async with pool.acquire() as conn:
            schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
            await conn.execute(schema_sql)

            async with conn.transaction():
                await conn.execute("TRUNCATE TABLE stop_times, trips, shapes, routes, stops")

                await copy_csv_to_table(
                    conn,
                    GTFS_DIR / "routes.csv",
                    "routes",
                    (
                        "agency_id",
                        "route_id",
                        "route_short_name",
                        "route_type",
                        "route_long_name",
                        "route_url",
                        "route_color",
                        "route_text_color",
                        "route_sort_order",
                    ),
                    transform_route,
                )

                await copy_csv_to_table(
                    conn,
                    GTFS_DIR / "trips.csv",
                    "trips",
                    (
                        "route_id",
                        "service_id",
                        "trip_id",
                        "trip_headsign",
                        "wheelchair_accessible",
                        "block_id",
                        "direction_id",
                        "shape_id",
                    ),
                    transform_trip,
                )

                await copy_csv_to_table(
                    conn,
                    GTFS_DIR / "stops.csv",
                    "stops",
                    (
                        "stop_id",
                        "stop_code",
                        "stop_name",
                        "stop_lat",
                        "stop_lon",
                        "zone_id",
                        "stop_url",
                    ),
                    transform_stop,
                )

                await copy_csv_to_table(
                    conn,
                    GTFS_DIR / "shapes.csv",
                    "shapes",
                    (
                        "shape_id",
                        "shape_pt_lat",
                        "shape_pt_lon",
                        "shape_dist_traveled",
                        "shape_pt_sequence",
                    ),
                    transform_shape,
                )

                await copy_csv_to_table(
                    conn,
                    GTFS_DIR / "stop_times.csv",
                    "stop_times",
                    (
                        "trip_id",
                        "arrival_time",
                        "departure_time",
                        "stop_id",
                        "stop_sequence",
                        "timepoint",
                        "shape_dist_traveled",
                    ),
                    transform_stop_time,
                )

            counts = {
                "routes": await conn.fetchval("SELECT COUNT(*) FROM routes"),
                "trips": await conn.fetchval("SELECT COUNT(*) FROM trips"),
                "stops": await conn.fetchval("SELECT COUNT(*) FROM stops"),
                "shapes": await conn.fetchval("SELECT COUNT(*) FROM shapes"),
                "stop_times": await conn.fetchval("SELECT COUNT(*) FROM stop_times"),
            }
            print("Carga concluida com sucesso.")
            for table_name, count in counts.items():
                print(f"{table_name}: {count}")

    finally:
        await pool.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Carrega dados GTFS para PostgreSQL/Supabase")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="DSN PostgreSQL. Por omissao usa a variavel de ambiente DATABASE_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida os CSV GTFS sem escrever na base de dados.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.dry_run:
        run_dry_run()
        return

    database_url = args.database_url.strip()

    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]

    if not database_url:
        raise SystemExit("DATABASE_URL nao definido. Usa --database-url ou exporta DATABASE_URL.")

    asyncio.run(run(database_url))


if __name__ == "__main__":
    main()
