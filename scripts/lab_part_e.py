"""Laboratorio Integral de Extensión Híbrida con MongoDB (Parte E: E1, E2, E3, E4).

Ejecuta y genera todas las evidencias requeridas en `evidencias/parte_e/`:
  E1: Ejecución del ETL completo (1.000 películas) y volcado del documento `_id: 1`.
  E2: Demostración con `explain("executionStats")` del paso de COLLSCAN a IXSCAN y prueba de GET /api/catalog.
  E3: Demostración del desfase (eventual consistency lag) al actualizar `film.rental_rate` en MySQL
      y posterior sincronización con `sync_film(1)`.
  E4: Verificación de que `POST /api/checkout` funciona al 100% con MongoDB apagado/inaccesible.
"""
import os
import sys
import json
import time
import mysql.connector
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

from config import Config
from app import create_app
from app.mongo import get_films_collection, reset_mongo_client
from scripts.etl_catalog import run_etl, sync_film
from scripts.race_test import cleanup_inventory_rentals


def get_admin_mysql():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "sakila"),
        autocommit=True,
    )


def save_evidence(filename, lines):
    os.makedirs("evidencias/parte_e", exist_ok=True)
    path = os.path.join("evidencias/parte_e", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Evidencia guardada en: {path}")


def extract_winning_stage(plan):
    """Extrae recursivamente la etapa principal (COLLSCAN / IXSCAN) del queryPlanner."""
    if not isinstance(plan, dict):
        return "UNKNOWN"
    stage = plan.get("stage")
    input_stage = plan.get("inputStage")
    if input_stage:
        inner = extract_winning_stage(input_stage)
        return f"{stage} -> {inner}"
    return stage or "UNKNOWN"


def run_e1():
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("=" * 80)
    log("PARTE E1: EJECUCIÓN DE ETL (MySQL -> MongoDB sakila_catalog.films)")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 80)

    total_docs, sample_doc = run_etl(drop_existing=True)
    log(f"Total documentos cargados en `sakila_catalog.films`: {total_docs}")
    log("\nDocumento cargado para film_id = 1 (ACADEMY DINOSAUR):")
    log(json.dumps(sample_doc, indent=2, ensure_ascii=False))
    save_evidence("E1_etl_y_documento_1.txt", lines)


