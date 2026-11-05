"""Script de verificación integral de la Parte C (Control de Concurrencia).
Verifica:
  1. Presencia de evidencias C1 (antes y después).
  2. Presencia de evidencias C4 (a, b, c).
  3. Lógica del decorador retry_transient_locks (C5):
     - Reintento ante error 1213 (Deadlock).
     - Reintento ante error 1205 (Lock Wait Timeout).
     - No reintento ante errores no transitorios (e.g. 1062 Duplicate Key).
     - Límite de reintentos (max_attempts).
"""
import os
import sys
import unittest
from unittest.mock import MagicMock
import mysql.connector

# Insertar raíz en sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.retry import retry_transient_locks

class TestPartCConcurrency(unittest.TestCase):

    def test_c1_evidence_files_exist(self):
        antes_path = "evidencias/parte_c/C1_race_test_antes.txt"
        despues_path = "evidencias/parte_c/C1_race_test_despues.txt"
        self.assertTrue(os.path.exists(antes_path), f"Falta {antes_path}")
        self.assertTrue(os.path.exists(despues_path), f"Falta {despues_path}")

        with open(antes_path, "r", encoding="utf-8") as f:
            antes_content = f.read()
        self.assertIn("CONDICIÓN DE CARRERA DETECTADA", antes_content)

        with open(despues_path, "r", encoding="utf-8") as f:
            despues_content = f.read()
        self.assertIn("EXCLUSIÓN MUTUA EXITOSA", despues_content)
        self.assertIn("Resultado COUNT(*): 1", despues_content)

    def test_c4_evidence_files_exist(self):
        c4a_path = "evidencias/parte_c/C4_a_lock_wait_timeout_1205.txt"
        c4b_path = "evidencias/parte_c/C4_b_deadlock_1213.txt"
        c4c_path = "evidencias/parte_c/C4_c_dirty_read.txt"

        self.assertTrue(os.path.exists(c4a_path), f"Falta {c4a_path}")
        self.assertTrue(os.path.exists(c4b_path), f"Falta {c4b_path}")
        self.assertTrue(os.path.exists(c4c_path), f"Falta {c4c_path}")

        with open(c4a_path, "r", encoding="utf-8") as f:
            c4a_content = f.read()
        self.assertIn("1205", c4a_content)
        self.assertIn("innodb_locks", c4a_content)

        with open(c4b_path, "r", encoding="utf-8") as f:
            c4b_content = f.read()
        self.assertIn("1213", c4b_content)
        self.assertIn("LATEST DETECTED DEADLOCK", c4b_content)

        with open(c4c_path, "r", encoding="utf-8") as f:
            c4c_content = f.read()
        self.assertIn("READ UNCOMMITTED", c4c_content)
        self.assertIn("DIRTY_CLIENT", c4c_content)

    def test_retry_transient_locks_success_after_deadlock(self):
        """Prueba que el decorador reintenta y tiene éxito si el deadlock desaparece."""
        mock_func = MagicMock()
        deadlock_err = mysql.connector.Error(msg="Deadlock found", errno=1213)
        mock_func.side_effect = [deadlock_err, {"status": "ok"}]

        decorated = retry_transient_locks(max_attempts=3, base_delay=0.01)(mock_func)
        result = decorated("arg1")

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(mock_func.call_count, 2)

    def test_retry_transient_locks_success_after_lock_timeout(self):
        """Prueba que el decorador reintenta ante error 1205 (lock timeout)."""
        mock_func = MagicMock()
        timeout_err = mysql.connector.Error(msg="Lock wait timeout", errno=1205)
        mock_func.side_effect = [timeout_err, {"status": "ok"}]

        decorated = retry_transient_locks(max_attempts=3, base_delay=0.01)(mock_func)
        result = decorated("arg1")

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(mock_func.call_count, 2)

    def test_retry_transient_locks_does_not_retry_non_transient(self):
        """Prueba que un error permanente (ej. 1062 Duplicate Key) falla de inmediato sin reintentar."""
        mock_func = MagicMock()
        dup_err = mysql.connector.Error(msg="Duplicate entry", errno=1062)
        mock_func.side_effect = dup_err

        decorated = retry_transient_locks(max_attempts=3, base_delay=0.01)(mock_func)
        with self.assertRaises(mysql.connector.Error) as ctx:
            decorated("arg1")

        self.assertEqual(ctx.exception.errno, 1062)
        self.assertEqual(mock_func.call_count, 1)

    def test_retry_transient_locks_exhausts_max_attempts(self):
        """Prueba que si el error transitorio persiste más del límite, se lanza la excepción."""
        mock_func = MagicMock()
        deadlock_err = mysql.connector.Error(msg="Deadlock found", errno=1213)
        mock_func.side_effect = deadlock_err

        decorated = retry_transient_locks(max_attempts=3, base_delay=0.01)(mock_func)
        with self.assertRaises(mysql.connector.Error) as ctx:
            decorated("arg1")

        self.assertEqual(ctx.exception.errno, 1213)
        self.assertEqual(mock_func.call_count, 3)

if __name__ == "__main__":
    unittest.main()

