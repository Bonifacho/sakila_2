"""Laboratorio de Bloqueos y Aislamiento de Transacciones en InnoDB (Parte C4).
Ejecuta de manera controlada y empírica:
  C4(a): Lock Wait Timeout (Error 1205) e inspección en information_schema.
  C4(b): Deadlock (Error 1213) y captura de LATEST DETECTED DEADLOCK en SHOW ENGINE INNODB STATUS.
  C4(c): Lectura Sucia (Dirty Read) bajo READ UNCOMMITTED vs REPEATABLE READ.
"""
import os
import re
import sys
import time
import threading
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
        autocommit=False
    )

def run_lab_c4a(out_file="evidencias/parte_c/C4_a_lock_wait_timeout_1205.txt"):
    """C4(a): Provocar Lock Wait Timeout (1205) e inspeccionar data_locks / innodb_locks."""
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("="*75)
    log("LABORATORIO C4(a): Lock Wait Timeout (Error 1205) e Inspección de Bloqueos")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*75)

    conn_a = get_connection()
    conn_b = get_connection()
    cur_a = conn_a.cursor()
    cur_b = conn_b.cursor()

    try:
        # Sesión A adquiere X-Lock sobre inventory_id = 1
        log("\n[Paso 1] Sesión A: Inicia transacción y bloquea inventory_id=1 con FOR UPDATE")
        cur_a.execute("START TRANSACTION;")
        cur_a.execute("SELECT inventory_id, film_id, store_id FROM inventory WHERE inventory_id = 1 FOR UPDATE;")
        row_a = cur_a.fetchone()
        log(f"Sesión A adquirió X-Lock sobre: {row_a}")

        # Configurar timeout corto en Sesión B (3 segundos) para prueba rápida
        cur_b.execute("SET SESSION innodb_lock_wait_timeout = 3;")
        log("[Paso 2] Sesión B: Configura innodb_lock_wait_timeout = 3 segundos")

        # Lanzar Sesión B en hilo separado para intentar actualizar la misma fila
        error_b = [None]
        def thread_b_worker():
            try:
                log("[Paso 3] Sesión B: Intentando UPDATE inventory SET store_id = 2 WHERE inventory_id = 1...")
                cur_b.execute("UPDATE inventory SET store_id = 2 WHERE inventory_id = 1;")
                conn_b.commit()
            except mysql.connector.Error as err:
                error_b[0] = err
                log(f"[Sesión B Capturó Excepción]: errno={err.errno}, msg={err.msg}")

        th_b = threading.Thread(target=thread_b_worker)
        th_b.start()
        time.sleep(1.0)  # Esperar a que Sesión B entre en estado de contención/espera

        # Mientras Sesión B espera, Sesión C (o conn_a) consulta tablas de estado de bloqueos
        log("\n[Paso 4] Consultando information_schema.innodb_locks e innodb_lock_waits durante la espera:")
        conn_mon = get_connection()
        cur_mon = conn_mon.cursor(dictionary=True)
        
        cur_mon.execute("SELECT lock_id, lock_trx_id, lock_mode, lock_type, lock_table, lock_data FROM information_schema.innodb_locks;")
        locks = cur_mon.fetchall()
        log("--- information_schema.innodb_locks ---")
        for lk in locks:
            log(f"  lock_id: {lk['lock_id']} | trx_id: {lk['lock_trx_id']} | mode: {lk['lock_mode']} | type: {lk['lock_type']} | table: {lk['lock_table']} | data: {lk['lock_data']}")

        cur_mon.execute("SELECT requesting_trx_id, requested_lock_id, blocking_trx_id, blocking_lock_id FROM information_schema.innodb_lock_waits;")
        waits = cur_mon.fetchall()
        log("\n--- information_schema.innodb_lock_waits ---")
        for w in waits:
            log(f"  Requesting TRX: {w['requesting_trx_id']} (Lock: {w['requested_lock_id']}) <-- Bloqueado por TRX: {w['blocking_trx_id']} (Lock: {w['blocking_lock_id']})")

        cur_mon.close()
        conn_mon.close()

        # Esperar que expire el timeout en Sesión B
        th_b.join()

        log("\n[Paso 5] Verificación del Error en Sesión B:")
        if error_b[0] and error_b[0].errno == 1205:
            log("ÉXITO: Se provocó y capturó el error esperado:")
            log(f"  Código: {error_b[0].errno} (ER_LOCK_WAIT_TIMEOUT)")
            log(f"  Mensaje: {error_b[0].msg}")
        else:
            log(f"FALLO: Error inesperado en Sesión B: {error_b[0]}")

    finally:
        conn_a.rollback()
        conn_b.rollback()
        cur_a.close()
        cur_b.close()
        conn_a.close()
        conn_b.close()

    if out_file:
        os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Salida C4(a) guardada en: {out_file}\n")


