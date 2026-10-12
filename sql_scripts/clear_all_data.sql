-- Clear rows from every non-system table, including user-created schemas.
-- RESTART IDENTITY resets sequences owned by the truncated tables.
DO $$
DECLARE
    user_tables TEXT;
BEGIN
    SELECT string_agg(format('%I.%I', n.nspname, c.relname), ', ')
    INTO user_tables
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p')
      AND NOT c.relispartition
      AND n.nspname <> 'information_schema'
      AND n.nspname !~ '^pg_'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_depend AS d
          WHERE d.classid = 'pg_class'::regclass
            AND d.objid = c.oid
            AND d.deptype = 'e'
      );

    IF user_tables IS NOT NULL THEN
        EXECUTE 'TRUNCATE TABLE ' || user_tables || ' RESTART IDENTITY CASCADE';
    END IF;
END;
$$;
