-- Emit PostgreSQL schema metadata as TSV for Mermaid ERD generation.
--
-- Usage:
--   psql -v erd_schema="stonks" -f tools/docs/db/mermaid-erd-meta.sql
--
-- Required psql var:
--   :erd_schema

\pset format unaligned
\pset tuples_only on
\pset fieldsep '\t'

SELECT 'T', t.table_schema, t.table_name
FROM information_schema.tables t
WHERE t.table_schema = :'erd_schema'
  AND t.table_type = 'BASE TABLE'
  AND t.table_name <> 'flyway_schema_history'
ORDER BY t.table_name;

SELECT 'C', c.table_schema, c.table_name, c.column_name, c.data_type, c.is_nullable, c.ordinal_position::text
FROM information_schema.columns c
WHERE c.table_schema = :'erd_schema'
ORDER BY c.table_name, c.ordinal_position;

SELECT 'PK', kcu.table_schema, kcu.table_name, kcu.column_name, kcu.ordinal_position::text
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
 AND tc.table_name = kcu.table_name
WHERE tc.table_schema = :'erd_schema'
  AND tc.constraint_type = 'PRIMARY KEY'
ORDER BY kcu.table_name, kcu.ordinal_position;

SELECT 'UQ', kcu.table_schema, kcu.table_name, kcu.constraint_name, kcu.column_name, kcu.ordinal_position::text
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
 AND tc.table_name = kcu.table_name
WHERE tc.table_schema = :'erd_schema'
  AND tc.constraint_type = 'UNIQUE'
ORDER BY kcu.table_name, kcu.constraint_name, kcu.ordinal_position;

SELECT
  'FK',
  kcu.table_schema,
  kcu.table_name,
  kcu.constraint_name,
  kcu.column_name,
  ccu.table_schema AS ref_schema,
  ccu.table_name   AS ref_table,
  ccu.column_name  AS ref_column,
  kcu.ordinal_position::text
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
 AND ccu.table_schema = tc.table_schema
WHERE tc.table_schema = :'erd_schema'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY kcu.table_name, kcu.constraint_name, kcu.ordinal_position;