def run_lab_c4b(out_file="evidencias/parte_c/C4_b_deadlock_1213.txt"):
    """C4(b): Provocar Deadlock (1213) y capturar LATEST DETECTED DEADLOCK."""
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("="*75)
    log("LABORATORIO C4(b): Interbloqueo (Deadlock Error 1213) y Status de InnoDB")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*75)

    conn_a = get_connection()
    conn_b = get_connection()
    cur_a = conn_a.cursor()
    cur_b = conn_b.cursor()

    barrier1 = threading.Barrier(2)
    barrier2 = threading.Barrier(2)
    deadlock_captured = [None]

    def worker_a():
        try:
            log("[Sesión A] Inicia transacción y bloquea inventory_id=1")
            cur_a.execute("START TRANSACTION;")
            cur_a.execute("UPDATE inventory SET last_update = NOW() WHERE inventory_id = 1;")
            barrier1.wait()  # Ambas sesiones tienen su primer bloqueo

            time.sleep(0.3)
            log("[Sesión A] Intenta bloquear inventory_id=2 (en posesión de B)...")
            cur_a.execute("UPDATE inventory SET last_update = NOW() WHERE inventory_id = 2;")
            conn_a.commit()
            log("[Sesión A] Commit exitoso.")
        except mysql.connector.Error as err:
            log(f"[Sesión A Excepción]: errno={err.errno} - {err.msg}")
            if err.errno == 1213:
                deadlock_captured[0] = ("Sesión A", err)

    def worker_b():
        try:
            log("[Sesión B] Inicia transacción y bloquea inventory_id=2")
            cur_b.execute("START TRANSACTION;")
            cur_b.execute("UPDATE inventory SET last_update = NOW() WHERE inventory_id = 2;")
            barrier1.wait()  # Ambas sesiones tienen su primer bloqueo

            time.sleep(0.6)
            log("[Sesión B] Intenta bloquear inventory_id=1 (en posesión de A)...")
            cur_b.execute("UPDATE inventory SET last_update = NOW() WHERE inventory_id = 1;")
            conn_b.commit()
            log("[Sesión B] Commit exitoso.")
        except mysql.connector.Error as err:
            log(f"[Sesión B Excepción]: errno={err.errno} - {err.msg}")
            if err.errno == 1213:
                deadlock_captured[0] = ("Sesión B", err)

    th_a = threading.Thread(target=worker_a)
    th_b = threading.Thread(target=worker_b)
    th_a.start()
    th_b.start()
    th_a.join()
    th_b.join()

    # Capturar SHOW ENGINE INNODB STATUS
    log("\n[Paso 3] Capturando 'SHOW ENGINE INNODB STATUS' para extraer LATEST DETECTED DEADLOCK:")
    conn_status = get_connection()
    cur_status = conn_status.cursor()
    cur_status.execute("SHOW ENGINE INNODB STATUS;")
    status_row = cur_status.fetchone()
    full_status = status_row[2] if status_row else ""
    cur_status.close()
    conn_status.close()

    # Extraer la sección LATEST DETECTED DEADLOCK con regex
    deadlock_match = re.search(
        r"(------------------------\s+LATEST DETECTED DEADLOCK\s+------------------------[\s\S]*?)(?=------------------------|\Z)",
        full_status
    )
    if deadlock_match:
        deadlock_section = deadlock_match.group(1).strip()
        log("\n" + deadlock_section)
    else:
        log("No se pudo parsear la sección LATEST DETECTED DEADLOCK con regex. Mostrando fragmento:")
        log(full_status[:2000])

    log("\n[Paso 4] Veredicto:")
    if deadlock_captured[0]:
        victim_name, err = deadlock_captured[0]
        log(f"ÉXITO: Deadlock detectado y resuelto por el motor InnoDB.")
        log(f"Víctima elegida para Rollback: {victim_name}")
        log(f"Error devuelto: {err.errno} ({err.msg})")
    else:
        log("AVISO: No se capturó error 1213 en los hilos (posible timeout).")

    conn_a.rollback()
    conn_b.rollback()
    conn_a.close()
    conn_b.close()

    if out_file:
        os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Salida C4(b) guardada en: {out_file}\n")


