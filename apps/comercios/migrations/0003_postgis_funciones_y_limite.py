"""
Migración PostGIS sin GDAL para PostgreSQL / Supabase (# ADR-005 / REQ-02, REQ-05).

Crea (solo en PostgreSQL; en SQLite local es no-op seguro):
- Esquema `extensions` y extensiones `postgis`, `unaccent`, `pg_trgm`.
- Columna generada `comercios_sucursal.ubicacion geography(Point,4326)` usando
  `ST_MakePoint(longitud::float8, latitud::float8)` (orden correcto lng, lat) + índice GIST.
- Tabla `limite_comuna` con el polígono de Pedro Aguirre Cerda + RLS "denegar todo".
- Funciones SQL parametrizadas y `STABLE`:
    * `luca_sucursales_cercanas(lat, lng, radio_m, limite)`
    * `luca_sucursales_en_vista(oeste, sur, este, norte)`
    * `luca_punto_en_comuna(lat, lng)`
- Revoca `EXECUTE` a los roles `PUBLIC`, `anon` y `authenticated` de Supabase.
"""
import json
from pathlib import Path

from django.conf import settings
from django.db import migrations


def aplicar_postgis(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    geojson_path = Path(settings.BASE_DIR) / "data" / "limite_pac.geojson"
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    geometria_json = json.dumps(geojson["features"][0]["geometry"])
    fuente_txt = geojson.get("fuente", "BCN / OpenStreetMap")

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS extensions;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;")

        # Columna generada STORED con orden explícito (LONGITUD, LATITUD)
        cursor.execute(
            """
            ALTER TABLE public.comercios_sucursal
            ADD COLUMN IF NOT EXISTS ubicacion extensions.geography(Point, 4326)
            GENERATED ALWAYS AS (
                extensions.ST_SetSRID(
                    extensions.ST_MakePoint(longitud::double precision, latitud::double precision),
                    4326
                )::extensions.geography
            ) STORED;
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_comercios_sucursal_ubicacion_gist "
            "ON public.comercios_sucursal USING GIST (ubicacion);"
        )

        # Tabla limite_comuna con RLS denegar todo
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS public.limite_comuna (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(120) UNIQUE NOT NULL,
                fuente VARCHAR(255) NOT NULL DEFAULT '',
                geom extensions.geometry(MultiPolygon, 4326) NOT NULL,
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cursor.execute("ALTER TABLE public.limite_comuna ENABLE ROW LEVEL SECURITY;")
        cursor.execute(
            """
            INSERT INTO public.limite_comuna (nombre, fuente, geom)
            VALUES (
                'Pedro Aguirre Cerda',
                %s,
                extensions.ST_SetSRID(extensions.ST_GeomFromGeoJSON(%s), 4326)
            )
            ON CONFLICT (nombre) DO UPDATE
            SET fuente = EXCLUDED.fuente, geom = EXCLUDED.geom;
            """,
            [fuente_txt, geometria_json],
        )

        # Función 1: luca_sucursales_cercanas (usa ST_DWithin + ST_Distance con índice GIST)
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION public.luca_sucursales_cercanas(
                p_lat double precision,
                p_lng double precision,
                p_radio_m double precision DEFAULT 3000,
                p_limite integer DEFAULT 50
            )
            RETURNS TABLE(id_sucursal bigint, distancia_m double precision)
            LANGUAGE sql
            STABLE
            AS $$
                SELECT
                    s.id AS id_sucursal,
                    extensions.ST_Distance(
                        s.ubicacion,
                        extensions.ST_SetSRID(extensions.ST_MakePoint(p_lng, p_lat), 4326)::extensions.geography
                    ) AS distancia_m
                FROM public.comercios_sucursal s
                INNER JOIN public.comercios_comercio c ON c.id = s.comercio_id
                WHERE s.activa = TRUE
                  AND c.activo = TRUE
                  AND c.estado = 'ACTIVO'
                  AND extensions.ST_DWithin(
                        s.ubicacion,
                        extensions.ST_SetSRID(extensions.ST_MakePoint(p_lng, p_lat), 4326)::extensions.geography,
                        p_radio_m
                  )
                ORDER BY distancia_m ASC
                LIMIT p_limite;
            $$;
            """
        )

        # Función 2: luca_sucursales_en_vista (bbox visible con ST_MakeEnvelope + &&)
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION public.luca_sucursales_en_vista(
                p_oeste double precision,
                p_sur double precision,
                p_este double precision,
                p_norte double precision
            )
            RETURNS TABLE(id_sucursal bigint)
            LANGUAGE sql
            STABLE
            AS $$
                SELECT s.id AS id_sucursal
                FROM public.comercios_sucursal s
                INNER JOIN public.comercios_comercio c ON c.id = s.comercio_id
                WHERE s.activa = TRUE
                  AND s.verificada_mapa = TRUE
                  AND c.activo = TRUE
                  AND c.estado = 'ACTIVO'
                  AND s.ubicacion::extensions.geometry && extensions.ST_MakeEnvelope(p_oeste, p_sur, p_este, p_norte, 4326);
            $$;
            """
        )

        # Función 3: luca_punto_en_comuna (ST_Covers contra limite_comuna)
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION public.luca_punto_en_comuna(
                p_lat double precision,
                p_lng double precision
            )
            RETURNS boolean
            LANGUAGE sql
            STABLE
            AS $$
                SELECT EXISTS (
                    SELECT 1
                    FROM public.limite_comuna lc
                    WHERE extensions.ST_Covers(
                        lc.geom,
                        extensions.ST_SetSRID(extensions.ST_MakePoint(p_lng, p_lat), 4326)
                    )
                );
            $$;
            """
        )

        # SEGURIDAD (# ADR-002 / Prompt 5 Sección 1.3): revocar EXECUTE a roles públicos de Supabase
        cursor.execute(
            """
            DO $$
            DECLARE
                rol text;
            BEGIN
                FOREACH rol IN ARRAY ARRAY['PUBLIC', 'anon', 'authenticated'] LOOP
                    BEGIN
                        EXECUTE format('REVOKE ALL ON FUNCTION public.luca_sucursales_cercanas(double precision, double precision, double precision, integer) FROM %I;', rol);
                        EXECUTE format('REVOKE ALL ON FUNCTION public.luca_sucursales_en_vista(double precision, double precision, double precision, double precision) FROM %I;', rol);
                        EXECUTE format('REVOKE ALL ON FUNCTION public.luca_punto_en_comuna(double precision, double precision) FROM %I;', rol);
                    EXCEPTION WHEN undefined_object THEN
                        NULL;
                    END;
                END LOOP;
            END $$;
            """
        )


def revertir_postgis(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP FUNCTION IF EXISTS public.luca_punto_en_comuna(double precision, double precision);")
        cursor.execute("DROP FUNCTION IF EXISTS public.luca_sucursales_en_vista(double precision, double precision, double precision, double precision);")
        cursor.execute("DROP FUNCTION IF EXISTS public.luca_sucursales_cercanas(double precision, double precision, double precision, integer);")
        cursor.execute("DROP TABLE IF EXISTS public.limite_comuna;")
        cursor.execute("DROP INDEX IF EXISTS public.idx_comercios_sucursal_ubicacion_gist;")
        cursor.execute("ALTER TABLE public.comercios_sucursal DROP COLUMN IF EXISTS ubicacion;")


class Migration(migrations.Migration):
    dependencies = [
        ("comercios", "0002_usoapimapas_comercio_logo_comercio_logo_estado_and_more"),
    ]

    operations = [
        migrations.RunPython(aplicar_postgis, reverse_code=revertir_postgis),
    ]
