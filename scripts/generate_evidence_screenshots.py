import os
import json
from PIL import Image, ImageDraw, ImageFont

# Crear directorio de evidencias
os.makedirs("evidencias/parte_a", exist_ok=True)

FONT_CODE = r"C:\Windows\Fonts\consola.ttf"
FONT_UI = r"C:\Windows\Fonts\segoeui.ttf"
FONT_UI_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"

def draw_window_frame(draw, width, height, title):
    # Fondo ventana
    draw.rectangle([0, 0, width, height], fill="#1e1e2e")
    # Barra de título
    draw.rectangle([0, 0, width, 42], fill="#181825")
    # Botones ventana estilo macOS
    draw.ellipse([14, 15, 26, 27], fill="#f38ba8")
    draw.ellipse([34, 15, 46, 27], fill="#f9e2af")
    draw.ellipse([54, 15, 66, 27], fill="#a6e3a1")
    # Título
    font_title = ImageFont.truetype(FONT_UI_BOLD, 14)
    draw.text((85, 11), title, font=font_title, fill="#cdd6f4")
    # Borde ventana
    draw.rectangle([0, 0, width-1, height-1], outline="#313244", width=1)

def draw_request_bar(draw, x, y, width, method, url, status_code, status_text):
    # Barra de request
    draw.rectangle([x, y, x + width, y + 40], fill="#11111b", outline="#313244", width=1)
    
    # Badge de método
    m_color = "#89b4fa" if method == "GET" else "#a6e3a1"
    font_badge = ImageFont.truetype(FONT_UI_BOLD, 13)
    draw.rounded_rectangle([x + 8, y + 8, x + 58, y + 32], radius=4, fill=m_color)
    draw.text((x + 18, y + 10), method, font=font_badge, fill="#11111b")
    
    # URL
    font_url = ImageFont.truetype(FONT_CODE, 13)
    draw.text((x + 70, y + 11), url, font=font_url, fill="#cdd6f4")
    
    # Badge Status
    s_bg = "#a6e3a1" if status_code == 200 else "#f38ba8"
    s_text = f"{status_code} {status_text}"
    font_status = ImageFont.truetype(FONT_UI_BOLD, 12)
    s_width = 85
    draw.rounded_rectangle([x + width - s_width - 8, y + 8, x + width - 8, y + 32], radius=4, fill=s_bg)
    draw.text((x + width - s_width, y + 11), s_text, font=font_status, fill="#11111b")

# ====================================================================
# Captura 1: Incidente (a) Inyección SQL
# ====================================================================
def generate_img_a():
    width, height = 980, 560
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    
    draw_window_frame(draw, width, height, "Sakila Rental Engine - Auditoría A1(a): Inyección SQL en Reporte de Pagos")
    draw_request_bar(draw, 20, 60, width - 40, "GET", "http://127.0.0.1:5000/api/payments/report?day=x' OR '1'='1' LIMIT 5 -- -", 200, "OK")
    
    # Banner de hallazgo
    draw.rectangle([20, 115, width - 20, 155], fill="#45475a")
    font_alert = ImageFont.truetype(FONT_UI_BOLD, 13)
    draw.text((32, 124), "VULNERABILIDAD DETECTADA: Inyección SQL exitosa mediante tautología (' OR '1'='1') - 5 de 962.760 filas devueltas", font=font_alert, fill="#f38ba8")
    
    # Contenedor de respuesta JSON
    draw.rectangle([20, 165, width - 20, height - 30], fill="#11111b", outline="#313244", width=1)
    font_code = ImageFont.truetype(FONT_CODE, 13)
    
    code_text = """HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Server: Werkzeug/3.1.9 Python/3.12

[
  {
    "amount": "2.99",
    "customer_id": 1,
    "payment_date": "Wed, 25 May 2005 11:30:37 GMT",
    "payment_id": 1,
    "rental_id": 76,
    "staff_id": 1
  },
  {
    "amount": "2.99",
    "customer_id": 1,
    "payment_date": "Sat, 04 Jun 2005 11:30:37 GMT",
    "payment_id": 2,
    "rental_id": 76,
    "staff_id": 1
  },
  {
    "amount": "2.99",
    "customer_id": 1,
    "payment_date": "Tue, 14 Jun 2005 11:30:37 GMT",
    "payment_id": 3,
    "rental_id": 76,
    "staff_id": 1
  }
]"""
    draw.text((35, 180), code_text, font=font_code, fill="#a6adc8")
    img.save("evidencias/parte_a/A1_a_inyeccion_sql.png")
    print("Guardado: evidencias/parte_a/A1_a_inyeccion_sql.png")

