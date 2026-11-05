# Documento de Entrega y Defensa Técnica: Parte C - Control de Concurrencia

**Curso:** Sistemas de Base de Datos - 6.° Semestre  
**Universidad de Cundinamarca**  
**Docente:** Jesús David Villalba Góngora  
**Proyecto:** Sakila Rental Engine  

---

## 1. Resumen Ejecutivo de la Fase

La **Parte C** aborda la dimensión crítica de **concurrencia y aislamiento transaccional** en el motor relacional InnoDB (MariaDB 11.4 / MySQL 8.0). Durante la auditoría del sistema heredado y las primeras pruebas de carga, se identificó que la mera inclusión de transacciones atómicas (`START TRANSACTION ... COMMIT`) es **insuficiente** para prevenir la sobreventa o doble asignación de copias físicas cuando múltiples hilos intentan reservar el mismo recurso al mismo milisegundo.

En esta fase se diseñó un banco de pruebas multihilo (`scripts/race_test.py`), se reprodujo empíricamente la anomalía de carrera, se implementó el protocolo de **Bloqueo Pesimista a Nivel de Fila con Lecturas Bloqueantes (Locking Reads)**, se ejecutó un laboratorio completo de estados de contención y aislamiento (errores 1205, 1213 y Dirty Read), y se dotó a la capa de servicios de una política de resiliencia mediante un **decorador de reintento acotado con retroceso exponencial (Exponential Backoff con Jitter)**.

---

## 2. Actividad C1: Reproducción Empírica de la Condición de Carrera

### 2.1. Metodología de la Prueba (`scripts/race_test.py`)
Para garantizar que todos los hilos ataquen el servidor de forma estrictamente simultánea y no secuencial, se utilizó la primitiva de sincronización `threading.Barrier(10)` de Python. 
- Diez hilos clientes concurrentes (`customer_id` del 1 al 10) se inicializan y esperan en la barrera.
- Al llegar el último hilo, la barrera se libera al unísono, disparando 10 peticiones `POST /api/checkout` hacia `http://127.0.0.1:5000/api/checkout` compitiendo por la misma copia física de inventario (`inventory_id = 1`).
- La disponibilidad previa de la copia fue verificada mediante `SELECT inventory_in_stock(1);` (devolviendo `1`).

### 2.2. Evidencia C1 (ANTES): Sin Control de Concurrencia
*Ejecutado sobre el servicio sin bloqueo exclusivo:*

