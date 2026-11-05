"""Decorador de reintento acotado para errores transitorios de concurrencia de InnoDB.
Reintenta exclusivamente ante:
  - Error 1213: Deadlock (ER_LOCK_DEADLOCK)
  - Error 1205: Lock wait timeout (ER_LOCK_WAIT_TIMEOUT)
Aplica espera exponencial (exponential backoff) con jitter para mitigar tormentas de reintento.
"""
import time
import random
import logging
import functools
import mysql.connector

logger = logging.getLogger(__name__)

TRANSIENT_MYSQL_ERRORS = {
    1213,  # ER_LOCK_DEADLOCK: Deadlock found when trying to get lock; try restarting transaction
    1205,  # ER_LOCK_WAIT_TIMEOUT: Lock wait timeout exceeded; try restarting transaction
}

def retry_transient_locks(max_attempts=3, base_delay=0.05, max_delay=0.5):
    """Decorador para reintentar funciones transaccionales ante errores 1213 y 1205."""
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
                        delay = min(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.03), max_delay)
                        logger.warning(
                            "Error transitorio de bloqueo (errno=%s: %s). Reintentando intento %d/%d tras %.3fs...",
                            errno, err.msg, attempt, max_attempts, delay
                        )
                        time.sleep(delay)
                        attempt += 1
                    else:
                        if errno in TRANSIENT_MYSQL_ERRORS:
                            logger.error(
                                "Error transitorio agotó el máximo de %d reintentos (errno=%s). Abortando.",
                                max_attempts, errno
                            )
                        raise
        return wrapper
    return decorator

