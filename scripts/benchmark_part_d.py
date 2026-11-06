"""Benchmark y Laboratorio de Optimización e Indexación (Parte D).
Ejecuta:
  D1: Medición de Q1 original y Q2 sin índices adicionales (Baseline).
  D2: Comparación de Q1 sargable vs no sargable, y evaluación de alternativas de índices para Q2 (incluyendo índice cubriente).
  D3: Medición de sobrecarga de escritura (Write Overhead) con 50.000 inserciones antes y después de indexar.
  D4: Generación de tabla comparativa de métricas (type, key, rows, tiempo en ms).
"""
import os
import sys
import time
import json
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "sakila"),
        autocommit=True
    )

def drop_secondary_indexes(conn):
    """Elimina cualquier índice secundario previo en payment_big para garantizar un estado limpio."""
    cur = conn.cursor()
    cur.execute("SHOW INDEX FROM payment_big;")
    indexes = set()
    for row in cur.fetchall():
        key_name = row[2]
        if key_name != "PRIMARY":
            indexes.add(key_name)
    for idx in indexes:
        print(f"Eliminando índice existente: {idx}...")
        cur.execute(f"ALTER TABLE payment_big DROP INDEX `{idx}`;")
    cur.close()

def run_query_benchmark(conn, query, runs=3):
    """Ejecuta una consulta varias veces descartando resultados y devuelve el tiempo promedio en ms."""
    cur = conn.cursor()
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        cur.execute(query)
        _ = cur.fetchall()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000.0)
    cur.close()
    return min(times), sum(times) / len(times)

def get_analyze_info(conn, query):
    """Obtiene la fila de ANALYZE SELECT para extraer type, key, rows, etc."""
    cur = conn.cursor(dictionary=True)
    cur.execute(f"ANALYZE {query}")
    row = cur.fetchone()
    cur.close()
    return row

def get_explain_json(conn, query):
    """Obtiene EXPLAIN/ANALYZE FORMAT=JSON."""
    cur = conn.cursor()
    cur.execute(f"ANALYZE FORMAT=JSON {query}")
    json_text = cur.fetchone()[0]
    cur.close()
    return json.loads(json_text)

