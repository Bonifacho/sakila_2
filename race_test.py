"""Punto de entrada raíz para race_test.py (delega en scripts/race_test.py)."""
from scripts.race_test import run_race_test, cleanup_inventory_rentals
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba de condición de carrera en Sakila Rental Engine")
    parser.add_argument("--threads", type=int, default=10, help="Número de hilos concurrentes (default: 10)")
    parser.add_argument("--inventory-id", type=int, default=None, help="ID de inventario a probar")
    parser.add_argument("--out", type=str, default=None, help="Archivo para guardar la salida")
    parser.add_argument("--cleanup", action="store_true", help="Limpiar registros de prueba creados")
    args = parser.parse_args()

    if args.cleanup:
        inv_id = args.inventory_id or 1
        del_count = cleanup_inventory_rentals(inv_id)
        print(f"Limpieza completada: {del_count} registros eliminados para inventory_id={inv_id}")
    else:
        run_race_test(num_threads=args.threads, inventory_id=args.inventory_id, out_file=args.out)