```text
===========================================================================
RACE TEST: Prueba de Concurrencia con 10 Hilos Sincronizados
Fecha: 2026-11-04 23:06:35
Copia de inventario seleccionada: inventory_id = 1
===========================================================================
Alquileres no devueltos iniciales para inventory_id=1: 0

Disparando 10 hilos simultáneos hacia POST http://127.0.0.1:5000/api/checkout...

--- Respuestas HTTP de los hilos ---
Hilo #00 (Cliente 01): HTTP 201 (1.077s) -> {'rental_id': 16063, 'payment_id': 16057, 'customer_id': 1, 'inventory_id': 1, 'staff_id': 1, 'amount': '0.99'}
Hilo #01 (Cliente 02): HTTP 201 (1.060s) -> {'rental_id': 16060, 'payment_id': 16055, 'customer_id': 2, 'inventory_id': 1, 'staff_id': 1, 'amount': '0.99'}
Hilo #02 (Cliente 03): HTTP 409 (1.078s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #03 (Cliente 04): HTTP 201 (1.085s) -> {'rental_id': 16061, 'payment_id': 16059, 'customer_id': 4, 'inventory_id': 1, 'staff_id': 1, 'amount': '0.99'}
Hilo #04 (Cliente 05): HTTP 409 (1.089s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #05 (Cliente 06): HTTP 201 (1.076s) -> {'rental_id': 16064, 'payment_id': 16058, 'customer_id': 6, 'inventory_id': 1, 'staff_id': 1, 'amount': '0.99'}
Hilo #06 (Cliente 07): HTTP 409 (1.084s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #07 (Cliente 08): HTTP 201 (1.070s) -> {'rental_id': 16062, 'payment_id': 16056, 'customer_id': 8, 'inventory_id': 1, 'staff_id': 1, 'amount': '0.99'}
Hilo #08 (Cliente 09): HTTP 409 (1.089s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #09 (Cliente 10): HTTP 201 (1.055s) -> {'rental_id': 16059, 'payment_id': 16054, 'customer_id': 10, 'inventory_id': 1, 'staff_id': 1, 'amount': '0.99'}

Resumen de códigos HTTP recibidos: {201: 6, 409: 4}

--- Comprobación en Base de Datos ---
SQL> SELECT COUNT(*) FROM rental WHERE inventory_id = 1 AND return_date IS NULL;
Resultado COUNT(*): 6

Registros activos encontrados en rental para inventory_id=1:
  rental_id=16059 | rental_date=2026-11-04 23:06:36 | customer_id=10 | staff_id=1
  rental_id=16060 | rental_date=2026-11-04 23:06:36 | customer_id=2 | staff_id=1
  rental_id=16061 | rental_date=2026-11-04 23:06:36 | customer_id=4 | staff_id=1
  rental_id=16062 | rental_date=2026-11-04 23:06:36 | customer_id=8 | staff_id=1
  rental_id=16063 | rental_date=2026-11-04 23:06:36 | customer_id=1 | staff_id=1
  rental_id=16064 | rental_date=2026-11-04 23:06:36 | customer_id=6 | staff_id=1

===========================================================================
VEREDICTO: ¡CONDICIÓN DE CARRERA DETECTADA! (ANOMALÍA)
Se entregó la MISMA copia física (inventory_id=1) a 6 clientes diferentes al mismo tiempo.
Total clientes con HTTP 201 Created: 6
===========================================================================
```

### 2.3. Evidencia C1 (DESPUÉS): Con Bloqueo Pesimista y Current Read
*Ejecutado tras implementar `SELECT ... FOR UPDATE` en inventario y alquiler:*

```text
===========================================================================
RACE TEST: Prueba de Concurrencia con 10 Hilos Sincronizados
Fecha: 2026-11-05 00:06:19
Copia de inventario seleccionada: inventory_id = 1
===========================================================================
Alquileres no devueltos iniciales para inventory_id=1: 0

Disparando 10 hilos simultáneos hacia POST http://127.0.0.1:5000/api/checkout...

--- Respuestas HTTP de los hilos ---
Hilo #00 (Cliente 01): HTTP 409 (1.416s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #01 (Cliente 02): HTTP 409 (1.409s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #02 (Cliente 03): HTTP 409 (1.429s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #03 (Cliente 04): HTTP 409 (1.424s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #04 (Cliente 05): HTTP 409 (1.418s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #05 (Cliente 06): HTTP 409 (1.436s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #06 (Cliente 07): HTTP 409 (1.439s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #07 (Cliente 08): HTTP 409 (1.423s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #08 (Cliente 09): HTTP 409 (1.433s) -> {'code': 'NOT_AVAILABLE', 'message': 'La copia solicitada no está disponible'}
Hilo #09 (Cliente 10): HTTP 201 (1.407s) -> {'rental_id': 16075, 'payment_id': 16070, 'customer_id': 10, 'inventory_id': 1, 'staff_id': 1, 'amount': '0.99'}

Resumen de códigos HTTP recibidos: {409: 9, 201: 1}

--- Comprobación en Base de Datos ---
SQL> SELECT COUNT(*) FROM rental WHERE inventory_id = 1 AND return_date IS NULL;
Resultado COUNT(*): 1

Registros activos encontrados en rental para inventory_id=1:
  rental_id=16075 | rental_date=2026-11-05 00:06:20 | customer_id=10 | staff_id=1

===========================================================================
VEREDICTO: ¡EXCLUSIÓN MUTUA EXITOSA!
Exactamente 1 hilo obtuvo la copia (HTTP 201) y los demás 9 fueron rechazados.
===========================================================================
```