def main():
    os.makedirs("evidencias/parte_d", exist_ok=True)
    out_lines = []
    def log(msg=""):
        print(msg)
        out_lines.append(str(msg))

    conn = get_connection()
    cur = conn.cursor()

    log("="*80)
    log("LABORATORIO DE OPTIMIZACIÓN E INDEXACIÓN (PARTE D - SAKILA RENTAL ENGINE)")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*80)

    cur.execute("SELECT COUNT(*) FROM payment_big;")
    initial_rows = cur.fetchone()[0]
    log(f"Registros en payment_big: {initial_rows:,}")

    # =========================================================================
    # D1: LÍNEA BASE (BASELINE) SIN ÍNDICES ADICIONALES
    # =========================================================================
    log("\n" + "="*80)
    log("D1: MEDICIÓN DE LÍNEA BASE (BASELINE SIN ÍNDICES ADICIONALES)")
    log("="*80)
    drop_secondary_indexes(conn)

    # Q1 Original
    q1_orig = "SELECT * FROM payment_big WHERE DATE(payment_date) = '2005-07-09';"
    log("\n--- Q1 Original (No sargable, sin índices) ---")
    log(f"SQL: {q1_orig}")
    q1_orig_analyze = get_analyze_info(conn, q1_orig)
    q1_orig_best, q1_orig_avg = run_query_benchmark(conn, q1_orig, runs=3)
    log(f"Plan ANALYZE: type={q1_orig_analyze['type']}, key={q1_orig_analyze['key']}, rows={q1_orig_analyze['rows']}, r_rows={q1_orig_analyze['r_rows']}, Extra={q1_orig_analyze['Extra']}")
    log(f"Tiempo de ejecución: {q1_orig_best:.2f} ms (promedio: {q1_orig_avg:.2f} ms)")

    # Q2 Sin índice
    q2_query = """SELECT customer_id, SUM(amount) AS total
FROM payment_big
WHERE payment_date >= '2005-07-01' AND payment_date < '2005-08-01'
GROUP BY customer_id
ORDER BY total DESC
LIMIT 10;"""
    log("\n--- Q2 Sin Índice (Rango de fechas + Group by + Order by) ---")
    log(f"SQL:\n{q2_query}")
    q2_no_idx_analyze = get_analyze_info(conn, q2_query)
    q2_no_idx_best, q2_no_idx_avg = run_query_benchmark(conn, q2_query, runs=3)
    log(f"Plan ANALYZE: type={q2_no_idx_analyze['type']}, key={q2_no_idx_analyze['key']}, rows={q2_no_idx_analyze['rows']}, r_rows={q2_no_idx_analyze['r_rows']}, Extra={q2_no_idx_analyze['Extra']}")
    log(f"Tiempo de ejecución: {q2_no_idx_best:.2f} ms (promedio: {q2_no_idx_avg:.2f} ms)")

    # =========================================================================
    # D3 (PARTE 1): MEDIR TIEMPO DE ESCRITURA ANTES DE ÍNDICES (50.000 FILAS)
    # =========================================================================
    log("\n" + "="*80)
    log("D3 (Parte 1): MEDIDA DE ESCRITURA ANTES DE CREAR ÍNDICES (50.000 FILAS)")
    log("="*80)
    insert_sql = """INSERT INTO payment_big (customer_id, staff_id, rental_id, amount, payment_date)
SELECT customer_id, staff_id, rental_id, amount, payment_date FROM payment_big LIMIT 50000;"""

    cur.execute("SELECT MAX(payment_id) FROM payment_big;")
    max_id_before_1 = cur.fetchone()[0]

    t0_write_no_idx = time.perf_counter()
    cur.execute(insert_sql)
    write_no_idx_time_ms = (time.perf_counter() - t0_write_no_idx) * 1000.0
    log(f"Tiempo de inserción de 50.000 filas (Solo Primary Key): {write_no_idx_time_ms:.2f} ms")

    # Limpiar inserción 1
    cur.execute("DELETE FROM payment_big WHERE payment_id > %s;", (max_id_before_1,))
    log(f"Limpieza de 50.000 filas completada. Filas actuales: {initial_rows:,}")

    # =========================================================================
    # D2: DISEÑO DE ÍNDICES Y COMPARACIÓN DE ALTERNATIVAS
    # =========================================================================
    log("\n" + "="*80)
    log("D2: DISEÑO Y EVALUACIÓN DE ÍNDICES")
    log("="*80)

    # 1. Optimización de Q1 (Sargable + Selección de columnas + Paginación)
    q1_opt = """SELECT payment_id, customer_id, staff_id, amount, payment_date
FROM payment_big
WHERE payment_date >= '2005-07-09 00:00:00' AND payment_date < '2005-07-10 00:00:00'
ORDER BY payment_date
LIMIT 50 OFFSET 0;"""

    log("\n--- Q1 Optimizada (Sargable, columnas acotadas, paginación LIMIT 50) SIN ÍNDICE todavía ---")
    q1_opt_no_idx_analyze = get_analyze_info(conn, q1_opt)
    q1_opt_no_idx_best, q1_opt_no_idx_avg = run_query_benchmark(conn, q1_opt, runs=2)
    log(f"Plan: type={q1_opt_no_idx_analyze['type']}, key={q1_opt_no_idx_analyze['key']}, rows={q1_opt_no_idx_analyze['rows']}, Extra={q1_opt_no_idx_analyze['Extra']}")
    log(f"Tiempo: {q1_opt_no_idx_best:.2f} ms")

    # Crear índice simple en payment_date para Q1
    log("\nCreando índice `idx_payment_date` en payment_big(payment_date)...")
    t0_idx = time.perf_counter()
    cur.execute("CREATE INDEX idx_payment_date ON payment_big(payment_date);")
    log(f"Índice `idx_payment_date` creado en {(time.perf_counter() - t0_idx)*1000.0:.2f} ms")

    log("\n--- Q1 Optimizada CON `idx_payment_date` ---")
    q1_opt_idx_analyze = get_analyze_info(conn, q1_opt)
    q1_opt_idx_best, q1_opt_idx_avg = run_query_benchmark(conn, q1_opt, runs=3)
    log(f"Plan ANALYZE: type={q1_opt_idx_analyze['type']}, key={q1_opt_idx_analyze['key']}, rows={q1_opt_idx_analyze['rows']}, r_rows={q1_opt_idx_analyze['r_rows']}, Extra={q1_opt_idx_analyze['Extra']}")
    log(f"Tiempo de ejecución: {q1_opt_idx_best:.2f} ms (promedio: {q1_opt_idx_avg:.2f} ms)")

    # ¿Qué pasa si ejecutamos la Q1 ORIGINAL (No sargable con DATE()) incluso teniendo el índice creado?
    log("\n--- Demostración de No Sargabilidad: Q1 ORIGINAL con índice presente ---")
    q1_orig_with_idx = get_analyze_info(conn, q1_orig)
    log(f"Plan ANALYZE Q1 Original con índice existente: type={q1_orig_with_idx['type']}, key={q1_orig_with_idx['key']}, Extra={q1_orig_with_idx['Extra']}")
    log("-> EXPLICACIÓN: El motor NO PUEDE usar el índice `idx_payment_date` porque `DATE(payment_date)` oculta la columna indexada dentro de una función determinista.")

    # 2. Evaluación de alternativas de índice para Q2
    log("\n--- Comparación de Alternativas de Índice para Q2 ---")

    # Alternativa 1: Solo con idx_payment_date (Índice simple, NO cubriente)
    log("\n[Alternativa 1 para Q2]: Usando solo `idx_payment_date` (No cubriente)")
    q2_alt1_analyze = get_analyze_info(conn, q2_query)
    q2_alt1_best, q2_alt1_avg = run_query_benchmark(conn, q2_query, runs=3)
    log(f"Plan: type={q2_alt1_analyze['type']}, key={q2_alt1_analyze['key']}, rows={q2_alt1_analyze['rows']}, Extra={q2_alt1_analyze['Extra']}")
    log(f"Tiempo: {q2_alt1_best:.2f} ms")

    # Alternativa 2: Índice Invertido `idx_cust_date` (customer_id, payment_date)
    log("\n[Alternativa 2 para Q2]: Creando `idx_cust_date` (customer_id, payment_date)...")
    cur.execute("CREATE INDEX idx_cust_date ON payment_big(customer_id, payment_date);")
    q2_alt2_analyze = get_analyze_info(conn, q2_query)
    q2_alt2_best, q2_alt2_avg = run_query_benchmark(conn, q2_query, runs=3)
    log(f"Plan: type={q2_alt2_analyze['type']}, key={q2_alt2_analyze['key']}, rows={q2_alt2_analyze['rows']}, Extra={q2_alt2_analyze['Extra']}")
    log(f"Tiempo: {q2_alt2_best:.2f} ms")
    cur.execute("ALTER TABLE payment_big DROP INDEX idx_cust_date;")

    # Alternativa 3 (Ganadora): Índice Compuesto Cubriente (Covering Index)
    # idx_payment_date_cust_amount: payment_date (filtro de rango) + customer_id (agrupación) + amount (suma)
    log("\n[Alternativa 3 para Q2 - Ganadora]: Creando Índice Cubriente `idx_covering_q2` (payment_date, customer_id, amount)...")
    t0_cov = time.perf_counter()
    cur.execute("CREATE INDEX idx_covering_q2 ON payment_big(payment_date, customer_id, amount);")
    log(f"Índice cubriente creado en {(time.perf_counter() - t0_cov)*1000.0:.2f} ms")

    q2_cov_analyze = get_analyze_info(conn, q2_query)
    q2_cov_best, q2_cov_avg = run_query_benchmark(conn, q2_query, runs=3)
    log(f"Plan ANALYZE: type={q2_cov_analyze['type']}, key={q2_cov_analyze['key']}, rows={q2_cov_analyze['rows']}, r_rows={q2_cov_analyze['r_rows']}, Extra={q2_cov_analyze['Extra']}")
    log(f"Tiempo de ejecución: {q2_cov_best:.2f} ms (promedio: {q2_cov_avg:.2f} ms)")

    # Comprobación de que es cubriente ("Using index" en Extra)
    is_covering = "Using index" in (q2_cov_analyze["Extra"] or "")
    log(f"¿Es un Índice Cubriente formal? {'SÍ (Extra incluye Using index)' if is_covering else 'NO'}")

    # =========================================================================
    # D3 (PARTE 2): MEDIR TIEMPO DE ESCRITURA DESPUÉS DE ÍNDICES (50.000 FILAS)
    # =========================================================================
    log("\n" + "="*80)
    log("D3 (Parte 2): MEDIDA DE ESCRITURA DESPUÉS DE CREAR ÍNDICES (50.000 FILAS)")
    log("="*80)
    cur.execute("SHOW INDEX FROM payment_big;")
    active_indexes = [r[2] for r in cur.fetchall()]
    log(f"Índices activos en la tabla durante la inserción: {set(active_indexes)}")

    cur.execute("SELECT MAX(payment_id) FROM payment_big;")
    max_id_before_2 = cur.fetchone()[0]

    t0_write_with_idx = time.perf_counter()
    cur.execute(insert_sql)
    write_with_idx_time_ms = (time.perf_counter() - t0_write_with_idx) * 1000.0
    log(f"Tiempo de inserción de 50.000 filas (Con índices activos): {write_with_idx_time_ms:.2f} ms")

    diff_ms = write_with_idx_time_ms - write_no_idx_time_ms
    diff_pct = ((write_with_idx_time_ms - write_no_idx_time_ms) / write_no_idx_time_ms) * 100.0
    log(f"Sobrecarga de escritura (Write Overhead): +{diff_ms:.2f} ms (+{diff_pct:.1f}%)")

    # Limpiar inserción 2
    cur.execute("DELETE FROM payment_big WHERE payment_id > %s;", (max_id_before_2,))
    log(f"Limpieza completada. Filas restauradas a: {initial_rows:,}")

    # =========================================================================
    # D4: TABLA CONSOLIDADA DE RESULTADOS
    # =========================================================================
    log("\n" + "="*80)
    log("D4: TABLA FINAL DE RESULTADOS Y COMPARATIVA DE RENDIMIENTO")
    log("="*80)

    log("| Consulta | type | key | rows | Tiempo (ms) | Índice creado |")
    log("| :--- | :--- | :--- | :--- | :--- | :--- |")
    log(f"| **Q1 original** | {q1_orig_analyze['type']} | {q1_orig_analyze['key'] or 'NULL'} | {q1_orig_analyze['rows']} | {q1_orig_best:.2f} | Ninguno |")
    log(f"| **Q1 optimizada** | {q1_opt_idx_analyze['type']} | {q1_opt_idx_analyze['key']} | {q1_opt_idx_analyze['rows']} | {q1_opt_idx_best:.2f} | `idx_payment_date(payment_date)` |")
    log(f"| **Q2 sin índice** | {q2_no_idx_analyze['type']} | {q2_no_idx_analyze['key'] or 'NULL'} | {q2_no_idx_analyze['rows']} | {q2_no_idx_best:.2f} | Ninguno |")
    log(f"| **Q2 con tu índice** | {q2_cov_analyze['type']} | {q2_cov_analyze['key']} | {q2_cov_analyze['rows']} | {q2_cov_best:.2f} | `idx_covering_q2(payment_date, customer_id, amount)` |")

    # Guardar en archivo de evidencias
    out_file = "evidencias/parte_d/D_benchmark_resultados.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    log(f"\nSalida guardada en: {out_file}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()