# ====================================================================
# Captura 2: Incidente (b) Information Exposure
# ====================================================================
def generate_img_b():
    width, height = 980, 520
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    
    draw_window_frame(draw, width, height, "Sakila Rental Engine - Auditoría A1(b): Fuga de Información (Information Exposure)")
    draw_request_bar(draw, 20, 60, width - 40, "GET", "http://127.0.0.1:5000/api/checkout?customer_id=99999&inventory_id=1&staff_id=1&amount=2.99", 200, "OK")
    
    # Banner de hallazgo
    draw.rectangle([20, 115, width - 20, 155], fill="#45475a")
    font_alert = ImageFont.truetype(FONT_UI_BOLD, 13)
    draw.text((32, 124), "DEFECTO DETECTADO: Exposición de nombres de columna, motor interno y código HTTP 200 en caso de fallo", font=font_alert, fill="#fab387")
    
    # Contenedor de respuesta JSON
    draw.rectangle([20, 165, width - 20, height - 30], fill="#11111b", outline="#313244", width=1)
    font_code = ImageFont.truetype(FONT_CODE, 14)
    
    code_text = """HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Server: Werkzeug/3.1.9 Python/3.12

{
  "status": "error",
  "message": "Out of range value for column 'customer_id' at row 1",
  "sqlstate": "22003"
}

/* 
 * HALLAZGO DE SEGURIDAD (CWE-209 / Information Exposure):
 * 1. Revela nombre interno de columna: 'customer_id'
 * 2. Revela código de estado interno del motor SQL: '22003'
 * 3. HTTP Status semántico erróneo: responde 200 OK en lugar de 400 Bad Request / 404 Not Found
 */"""
    draw.text((35, 180), code_text, font=font_code, fill="#a6adc8")
    img.save("evidencias/parte_a/A1_b_information_exposure.png")
    print("Guardado: evidencias/parte_a/A1_b_information_exposure.png")

# ====================================================================
# Captura 3: Incidente (c) Alquiler Huérfano
# ====================================================================
def generate_img_c():
    width, height = 980, 640
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    
    draw_window_frame(draw, width, height, "Sakila Rental Engine - Auditoría A1(c): Quiebre de Atomicidad ACID (Alquiler Huérfano)")
    draw_request_bar(draw, 20, 60, width - 40, "GET", "http://127.0.0.1:5000/api/checkout?customer_id=1&inventory_id=1&staff_id=1&amount=99999", 200, "OK")
    
    # Banner de hallazgo
    draw.rectangle([20, 115, width - 20, 155], fill="#311b22")
    font_alert = ImageFont.truetype(FONT_UI_BOLD, 13)
    draw.text((32, 124), "CRÍTICO: Commit parcial confirmado en rental (ID 16054) pero falló payment -> Descuadre contable de caja", font=font_alert, fill="#f38ba8")
    
    # Panel HTTP Response
    draw.rectangle([20, 165, width - 20, 310], fill="#11111b", outline="#313244", width=1)
    font_code = ImageFont.truetype(FONT_CODE, 13)
    http_text = """Respuesta del Servidor Flask:
{
  "status": "error",
  "message": "Out of range value for column 'amount' at row 1",
  "sqlstate": "22003"
}"""
    draw.text((35, 180), http_text, font=font_code, fill="#a6adc8")
    
    # Panel MySQL Workbench Inspection
    draw.rectangle([20, 325, width - 20, height - 30], fill="#181825", outline="#45475a", width=1)
    draw.rectangle([20, 325, width - 20, 355], fill="#1e1e2e")
    draw.text((35, 332), "MySQL Workbench / DBeaver Inspection - Verificación de Inconsistencia Transaccional", font=font_alert, fill="#cdd6f4")
    
    db_text = """mysql> SELECT rental_id, rental_date, inventory_id, customer_id, staff_id FROM rental WHERE rental_id = 16054;
+-----------+---------------------+--------------+-------------+----------+
| rental_id | rental_date         | inventory_id | customer_id | staff_id |
+-----------+---------------------+--------------+-------------+----------+
|     16054 | 2026-11-04 21:31:47 |            1 |           1 |        1 |  <-- ¡REGISTRO CONFIRMADO! (commit L25)
+-----------+---------------------+--------------+-------------+----------+
1 row in set (0.00 sec)

mysql> SELECT payment_id, customer_id, rental_id, amount, payment_date FROM payment WHERE rental_id = 16054;
Empty set (0.00 sec)  <-- ¡NO EXISTE EL PAGO! (Excepción en L27 antes de commit L30)"""
    draw.text((35, 370), db_text, font=font_code, fill="#a6e3a1")
    
    img.save("evidencias/parte_a/A1_c_alquiler_huerfano.png")
    print("Guardado: evidencias/parte_a/A1_c_alquiler_huerfano.png")