---

## 3. Actividad C2: Análisis Teórico y Cronológico de la Anomalía

### 3.1. Nomenclatura Formal
En la literatura clásica de bases de datos (Gray & Reuter, Berenson et al.), esta anomalía se clasifica como:
1. **Asignación Múltiple Concurrente (Concurrent Double-Booking / Double Allocation)**.
2. Variante de **Write Skew / Lost Update**: Dos o más transacciones concurrentes leen un predicado superpuesto (`inventory_in_stock(1) == 1`), evalúan de forma independiente que se cumple la regla de negocio, y ejecutan escrituras concurrentes que violan la invariante global del dominio físico (un único ejemplar en DVD no puede ser poseído por dos personas a la vez).

### 3.2. Línea de Tiempo de Ejecución Concurrente

| Tiempo | Transacción A (Cliente 1) | Transacción B (Cliente 2) | Estado en Base de Datos (`rental`) |
| :--- | :--- | :--- | :--- |
| **$t_0$** | Inicia Transacción (`START TRANSACTION`) | Inicia Transacción (`START TRANSACTION`) | Alquileres activos para `inv_id=1`: **0** |
| **$t_1$** | `SELECT COUNT(*) ... WHERE return_date IS NULL;` $\to$ Retorna **0** (Disponible). | — | Transacciones independientes. |
| **$t_2$** | — | `SELECT COUNT(*) ... WHERE return_date IS NULL;` $\to$ Retorna **0** (Disponible). | Transacciones independientes. |
| **$t_3$** | `INSERT INTO rental ...` | — | Fila insertada en buffer de A (no confirmada aún). |
| **$t_4$** | — | `INSERT INTO rental ...` | Fila insertada en buffer de B (no confirmada aún). |
| **$t_5$** | `COMMIT;` (Se confirma alquiler A) | — | Alquileres confirmados: **1** |
| **$t_6$** | — | `COMMIT;` (Se confirma alquiler B) | Alquileres confirmados: **2** (**¡SOBREVENTA!**) |

### 3.3. ¿Por qué la transacción atómica de la Parte B no la evita bajo `REPEATABLE READ`?
El nivel de aislamiento estándar de InnoDB en MariaDB/MySQL es `REPEATABLE READ`. Bajo este nivel, el motor utiliza **MVCC (Multi-Version Concurrency Control)** implementando **Lecturas Consistentes No Bloqueantes (Snapshot Reads)**:

1. **Snapshot Read:** Cuando una transacción ejecuta un `SELECT` ordinario, InnoDB genera una vista de lectura (*Read View*) o snapshot con el estado de los datos confirmados exactamente en el instante del primer `SELECT` de dicha transacción.
2. Si la Transacción B ejecuta su `SELECT` antes de que la Transacción A haga `COMMIT`, la Transacción B **no ve** la fila insertada por A (respetando el aislamiento y evitando lecturas sucias).
3. Aun si la Transacción B se ejecutara milisegundos después de que la Transacción A hubiera confirmado, si la Transacción B ya había abierto su snapshot previamente, su `SELECT` ordinario continuará leyendo la versión histórica donde el inventario aparecía con 0 alquileres.
4. Las lecturas ordinarias no adquieren ningún tipo de cerrojo (ni Shared `S` ni Exclusive `X`). En consecuencia, ambas transacciones pasan la validación de negocio y ejecutan su respectivo `INSERT`. Para InnoDB, no hay conflicto de clave primaria ni violación de unicidad técnica, pues cada `rental` genera un `rental_id` auto-incremental distinto.

**Conclusión Teórica:** Una transacción por sí sola garantiza **Atomicidad** e **Integridad**, pero no garantiza **Serializabilidad** frente a condiciones de carrera de lectura-comprobación-escritura (*Check-Then-Act*) sin un mecanismo explícito de bloqueo.

---

## 4. Actividad C3: Implementación y Justificación de la Solución

