"""Script de empaquetado final del entregable: Bonilla_Andres_TallerSakila.zip.

Incluye toda la estructura modular, requirements.txt, README.md, .env.example,
scripts SQL (usuario e índices), y los scripts race_test.py y etl_catalog.py.
Excluye venv/, .git/, __pycache__/, .env (credenciales privadas) y archivos temporales.
"""
import os
import zipfile

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ZIP_NAME = "Bonilla_Andres_TallerSakila.zip"
ZIP_PATH = os.path.join(ROOT_DIR, ZIP_NAME)

INCLUDE_DIRS = ["app", "sql", "scripts"]
INCLUDE_ROOT_FILES = [
    "README.md",
    "requirements.txt",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    "config.py",
    "run.py",
    "legacy_app.py",
    "race_test.py",
    "etl_catalog.py",
]


def build_zip():
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in INCLUDE_ROOT_FILES:
            fpath = os.path.join(ROOT_DIR, fname)
            if os.path.exists(fpath):
                zf.write(fpath, arcname=fname)

        for dname in INCLUDE_DIRS:
            dpath = os.path.join(ROOT_DIR, dname)
            for root, dirs, files in os.walk(dpath):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    if f.endswith((".pyc", ".pyo")):
                        continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, ROOT_DIR)
                    zf.write(full_path, arcname=rel_path)

    print(f"Archivo ZIP generado exitosamente: {ZIP_PATH}")
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        print(f"Total archivos empaquetados: {len(zf.namelist())}")
        for name in sorted(zf.namelist()):
            print(f"  - {name}")


if __name__ == "__main__":
    build_zip()
