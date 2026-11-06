-- =====================================================================
-- 01_create_app_user.sql  -  Usuario de aplicación con privilegios mínimos
-- Ejecutar como root. El marcador {{APP_DB_PASSWORD}} lo reemplaza
-- scripts/run_sql.py con el valor de la variable de entorno APP_DB_PASSWORD.
-- =====================================================================

DROP USER IF EXISTS 'sakila_app'@'localhost';
CREATE USER 'sakila_app'@'localhost' IDENTIFIED BY '{{APP_DB_PASSWORD}}';

-- Lectura: solo las tablas que el servicio y el ETL de catálogo consultan
GRANT SELECT ON sakila.customer      TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.staff         TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.inventory     TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.film          TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.language      TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.category      TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.film_category TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.actor         TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.film_actor    TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.rental        TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.payment       TO 'sakila_app'@'localhost';
GRANT SELECT ON sakila.payment_big   TO 'sakila_app'@'localhost';

-- Escritura: solo lo que exige el checkout y la devolución
GRANT INSERT ON sakila.rental  TO 'sakila_app'@'localhost';
GRANT INSERT ON sakila.payment TO 'sakila_app'@'localhost';
GRANT UPDATE (return_date) ON sakila.rental TO 'sakila_app'@'localhost';

-- Función de disponibilidad (SQL SECURITY DEFINER)
GRANT EXECUTE ON FUNCTION sakila.inventory_in_stock TO 'sakila_app'@'localhost';

-- Sin DELETE, sin DDL (CREATE/DROP/ALTER), sin GRANT OPTION, sin acceso a otras BD.
FLUSH PRIVILEGES;

