import os
import time
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("DB_HOST", "127.0.0.1")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "root")
password = os.getenv("DB_PASSWORD", "")
database = os.getenv("DB_NAME", "sakila")

print("Conectando a la base de datos...")
conn = mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)
cur = conn.cursor()

# Verificar si payment_big ya existe
cur.execute("SHOW TABLES LIKE 'payment_big';")
exists = cur.fetchone()

if exists:
    cur.execute("SELECT COUNT(*) FROM payment_big;")
    count = cur.fetchone()[0]
    print(f"La tabla payment_big ya existe y tiene {count:,} filas.")
    if count >= 900000:
        print("No es necesario volver a poblarla.")
        cur.close()
        conn.close()
        exit(0)
    else:
        print("La tabla tiene pocas filas, se recreará...")
        cur.execute("DROP TABLE payment_big;")

print("Creando tabla payment_big...")
cur.execute("""
CREATE TABLE IF NOT EXISTS payment_big (
  payment_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id  SMALLINT UNSIGNED NOT NULL,
  staff_id     TINYINT UNSIGNED NOT NULL,
  rental_id    INT DEFAULT NULL,
  amount       DECIMAL(5,2) NOT NULL,
  payment_date DATETIME NOT NULL,
  PRIMARY KEY (payment_id)
) ENGINE=InnoDB;
""")
conn.commit()

print("Poblando payment_big (multiplicando pagos reales x60, aprox. 1 millón de registros)...")
t0 = time.time()
cur.execute("""
INSERT INTO payment_big (customer_id, staff_id, rental_id, amount, payment_date)
SELECT p.customer_id, p.staff_id, p.rental_id, p.amount,
       p.payment_date + INTERVAL (a.d + 10 * b.d) DAY
FROM payment p
CROSS JOIN (SELECT 0 d UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
            UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8
            UNION ALL SELECT 9) a
CROSS JOIN (SELECT 0 d UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
            UNION ALL SELECT 5) b;
""")
conn.commit()
elapsed = time.time() - t0

cur.execute("SELECT COUNT(*) FROM payment_big;")
total = cur.fetchone()[0]
print(f"¡Listo! payment_big poblada con {total:,} registros en {elapsed:.2f} segundos.")

cur.close()
conn.close()