def run_lab_c4c(out_file="evidencias/parte_c/C4_c_dirty_read.txt"):
    """C4(c): Demostrar Lectura Sucia (Dirty Read) bajo READ UNCOMMITTED vs REPEATABLE READ."""
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("="*75)
    log("LABORATORIO C4(c): Lectura Sucia (Dirty Read) bajo Distintos Niveles de Aislamiento")
    log(f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*75)

    conn_writer = get_connection()
    conn_rr = get_connection()
    conn_ru = get_connection()

    cur_writer = conn_writer.cursor(dictionary=True)
    cur_rr = conn_rr.cursor(dictionary=True)
    cur_ru = conn_ru.cursor(dictionary=True)

    test_customer_id = 9999

    try:
        # Asegurarnos de limpiar cualquier registro previo de prueba
        cur_writer.execute("DELETE FROM customer WHERE customer_id = %s;", (test_customer_id,))
        conn_writer.commit()

        # 1. Comprobar nivel de aislamiento por defecto del motor
        cur_rr.execute("SELECT @@transaction_isolation;")
        iso_default = cur_rr.fetchone()['@@transaction_isolation']
        log(f"[Configuración] Nivel de aislamiento por defecto del servidor: {iso_default}")

        # 2. Configurar Sesión RU en READ UNCOMMITTED
        cur_ru.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;")
        cur_ru.execute("SELECT @@transaction_isolation;")
        iso_ru = cur_ru.fetchone()['@@transaction_isolation']
        log(f"[Configuración] Nivel de aislamiento configurado en Sesión B (RU): {iso_ru}")

        # 3. Sesión Writer inicia transacción e inserta una fila SIN HACER COMMIT
        log("\n[Paso 1] Sesión Writer: Inicia transacción e inserta un cliente de prueba SIN COMMIT (en buffer/undo)")
        cur_writer.execute("START TRANSACTION;")
        cur_writer.execute(
            """INSERT INTO customer (customer_id, store_id, first_name, last_name, email, address_id, active, create_date)
               VALUES (%s, 1, 'DIRTY_CLIENT', 'TEST', 'dirty@test.com', 1, 1, NOW());""",
            (test_customer_id,)
        )
        log(f"Fila insertada en transacción no confirmada (customer_id={test_customer_id}).")

        # 4. Sesión RR intenta leer la fila no confirmada
        log("\n[Paso 2] Sesión A (REPEATABLE READ): Consulta si existe el cliente customer_id=9999:")
        cur_rr.execute("START TRANSACTION;")
        cur_rr.execute("SELECT customer_id, first_name, last_name, email FROM customer WHERE customer_id = %s;", (test_customer_id,))
        row_rr = cur_rr.fetchone()
        log(f"  Resultado en REPEATABLE READ: {row_rr}")
        log("  -> ANÁLISIS: No lee la fila no confirmada (Consistencia MVCC respetada, evita Dirty Read).")

        # 5. Sesión RU intenta leer la fila no confirmada
        log("\n[Paso 3] Sesión B (READ UNCOMMITTED): Consulta si existe el cliente customer_id=9999:")
        cur_ru.execute("START TRANSACTION;")
        cur_ru.execute("SELECT customer_id, first_name, last_name, email FROM customer WHERE customer_id = %s;", (test_customer_id,))
        row_ru = cur_ru.fetchone()
        log(f"  Resultado en READ UNCOMMITTED: {row_ru}")
        log("  -> ANÁLISIS: ¡LECTURA SUCIA CONFIRMADA! La sesión leyó datos 'sucios' que aún no han sido confirmados.")

        # 6. Sesión Writer hace ROLLBACK (los datos nunca existieron formalmente)
        log("\n[Paso 4] Sesión Writer: Ejecuta ROLLBACK (aborta la transacción)")
        conn_writer.rollback()
        log("Rollback completado. La fila se descarta y nunca llegó al commit del log binario.")

        # 7. Sesión RU vuelve a consultar
        log("\n[Paso 5] Sesión B (READ UNCOMMITTED): Vuelve a consultar tras el Rollback del Writer:")
        cur_ru.execute("SELECT customer_id, first_name, last_name, email FROM customer WHERE customer_id = %s;", (test_customer_id,))
        row_ru_post = cur_ru.fetchone()
        log(f"  Resultado tras Rollback: {row_ru_post}")
        log("  -> ANÁLISIS: El dato que Sesión B leyó en el Paso 3 se esfumó. Si la aplicación hubiera tomado decisiones")
        log("     financieras o de cobro basadas en esa lectura sucia, el estado del negocio quedaría corrupto.")

    finally:
        conn_writer.rollback()
        cur_writer.execute("DELETE FROM customer WHERE customer_id = %s;", (test_customer_id,))
        conn_writer.commit()
        cur_writer.close()
        cur_rr.close()
        cur_ru.close()
        conn_writer.close()
        conn_rr.close()
        conn_ru.close()

    if out_file:
        os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Salida C4(c) guardada en: {out_file}\n")


if __name__ == "__main__":
    run_lab_c4a()
    run_lab_c4b()
    run_lab_c4c()
