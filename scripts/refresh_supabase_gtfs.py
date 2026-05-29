import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from load_supabase_data import run, run_dry_run

# carrega .env na raiz do projeto (como app/config.py)
_RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(_RAIZ / ".env", override=False)


CONFIRM_TOKEN = "ATUALIZAR"


def normalizar_dsn(dsn: str) -> str:
    valor = (dsn or "").strip()
    if valor.startswith("postgres://"):
        return "postgresql://" + valor[len("postgres://") :]
    return valor


def pedir_confirmacao() -> bool:
    texto = input(
        "Esta operacao limpa e recarrega routes/trips/stops/shapes/stop_times. "
        f"Escreve {CONFIRM_TOKEN} para continuar: "
    ).strip()
    return texto == CONFIRM_TOKEN


def parse_args():
    parser = argparse.ArgumentParser(
        description="Limpa e recarrega tabelas GTFS no Supabase/PostgreSQL."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="DSN PostgreSQL. Por omissao usa DATABASE_URL.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Executa sem confirmacao interativa.",
    )
    parser.add_argument(
        "--skip-dry-run",
        action="store_true",
        help="Salta validacao previa dos ficheiros GTFS.",
    )
    parser.add_argument(
        "--dry-run-only",
        action="store_true",
        help="Valida os ficheiros GTFS e termina sem escrever na base de dados.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dsn = normalizar_dsn(args.database_url)

    if not args.skip_dry_run:
        print("[1/3] A validar GTFS (dry-run)...")
        run_dry_run()

    if args.dry_run_only:
        print("Dry-run concluido. Nenhuma alteracao foi aplicada na base de dados.")
        return

    if not dsn:
        raise SystemExit(
            "DATABASE_URL nao definido. Coloca no ficheiro .env na raiz do projeto "
            "ou passa --database-url \"postgresql://...\""
        )

    if not args.yes:
        print("[2/3] Confirmacao de limpeza da base...")
        if not pedir_confirmacao():
            raise SystemExit("Operacao cancelada pelo utilizador.")

    print("[3/3] A limpar e recarregar GTFS na base de dados...")
    asyncio.run(run(dsn))
    print("Atualizacao GTFS concluida com sucesso.")


if __name__ == "__main__":
    main()
