"""Módulo de conectividad con MongoDB (Catálogo Documental - Parte E).

Implementa un cliente compartido (Singleton por proceso) con conexión perezosa (lazy)
y tiempos de espera acotados (serverSelectionTimeoutMS).
Si MongoDB está apagado, las operaciones transaccionales en MySQL (/api/checkout)
NO se ven afectadas en absoluto (Desacoplamiento / Degradación Elegante).
"""
import logging
import threading
from pymongo import MongoClient
from config import Config

logger = logging.getLogger(__name__)

_client = None
_lock = threading.Lock()


def get_mongo_client() -> MongoClient:
    """Devuelve la instancia única de MongoClient por proceso."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = MongoClient(
                    Config.MONGO_URI,
                    serverSelectionTimeoutMS=Config.MONGO_TIMEOUT_MS,
                    connectTimeoutMS=Config.MONGO_TIMEOUT_MS,
                    socketTimeoutMS=Config.MONGO_TIMEOUT_MS,
                    unicode_decode_error_handler="replace",
                )
                logger.info(
                    "Cliente MongoDB inicializado hacia %s (DB: %s)",
                    Config.MONGO_URI,
                    Config.MONGO_DB_NAME,
                )
    return _client


def get_films_collection():
    """Devuelve la colección `films` de la base `sakila_catalog`."""
    client = get_mongo_client()
    db = client[Config.MONGO_DB_NAME]
    return db[Config.MONGO_COLLECTION_FILMS]


def reset_mongo_client():
    """Cierra y reinicia el cliente (útil para pruebas de resiliencia)."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None