def run_e2(client):
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("=" * 80)
    log("PARTE E2: ENDPOINT GET /api/catalog Y DEMOSTRACIÓN COLLSCAN -> IXSCAN")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 80)

    coll = get_films_collection()
    # Eliminar índices secundarios previos para medir COLLSCAN limpio
    for idx_name in list(coll.index_information().keys()):
        if idx_name != "_id_":
            coll.drop_index(idx_name)

    filter_query = {"categories": "Action", "rental_rate": {"$lte": 2.99}}
    log(f"\nFiltro de prueba en MongoDB: {json.dumps(filter_query)}")

    # 1. Explain ANTES del índice (COLLSCAN)
    explain_before = coll.find(filter_query).explain()
    qp_before = explain_before.get("queryPlanner", {}).get("winningPlan", {})
    stats_before = explain_before.get("executionStats", {})

    log("\n--- 1. ANTES DEL ÍNDICE (Sin índices secundarios) ---")
    log(f"Winning Plan Stage : {extract_winning_stage(qp_before)}")
    log(f"nReturned          : {stats_before.get('nReturned')}")
    log(f"totalKeysExamined  : {stats_before.get('totalKeysExamined')}")
    log(f"totalDocsExamined  : {stats_before.get('totalDocsExamined')} (Escaneo completo de los 1.000 documentos)")
    log(f"executionTimeMillis: {stats_before.get('executionTimeMillis')} ms")
    log("Resumen JSON executionStats (ANTES):")
    log(json.dumps({
        "winningPlan": qp_before,
        "nReturned": stats_before.get("nReturned"),
        "totalKeysExamined": stats_before.get("totalKeysExamined"),
        "totalDocsExamined": stats_before.get("totalDocsExamined"),
        "executionTimeMillis": stats_before.get("executionTimeMillis"),
    }, indent=2))

    # 2. Crear índices compuestos multikey en MongoDB
    log("\n--- 2. CREACIÓN DE ÍNDICES EN MONGODB ---")
    idx1 = coll.create_index([("categories", 1), ("rental_rate", 1)], name="idx_categories_rental_rate")
    idx2 = coll.create_index([("actors.name", 1), ("rental_rate", 1)], name="idx_actors_name_rate")
    log(f"Índices creados: `{idx1}`, `{idx2}`")

    # 3. Explain DESPUÉS del índice (IXSCAN)
    explain_after = coll.find(filter_query).explain()
    qp_after = explain_after.get("queryPlanner", {}).get("winningPlan", {})
    stats_after = explain_after.get("executionStats", {})

    log("\n--- 3. DESPUÉS DEL ÍNDICE (Con `idx_categories_rental_rate`) ---")
    log(f"Winning Plan Stage : {extract_winning_stage(qp_after)}")
    log(f"nReturned          : {stats_after.get('nReturned')}")
    log(f"totalKeysExamined  : {stats_after.get('totalKeysExamined')}")
    log(f"totalDocsExamined  : {stats_after.get('totalDocsExamined')} (Solo examina los documentos que cumplen el índice)")
    log(f"executionTimeMillis: {stats_after.get('executionTimeMillis')} ms")
    log("Resumen JSON executionStats (DESPUÉS):")
    log(json.dumps({
        "winningPlan": qp_after,
        "nReturned": stats_after.get("nReturned"),
        "totalKeysExamined": stats_after.get("totalKeysExamined"),
        "totalDocsExamined": stats_after.get("totalDocsExamined"),
        "executionTimeMillis": stats_after.get("executionTimeMillis"),
    }, indent=2))

    # 4. Probar endpoint HTTP GET /api/catalog
    log("\n--- 4. PRUEBA DEL ENDPOINT HTTP GET /api/catalog ---")
    resp = client.get("/api/catalog?category=Action&max_rate=2.99&page=1&page_size=3")
    log(f"GET /api/catalog?category=Action&max_rate=2.99&page=1&page_size=3 -> HTTP {resp.status_code}")
    log(json.dumps(resp.get_json(), indent=2, ensure_ascii=False))

    save_evidence("E2_explain_collscan_vs_ixscan.txt", lines)


def run_e3(client):
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("=" * 80)
    log("PARTE E3: DEMOSTRACIÓN DE DESFASE (CONSISTENCIA EVENTUAL) Y sync_film(1)")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 80)

    conn = get_admin_mysql()
    cur = conn.cursor()

    try:
        # 1. Estado inicial sincronizado
        cur.execute("UPDATE film SET rental_rate = 0.99 WHERE film_id = 1;")
        sync_film(1)

        cur.execute("SELECT rental_rate FROM film WHERE film_id = 1;")
        mysql_rate_0 = float(cur.fetchone()[0])
        mongo_doc_0 = client.get("/api/catalog/1").get_json()["data"]
        log(f"[Paso 1 - Estado Inicial] MySQL rental_rate = {mysql_rate_0} | MongoDB rental_rate = {mongo_doc_0['rental_rate']}")

        # 2. Actualizar precio en MySQL (Fuente de Verdad) sin sincronizar aún
        log("\n[Paso 2 - Cambio en Fuente de Verdad] Ejecutando en MySQL: UPDATE film SET rental_rate = 4.99 WHERE film_id = 1;")
        cur.execute("UPDATE film SET rental_rate = 4.99 WHERE film_id = 1;")

        cur.execute("SELECT rental_rate FROM film WHERE film_id = 1;")
        mysql_rate_1 = float(cur.fetchone()[0])
        mongo_doc_1 = client.get("/api/catalog/1").get_json()["data"]
        log(f"[Paso 3 - Desfase Demostrado (Stale Read)]")
        log(f"  -> Tarifa real en MySQL (Fuente de Verdad): {mysql_rate_1}")
        log(f"  -> Tarifa en catálogo MongoDB (Desactualizada): {mongo_doc_1['rental_rate']}")

        # 3. Invocar sync_film(1) vía endpoint o función
        log("\n[Paso 4 - Sincronización] Ejecutando sync_film(1) / POST /api/catalog/sync/1...")
        sync_resp = client.post("/api/catalog/sync/1")
        log(f"  -> Respuesta HTTP {sync_resp.status_code}")

        mongo_doc_2 = client.get("/api/catalog/1").get_json()["data"]
        log(f"[Paso 5 - Consistencia Restaurada]")
        log(f"  -> Tarifa en MySQL  : {mysql_rate_1}")
        log(f"  -> Tarifa en MongoDB: {mongo_doc_2['rental_rate']}")

    finally:
        # Restaurar tarifa original 0.99
        cur.execute("UPDATE film SET rental_rate = 0.99 WHERE film_id = 1;")
        sync_film(1)
        cur.close()
        conn.close()

    save_evidence("E3_desfase_y_sync_film.txt", lines)


