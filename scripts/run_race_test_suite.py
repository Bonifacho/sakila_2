import os
import sys
import time
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from werkzeug.serving import make_server
from scripts.race_test import run_race_test

def main():
    os.makedirs("evidencias/parte_c", exist_ok=True)
    
    # 1. Iniciar servidor Flask refactorizado en hilo daemon
    app = create_app()
    server = make_server("127.0.0.1", 5000, app, threaded=True)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(1)
    print("Servidor Flask corriendo en http://127.0.0.1:5000")

    # 2. Ejecutar prueba de concurrencia
    out_path = sys.argv[1] if len(sys.argv) > 1 else "evidencias/parte_c/C1_race_test_antes.txt"
    inv_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    print(f"Lanzando race_test con inventory_id={inv_id}, salida en {out_path}...")
    final_count, status_counts = run_race_test(num_threads=10, inventory_id=inv_id, out_file=out_path)
    
    server.shutdown()
    print("Servidor detenido.")

if __name__ == "__main__":
    main()

