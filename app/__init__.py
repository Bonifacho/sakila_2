"""Application factory del Sakila Rental Engine refactorizado."""
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, Response

from config import Config


def _configure_logging(log_file):
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3,
                                       encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console)
    logging.getLogger("mysql.connector").setLevel(logging.WARNING)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.sort_keys = False
    _configure_logging(Config.LOG_FILE)

    from app.errors import register_error_handlers
    from app.routes import catalog_routes, rental_routes, report_routes

    app.register_blueprint(rental_routes.bp)
    app.register_blueprint(report_routes.bp)
    app.register_blueprint(catalog_routes.bp)
    register_error_handlers(app)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/favicon.ico")
    def favicon():
        return Response(status=204)

    return app
