"""
Migración condicional para PostgreSQL / Supabase (# ADR-001, ADR-002, REQ-04, REQ-16).

- En PostgreSQL habilita `unaccent` y `pg_trgm` para búsqueda tolerante a tildes y typos.
- Activa Row Level Security (RLS) sin políticas permisivas ("denegar todo") en todas las
  tablas del esquema `public`, impidiendo que la `anon key` de Supabase lea o modifique datos.
- En SQLite (desarrollo local sin `DATABASE_URL`) se omite de forma segura.
"""
from django.db import migrations


def configurar_postgresql_y_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        # Habilitar RLS en todas las tablas del esquema public (# SEGURIDAD / ADR-002)
        cursor.execute(
            """
            DO $$
            DECLARE
                tabla RECORD;
            BEGIN
                FOR tabla IN
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                LOOP
                    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', tabla.tablename);
                END LOOP;
            END $$;
            """
        )


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.RunPython(configurar_postgresql_y_rls, reverse_code=migrations.RunPython.noop),
    ]
