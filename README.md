# Sakila Rental Engine — Refactorización Transaccional e Híbrida (MySQL + MongoDB)

**Universidad de Cundinamarca — Ingeniería de Sistemas y Computación**  
**Asignatura:** Sistemas de Base de Datos (6.° Semestre)  
**Docente:** Jesús David Villalba Góngora  

---

## 1. Descripción General de la Arquitectura

Este proyecto corresponde a la auditoría, refactorización y extensión del motor de alquileres **Sakila Rental Engine**, migrando desde un monolito heredado (`legacy_app.py`) hacia una **arquitectura en capas desacoplada y políglota (CQRS)**:

1. **Capa de Presentación / Rutas REST (`app/routes/`):**
   * Valida entradas estrictas y aplica **Information Hiding** (oculta errores nativos de MySQL/MongoDB tras códigos HTTP semánticos y respuestas JSON uniformes).
2. **Capa de Lógica de Negocio (`app/services/`):**
   * Orquesta la **transacción atómica única (`COMMIT` / `ROLLBACK`)** del checkout (`rental` + `payment`).
   * Aplica **Bloqueo Pesimista Exclusivo (`SELECT ... FOR UPDATE`)** y **Current Reads** para impedir condiciones de carrera.
   * Incluye el decorador `@retry_transient_locks` (`app/retry.py`) con **Exponential Backoff + Jitter** ante errores transitorios `1213` (Deadlock) y `1205` (Lock Wait Timeout).
3. **Capa de Acceso a Datos (`app/repositories/`):**
   * **100 % de consultas SQL parametrizadas (`%s`)** — cero concatenación de cadenas.
   * Pool de conexiones singleton (`app/db.py`) con control de concurrencia por semáforo y liberación garantizada en bloques `finally`.
   * Cliente MongoDB perezoso (`app/mongo.py`) para el catálogo documental (`sakila_catalog.films`).

---

## 2. Estructura del Proyecto

```text
sakila2/
├── app/
│   ├── __init__.py              # Application Factory y configuración de logs rotativos
│   ├── db.py                    # Pool de conexiones MySQL Singleton + Context Manager
│   ├── mongo.py                 # Cliente MongoDB Singleton (conexión perezosa y resiliente)
│   ├── errors.py                # Manejo global de excepciones e Information Hiding
│   ├── retry.py                 # Decorador de reintento exponencial (errores 1213 y 1205)
│   ├── validators.py            # Validación estricta de tipos, rangos y formatos
│   ├── repositories/
│   │   ├── inventory_repo.py    # Consultas y bloqueos FOR UPDATE sobre inventario
│   │   ├── rental_repo.py       # Inserción y devolución de alquileres
│   │   ├── payment_repo.py      # Reportes sargables y paginados de pagos
│   │   └── catalog_repo.py      # Consultas híbridas MySQL -> MongoDB
│   ├── services/
│   │   ├── rental_service.py    # Lógica transaccional ACID del checkout y devolución
│   │   ├── report_service.py    # Lógica de reportes paginados
│   │   └── catalog_service.py   # Búsqueda en catálogo MongoDB y sync_film(film_id)
│   └── routes/
│       ├── rental_routes.py     # POST /api/checkout, PATCH /api/rentals/<id>/return, GET /api/rentals/<id>
│       ├── report_routes.py     # GET /api/payments/report
│       └── catalog_routes.py    # GET /api/catalog, GET /api/catalog/<id>, POST /api/catalog/sync/<id>
├── sql/
│   ├── 01_create_app_user.sql   # Creación del usuario de privilegios mínimos `sakila_app`
│   └── 02_payment_big_indexes.sql # Índices sargables y cubrientes sobre `payment_big`
├── scripts/
│   ├── setup_payment_big.py     # Generación de ~1M de filas en `payment_big`
│   ├── audit_part_a.py          # Reproducción automatizada de los 4 incidentes de la Parte A
│   ├── race_test.py             # Prueba de concurrencia con 10 hilos sincronizados (Barrier)
│   ├── lab_concurrency.py       # Laboratorio de bloqueos (1205, 1213 Deadlock, Dirty Read)
│   ├── benchmark_part_d.py      # Benchmark EXPLAIN/ANALYZE de Q1, Q2 y sobrecarga de escritura
│   ├── etl_catalog.py           # ETL MySQL -> MongoDB (`sakila_catalog.films`) y `sync_film`
│   └── lab_part_e.py            # Laboratorio COLLSCAN -> IXSCAN, desfase y resiliencia
├── config.py                    # Lectura de variables de entorno (.env)
├── run.py                       # Punto de entrada del servidor Flask refactorizado
├── race_test.py                 # Wrapper raíz para ejecución directa de prueba de carrera
├── etl_catalog.py               # Wrapper raíz para ejecución directa del ETL
└── requirements.txt             # Dependencias del proyecto
```

