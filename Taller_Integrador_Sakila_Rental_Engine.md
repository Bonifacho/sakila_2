# Universidad de Cundinamarca · Programación y Administración de Bases de Datos
**Taller Integrador Sakila · Página 1 de 10**

---

# TALLER INTEGRADOR
## Auditoría y Refactorización del “Sakila Rental Engine”
*Conectividad con pool, transacciones ACID, concurrencia, optimización con índices, API REST segura y arquitectura híbrida SQL + NoSQL*

| Asignatura | Programación y Administración de Bases de Datos |
| :--- | :--- |
| **Docente** | Jesús David Villalba Góngora |
| **Programa y nivel** | Ingeniería de Software · Sexto semestre · Nivel intermedio–avanzado |
| **Bases de datos** | Sakila Sample Database (MySQL 8.0 o superior) y MongoDB (parte híbrida) |
| **Lenguaje backend** | Python 3.10+ (Flask) |
| **Modalidad y duración** | Individual · 2 semanas (aprox. 20 horas de trabajo) |
| **Valor** | 5.0 puntos (sustentación 3.0 · desarrollo 1.0 · evidencias 1.0) |

---

## 1. Objetivo y resultados de aprendizaje

Auditar, diagnosticar y refactorizar un microservicio heredado de alquiler de películas, aplicando conectividad backend con pool de conexiones, transacciones ACID, control de concurrencia, optimización con índices, buenas prácticas de API REST y seguridad defensiva, y diseñando una extensión híbrida SQL + NoSQL.

Al finalizar el taller el estudiante será capaz de:
* Diagnosticar defectos de arquitectura, seguridad y rendimiento en código existente, y justificarlos con el fundamento teórico correspondiente.
* Configurar la conexión entre Python y MySQL con un pool único y ejecutar operaciones multi-tabla de forma atómica.
* Reproducir, explicar y resolver anomalías de concurrencia: condiciones de carrera, lecturas sucias, bloqueos y deadlocks.
* Leer planes de ejecución y diseñar índices con criterio, midiendo también su costo de escritura.
* Decidir qué datos viven en MySQL y cuáles en MongoDB, definiendo la fuente de verdad y la estrategia de sincronización.

---

## 2. Contexto del caso

La franquicia Sakila heredó de un contratista externo el microservicio “Sakila Rental Engine”, que registra los alquileres y cobros de sus sucursales. Desde que abrió la tercera sucursal se han reportado estos incidentes:
* La misma copia de una película fue entregada a dos clientes al mismo tiempo.
* Existen alquileres sin pago registrado y descuadres de caja al cierre del día.
* El reporte diario de pagos tarda cada vez más a medida que crece la tabla.
* Un auditor externo vio nombres de tablas y restricciones en un mensaje de error del navegador y logró listar pagos manipulando un parámetro de la URL.

Su equipo fue contratado para auditar el código, documentar los hallazgos y entregar una versión refactorizada. Además, la gerencia quiere evaluar un catálogo de búsqueda en MongoDB. No se aceptan parches: cada defecto debe corregirse en su causa raíz.

---

## 3. Preparación del entorno

* **MySQL 8.0.18 o superior** (necesario para `EXPLAIN ANALYZE`) y MySQL Workbench. Cargue el archivo adjunto `sakila-schema.sql` y después `sakila-data.sql` del paquete oficial de Sakila. Verifique con `SELECT COUNT(*) FROM payment;` (debe devolver alrededor de 16.000 filas).
* **Python 3.10 o superior** con Flask, un conector a MySQL (`mysql-connector-python`, o SQLAlchemy con PyMySQL; la elección es libre, pero debe justificarla), `pymongo` y `requests`.
* **MongoDB 6.0 o superior** (instalación local o un clúster gratuito en Atlas) y `mongosh` o Compass.
* **Git:** antes de modificar nada, haga un commit con el código heredado tal cual. Lo usará para comparar y para la prueba de concurrencia.
* Trabaje siempre sobre su copia local de la base de datos. Si algún experimento altera los datos, restáurela con los scripts originales.

### Tabla de volumen
Ejecute este script una sola vez para crear `payment_big`, una tabla de aproximadamente un millón de pagos que se usará en las partes A y D:

```sql
USE sakila;

CREATE TABLE payment_big (
  payment_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id SMALLINT UNSIGNED NOT NULL,
  staff_id TINYINT UNSIGNED NOT NULL,
  rental_id INT DEFAULT NULL,
  amount DECIMAL(5,2) NOT NULL,
  payment_date DATETIME NOT NULL,
  PRIMARY KEY (payment_id)
) ENGINE=InnoDB;

-- Multiplica los pagos reales x60 desplazando la fecha (aprox. 1 millón de filas)
INSERT INTO payment_big (customer_id, staff_id, rental_id, amount, payment_date)
SELECT p.customer_id, p.staff_id, p.rental_id, p.amount,
       p.payment_date + INTERVAL (a.d + 10 * b.d) DAY
FROM payment p
CROSS JOIN (SELECT 0 d UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
            UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8
            UNION ALL SELECT 9) a
CROSS JOIN (SELECT 0 d UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
            UNION ALL SELECT 5) b;
```

---

## 4. Código heredado

Guarde este archivo como `legacy_app.py` y ejecútelo tal cual. No lo corrija todavía: primero debe auditarlo.

```python
# legacy_app.py - Sakila Rental Engine v0.1 (código heredado)
from flask import Flask, request, jsonify
import mysql.connector

app = Flask(__name__)

def get_conn():
    return mysql.connector.connect(host="localhost", user="root",
                                   password="root", database="sakila")

@app.route("/api/checkout", methods=["GET"])
def checkout():
    customer_id = request.args.get("customer_id")
    inventory_id = request.args.get("inventory_id")
    staff_id = request.args.get("staff_id")
    amount = request.args.get("amount")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT inventory_in_stock(" + inventory_id + ")")
        if cur.fetchone()[0]:
            cur.execute("INSERT INTO rental (rental_date, inventory_id, "
                        "customer_id, staff_id) VALUES (NOW(), " + inventory_id +
                        ", " + customer_id + ", " + staff_id + ")")
            conn.commit()
            rental_id = cur.lastrowid
            cur.execute(f"INSERT INTO payment (customer_id, staff_id, rental_id, "
                        f"amount, payment_date) VALUES ({customer_id}, {staff_id}, "
                        f"{rental_id}, {amount}, NOW())")
            conn.commit()
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Película no disponible"})
    except mysql.connector.Error as err:
        return jsonify({"status": "error", "message": err.msg, "sqlstate": err.sqlstate})

@app.route("/api/rentals/delete", methods=["GET"])
def delete_rental():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM rental WHERE rental_id = " + request.args.get("id"))
    conn.commit()
    return jsonify({"status": "success"})

@app.route("/api/payments/report")
def report():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    day = request.args.get("day")
    cur.execute("SELECT * FROM payment_big "
                "WHERE DATE(payment_date) = '" + day + "'")
    return jsonify(cur.fetchall())

if __name__ == "__main__":
    app.run(debug=True)
```

---

## 5. Actividades

### Parte A. Auditoría del código heredado

**A1.** Ejecute la aplicación y reproduzca estos cuatro incidentes, guardando la petición usada y una captura de cada resultado:
* **(a) Inyección SQL.** Consulte `/api/payments/report?day=x' OR '1'='1' LIMIT 5 -- -`. El `LIMIT 5` evita saturar su equipo, porque sin él se devolverían casi un millón de filas.
* **(b) Information Exposure.** Lance un checkout con un `customer_id` inexistente (por ejemplo, `99999`) y analice qué revela la respuesta.
* **(c) Alquiler huérfano.** Lance un checkout válido con `amount=99999` y consulte `rental` y `payment`. ¿Qué quedó guardado y por qué?
* **(d) Handshake por petición.** Registre `SHOW GLOBAL STATUS LIKE 'Connections';` antes y después de 50 llamadas a `/api/payments/report?day=2005-07-09`. ¿Cuánto creció el contador?

**A2.** Complete una tabla de hallazgos con un mínimo de 12 defectos distintos, indicando las líneas del código, la categoría (ACID, red y escalabilidad, REST, seguridad, concurrencia o rendimiento), el riesgo y la corrección con su concepto teórico.

| # | Línea(s) | Defecto detectado | Categoría | Riesgo o impacto | Corrección y concepto |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| … | | | | | |

**A3.** Señale los tres hallazgos más críticos y justifique la prioridad considerando impacto y probabilidad.

---

### Parte B. Refactorización: conectividad, transacción, REST y seguridad

**B1.** Estructure el proyecto de forma modular (rutas, acceso a datos, lógica de negocio y configuración en archivos separados). Las credenciales deben leerse de variables de entorno.

**B2.** Implemente un pool de conexiones creado una única vez por proceso (instancia única o módulo compartido). Justifique el tamaño del pool y garantice que cada conexión se devuelva, incluso cuando ocurre una excepción.