### 4.1. Solución Implementada: Bloqueo Pesimista de Fila (Pessimistic Locking)
La solución adoptada en `app/repositories/inventory_repo.py` y `app/services/rental_service.py` consta de dos pilares dentro de la misma transacción:

```python
# 1. Bloqueo exclusivo de la fila física de inventario (X-Lock)
cur.execute("SELECT inventory_id FROM inventory WHERE inventory_id = %s FOR UPDATE;", (inventory_id,))

# 2. Comprobación de disponibilidad mediante Locking Read (Current Read)
cur.execute("SELECT COUNT(*) FROM rental WHERE inventory_id = %s AND return_date IS NULL FOR UPDATE;", (inventory_id,))
```

#### ¿Por qué es fundamental el `FOR UPDATE` en la segunda consulta?
Bajo `REPEATABLE READ`, si un segundo hilo adquiere el cerrojo del inventario luego de que el primer hilo confirma su checkout, un `SELECT COUNT(*)` convencional seguiría leyendo el snapshot inicial desactualizado. Al agregar `FOR UPDATE` (o `LOCK IN SHARE MODE`), InnoDB cambia de **Snapshot Read** a **Current Read (Lectura Actualizada)**, forzando la lectura de la última versión confirmada en el motor y bloqueando los registros encontrados.

### 4.2. Matriz Comparativa Frente a Otras Alternativas

| Enfoque | Mecanismo | Ventajas | Desventajas | Decisión |
| :--- | :--- | :--- | :--- | :--- |
| **Bloqueo Pesimista de Fila (`FOR UPDATE`)** | Cerrojo exclusivo a nivel de registro (`Record X-Lock`) sobre la clave primaria de `inventory`. | • Granularidad mínima: solo bloquea el DVD solicitado.<br>• Clientes alquilando otros inventarios no sufren contención.<br>• Sin cambios de esquema. | Si las transacciones tardan demasiado, las esperas saturan las conexiones. | **ELEGIDA:** Equilibrio óptimo entre rigor ACID, simplicidad y rendimiento. |
| **Control Optimista (OCC / Versioning / CAS)** | Agregar columna `version INT` o `status` en `inventory` y hacer `UPDATE inventory SET version=version+1 WHERE inventory_id=%s AND version=@v;`. | • No retiene bloqueos durante la lectura.<br>• Excelente rendimiento en escenarios de baja contención (pocas colisiones). | • Requiere alterar el esquema relacional (`ALTER TABLE`).<br>• En alta contención genera tormentas de reintentos infructuosos. | Descartada por restricción de esquema del taller. |
| **Bloqueo de Tabla (`LOCK TABLES inventory WRITE`)** | Cerrojo exclusivo sobre toda la tabla `inventory`. | • Simplicidad extrema. | • Destruye el rendimiento y la escalabilidad.<br>• Ningún cliente puede alquilar ninguna película simultáneamente. | Descartada categóricamente por mala práctica. |
| **Nivel de Aislamiento `SERIALIZABLE`** | `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;` | • Convierte todos los `SELECT` implícitamente en `LOCK IN SHARE MODE`. | • Incrementa masivamente la tasa de Deadlocks (dos lectores compartidos intentando escalar a escritura). | Descartada: el bloqueo pesimista explícito es más predecible y eficiente. |

---

## 5. Actividad C4: Laboratorio de Bloqueos y Aislamiento

El script `scripts/lab_concurrency.py` implementó de manera programática y reproducible los tres escenarios del laboratorio de bloqueos:

### 5.1. C4(a): Lock Wait Timeout (Error 1205) e Inspección de Bloqueos
- **Procedimiento:** La Sesión A inicia transacción y adquiere un `X-Lock` sobre `inventory_id=1` mediante `SELECT ... FOR UPDATE`. La Sesión B configura `SET SESSION innodb_lock_wait_timeout = 3;` e intenta ejecutar `UPDATE inventory SET store_id = 2 WHERE inventory_id = 1;`.
- **Inspección en `information_schema` durante la contención:**
  ```text
  --- information_schema.innodb_locks ---
    lock_id: 2472:156:6:2 | trx_id: 2472 | mode: X | type: RECORD | table: `sakila`.`inventory` | data: 1
    lock_id: 2471:156:6:2 | trx_id: 2471 | mode: X | type: RECORD | table: `sakila`.`inventory` | data: 1

  --- information_schema.innodb_lock_waits ---
    Requesting TRX: 2472 (Lock: 2472:156:6:2) <-- Bloqueado por TRX: 2471 (Lock: 2471:156:6:2)
  ```
