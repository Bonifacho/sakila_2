"""Punto de entrada del servicio refactorizado."""
from app import create_app
from config import Config

app = create_app()

if __name__ == "__main__":
    # threaded=True: cada petición en su hilo; el pool limita las conexiones reales a MySQL.
    app.run(host="127.0.0.1", port=Config.PORT, debug=Config.DEBUG, threaded=True)