**B3.** Implemente `POST /api/checkout` con cuerpo JSON (`customer_id`, `inventory_id`, `staff_id`). El monto ya no lo envía el cliente: el servidor lo calcula a partir de la tarifa de la película asociada al inventario. El alquiler y el cobro deben ejecutarse en una sola transacción, con `ROLLBACK` ante cualquier error y un único `COMMIT`.

**B4.** Diseñe respuestas JSON uniformes con códigos HTTP coherentes (éxito, datos inválidos, recurso inexistente, copia no disponible y error interno). Registre el error real en un log del servidor y devuelva al cliente únicamente un mensaje genérico.

**B5.** Parametrice todas las consultas, valide tipos y rangos de cada entrada, y cree un usuario MySQL dedicado (`sakila_app`) con los privilegios mínimos necesarios en lugar de usar `root`.

**B6.** Reemplace el endpoint de borrado heredado. Analice qué ocurre con `payment.rental_id` cuando se elimina un alquiler (revise la restricción de clave foránea en el esquema) y proponga una alternativa con la semántica REST adecuada, justificando su decisión.

> **Evidencia requerida:** captura de la petición exitosa y de un `SELECT` en Workbench que muestre el registro de `rental` y su `payment` asociado con el mismo `rental_id` y fecha casi idéntica; captura de un fallo provocado donde no queda ningún alquiler a medias; salida de `SHOW GRANTS FOR 'sakila_app'@'localhost';`; y el contador `Connections` antes y después de 200 peticiones concurrentes a un endpoint de lectura.

---

### Parte C. Control de concurrencia

**C1.** Elija una copia disponible (verifique con `SELECT inventory_in_stock(<id>);`). Escriba `race_test.py`, que lance al menos 10 hilos sincronizados (por ejemplo, con una barrera) que intenten alquilar esa misma copia con clientes distintos, usando la versión de su servicio sin control de concurrencia. Después ejecute `SELECT COUNT(*) FROM rental WHERE inventory_id = <id> AND return_date IS NULL;` y documente el resultado.

**C2.** Explique la anomalía con una línea de tiempo (quién lee, quién escribe y cuándo) y nómbrela con la terminología vista en clase. ¿Por qué la transacción de la Parte B por sí sola no la evita bajo el nivel de aislamiento por defecto?

**C3.** Implemente una solución que garantice que solo un hilo obtenga la copia y que los demás reciban la respuesta de “no disponible”. Justifique su elección frente a al menos otra alternativa y repita la prueba.

**C4.** Con dos sesiones de Workbench realice el laboratorio de bloqueos:
* **(a)** Mantenga un bloqueo abierto en la sesión A, observe la espera en la sesión B y capture la información de bloqueos desde `performance_schema` (o `sys.innodb_lock_waits`). Provoque el error 1205 (lock wait timeout).
* **(b)** Provoque un deadlock haciendo que dos sesiones actualicen dos mismas filas en orden opuesto (por ejemplo, dos filas de `inventory`). Capture la sección `LATEST DETECTED DEADLOCK` de `SHOW ENGINE INNODB STATUS`.
* **(c)** Demuestre una lectura sucia con `READ UNCOMMITTED` y compruebe que no ocurre con el nivel por defecto (`SELECT @@transaction_isolation;`).

**C5.** Agregue a su servicio un reintento acotado (máximo 3 intentos con espera creciente) ante los errores 1213 y 1205, sin reintentar errores que no sean transitorios.

> **Evidencia requerida:** salida de `race_test.py` antes y después de la corrección, y las capturas de C4.

---

### Parte D. Optimización e indexación

Trabaje sobre `payment_big`, que solo tiene la llave primaria. Use estas dos consultas:

* **Q1. Reporte diario heredado:**
  ```sql
  SELECT * FROM payment_big WHERE DATE(payment_date) = '2005-07-09';
  ```

* **Q2. Los diez clientes con mayor recaudo de un mes:**
  ```sql
  SELECT customer_id, SUM(amount) AS total
  FROM payment_big
  WHERE payment_date >= '2005-07-01' AND payment_date < '2005-08-01'
  GROUP BY customer_id
  ORDER BY total DESC
  LIMIT 10;
  ```

**D1.** Ejecute `EXPLAIN ANALYZE` sobre Q1 y Q2 sin índices adicionales y registre `type`, `key`, `rows` y el tiempo real.

**D2.** Reescriba Q1 para que sea sargable, pida solo las columnas necesarias e incluya paginación. Diseñe los índices para Q1 y Q2. Evalúe al menos dos alternativas de índice para Q2 (por ejemplo, distinto orden de columnas, con y sin cobertura) y demuestre con `EXPLAIN ANALYZE` cuál es mejor y por qué.

