"""Configuración centralizada. Todas las credenciales se leen de variables de entorno (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value


class Config:
    # Conexión de la APLICACIÓN: usuario con privilegios mínimos (nunca root).
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_NAME = os.getenv("DB_NAME", "sakila")
    DB_USER = _require("APP_DB_USER")
    DB_PASSWORD = _require("APP_DB_PASSWORD")

    # Pool de conexiones
    DB_POOL_NAME = os.getenv("DB_POOL_NAME", "sakila_pool")
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    # Segundos que una petición espera por una conexión libre antes de fallar (503).
    DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "5"))

    # Paginación
    DEFAULT_PAGE_SIZE = 100
    MAX_PAGE_SIZE = 500

    # Flask
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    PORT = int(os.getenv("PORT", "5000"))
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")
