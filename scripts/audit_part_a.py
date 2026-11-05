import os
import sys
import time
import json
import threading

# Agregar raíz del proyecto a sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# Importar app heredada
from legacy_app import app

# Iniciar Flask en hilo secundario daemon
print("Iniciando legacy_app en segundo plano...")
server_thread = threading.Thread(
    target=lambda: app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False),
    daemon=True
)
server_thread.start()
time.sleep(2) # Esperar a que Flask esté listo
print("legacy_app iniciado en http://127.0.0.1:5000")

# Conexión directa a MySQL para comprobaciones
def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "sakila")
    )

BASE_URL = "http://127.0.0.1:5000"

results = {}

print("="*60)
print("INICIANDO AUDITORÍA DE LA PARTE A (CÓDIGO HEREDADO)")
print("="*60)

# -------------------------------------------------------------
# Incidente (a): Inyección SQL
# -------------------------------------------------------------
print("\n--- Incidente (a): Inyección SQL ---")
url_a = f"{BASE_URL}/api/payments/report?day=x' OR '1'='1' LIMIT 5 -- -"
print(f"GET {url_a}")
resp_a = requests.get(url_a)
results['a_sqli'] = {
    'request_url': url_a,
    'status_code': resp_a.status_code,
    'response_json': resp_a.json()
}
print(f"Status: {resp_a.status_code}")
print(f"Filas devueltas: {len(resp_a.json())}")
print(f"Muestra de respuesta: {json.dumps(resp_a.json()[:2], indent=2, default=str)}")

# -------------------------------------------------------------
# Incidente (b): Information Exposure
# -------------------------------------------------------------
print("\n--- Incidente (b): Information Exposure ---")
# Usamos un inventory_id válido disponible
conn = get_db()
cur = conn.cursor()
cur.execute("SELECT inventory_id FROM inventory WHERE inventory_in_stock(inventory_id) = 1 LIMIT 1;")
inv_id = cur.fetchone()[0]
cur.close()
conn.close()

url_b = f"{BASE_URL}/api/checkout?customer_id=99999&inventory_id={inv_id}&staff_id=1&amount=2.99"
print(f"GET {url_b}")
resp_b = requests.get(url_b)
results['b_info_exposure'] = {
    'request_url': url_b,
    'status_code': resp_b.status_code,
    'response_json': resp_b.json()
}
print(f"Status: {resp_b.status_code}")
print(f"Respuesta: {json.dumps(resp_b.json(), indent=2)}")

# -------------------------------------------------------------
# Incidente (c): Alquiler Huérfano
# -------------------------------------------------------------
print("\n--- Incidente (c): Alquiler Huérfano ---")
# Obtener un inventory_id disponible
conn = get_db()
cur = conn.cursor()
cur.execute("SELECT inventory_id FROM inventory WHERE inventory_in_stock(inventory_id) = 1 LIMIT 1;")
inv_id_c = cur.fetchone()[0]

# Consultar últimos rental_id y payment_id antes
cur.execute("SELECT MAX(rental_id) FROM rental;")
max_rental_before = cur.fetchone()[0] or 0
cur.execute("SELECT MAX(payment_id) FROM payment;")
max_payment_before = cur.fetchone()[0] or 0
cur.close()
conn.close()

url_c = f"{BASE_URL}/api/checkout?customer_id=1&inventory_id={inv_id_c}&staff_id=1&amount=99999"
print(f"GET {url_c}")
resp_c = requests.get(url_c)
print(f"Status: {resp_c.status_code}")
print(f"Respuesta: {json.dumps(resp_c.json(), indent=2)}")

# Consultar rental y payment después
conn = get_db()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT * FROM rental WHERE rental_id > %s;", (max_rental_before,))
new_rentals = cur.fetchall()
cur.execute("SELECT * FROM payment WHERE payment_id > %s;", (max_payment_before,))
new_payments = cur.fetchall()
cur.close()
conn.close()

results['c_orphan_rental'] = {
    'request_url': url_c,
    'status_code': resp_c.status_code,
    'response_json': resp_c.json(),
    'new_rentals': new_rentals,
    'new_payments': new_payments
}
print(f"Nuevos registros en rental: {len(new_rentals)} -> {new_rentals}")
print(f"Nuevos registros en payment: {len(new_payments)} -> {new_payments}")

# -------------------------------------------------------------
# Incidente (d): Handshake por petición
# -------------------------------------------------------------
print("\n--- Incidente (d): Handshake por petición ---")
conn = get_db()
cur = conn.cursor()
cur.execute("SHOW GLOBAL STATUS LIKE 'Connections';")
conn_before = int(cur.fetchone()[1])
cur.close()
conn.close()

print(f"Connections ANTES de 50 peticiones: {conn_before}")

url_d = f"{BASE_URL}/api/payments/report?day=2005-07-09"
for i in range(50):
    r = requests.get(url_d)

conn = get_db()
cur = conn.cursor()
cur.execute("SHOW GLOBAL STATUS LIKE 'Connections';")
conn_after = int(cur.fetchone()[1])
cur.close()
conn.close()

conn_growth = conn_after - conn_before
print(f"Connections DESPUÉS de 50 peticiones: {conn_after}")
print(f"Incremento total del contador: {conn_growth}")

results['d_handshake'] = {
    'request_url': url_d,
    'calls_count': 50,
    'connections_before': conn_before,
    'connections_after': conn_after,
    'growth': conn_growth
}

# Guardar resultados en JSON para el informe
with open("scripts/audit_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=str)

print("\nResultados guardados exitosamente en scripts/audit_results.json")
