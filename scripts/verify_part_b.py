"""Suite de verificación automatizada para validar compilación, lógica y endpoints de la Parte B."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app


def run_checks():
    app = create_app()
    client = app.test_client()

    # 1. Reporte diario paginado y sargable
    r1 = client.get("/api/payments/report?day=2005-07-09&page=1&page_size=5")
    assert r1.status_code == 200, f"Fallo en reporte: {r1.status_code}"
    body1 = r1.get_json()
    assert body1["success"] is True and len(body1["data"]["items"]) == 5
    print("[OK] 1. GET /api/payments/report paginado y sargable (HTTP 200)")

    # 2. Bloqueo de intento de Inyección SQL
    r2 = client.get("/api/payments/report?day=x' OR '1'='1' LIMIT 5 -- -")
    assert r2.status_code == 400, f"Debería rechazar SQLi con 400, dio {r2.status_code}"
    print("[OK] 2. Intento de Inyección SQL bloqueado en validación (HTTP 400)")

    # 3. Rechazo de manipulación de monto (amount enviado por el cliente)
    r3 = client.post(
        "/api/checkout",
        json={"customer_id": 1, "inventory_id": 1, "staff_id": 1, "amount": 0.01},
    )
    assert r3.status_code == 400
    print("[OK] 3. Manipulación de precio (campo amount) rechazada (HTTP 400)")

    # 4. Cliente inexistente (Information Hiding, sin filtrar SQLState)
    r4 = client.post(
        "/api/checkout",
        json={"customer_id": 60000, "inventory_id": 1, "staff_id": 1},
    )
    assert r4.status_code == 404
    body4 = r4.get_json()
    assert "sqlstate" not in str(body4).lower()
    print("[OK] 4. Recurso inexistente responde 404 limpio sin fugas de motor")

    # 5. Consulta de alquiler existente
    r5 = client.get("/api/rentals/1")
    assert r5.status_code == 200
    assert r5.get_json()["data"]["rental_id"] == 1
    print("[OK] 5. GET /api/rentals/1 funciona con el pool y usuario sakila_app (HTTP 200)")

    print("\n=== TODAS LAS PRUEBAS DE VERIFICACIÓN PASARON SIN ERRORES ===")


if __name__ == "__main__":
    run_checks()

