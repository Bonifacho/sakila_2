"""Evidencias REALES de la Parte B. Levanta el servicio refactorizado, ejecuta las pruebas
y guarda la salida textual exacta en evidencias/parte_b/. Requiere MariaDB en ejecución.
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import mysql.connector
import requests
from dotenv import load_dotenv
from werkzeug.serving import make_server

load_dotenv()
from app import create_app  # noqa: E402

OUT_DIR = "evidencias/parte_b"
BASE = "http://127.0.0.1:5001"
os.makedirs(OUT_DIR, exist_ok=True)


def admin_conn():
    return mysql.connector.connect(host=os.getenv("DB_HOST", "127.0.0.1"),
                                   user=os.environ["DB_USER"],
                                   password=os.environ["DB_PASSWORD"], database="sakila")


def admin_query(sql, params=()):
    conn = admin_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall() if cur.description else []
    conn.commit()
    cur.close()
    conn.close()
    return cols, rows


def table(cols, rows):
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c))
              for i, c in enumerate(cols)]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    out = [line, "| " + " | ".join(str(c).ljust(w) for c, w in zip(cols, widths)) + " |", line]
    for r in rows:
        out.append("| " + " | ".join(str(v).ljust(w) for v, w in zip(r, widths)) + " |")
    out.append(line)
    out.append(f"{len(rows)} row(s)")
    return "\n".join(out)


class Section:
    def __init__(self, filename, title):
        self.filename, self.lines = filename, []
        self.log(f"# {title}")
        self.log(f"# Ejecutado: {datetime.now().isoformat(timespec='seconds')}\n")

    def log(self, text=""):
        print(text)
        self.lines.append(str(text))

    def http(self, method, path, body=None):
        url = BASE + path
        resp = requests.request(method, url, json=body, timeout=30)
        self.log(f"> {method} {path}")
        if body is not None:
            self.log(f"> Body: {json.dumps(body)}")
        self.log(f"< HTTP {resp.status_code}")
        self.log(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        self.log()
        return resp

    def save(self):
        with open(os.path.join(OUT_DIR, self.filename), "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")


def available_inventory(exclude=()):
    _, rows = admin_query(
        "SELECT inventory_id FROM inventory WHERE inventory_in_stock(inventory_id) = 1 "
        "ORDER BY inventory_id LIMIT 20")
    return next(r[0] for r in rows if r[0] not in exclude)


def main():
    app = create_app()
    server = make_server("127.0.0.1", 5001, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(1)

    # ---------- B3: checkout exitoso + SELECT en rental y payment ----------
    s = Section("B3_checkout_exitoso.txt", "B3 - Checkout exitoso (transacción única)")
    inv = available_inventory()
    resp = s.http("POST", "/api/checkout", {"customer_id": 1, "inventory_id": inv, "staff_id": 1})
    rental_id = resp.json()["data"]["rental_id"]
    s.log("SQL> SELECT r.rental_id, r.rental_date, r.inventory_id, r.customer_id, "
          "p.payment_id, p.amount, p.payment_date, f.rental_rate FROM rental r "
          "JOIN payment p ON p.rental_id = r.rental_id JOIN inventory i ON i.inventory_id = "
          f"r.inventory_id JOIN film f ON f.film_id = i.film_id WHERE r.rental_id = {rental_id};")
    s.log(table(*admin_query(
        "SELECT r.rental_id, r.rental_date, r.inventory_id, r.customer_id, p.payment_id, "
        "p.amount, p.payment_date, f.rental_rate FROM rental r "
        "JOIN payment p ON p.rental_id = r.rental_id "
        "JOIN inventory i ON i.inventory_id = r.inventory_id "
        "JOIN film f ON f.film_id = i.film_id WHERE r.rental_id = %s", (rental_id,))))
    s.save()

    # ---------- B4: códigos HTTP coherentes ----------
    s = Section("B4_codigos_http.txt", "B4 - Respuestas JSON uniformes y códigos HTTP")
    s.http("POST", "/api/checkout", {"customer_id": "abc", "inventory_id": inv, "staff_id": 1})
    s.http("POST", "/api/checkout",
           {"customer_id": 1, "inventory_id": inv, "staff_id": 1, "amount": 0.01})
    s.http("POST", "/api/checkout", {"customer_id": 9999, "inventory_id": inv, "staff_id": 1})
    s.http("POST", "/api/checkout", {"customer_id": 1, "inventory_id": 999999, "staff_id": 1})
    s.http("POST", "/api/checkout", {"customer_id": 2, "inventory_id": inv, "staff_id": 1})
    s.http("GET", "/api/payments/report?day=x' OR '1'='1' LIMIT 5 -- -")
    s.save()

    # ---------- B3: fallo provocado -> ROLLBACK, sin alquiler a medias ----------
    s = Section("B3_fallo_provocado_rollback.txt",
                "B3 - Fallo provocado en el INSERT de payment: ROLLBACK total")
    trigger_sql = ("CREATE TRIGGER trg_test_fail_payment BEFORE INSERT ON payment FOR EACH ROW "
                   "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Fallo simulado en payment'")
    inv2 = available_inventory(exclude=(inv,))
    try:
        admin_query(trigger_sql)
        s.log("SQL (root)> " + trigger_sql + ";\n")
        before = admin_query("SELECT COUNT(*) FROM rental")[1][0][0]
        s.log(f"rental COUNT(*) antes: {before}\n")
        s.http("POST", "/api/checkout", {"customer_id": 3, "inventory_id": inv2, "staff_id": 1})
        after = admin_query("SELECT COUNT(*) FROM rental")[1][0][0]
        s.log(f"rental COUNT(*) después: {after}")
        s.log(f"SQL> SELECT * FROM rental WHERE inventory_id = {inv2} AND return_date IS NULL;")
        s.log(table(*admin_query(
            "SELECT rental_id, rental_date, inventory_id, customer_id FROM rental "
            "WHERE inventory_id = %s AND return_date IS NULL", (inv2,))))
        s.log(f"\nResultado: {'SIN alquiler huérfano (ROLLBACK OK)' if before == after else 'ERROR: quedó alquiler a medias'}")
    finally:
        admin_query("DROP TRIGGER IF EXISTS trg_test_fail_payment")
        s.log("\nSQL (root)> DROP TRIGGER IF EXISTS trg_test_fail_payment;")
    with open("logs/app.log", encoding="utf-8") as f:
        last = [l.rstrip() for l in f if "Fallo simulado" in l][-1:]
    s.log("\nLog del servidor (logs/app.log) - el detalle solo queda aquí:")
    for l in last:
        s.log(l)
    s.save()

    # ---------- B5: privilegios mínimos ----------
    s = Section("B5_show_grants.txt", "B5 - SHOW GRANTS FOR 'sakila_app'@'localhost'")
    cols, rows = admin_query("SHOW GRANTS FOR 'sakila_app'@'localhost'")
    s.log(table(cols, [(r[0].split("IDENTIFIED BY")[0] + ("IDENTIFIED BY PASSWORD '***'" if "IDENTIFIED BY" in r[0] else ""),) for r in rows]))
    s.save()

    # ---------- B2: Connections antes/después de 200 peticiones concurrentes ----------
    s = Section("B2_pool_connections.txt",
                "B2 - Contador Connections con 200 peticiones concurrentes (pool de 10)")
    before = int(admin_query("SHOW GLOBAL STATUS LIKE 'Connections'")[1][0][1])
    s.log(f"Connections ANTES:   {before}")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=50) as ex:
        codes = list(ex.map(lambda _: requests.get(f"{BASE}/api/rentals/{rental_id}",
                                                   timeout=30).status_code, range(200)))
    elapsed = time.time() - t0
    after = int(admin_query("SHOW GLOBAL STATUS LIKE 'Connections'")[1][0][1])
    s.log(f"Connections DESPUÉS: {after}")
    s.log(f"Peticiones: 200 (50 hilos concurrentes) en {elapsed:.2f}s")
    s.log(f"Códigos HTTP: { {c: codes.count(c) for c in set(codes)} }")
    s.log(f"Incremento: {after - before}")
    s.log("Nota: la consulta 'DESPUÉS' abre 1 conexión propia (root) que también suma al "
          "contador. El pool de 10 conexiones ya estaba creado desde el primer checkout, "
          "por lo que las 200 peticiones reutilizaron conexiones existentes.")
    s.log("Comparación: legacy_app sumó +51 conexiones con solo 50 peticiones (Parte A).")
    s.save()

    # ---------- B6: devolución en lugar de borrado ----------
    s = Section("B6_devolucion.txt", "B6 - PATCH /api/rentals/<id>/return (reemplaza el DELETE)")
    s.http("PATCH", f"/api/rentals/{rental_id}/return")
    s.http("PATCH", f"/api/rentals/{rental_id}/return")
    s.http("PATCH", "/api/rentals/99999999/return")
    s.save()

    server.shutdown()


if __name__ == "__main__":
    main()
