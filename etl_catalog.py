"""Punto de entrada raíz para etl_catalog.py (delegan en scripts/etl_catalog.py)."""
from scripts.etl_catalog import run_etl, sync_film
import argparse
import json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL de catálogo Sakila MySQL -> MongoDB")
    parser.add_argument("--sync-id", type=int, default=None, help="Sincronizar únicamente un film_id")
    args = parser.parse_args()

    if args.sync_id is not None:
        updated_doc = sync_film(args.sync_id)
        print(f"Película sincronizada (_id={args.sync_id}):")
        print(json.dumps(updated_doc, indent=2, ensure_ascii=False))
    else:
        run_etl()
