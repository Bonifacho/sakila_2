"""Ejecuta un script .sql como administrador (DB_USER del .env), sustituyendo marcadores
{{VARIABLE}} por variables de entorno. Uso: python scripts/run_sql.py sql/01_create_app_user.sql
"""
import os
import re
import sys

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def main(path):
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    sql = re.sub(r"\{\{(\w+)\}\}", lambda m: os.environ[m.group(1)], sql)
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
    )
    cur = conn.cursor()
    for stmt in statements:
        cur.execute(stmt)
        print("OK:", stmt.split("IDENTIFIED BY")[0][:90])
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1])
