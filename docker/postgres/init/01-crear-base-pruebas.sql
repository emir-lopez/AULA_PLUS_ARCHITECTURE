-- Se ejecuta solo la primera vez que se crea el volumen de PostgreSQL.
-- Base separada para que las pruebas de integración no toquen los datos de la demo.
CREATE DATABASE aulaplus_test;
