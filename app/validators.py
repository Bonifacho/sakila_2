"""Validación de tipos y rangos de entrada (según los tipos de columna del esquema Sakila)."""
from datetime import datetime

from app.errors import ValidationError

# Rangos de los tipos UNSIGNED del esquema
SMALLINT_MAX = 65535      # customer_id
MEDIUMINT_MAX = 16777215  # inventory_id
TINYINT_MAX = 255         # staff_id
INT_MAX = 4294967295      # rental_id


def parse_int(value, field, min_value=1, max_value=INT_MAX):
    # bool es subclase de int en Python: se rechaza explícitamente
    if isinstance(value, bool):
        raise ValidationError(f"'{field}' debe ser un entero")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ValidationError(f"'{field}' debe ser un entero")
    if not (min_value <= number <= max_value):
        raise ValidationError(f"'{field}' fuera de rango ({min_value}-{max_value})")
    return number


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValidationError(f"'{field}' es obligatorio con formato YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"'{field}' debe tener formato YYYY-MM-DD") from None


def parse_checkout(payload):
    if not isinstance(payload, dict):
        raise ValidationError("El cuerpo debe ser un objeto JSON")
    allowed = {"customer_id", "inventory_id", "staff_id"}
    extra = set(payload) - allowed
    if extra:
        # 'amount' u otros campos se rechazan: el monto lo calcula el servidor
        raise ValidationError(f"Campos no permitidos: {', '.join(sorted(extra))}")
    return {
        "customer_id": parse_int(payload.get("customer_id"), "customer_id", 1, SMALLINT_MAX),
        "inventory_id": parse_int(payload.get("inventory_id"), "inventory_id", 1, MEDIUMINT_MAX),
        "staff_id": parse_int(payload.get("staff_id"), "staff_id", 1, TINYINT_MAX),
    }


def parse_pagination(args, default_size, max_size):
    page = parse_int(args.get("page", "1"), "page", 1, 1_000_000)
    size = parse_int(args.get("page_size", str(default_size)), "page_size", 1, max_size)
    return page, size


def parse_float(value, field, min_value=0.0, max_value=999.99):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"'{field}' debe ser un número decimal válido") from None
    if not (min_value <= number <= max_value):
        raise ValidationError(f"'{field}' fuera de rango ({min_value}-{max_value})")
    return number


def parse_str_filter(value, field, max_len=100):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) > max_len:
        raise ValidationError(f"'{field}' excede la longitud máxima ({max_len})")
    return s

