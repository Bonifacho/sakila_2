"""Script de verificación automática de la Parte D (Optimización e Indexación).
Verifica:
  1. Existencia del archivo de benchmark y evidencias numéricas en evidencias/parte_d/
  2. Presencia de índices requeridos en payment_big
  3. Comportamiento del plan de ejecución para Q1 optimizada (type=range, key=idx_payment_date)
  4. Comportamiento de índice cubriente para Q2 (Extra contiene 'Using index')
"""
import os
import sys
import unittest
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

class TestPartDOptimization(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.getenv("DB_NAME", "sakila")
        )
        cls.cur = cls.conn.cursor(dictionary=True)

    @classmethod
    def tearDownClass(cls):
        cls.cur.close()
        cls.conn.close()

    def test_evidence_file_exists_and_contains_data(self):
        ev_file = "evidencias/parte_d/D_benchmark_resultados.txt"
        self.assertTrue(os.path.exists(ev_file), f"No existe el archivo {ev_file}")
        with open(ev_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("D1: MEDICIÓN DE LÍNEA BASE", content)
        self.assertIn("D2: DISEÑO Y EVALUACIÓN DE ÍNDICES", content)
        self.assertIn("D3 (Parte 1)", content)
        self.assertIn("D3 (Parte 2)", content)
        self.assertIn("idx_covering_q2", content)
        self.assertIn("Using index", content)

    def test_indexes_exist_on_payment_big(self):
        self.cur.execute("SHOW INDEX FROM payment_big;")
        indexes = {r["Key_name"] for r in self.cur.fetchall()}
        self.assertIn("PRIMARY", indexes)
        self.assertIn("idx_payment_date", indexes)
        self.assertIn("idx_covering_q2", indexes)

    def test_q1_optimized_plan(self):
        q1_opt = """SELECT payment_id, customer_id, staff_id, amount, payment_date
FROM payment_big
WHERE payment_date >= '2005-07-09 00:00:00' AND payment_date < '2005-07-10 00:00:00'
ORDER BY payment_date
LIMIT 50;"""
        self.cur.execute(f"EXPLAIN {q1_opt}")
        plan = self.cur.fetchone()
        self.assertEqual(plan["type"], "range")
        self.assertEqual(plan["key"], "idx_payment_date")

    def test_q2_covering_index_plan(self):
        q2 = """SELECT customer_id, SUM(amount) AS total
FROM payment_big
WHERE payment_date >= '2005-07-01' AND payment_date < '2005-08-01'
GROUP BY customer_id
ORDER BY total DESC
LIMIT 10;"""
        self.cur.execute(f"EXPLAIN {q2}")
        plan = self.cur.fetchone()
        self.assertEqual(plan["type"], "range")
        self.assertEqual(plan["key"], "idx_covering_q2")
        self.assertIn("Using index", plan["Extra"])

if __name__ == "__main__":
    unittest.main()

