# Parte B. Refactorización: conectividad, transacción, REST y seguridad

## B1. Estructura modular

```
config.py                      Configuración; credenciales desde variables de entorno (.env)
run.py                         Punto de entrada
app/
├── __init__.py                Application factory + logging (logs/app.log)
├── db.py                      Pool único por proceso + context manager get_connection()
├── errors.py                  Errores de negocio, JSON uniforme, Information Hiding
├── validators.py              Validación de tipos y rangos
├── routes/                    Capa HTTP (sin SQL)
│   ├── rental_routes.py       POST /api/checkout, GET /api/rentals/<id>, PATCH /api/rentals/<id>/return
│   └── report_routes.py       GET /api/payments/report
├── services/                  Lógica de negocio y transacciones
│   ├── rental_service.py
│   └── report_service.py
└── repositories/              SQL puro, 100 % parametrizado, sin commit
    ├── inventory_repo.py
    ├── rental_repo.py
    └── payment_repo.py
sql/01_create_app_user.sql     Usuario sakila_app con privilegios mínimos
```

Regla de dependencias: `routes → services → repositories → db`. Ninguna ruta ejecuta SQL y ningún repositorio hace commit: la transacción la controla el servicio.

## B2. Pool de conexiones

- **Creación única:** `app/db.py` crea un `MySQLConnectionPool` una sola vez por proceso (singleton a nivel de módulo con bloqueo de doble verificación).
- **Devolución garantizada:** `get_connection()` es un context manager. En el `finally` hace `rollback()` si quedó una transacción abierta y `close()`, que en una conexión de pool la **devuelve** al pool. Esto se cumple también cuando hay una excepción.
- **Espera en cola:** mysql-connector lanza `PoolError` en cuanto el pool se agota. Para que las peticiones esperen, se usa un semáforo acotado al tamaño del pool con `DB_POOL_TIMEOUT = 5 s`. Pasado ese tiempo se responde `503 SERVICE_BUSY`.
- **Tamaño = 10. Por qué:**
  - Las operaciones son cortas, de milisegundos. Con 3 sucursales y pocos cajeros, la concurrencia real a la BD es baja.
  - Un pool grande no acelera nada: cada conexión ocupa memoria y hilos en el servidor, y añade más contención de bloqueos.
  - 10 es muy inferior a `max_connections = 151` del servidor, así que queda margen para administración y otros procesos.
  - Se ajusta con `DB_POOL_SIZE` sin tocar código.
- **Evidencia (`evidencias/parte_b/B2_pool_connections.txt`):** 200 peticiones desde 50 hilos concurrentes. `Connections` subió en +1, y esa única conexión es la de la propia medición. El código heredado sumó **+51 con solo 50 peticiones**.

## B3. Checkout transaccional

`POST /api/checkout` con cuerpo JSON `{customer_id, inventory_id, staff_id}`:

1. `start_transaction()`
2. Valida que existan el cliente, el empleado y la copia (404 si alguno falta).
3. Lee el **monto en el servidor**: `film.rental_rate` de la película asociada a la copia. Si el cliente envía `amount`, se rechaza con 400.
4. Verifica la disponibilidad con `inventory_in_stock` (409 si no está disponible).
5. `INSERT rental` → `INSERT payment` con el `rental_id` obtenido.
6. **Un único `COMMIT`.** Cualquier excepción ejecuta `ROLLBACK` y se relanza.

**Evidencias:**
- `B3_checkout_exitoso.txt`: `rental` y `payment` con el mismo `rental_id`, la misma fecha y `amount = rental_rate`.
- `B3_fallo_provocado_rollback.txt`: se crea temporalmente un trigger que hace fallar el `INSERT` en `payment`. El servicio responde 500 genérico, el conteo de `rental` no cambia y no queda ningún alquiler a medias. El detalle técnico (`errno=1644`) solo aparece en `logs/app.log`.

> Esta versión **todavía no controla la concurrencia**. La condición de carrera se demuestra y se corrige en la Parte C.

## B4. Respuestas uniformes y códigos HTTP

| Situación | HTTP | `error.code` |
| :--- | :-: | :--- |
| Éxito al crear (checkout) | 201 | – |
| Éxito al leer o actualizar | 200 | – |
| Datos inválidos (tipo, rango, campo `amount`, fecha mal formada) | 400 | `INVALID_DATA` |
| Cliente, empleado, copia o alquiler inexistente | 404 | `NOT_FOUND` |
| Copia no disponible | 409 | `NOT_AVAILABLE` |
| Alquiler ya devuelto | 409 | `CONFLICT` |
| Pool agotado | 503 | `SERVICE_BUSY` |
| Error de BD o inesperado | 500 | `INTERNAL_ERROR` (mensaje genérico; el detalle va al log) |

Formato único: `{"success": true, "data": ...}` o `{"success": false, "error": {"code", "message"}}`.

## B5. Seguridad defensiva

- 100 % de las consultas usan marcadores `%s` con tupla de parámetros. No hay concatenación ni f-strings con datos de entrada. La única f-string SQL (`_RENTAL_COLUMNS`) es una constante del código, no una entrada del usuario.
- Se validan tipos y rangos según el esquema: `customer_id` SMALLINT (1–65535), `inventory_id` MEDIUMINT (1–16777215), `staff_id` TINYINT (1–255), fechas `YYYY-MM-DD` y paginación acotada (máx. 500).
- La aplicación se conecta con `sakila_app`, nunca con `root`. Sus permisos son solo `SELECT` en las tablas usadas, `INSERT` en `rental` y `payment`, `UPDATE` **solo de la columna** `rental.return_date` y `EXECUTE` en `inventory_in_stock`. No tiene `DELETE`, ni DDL, ni `GRANT OPTION` (`B5_show_grants.txt`).
- `debug` se desactiva por defecto (`FLASK_DEBUG`).

## B6. Reemplazo del borrado

El esquema define `fk_payment_rental ... ON DELETE SET NULL`. Si se borra un alquiler, sus pagos **no se borran**, pero quedan con `rental_id = NULL`. Hay dinero cobrado sin saber por qué alquiler, y se pierde la trazabilidad contable y de auditoría. Además, el endpoint heredado borraba con `GET` y con concatenación.

**Decisión:** en el negocio, un alquiler no "desaparece": se **devuelve**. Se reemplaza el borrado por:

```
PATCH /api/rentals/<id>/return   → registra return_date = NOW()
```

- `PATCH` es el verbo correcto porque modifica parcialmente un recurso existente.
- Si el alquiler ya fue devuelto responde 409, y 404 si no existe (`B6_devolucion.txt`).
- El histórico de `rental` y `payment` se conserva íntegro.
- `sakila_app` no tiene privilegio `DELETE`, así que el borrado físico queda impedido también a nivel de base de datos.