- **Resultado en Sesión B tras 3 segundos:**
  ```text
  [Sesión B Capturó Excepción]: errno=1205, msg=Lock wait timeout exceeded; try restarting transaction
  ```

### 5.2. C4(b): Deadlock (Error 1213) y Extracción de `LATEST DETECTED DEADLOCK`
- **Procedimiento:** Se coordinaron dos transacciones concurrentes actualizando registros en orden inverso:
  - Sesión A: Actualiza `inventory_id = 1` y luego intenta actualizar `inventory_id = 2`.
  - Sesión B: Actualiza `inventory_id = 2` y luego intenta actualizar `inventory_id = 1`.
- **Detección Automática por InnoDB:** El motor detecta el ciclo en el grafo de espera (*Wait-For Graph*), elige a la Sesión B como víctima por tener menor costo de deshecho (*undo log*), y aborta inmediatamente su transacción con error `1213`.
- **Fragmento de `SHOW ENGINE INNODB STATUS`:**
  ```text
  ------------------------
  LATEST DETECTED DEADLOCK
  ------------------------
  2026-11-05 00:09:53 0x32f0
  *** (1) TRANSACTION:
  TRANSACTION 2474, ACTIVE 1 sec starting index read
  mysql tables in use 3, locked 3
  LOCK WAIT 3 lock struct(s), heap size 1128, 2 row lock(s), undo log entries 1
  MariaDB thread id 193, OS thread handle 13040, query id 4547 localhost 127.0.0.1 root Updating
  UPDATE inventory SET last_update = NOW() WHERE inventory_id = 1
  *** WAITING FOR THIS LOCK TO BE GRANTED:
  RECORD LOCKS space id 156 page no 6 n bits 600 index PRIMARY of table `sakila`.`inventory` trx id 2474 lock_mode X locks rec but not gap waiting
  ...
  *** (2) TRANSACTION:
  TRANSACTION 2473, ACTIVE 1 sec starting index read
  mysql tables in use 3, locked 3
  LOCK WAIT 3 lock struct(s), heap size 1128, 2 row lock(s), undo log entries 1
  MariaDB thread id 192, OS thread handle 7512, query id 4546 localhost 127.0.0.1 root Updating
  UPDATE inventory SET last_update = NOW() WHERE inventory_id = 2
  *** WAITING FOR THIS LOCK TO BE GRANTED:
  RECORD LOCKS space id 156 page no 6 n bits 600 index PRIMARY of table `sakila`.`inventory` trx id 2473 lock_mode X locks rec but not gap waiting
  ...
  *** WE ROLL BACK TRANSACTION (2)
  ```

### 5.3. C4(c): Demostración de Lectura Sucia (Dirty Read)
- **Procedimiento:** Una sesión escritora inserta un cliente de prueba (`customer_id=9999`) sin confirmar (`START TRANSACTION; INSERT ...`).
- **Observación comparativa:**
  - **Sesión en `REPEATABLE READ`:** Consulta `customer_id=9999` $\to$ Retorna `None`. No se observan datos no confirmados (Aislamiento preservado).
  - **Sesión en `READ UNCOMMITTED`:** Consulta `customer_id=9999` $\to$ Retorna `{'customer_id': 9999, 'first_name': 'DIRTY_CLIENT'}` (**Lectura Sucia exitosa**).
- **Efecto posterior al `ROLLBACK` de la sesión escritora:** La sesión en `READ UNCOMMITTED` vuelve a consultar y el registro ha desaparecido. Si un proceso de negocio hubiera tomado decisiones con base en esa lectura sucia, el sistema habría operado sobre datos fantasma inexistentes.

