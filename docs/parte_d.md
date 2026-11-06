# Documento de Entrega y Defensa Técnica: Parte D - Optimización e Indexación

**Curso:** Sistemas de Base de Datos - 6.° Semestre  
**Universidad de Cundinamarca**  
**Docente:** Jesús David Villalba Góngora  
**Proyecto:** Sakila Rental Engine  

---

## 1. Resumen Ejecutivo de la Fase

La **Parte D** aborda la optimización del rendimiento en motores relacionales (InnoDB) a través del análisis de planes de ejecución (`ANALYZE / EXPLAIN`), el diseño de consultas **sargables** (*Search Argument Able*), la arquitectura de **índices compuestos cubrientes** (*Covering Indexes*), y la cuantificación empírica de la **sobrecarga de escritura** (*Write Overhead*).

Todas las pruebas se ejecutaron sobre la tabla `payment_big`, poblada con **962.760 registros reales** en el motor MariaDB 11.4.10 / InnoDB, simulando un entorno de producción de alta volumetría.

---

## 2. Actividad D1: Medición de Línea Base (Baseline sin Índices Secundarios)

En el estado inicial, `payment_big` cuenta únicamente con su clave primaria (`PRIMARY KEY (payment_id)`). No existe ningún índice secundario sobre `payment_date`, `customer_id` ni `amount`.

### 2.1. Q1 Original: Reporte Diario Heredado
```sql
SELECT * FROM payment_big WHERE DATE(payment_date) = '2005-07-09';
```
* **Plan de Ejecución (`ANALYZE SELECT`):**
  * `type`: **`ALL`** (Full Table Scan / Escaneo secuencial de toda la tabla).
  * `key`: **`NULL`** (Ningún índice utilizado).
  * `rows` (estimadas): **960.572**.
  * `r_rows` (filas reales examinadas): **962.760,00** (el 100% de la tabla).
  * `Extra`: `Using where`.
* **Métricas de Rendimiento:**
  * **Tiempo de ejecución (Mejor):** **269,35 ms**
  * **Tiempo promedio (3 ejecuciones):** **289,88 ms**

### 2.2. Q2 Sin Índice: Los Diez Clientes con Mayor Recaudo de un Mes
```sql
SELECT customer_id, SUM(amount) AS total
FROM payment_big
WHERE payment_date >= '2005-07-01' AND payment_date < '2005-08-01'
GROUP BY customer_id
ORDER BY total DESC
LIMIT 10;
```
* **Plan de Ejecución (`ANALYZE SELECT`):**
  * `type`: **`ALL`** (Full Table Scan).
  * `key`: **`NULL`**.
  * `rows`: **960.572** (examinó 962.760 filas reales).
  * `Extra`: `Using where; Using temporary; Using filesort`.
* **Métricas de Rendimiento:**
  * **Tiempo de ejecución (Mejor):** **264,43 ms**
  * **Tiempo promedio (3 ejecuciones):** **268,18 ms**
  * **Diagnóstico:** El motor tuvo que escanear la tabla entera, volcar filas filtradas a una tabla temporal en memoria/disco (`Using temporary`) para agrupar por `customer_id`, y realizar un ordenamiento externo (`Using filesort`) para el `ORDER BY total DESC`.

---

## 3. Actividad D2: Optimización de Q1 y Evaluación de Alternativas para Q2

### 3.1. Reescritura y Optimización de Q1 (Sargabilidad, Proyección y Paginación)
La consulta original presentaba tres defectos graves de diseño:
1. **`SELECT *`:** Recupera columnas que el cliente no necesita (`rental_id`, `staff_id`), desperdiciando ancho de banda de red y memoria de buffers, impidiendo además cualquier optimización por índice cubriente.
2. **`DATE(payment_date)`:** Función envolvente que destruye la sargabilidad de la consulta.
3. **Sin Paginación:** Puede retornar miles de registros de golpe, arriesgando el agotamiento de memoria del cliente o del servidor de aplicaciones.

#### Consulta Reescrita (Sargable):
```sql
SELECT payment_id, customer_id, staff_id, amount, payment_date
FROM payment_big
WHERE payment_date >= '2005-07-09 00:00:00' AND payment_date < '2005-07-10 00:00:00'
ORDER BY payment_date
LIMIT 50 OFFSET 0;
```

#### Creación del Índice para Q1:
```sql
CREATE INDEX idx_payment_date ON payment_big (payment_date);
```

#### Comparativa de Q1 con y sin Índice:
* **Q1 Optimizada CON `idx_payment_date`:**
  * `type`: **`range`** (B-Tree Range Scan).
  * `key`: **`idx_payment_date`**.
  * `rows` estimadas: **5.484** (poda del 99,4% de la tabla).
  * `r_rows` (filas leídas realmente): **50,00** (gracias al `LIMIT 50`).
  * `Extra`: `Using index condition`.
  * **Tiempo de ejecución:** **2,32 ms** (frente a 269,35 ms originales).
  * **Factor de aceleración:** **¡116 veces más rápida (reducción del 99,1% del tiempo de CPU)!**

