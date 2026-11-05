"""Errores de negocio y respuestas JSON uniformes (Information Hiding).

Formato único:
    éxito -> {"success": true,  "data": {...}}
    error -> {"success": false, "error": {"code": "...", "message": "..."}}
El error nativo de MySQL solo se escribe en el log del servidor.
"""
import logging

import mysql.connector
from flask import jsonify
from werkzeug.exceptions import HTTPException

from app.db import PoolTimeoutError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    status = 500
    code = "INTERNAL_ERROR"
    message = "Error interno del servidor"

    def __init__(self, message=None):
        super().__init__(message or self.message)
        if message:
            self.message = message


class ValidationError(ApiError):
    status, code, message = 400, "INVALID_DATA", "Datos inválidos"


class NotFoundError(ApiError):
    status, code, message = 404, "NOT_FOUND", "Recurso no encontrado"


class ConflictError(ApiError):
    status, code, message = 409, "CONFLICT", "Conflicto con el estado actual del recurso"


class UnavailableError(ConflictError):
    code, message = "NOT_AVAILABLE", "La copia solicitada no está disponible"


def success(data, status=200):
    return jsonify({"success": True, "data": data}), status


def _error(status, code, message):
    return jsonify({"success": False, "error": {"code": code, "message": message}}), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return _error(err.status, err.code, err.message)

    @app.errorhandler(PoolTimeoutError)
    def handle_pool_timeout(err):
        logger.warning("Pool agotado: %s", err)
        return _error(503, "SERVICE_BUSY", "Servicio ocupado, intente de nuevo")

    @app.errorhandler(mysql.connector.Error)
    def handle_db_error(err):
        # Detalle técnico SOLO en el log; al cliente, mensaje genérico.
        logger.error("Error de base de datos errno=%s sqlstate=%s msg=%s",
                     getattr(err, "errno", None), getattr(err, "sqlstate", None), err.msg)
        return _error(500, "INTERNAL_ERROR", "Error interno del servidor")

    @app.errorhandler(HTTPException)
    def handle_http(err):
        return _error(err.code, err.name.upper().replace(" ", "_"), err.description)

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        logger.exception("Error no controlado")
        return _error(500, "INTERNAL_ERROR", "Error interno del servidor")
