"""Script de verificación automatizada de la Parte E (Extensión Híbrida MongoDB).

Verifica:
  1. Presencia de archivos de evidencia E1, E2, E3, E4 en `evidencias/parte_e/`.
  2. Colección `sakila_catalog.films` poblada con 1.000 documentos desnormalizados.
  3.Funcionamiento del endpoint `GET /api/catalog` con filtros y paginación.
  4. Paso de `COLLSCAN` a `IXSCAN` mediante el índice multikey `idx_categories_rental_rate`.
  5. Funcionamiento de `sync_film(film_id)` ante cambios en MySQL.
  6. Resiliencia e independencia de `POST /api/checkout` cuando MongoDB está apagado.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config
from app import create_app
from app.mongo import get_films_collection, reset_mongo_client
from scripts.etl_catalog import sync_film
from scripts.race_test import cleanup_inventory_rentals


class TestPartEHybridMongo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_1_evidence_files_exist(self):
        for fname in [
            "E1_etl_y_documento_1.txt",
            "E2_explain_collscan_vs_ixscan.txt",
            "E3_desfase_y_sync_film.txt",
            "E4_checkout_con_mongo_apagado.txt",
        ]:
            path = os.path.join("evidencias/parte_e", fname)
            self.assertTrue(os.path.exists(path), f"Falta evidencia: {path}")

    def test_2_etl_collection_populated(self):
        coll = get_films_collection()
        self.assertEqual(coll.count_documents({}), 1000)
        doc1 = coll.find_one({"_id": 1})
        self.assertIsNotNone(doc1)
        self.assertEqual(doc1["title"], "ACADEMY DINOSAUR")
        self.assertIn("Documentary", doc1["categories"])
        self.assertTrue(any(a["name"] == "PENELOPE GUINESS" for a in doc1["actors"]))

    def test_3_catalog_endpoint_filters_and_pagination(self):
        resp = self.client.get("/api/catalog?category=Action&max_rate=2.99&page=1&page_size=5")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["success"])
        data = body["data"]
        self.assertEqual(data["count"], 5)
        self.assertEqual(data["total"], 47)
        for item in data["items"]:
            self.assertIn("Action", item["categories"])
            self.assertLessEqual(item["rental_rate"], 2.99)

    def test_4_ixscan_active_in_mongodb(self):
        coll = get_films_collection()
        exp = coll.find({"categories": "Action", "rental_rate": {"$lte": 2.99}}).explain()
        plan_str = str(exp.get("queryPlanner", {}).get("winningPlan", {}))
        self.assertIn("IXSCAN", plan_str)
        stats = exp.get("executionStats", {})
        self.assertEqual(stats.get("totalDocsExamined"), 47)
        self.assertEqual(stats.get("nReturned"), 47)

    def test_5_sync_film_endpoint(self):
        resp = self.client.post("/api/catalog/sync/1")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["data"]["synced"])
        self.assertEqual(body["data"]["film"]["_id"], 1)

    def test_6_checkout_works_with_mongo_offline(self):
        orig_uri = Config.MONGO_URI
        orig_timeout = Config.MONGO_TIMEOUT_MS
        cleanup_inventory_rentals(3)
        try:
            Config.MONGO_URI = "mongodb://127.0.0.1:27099"
            Config.MONGO_TIMEOUT_MS = 300
            reset_mongo_client()

            cat_resp = self.client.get("/api/catalog")
            self.assertEqual(cat_resp.status_code, 503)

            co_resp = self.client.post(
                "/api/checkout",
                json={"customer_id": 1, "inventory_id": 3, "staff_id": 1},
            )
            self.assertEqual(co_resp.status_code, 201)
        finally:
            cleanup_inventory_rentals(3)
            Config.MONGO_URI = orig_uri
            Config.MONGO_TIMEOUT_MS = orig_timeout
            reset_mongo_client()


if __name__ == "__main__":
    unittest.main()