#### Demostración de No Sargabilidad:
Si se ejecuta la consulta original con `DATE(payment_date)` existiendo ya el índice `idx_payment_date`:
* El motor se ve forzado a ignorar la búsqueda binaria directa por valor en el árbol B-Tree porque no busca un valor de fecha puntual, sino el resultado de transformar cada fila con la función `DATE()`. Debe escanear todas las entradas para evaluar la función una a una.

---

### 3.2. Evaluación de Alternativas de Índice para Q2

Para la consulta Q2 se probaron empíricamente tres estrategias de indexación:

#### Alternativa 1: Índice Simple No Cubriente `idx_payment_date (payment_date)`
* **Idea:** Filtrar rápidamente por el rango de fechas del mes.
* **Resultado:**
  * `type`: `range`, `key`: `idx_payment_date`, `rows`: 416.568.
  * `Extra`: `Using index condition; Using temporary; Using filesort`.
  * **Tiempo:** **633,16 ms** (**¡Más lento que el Full Table Scan original de 264 ms!**).
* **¿Por qué empeoró? (Concepto Clave para Sustentación):**  
  El filtro del mes abarca aproximadamente 400.000 filas. Al usar un índice no cubriente, por **cada una de las 400.000 entradas** encontradas en el índice secundario, el motor debe hacer un **Bookmark Lookup** (acceso aleatorio a la página de datos del índice primario agrupado) para recuperar `customer_id` y `amount`. El costo de 400.000 accesos aleatorios a disco/buffer es enormemente superior al de leer la tabla de forma secuencial continua (*Full Table Scan*).

#### Alternativa 2: Índice Invertido `idx_cust_date (customer_id, payment_date)`
* **Idea:** Ayudar al `GROUP BY customer_id`.
* **Resultado:**
  * **Tiempo:** **631,87 ms**.
* **¿Por qué falló?**  
  En un árbol B-Tree compuesto, el motor solo puede podar rangos usando la columna líder (más a la izquierda). Al tener `customer_id` como primer campo y no haber filtro `WHERE customer_id = ...`, el motor no puede podar el rango de fechas `payment_date >= ... AND payment_date < ...` eficientemente.

#### Alternativa 3 (Ganadora): Índice Compuesto Cubriente `idx_covering_q2 (payment_date, customer_id, amount)`
* **Diseño Arquitectónico:**
  1. `payment_date` (1.ª columna): Prefijo líder para podar el rango del mes en el B-Tree.
  2. `customer_id` (2.ª columna): Presente en el índice para resolver el `GROUP BY`.
  3. `amount` (3.ª columna): Presente en las hojas del índice para calcular `SUM(amount)`.
* **Resultado (`ANALYZE SELECT`):**
  * `type`: **`range`**.
  * `key`: **`idx_covering_q2`**.
  * `rows`: **400.644**.
  * `Extra`: **`Using where; Using index; Using temporary; Using filesort`**.
  * **Tiempo de ejecución:** **106,42 ms** (promedio: 118,01 ms).
* **Confirmación de Índice Cubriente:**  
  La presencia de la directiva **`Using index`** en el campo `Extra` certifica formalmente que el motor resolvió la consulta **leyendo única y exclusivamente las páginas del índice B-Tree en memoria**, sin realizar ni un solo Bookmark Lookup a las páginas de la tabla física.
* **Aceleración:** **6 veces más rápido** que el índice simple (106 ms vs 633 ms) y **2,5 veces más rápido** que el escaneo completo sin índices (106 ms vs 264 ms).

---

## 4. Actividad D3: Medición de la Sobrecarga de Escritura (Write Overhead)

Todo índice es una estructura de datos B-Tree adicional que debe mantenerse sincronizada en disco y memoria ante cada operación DML (`INSERT`, `UPDATE`, `DELETE`).

Para cuantificar este costo, se ejecutó una inserción masiva de **50.000 filas** mediante:
```sql
INSERT INTO payment_big (customer_id, staff_id, rental_id, amount, payment_date)
SELECT customer_id, staff_id, rental_id, amount, payment_date 
FROM payment_big LIMIT 50000;
```

### Resultados de la Medición:
* **Tiempo de inserción SIN índices secundarios (Solo Primary Key):** **166,16 ms**
* **Tiempo de inserción CON índices secundarios (`idx_payment_date` + `idx_covering_q2`):** **788,46 ms**
* **Sobrecarga de Escritura (*Write Overhead*):** **+622,30 ms (+374,5%)**

### Justificación Teórica del Costo de Escritura:
1. **Actualización de Árboles B-Tree:** En la tabla base, el motor solo inserta en el índice primario agrupado (`PRIMARY`). Con los dos índices activos, cada una de las 50.000 inserciones debe navegar y actualizar **dos árboles B-Tree secundarios adicionales**.
2. **División de Páginas (*Page Splits*):** Cuando las páginas de 16 KB de InnoDB se llenan, el motor debe dividirlas en dos páginas al 50%, reacomodando punteros de nodos padre y hermanos.
3. **Escrituras en Redo Log y Change Buffer:** Se triplica la cantidad de entradas generadas en el log de transacciones (*WAL - Write-Ahead Logging*).

