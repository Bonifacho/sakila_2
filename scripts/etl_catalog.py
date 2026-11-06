"""Script ETL Híbrido: MySQL (Sakila) -> MongoDB (sakila_catalog.films) (Parte E1 y E3).

Lee las tablas relacionales `film`, `language`, `category`, `film_category`,
`actor` y `film_actor` desde MySQL y construye documentos desnormalizados con
categorías y actores embebidos en la colección `films` de MongoDB.
También expone `sync_film(film_id)` para sincronización individual bajo demanda.
"""
import os
import sys
import json
import time
import argparse
from pymongo import ReplaceOne

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import get_connection
from app.mongo import get_films_collection
from app.repositories.catalog_repo import fetch_all_films_from_mysql
from app.services.catalog_service import sync_film


def run_etl(drop_existing=True):
    """Ejecuta el proceso completo de extracción, transformación y carga (ETL)."""
    t0 = time.perf_counter()
    print("=" * 75)
    print("ETL SAKILA: MySQL (Relacional) -> MongoDB (Documental: sakila_catalog.films)")
    print("=" * 75)

    # 1. EXTRACT & TRANSFORM desde MySQL
    print("[1/3] Extrayendo películas, idiomas, categorías y actores desde MySQL...")
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            docs = fetch_all_films_from_mysql(cur)
        finally:
            cur.close()

    print(f"      -> {len(docs)} documentos de películas construidos en memoria.")

    # 2. LOAD en MongoDB
    print("[2/3] Cargando documentos en MongoDB (sakila_catalog.films)...")
    coll = get_films_collection()
    if drop_existing:
        coll.drop()

    operations = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs]
    result = coll.bulk_write(operations, ordered=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    total_in_mongo = coll.count_documents({})
    print(f"      -> Documentos en colección `films`: {total_in_mongo}")
    print(f"      -> Tiempo total de ETL: {elapsed_ms:.2f} ms")

    # 3. Mostrar documento de muestra (_id = 1)
    sample = coll.find_one({"_id": 1})
    print("\n[3/3] Documento de referencia cargado (_id = 1):")
    print(json.dumps(sample, indent=2, ensure_ascii=False))
    print("=" * 75)
    return total_in_mongo, sample


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