---

## 6. Actividad C5: Política de Reintento Acotado (Exponential Backoff + Jitter)

En sistemas transaccionales con alta concurrencia, los errores 1213 (Deadlock) y 1205 (Lock Wait Timeout) son **transitorios**: reintentar la transacción inmediatamente o tras una breve pausa suele resultar en éxito una vez que la transacción competidora libera sus recursos.

En `app/retry.py` se implementó el decorador `@retry_transient_locks`:

```python
TRANSIENT_MYSQL_ERRORS = {
    1213,  # ER_LOCK_DEADLOCK
    1205,  # ER_LOCK_WAIT_TIMEOUT
}

def retry_transient_locks(max_attempts=3, base_delay=0.05, max_delay=0.5):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            while True:
                try:
                    return func(*args, **kwargs)
                except mysql.connector.Error as err:
                    errno = getattr(err, "errno", None)
                    if errno in TRANSIENT_MYSQL_ERRORS and attempt < max_attempts:
                        # Exponential backoff con Jitter aleatorio
                        delay = min(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.03), max_delay)
                        logger.warning("Error transitorio (errno=%s). Reintentando %d/%d tras %.3fs...", errno, attempt, max_attempts, delay)
                        time.sleep(delay)
                        attempt += 1
                    else:
                        raise
        return wrapper
    return decorator
```

### Características Técnicas del Decorador:
1. **Discriminación Estricta:** Reintenta únicamente si `err.errno in {1213, 1205}`. Errores de sintaxis (1064), tablas inexistentes (1146), claves duplicadas (1062) o claves foráneas (1452) son permanentes y se propagan inmediatamente sin reintentos inútiles.
2. **Exponential Backoff:** El retardo se duplica en cada intento fallido ($t_i = t_{base} \cdot 2^{i-1}$), evitando colisiones reiteradas con la misma transacción competidora.
3. **Jitter Aleatorio:** Se añade una pequeña variación estocástica (`random.uniform(0, 0.03)`). Si múltiples hilos colisionan simultáneamente, el jitter desincroniza sus reintentos, desarticulando el fenómeno de "tormenta de reintentos" (*retry storm*).
4. **Validación Automática:** Probado y verificado al 100% en `scripts/verify_part_c.py` (6 pruebas unitarias exitosas).

---

## 7. Verificación Integral y Estado de Entregables de la Parte C

| Requisito | Estado | Ubicación de Código / Evidencia |
| :--- | :---: | :--- |
| **C1. `race_test.py` multihilo (10 hilos sincronizados)** | Cumplido al 100% | `scripts/race_test.py`<br>`evidencias/parte_c/C1_race_test_antes.txt`<br>`evidencias/parte_c/C1_race_test_despues.txt` |
| **C2. Cronología y análisis de MVCC / Snapshot Read** | Cumplido al 100% | Sección 3 de este documento |
| **C3. Solución `SELECT ... FOR UPDATE` + Current Read** | Cumplido al 100% | `app/repositories/inventory_repo.py`<br>`app/services/rental_service.py` |
| **C4(a). Lock Wait Timeout (1205) e `innodb_locks`** | Cumplido al 100% | `scripts/lab_concurrency.py`<br>`evidencias/parte_c/C4_a_lock_wait_timeout_1205.txt` |
| **C4(b). Deadlock (1213) y `INNODB STATUS`** | Cumplido al 100% | `scripts/lab_concurrency.py`<br>`evidencias/parte_c/C4_b_deadlock_1213.txt` |
| **C4(c). Dirty Read (`READ UNCOMMITTED` vs `RR`)** | Cumplido al 100% | `scripts/lab_concurrency.py`<br>`evidencias/parte_c/C4_c_dirty_read.txt` |
| **C5. Retry acotado con Exponential Backoff y Jitter** | Cumplido al 100% | `app/retry.py`<br>`scripts/verify_part_c.py` |
