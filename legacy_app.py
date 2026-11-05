# legacy_app.py - Sakila Rental Engine v0.1 (código heredado)
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import mysql.connector

load_dotenv()

app = Flask(__name__)

def get_conn():
    # En el original: password="root". Se permite fallback a variable de entorno para entornos locales.
    db_pass = os.getenv("DB_PASSWORD", "root")
    return mysql.connector.connect(host="127.0.0.1", user="root",
                                   password=db_pass, database="sakila")

@app.route("/api/checkout", methods=["GET"])
def checkout():
    customer_id = request.args.get("customer_id")
    inventory_id = request.args.get("inventory_id")
    staff_id = request.args.get("staff_id")
    amount = request.args.get("amount")
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT inventory_in_stock(" + inventory_id + ")")
        if cur.fetchone()[0]:
            cur.execute("INSERT INTO rental (rental_date, inventory_id, "
                        "customer_id, staff_id) VALUES (NOW(), " + inventory_id +
                        ", " + customer_id + ", " + staff_id + ")")
            conn.commit()
            rental_id = cur.lastrowid
            cur.execute(f"INSERT INTO payment (customer_id, staff_id, rental_id, "
                        f"amount, payment_date) VALUES ({customer_id}, {staff_id}, "
                        f"{rental_id}, {amount}, NOW())")
            conn.commit()
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Película no disponible"})
    except mysql.connector.Error as err:
        return jsonify({"status": "error", "message": err.msg, "sqlstate": err.sqlstate})

@app.route("/api/rentals/delete", methods=["GET"])
def delete_rental():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM rental WHERE rental_id = " + request.args.get("id"))
    conn.commit()
    return jsonify({"status": "success"})

@app.route("/api/payments/report")
def report():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    day = request.args.get("day")
    cur.execute("SELECT * FROM payment_big "
                "WHERE DATE(payment_date) = '" + day + "'")
    return jsonify(cur.fetchall())

if __name__ == "__main__":
    app.run(debug=True)