---

## 3. Requisitos e Instalación

1. **Crear y activar entorno virtual:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configurar variables de entorno (`.env`):**
   Copie `.env.example` a `.env` y ajuste las credenciales de su instancia local de MySQL/MariaDB y MongoDB:
   ```ini
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_NAME=sakila
   DB_USER=root
   DB_PASSWORD=tu_password_root
   APP_DB_USER=sakila_app
   APP_DB_PASSWORD=tu_password_sakila_app
   DB_POOL_SIZE=10
   DB_POOL_TIMEOUT=5
   MONGO_URI=mongodb://127.0.0.1:27017
   MONGO_DB_NAME=sakila_catalog
   ```

3. **Inicializar usuario de mínimos privilegios e índices SQL:**
   ```powershell
   python scripts/run_sql.py sql/01_create_app_user.sql
   python scripts/run_sql.py sql/02_payment_big_indexes.sql
   ```

---

## 4. Ejecución del Servidor y Scripts del Taller

### Iniciar el Servidor Refactorizado
```powershell
python run.py
```

### Ejecutar el ETL hacia MongoDB (Parte E)
```powershell
python etl_catalog.py
# Para sincronizar una sola película desde MySQL hacia MongoDB:
python etl_catalog.py --sync-id 1
```

### Ejecutar la Prueba de Condición de Carrera (Parte C)
```powershell
python race_test.py --threads 10 --inventory-id 1
# Para limpiar los registros de prueba creados:
python race_test.py --cleanup --inventory-id 1
```

### Ejecutar la Suite de Verificación Automatizada (Partes B, C, D y E)
```powershell
python scripts/verify_part_b.py
python scripts/verify_part_c.py
python scripts/verify_part_d.py
python scripts/verify_part_e.py
```

---

## 5. Endpoints Principales de la API REST

| Método | Ruta | Descripción | Fuente de Datos |
| :---: | :--- | :--- | :--- |
| `POST` | `/api/checkout` | Crea un alquiler y su pago en una **única transacción ACID** con bloqueo pesimista (`FOR UPDATE`). Calcula el monto en el servidor desde `film.rental_rate`. | MySQL (Fuente de Verdad) |
| `PATCH` | `/api/rentals/<id>/return` | Registra la devolución (`return_date = NOW()`) sin borrar el historial ni dejar pagos huérfanos. | MySQL |
| `GET` | `/api/rentals/<id>` | Consulta el detalle de un alquiler por su identificador. | MySQL |
| `GET` | `/api/payments/report` | Reporte diario de pagos **sargable** y paginado (`?day=YYYY-MM-DD&page=1&page_size=100`). | MySQL |
| `GET` | `/api/catalog` | Búsqueda en catálogo documental con filtros opcionales (`?category=Action&actor=PENELOPE+GUINESS&max_rate=2.99&page=1&page_size=20`). | MongoDB (Modelo de Consulta) |
| `POST` | `/api/catalog/sync/<id>` | Dispara `sync_film(film_id)` para actualizar el documento en MongoDB desde MySQL. | MySQL $\to$ MongoDB |