---

## 5. Actividad D4: Tabla Consolidada de Resultados y Respuestas Conceptuales

### 5.1. Tabla Comparativa de Rendimiento

| Consulta | type | key | rows | Tiempo (ms) | Índice creado |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Q1 original** | `ALL` | `NULL` | 960.572 | **269,35** | Ninguno |
| **Q1 optimizada** | `range` | `idx_payment_date` | 5.484 | **2,32** | `idx_payment_date(payment_date)` |
| **Q2 sin índice** | `ALL` | `NULL` | 960.572 | **264,43** | Ninguno |
| **Q2 con tu índice** | `range` | `idx_covering_q2` | 400.644 | **106,42** | `idx_covering_q2(payment_date, customer_id, amount)` |

---

### 5.2. Respuestas a las Preguntas Conceptuales

#### 1. ¿Por qué `DATE(payment_date)` impide usar un índice sobre la columna?
Un índice B-Tree almacena los valores de la columna ordenados de forma lexicográfica/cronológica para permitir búsquedas binarias directas en tiempo $O(\log N)$.  
Cuando se envuelve la columna en una función determinista como `DATE(payment_date)`, la condición de búsqueda deja de ser **sargable** (*Search Argument Able*). El optimizador de consultas no puede anticipar el resultado de la función sobre cada valor del árbol sin ejecutarla; por ende, queda imposibilitado de utilizar la estructura ordenada del B-Tree para saltar a un rango de claves. El motor se ve obligado a realizar un escaneo completo (evaluando la función `DATE()` sobre las 962.760 filas una por una).  
**Solución aplicada:** Transformar la consulta en un predicado de rango directo sobre la columna desnuda:  
`payment_date >= '2005-07-09 00:00:00' AND payment_date < '2005-07-10 00:00:00'`.

#### 2. ¿Qué es un índice cubriente y lo logró en su solución?
Un **Índice Cubriente (*Covering Index*)** es un índice secundario que contiene **todas y cada una de las columnas** requeridas por una consulta SQL (tanto las columnas proyectadas en el `SELECT`, como las usadas en cláusulas `WHERE`, `JOIN`, `GROUP BY` y `ORDER BY`).  
* **¿Se logró en la solución?** **SÍ, absolutamente.**  
  Para la consulta Q2 se diseñó el índice compuesto `idx_covering_q2(payment_date, customer_id, amount)`.
* **Evidencia técnica:** En el plan de ejecución de `ANALYZE / EXPLAIN`, la columna `Extra` muestra explícitamente **`Using index`**. Esto demuestra que InnoDB no tuvo que acudir al índice primario agrupado de la tabla para buscar datos adicionales (*evitó el 100% de los Bookmark Lookups*), leyendo directamente desde los nodos hoja del índice en memoria RAM.

#### 3. ¿En qué situaciones NO indexaría?
En el diseño profesional de bases de datos, **no se debe indexar indiscriminadamente**:
1. **Columnas de baja cardinalidad (baja selectividad):** Columnas con muy pocos valores distintos (ej. género `'M'/'F'`, estados booleanos `active TINYINT(1)`). Un índice donde el 50% de las filas tienen el mismo valor es ignorado por el optimizador, ya que el costo de consultar el índice y luego hacer bookmark lookup supera al escaneo secuencial.
2. **Tablas pequeñas (Lookup Tables):** Tablas de catálogo con menos de unos pocos cientos de filas (ej. `language` o `category`). La tabla entera cabe en una o dos páginas del Buffer Pool (16 KB), por lo que un escaneo en memoria toma microsegundos y el índice solo consume espacio inútil.
3. **Tablas con alta tasa de inserción/modificación y baja lectura (Write-Heavy):** Tablas de registro de auditoría, logs de eventos o series temporales de IoT. Como se demostró en la actividad D3, cada índice secundario penalizó la velocidad de inserción en más de un **374%**.
4. **Columnas sujetas a actualización constante:** Un `UPDATE` recurrente sobre una columna indexada obliga a rebalancear el árbol B-Tree continuamente, generando contención de bloqueos (*latch contention*) y fragmentación de páginas.

---

## 6. Verificación y Archivos del Entregable

* **Script de Benchmark y Pruebas Empíricas:** [`scripts/benchmark_part_d.py`](file:///c:/Users/andre/OneDrive/Documentos/UdeC/Semestre%206/B_D/sakila2/scripts/benchmark_part_d.py)
* **Script de Verificación Automatizada (Tests):** [`scripts/verify_part_d.py`](file:///c:/Users/andre/OneDrive/Documentos/UdeC/Semestre%206/B_D/sakila2/scripts/verify_part_d.py) (4 tests unitarios pasando al 100%).
* **Script DDL de Índices:** [`sql/02_payment_big_indexes.sql`](file:///c:/Users/andre/OneDrive/Documentos/UdeC/Semestre%206/B_D/sakila2/sql/02_payment_big_indexes.sql)
* **Archivo de Evidencias Numéricas:** `evidencias/parte_d/D_benchmark_resultados.txt`
