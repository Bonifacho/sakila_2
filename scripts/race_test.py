"""Script de prueba de concurrencia (Condición de Carrera / Race Condition).
Lanza al menos 10 hilos sincronizados mediante una barrera (threading.Barrier)
que intentan alquilar simultáneamente la misma copia física de inventario.
"""
import os
import sys
import time
import argparse
import threading
import requests
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://127.0.0.1:5000"

def get_admin_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "sakila")
    )

def find_available_inventory():
    conn = get_admin_connection()
    cur = conn.cursor()
    cur.execute("SELECT inventory_id FROM inventory WHERE inventory_in_stock(inventory_id) = 1 ORDER BY inventory_id;")
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    if not rows:
        raise RuntimeError("No hay copias disponibles en el inventario de Sakila")
    return rows[0]

def count_unreturned_rentals(inventory_id):
    conn = get_admin_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM rental WHERE inventory_id = %s AND return_date IS NULL;",
        (inventory_id,)
    )
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def get_rental_details(inventory_id):
    conn = get_admin_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT rental_id, rental_date, inventory_id, customer_id, staff_id "
        "FROM rental WHERE inventory_id = %s AND return_date IS NULL "
        "ORDER BY rental_id;",
        (inventory_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def cleanup_inventory_rentals(inventory_id, base_rental_id=16050):
    conn = get_admin_connection()
    cur = conn.cursor()
    # Eliminar pagos asociados a rentals de prueba
    cur.execute(
        "DELETE FROM payment WHERE rental_id IN (SELECT rental_id FROM rental WHERE inventory_id = %s AND rental_id >= %s);",
        (inventory_id, base_rental_id)
    )
    cur.execute(
        "DELETE FROM rental WHERE inventory_id = %s AND rental_id >= %s;",
        (inventory_id, base_rental_id)
    )
    conn.commit()
    deleted = cur.rowcount
    cur.close()
    conn.close()
    return deleted

def run_race_test(num_threads=10, inventory_id=None, out_file=None):
    if inventory_id is None:
        inventory_id = find_available_inventory()

    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("="*75)
    log(f"RACE TEST: Prueba de Concurrencia con {num_threads} Hilos Sincronizados")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Copia de inventario seleccionada: inventory_id = {inventory_id}")
    log("="*75)

    # 1. Comprobar disponibilidad inicial
    initial_unreturned = count_unreturned_rentals(inventory_id)
    log(f"Alquileres no devueltos iniciales para inventory_id={inventory_id}: {initial_unreturned}")
    assert initial_unreturned == 0, f"La copia {inventory_id} no está libre (tiene {initial_unreturned} alquileres activos)"

    # 2. Configurar barrera y resultados
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads

    def worker(thread_idx, customer_id):
        # Esperar a que todos los hilos estén listos en la línea de salida
        barrier.wait()
        
        t0 = time.time()
        payload = {
            "customer_id": customer_id,
            "inventory_id": inventory_id,
            "staff_id": 1
        }
        try:
            resp = requests.post(f"{BASE_URL}/api/checkout", json=payload, timeout=10)
            elapsed = time.time() - t0
            results[thread_idx] = {
                "thread_idx": thread_idx,
                "customer_id": customer_id,
                "status_code": resp.status_code,
                "response": resp.json(),
                "elapsed": elapsed
            }
        except Exception as e:
            results[thread_idx] = {
                "thread_idx": thread_idx,
                "customer_id": customer_id,
                "status_code": "ERROR",
                "response": str(e),
                "elapsed": time.time() - t0
            }

    log(f"\nDisparando {num_threads} hilos simultáneos hacia POST {BASE_URL}/api/checkout...")
    threads = []
    for i in range(num_threads):
        # Usamos customer_id del 1 al 10 (todos válidos en Sakila)
        t = threading.Thread(target=worker, args=(i, i + 1))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # 3. Analizar respuestas HTTP de los hilos
    log("\n--- Respuestas HTTP de los hilos ---")
    status_counts = {}
    for r in results:
        code = r["status_code"]
        status_counts[code] = status_counts.get(code, 0) + 1
        resp_data = r["response"].get("data") or r["response"].get("error") or r["response"]
        log(f"Hilo #{r['thread_idx']:02d} (Cliente {r['customer_id']:02d}): HTTP {code} ({r['elapsed']:.3f}s) -> {resp_data}")

    log(f"\nResumen de códigos HTTP recibidos: {status_counts}")

    # 4. Comprobar estado final en Base de Datos (Métrica exigida por C1)
    final_unreturned = count_unreturned_rentals(inventory_id)
    log("\n--- Comprobación en Base de Datos ---")
    log(f"SQL> SELECT COUNT(*) FROM rental WHERE inventory_id = {inventory_id} AND return_date IS NULL;")
    log(f"Resultado COUNT(*): {final_unreturned}")

    details = get_rental_details(inventory_id)
    log(f"\nRegistros activos encontrados en rental para inventory_id={inventory_id}:")
    for row in details:
        log(f"  rental_id={row['rental_id']} | rental_date={row['rental_date']} | customer_id={row['customer_id']} | staff_id={row['staff_id']}")

    # 5. Veredicto
    log("\n" + "="*75)
    if final_unreturned > 1:
        log(f"VEREDICTO: ¡CONDICIÓN DE CARRERA DETECTADA! (ANOMALÍA)")
        log(f"Se entregó la MISMA copia física (inventory_id={inventory_id}) a {final_unreturned} clientes diferentes al mismo tiempo.")
        log(f"Total clientes con HTTP 201 Created: {status_counts.get(201, 0)}")
    elif final_unreturned == 1 and status_counts.get(201, 0) == 1:
        log(f"VEREDICTO: ¡EXCLUSIÓN MUTUA EXITOSA!")
        log(f"Exactamente 1 hilo obtuvo la copia (HTTP 201) y los demás {num_threads - 1} fueron rechazados.")
    else:
        log(f"VEREDICTO: Comportamiento no esperado (COUNT={final_unreturned}, status={status_counts})")
    log("="*75)

    if out_file:
        os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nSalida guardada en: {out_file}")

    return final_unreturned, status_counts

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba de condición de carrera en Sakila Rental Engine")
    parser.add_argument("--threads", type=int, default=10, help="Número de hilos concurrentes (default: 10)")
    parser.add_argument("--inventory-id", type=int, default=None, help="ID de inventario a probar")
    parser.add_argument("--out", type=str, default=None, help="Archivo para guardar la salida")
    parser.add_argument("--cleanup", action="store_true", help="Limpiar registros de prueba creados")
    args = parser.parse_args()

    if args.cleanup:
        inv_id = args.inventory_id or 1
        del_count = cleanup_inventory_rentals(inv_id)
        print(f"Limpieza completada: {del_count} registros eliminados para inventory_id={inv_id}")
    else:
        run_race_test(num_threads=args.threads, inventory_id=args.inventory_id, out_file=args.out)

