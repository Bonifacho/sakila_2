-- =============================================================================
-- PARTE D: OPTIMIZACIÓN E INDEXACIÓN SOBRE payment_big
-- =============================================================================

USE sakila;

-- 1. Índice para Q1 optimizada (Búsqueda por rango en payment_date con paginación)
-- Permite un escaneo de rango B-Tree podando el 99.4% de la tabla.
CREATE INDEX IF NOT EXISTS idx_payment_date 
ON payment_big (payment_date);

-- 2. Índice Compuesto Cubriente (Covering Index) para Q2 (Top 10 clientes por mes)
-- Columnas:
--   - payment_date: Prefijo más a la izquierda para el filtro de rango del mes.
--   - customer_id: Incluido para la agrupación (GROUP BY) sin tocar páginas de datos.
--   - amount: Incluido para la agregación (SUM) directa en las hojas del árbol B-Tree.
-- Al contener todas las columnas de la consulta (WHERE, GROUP BY, SUM), el motor
-- resuelve la consulta 100% en memoria/índice ("Using index"), evitando los
-- costosos accesos aleatorios a las páginas de la tabla (Bookmark Lookups).
CREATE INDEX IF NOT EXISTS idx_covering_q2 
ON payment_big (payment_date, customer_id, amount);