**D3.** Mida el costo de escritura: inserte 50.000 filas (con `INSERT ... SELECT` desde la propia tabla y `LIMIT`) antes y después de crear sus índices, y compare los tiempos.

**D4.** Complete la tabla de resultados y responda: ¿por qué `DATE(payment_date)` impide usar un índice sobre la columna?, ¿qué es un índice cubriente y lo logró en su solución?, ¿en qué situaciones no indexaría?

| Consulta | type | key | rows | Tiempo (ms) | Índice creado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Q1 original** | | | | | |
| **Q1 optimizada** | | | | | |
| **Q2 sin índice** | | | | | |
| **Q2 con tu índice** | | | | | |

*Las cifras dependen de su equipo; lo evaluado es el análisis, no el valor absoluto.*

---

### Parte E. Extensión híbrida con MongoDB

**E1.** Escriba `etl_catalog.py`, que lea desde MySQL las tablas `film`, `language`, `category`, `film_category`, `actor` y `film_actor`, y cargue en MongoDB (base `sakila_catalog`, colección `films`) un documento por película con categorías y actores embebidos. Justifique qué embebió y qué referenciaría. Documento de referencia (ilustrativo):

```json
{
  "_id": 1,
  "title": "ACADEMY DINOSAUR",
  "language": "English",
  "rental_rate": 0.99,
  "length": 86,
  "rating": "PG",
  "categories": ["Documentary"],
  "actors": [ { "actor_id": 1, "name": "PENELOPE GUINESS" } ],
  "special_features": ["Deleted Scenes", "Behind the Scenes"]
}
```

**E2.** Implemente `GET /api/catalog` con filtros opcionales (`category`, `actor`, `max_rate`) y paginación. Cree el índice de MongoDB adecuado y demuestre con `explain("executionStats")` el cambio de `COLLSCAN` a `IXSCAN`.

**E3.** Defina la fuente de verdad: el checkout debe tomar la tarifa desde MySQL, y MongoDB funciona solo como modelo de consulta. Implemente `sync_film(film_id)` y demuestre el desfase: cambie `film.rental_rate` en MySQL, consulte el catálogo (dato desactualizado), sincronice y vuelva a consultar.

**E4.** Verifique que el checkout sigue funcionando con MongoDB apagado. En el informe responda, en máximo cinco líneas cada una: ¿por qué no mover `rental` y `payment` a MongoDB?, ¿qué estrategia de sincronización usaría en producción (manual, periódica o por eventos) y qué riesgos acepta?

> **Evidencia requerida:** captura de un documento en Compass o mongosh, salida de `explain` antes y después del índice, y la demostración del desfase y la sincronización.

---

## 6. Checklist de diseño (checklist teórico)

Estos son los criterios que se usarán para guiar la sustentación. Marque cada eje solo cuando pueda demostrarlo y explicarlo sin leer su código.

| Eje temático | Lo que debes poder demostrar y defender | Listo |
| :--- | :--- | :---: |
| **1. Conectividad (ORM / pool)** | El pool se crea una sola vez por proceso; parámetros justificados (tamaño, desbordamiento, timeout); las conexiones siempre se devuelven; credenciales fuera del código. | [ ] |
| **2. Transacciones ACID** | Rental y payment dentro de una única transacción; ROLLBACK ante cualquier excepción; un solo COMMIT; sabes explicar cómo se cumple cada propiedad A-C-I-D en tu solución. | [ ] |
| **3. Control de concurrencia** | Anomalía identificada y nombrada; bloqueo o estrategia que la elimina; nivel de aislamiento justificado; reintento ante deadlock (error 1213) y lock wait timeout (error 1205). | [ ] |
| **4. API REST e Information Hiding** | Verbos con semántica correcta; códigos HTTP coherentes; JSON uniforme de éxito y error; el error nativo de MySQL solo aparece en el log del servidor. | [ ] |
| **5. Seguridad defensiva** | 100 % de las consultas parametrizadas; validación de tipos y rangos; monto calculado en el servidor; usuario MySQL con privilegios mínimos. | [ ] |
| **6. Optimización e indexación** | EXPLAIN ANALYZE antes y después; condiciones sargables; índice compuesto con orden de columnas justificado; sin SELECT *; paginación. | [ ] |
| **7. Arquitectura híbrida** | Modelo documental justificado (embeber o referenciar); fuente de verdad definida; estrategia de sincronización; el checkout no depende de MongoDB. | [ ] |

---

## 7. Entregables