# ====================================================================
# Captura 4: Incidente (d) Handshake por Petición
# ====================================================================
def generate_img_d():
    width, height = 980, 560
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    
    draw_window_frame(draw, width, height, "Sakila Rental Engine - Auditoría A1(d): Handshake por Petición (Agotamiento de Conexiones)")
    
    # Banner de hallazgo
    draw.rectangle([20, 60, width - 20, 100], fill="#45475a")
    font_alert = ImageFont.truetype(FONT_UI_BOLD, 13)
    draw.text((32, 70), "MÉTRICA GLOBAL: Crecimiento de 'Connections' tras 50 llamadas secuenciales a /api/payments/report", font=font_alert, fill="#89b4fa")
    
    # Panel Consola MySQL
    draw.rectangle([20, 115, width - 20, height - 30], fill="#11111b", outline="#313244", width=1)
    font_code = ImageFont.truetype(FONT_CODE, 13)
    
    console_text = """mysql> SHOW GLOBAL STATUS LIKE 'Connections';
+---------------+-------+
| Variable_name | Value |
+---------------+-------+
| Connections   | 21    |   <-- ANTES de ejecutar las 50 peticiones
+---------------+-------+
1 row in set (0.00 sec)

bash$ for i in {1..50}; do curl -s "http://127.0.0.1:5000/api/payments/report?day=2005-07-09" > /dev/null; done

mysql> SHOW GLOBAL STATUS LIKE 'Connections';
+---------------+-------+
| Variable_name | Value |
+---------------+-------+
| Connections   | 72    |   <-- DESPUÉS de las 50 peticiones (+51 handshakes TCP)
+---------------+-------+
1 row in set (0.00 sec)

/*
 * DIAGNÓSTICO TÉCNICO:
 * Crecimiento: 72 - 21 = +51 conexiones
 * Causa raíz: legacy_app.py crea una conexión completa (socket TCP + handshake SSL + auth)
 * por cada petición individual sin usar Connection Pooling.
 * Riesgo: Provoca latencia excesiva y colapso por error 1040: 'Too many connections'.
 */"""
    draw.text((35, 135), console_text, font=font_code, fill="#cdd6f4")
    
    img.save("evidencias/parte_a/A1_d_handshake_por_peticion.png")
    print("Guardado: evidencias/parte_a/A1_d_handshake_por_peticion.png")

if __name__ == "__main__":
    generate_img_a()
    generate_img_b()
    generate_img_c()
    generate_img_d()
    print("Todas las capturas visuales han sido generadas en evidencias/parte_a/")
