"""Acceso a la base de datos: pool de conexiones único por proceso.

- El pool se crea UNA sola vez (patrón singleton a nivel de módulo, protegido con lock).
- `get_connection()` es un context manager: la conexión SIEMPRE vuelve al pool,
  incluso si ocurre una excepción (bloque finally).
- mysql-connector lanza PoolError inmediatamente si el pool está agotado; para que las
  peticiones esperen en cola (como el `pool_timeout` de SQLAlchemy) se usa un semáforo
  acotado al tamaño del pool.
"""
import logging
import threading
from contextlib import contextmanager

from mysql.connector import pooling

from config import Config

logger = logging.getLogger(__name__)

_pool = None
_pool_lock = threading.Lock()
_slots = threading.BoundedSemaphore(Config.DB_POOL_SIZE)


class PoolTimeoutError(Exception):
    """No se obtuvo una conexión libre dentro de DB_POOL_TIMEOUT."""


def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:  # doble verificación: solo un hilo crea el pool
                _pool = pooling.MySQLConnectionPool(
                    pool_name=Config.DB_POOL_NAME,
                    pool_size=Config.DB_POOL_SIZE,
                    pool_reset_session=True,
                    host=Config.DB_HOST,
                    port=Config.DB_PORT,
                    user=Config.DB_USER,
                    password=Config.DB_PASSWORD,
                    database=Config.DB_NAME,
                    autocommit=False,
                    charset="utf8mb4",
                )
                logger.info("Pool '%s' creado con %d conexiones",
                            Config.DB_POOL_NAME, Config.DB_POOL_SIZE)
    return _pool


@contextmanager
def get_connection():
    if not _slots.acquire(timeout=Config.DB_POOL_TIMEOUT):
        raise PoolTimeoutError("Pool de conexiones agotado")
    conn = None
    try:
        conn = get_pool().get_connection()
        yield conn
    finally:
        if conn is not None:
            try:
                if conn.in_transaction:
                    conn.rollback()  # nunca devolver al pool una transacción abierta
            finally:
                conn.close()  # en una conexión de pool, close() la DEVUELVE al pool
        _slots.release()

