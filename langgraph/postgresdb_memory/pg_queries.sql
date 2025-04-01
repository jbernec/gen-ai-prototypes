-- Option 1: Using information_schema (ANSI standard)
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public';


SELECT * from store_vectors

SELECT * FROM CHECKPOINTs

SELECT * from chathistory

SELECT DISTINCT prefix FROM store;

CREATE DATABASE langgraph_memorydb;

-- List all databases
SELECT datname FROM pg_database WHERE datistemplate = false;