* **Código fuente** en un archivo `.zip` (`Apellido_Nombre_TallerSakila.zip`) con la estructura modular, `requirements.txt`, un `README.md` con las instrucciones de ejecución, los scripts SQL (usuario, índices) y los scripts `race_test.py` y `etl_catalog.py`.
* **Informe en PDF o Word** (máximo 8 páginas) con la tabla de hallazgos, las respuestas conceptuales y todas las evidencias de las partes A a E, cada una rotulada.
* **Pantallazo obligatorio** de una ejecución exitosa del checkout junto con el `SELECT` en MySQL Workbench que demuestra los registros en `rental` y `payment`.
* **Sustentación individual** (Code Defense) en la fecha indicada por el docente.

> [!IMPORTANT]
> ### Requisito habilitante
> Para tener derecho a la sustentación, el sistema debe estar funcional y completo, con los pantallazos adjuntos. Sin este requisito no se asigna calificación a los criterios 2 y 3.

---

## 9. Rúbrica de evaluación

La calificación final es la suma de los tres criterios (escala de 0.0 a 5.0).

| Criterio de evaluación | Ponderación | Descripción y niveles de desempeño |
| :--- | :---: | :--- |
| **1. Sustentación técnica y dominio (Code Defense)** | **3.0 puntos**<br>(60 %) | **Excelente (3.0):** Explica con claridad la arquitectura de su solución basándose en el checklist teórico. Responde las preguntas de defensa sin dudar, razona y modifica su código en vivo, y demuestra dominio del entorno MySQL y del backend.<br><br>**Bueno (2.4):** Explica el código y demuestra apropiación, pero duda levemente en terminología técnica específica (aislamiento, bloqueos, planes de ejecución) durante las preguntas.<br><br>**Aceptable (1.8):** Conoce la estructura general de su solución, pero responde con imprecisiones sobre cómo opera el motor (pool, bloqueos, índices) o sobre el porqué de sus decisiones.<br><br>**Insuficiente (0.0 – 1.5):** No logra explicar fragmentos de su propio código, no domina la teoría subyacente o no sabe cómo interactúa su solución con la base de datos. No presentarse a la sustentación equivale a 0.0.<br><br>*Condición estricta: si la nota en este criterio es Insuficiente, se asume dependencia total de herramientas de IA y la nota máxima global del taller queda limitada a 2.0, aunque el código de los criterios 2 y 3 funcione a la perfección.* |
| **2. Desarrollo, lógica y solución del caso** | **1.0 punto**<br>(20 %) | **Excelente (1.0):** Encuentra los errores y los refactoriza aplicando la solución óptima esperada (transacciones, pool, REST, parametrización, control de concurrencia, índices y estrategia híbrida) en las cinco partes del taller.<br><br>**Bueno (0.8):** Resuelve correctamente las partes A a D; la parte híbrida (E) es parcial o carece de estrategia de sincronización.<br><br>**Parcial (0.5):** El programa funciona a nivel básico, pero la arquitectura no es la más eficiente, mantiene malas prácticas secundarias o no resuelve el problema de raíz (por ejemplo, la condición de carrera persiste).<br><br>**Insuficiente (0.0 – 0.3):** La solución no funciona, no implementa ROLLBACK o mantiene concatenación directa de variables en cualquier consulta SQL (esto último anula la entrega). |
| **3. Buenas prácticas y evidencias** | **1.0 punto**<br>(20 %) | **Excelente (1.0):** El código es limpio, estandarizado (PEP 8) y modular, y el informe incluye la evidencia de diagnóstico (tabla de hallazgos, pruebas de concurrencia y EXPLAIN antes y después) junto con el pantallazo obligatorio que demuestra la ejecución exitosa interactuando con MySQL.<br><br>**Bueno (0.8):** El código tiene formato ordenado y adjunta las evidencias, pero algunas son parciales o faltan comentarios clave.<br><br>**Parcial (0.5):** Omite convenciones de limpieza de código, entrega un diagnóstico incompleto, o el pantallazo de validación no es del todo legible o concluyente.<br><br>**Insuficiente (0.0 – 0.3):** Código desordenado y sin evidencias de diagnóstico, o ausencia del pantallazo de validación con MySQL. |

---

> [!CAUTION]
> ### Reglas de penalización
> * **Anti-copia con IA:** puede consultar documentación y herramientas de apoyo, pero la nota depende de que pueda explicar y modificar su propio código. Un resultado Insuficiente en el criterio 1 limita la nota máxima global a 2.0, independientemente de que el código funcione.
> * **Inyección SQL:** cualquier concatenación directa de variables en una consulta SQL anula la entrega.

