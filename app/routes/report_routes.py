"""Rutas HTTP de reportes."""
from flask import Blueprint, current_app, request

from app.errors import success
from app.services import report_service
from app.validators import parse_date, parse_pagination

bp = Blueprint("reports", __name__, url_prefix="/api")


@bp.get("/payments/report")
def report():
    day = parse_date(request.args.get("day"), "day")
    page, page_size = parse_pagination(
        request.args,
        current_app.config["DEFAULT_PAGE_SIZE"],
        current_app.config["MAX_PAGE_SIZE"],
    )
    return success(report_service.daily_report(day, page, page_size))