def run_e4(client):
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("=" * 80)
    log("PARTE E4: PRUEBA DE RESILIENCIA (CHECKOUT FUNCIONAL CON MONGODB APAGADO)")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 80)

    original_uri = Config.MONGO_URI
    original_timeout = Config.MONGO_TIMEOUT_MS
    cleanup_inventory_rentals(2)

    try:
        # Simular MongoDB apagado apuntando a un puerto local cerrado con timeout rápido
        Config.MONGO_URI = "mongodb://127.0.0.1:27099"
        Config.MONGO_TIMEOUT_MS = 500
        reset_mongo_client()
        log("[Paso 1] MongoDB desconectado/apagado (URI apuntando a puerto cerrado 27099)")

        # 1. Verificar que el catálogo responde 503 controlado sin tumbar la app
        cat_resp = client.get("/api/catalog")
        log(f"\n[Paso 2] Petición a GET /api/catalog con MongoDB apagado:")
        log(f"  -> HTTP {cat_resp.status_code}: {json.dumps(cat_resp.get_json(), ensure_ascii=False)}")

        # 2. Verificar que POST /api/checkout funciona al 100% porque solo depende de MySQL
        checkout_payload = {"customer_id": 1, "inventory_id": 2, "staff_id": 1}
        log(f"\n[Paso 3] Ejecutando POST /api/checkout con MongoDB apagado: {checkout_payload}")
        co_resp = client.post("/api/checkout", json=checkout_payload)
        log(f"  -> HTTP {co_resp.status_code}: {json.dumps(co_resp.get_json(), ensure_ascii=False)}")
        assert co_resp.status_code == 201, f"El checkout falló con Mongo apagado: {co_resp.get_json()}"
        log("\nVEREDICTO: ¡ÉXITO! El motor transaccional de alquileres y pagos (MySQL) es 100% independiente de fallos en MongoDB.")

    finally:
        cleanup_inventory_rentals(2)
        Config.MONGO_URI = original_uri
        Config.MONGO_TIMEOUT_MS = original_timeout
        reset_mongo_client()

    save_evidence("E4_checkout_con_mongo_apagado.txt", lines)


def main():
    # Asegurar que sakila_app tenga permisos SELECT sobre las tablas de catálogo
    conn = get_admin_mysql()
    cur = conn.cursor()
    for tbl in ["language", "category", "film_category", "actor", "film_actor"]:
        cur.execute(f"GRANT SELECT ON sakila.{tbl} TO 'sakila_app'@'localhost';")
    cur.execute("FLUSH PRIVILEGES;")
    cur.close()
    conn.close()

    app = create_app()
    client = app.test_client()

    run_e1()
    run_e2(client)
    run_e3(client)
    run_e4(client)


if __name__ == "__main__":
    main()
