"""
Migración de defensa en profundidad en base de datos (# Prompt 7 Sección 4).

Instala triggers y restricciones reversibles tanto en PostgreSQL/Supabase como en SQLite:
1. Inmutabilidad de `auditoria_registroauditoria` y `gobernanza_historialhabilitacion` (prohíbe UPDATE/DELETE).
2. Inmutabilidad de valores en precios ya PUBLICADOS (solo se permite transitar estado).
3. Regla de cuatro ojos (`revisado_por_id <> registrado_por_id`) en precios con aprobación manual.
4. Bloqueo `BEFORE INSERT` en `precios_precio` para fuentes COMERCIANTE / CARGA_MASIVA si el comercio
   no está ACTIVO o no cuenta con una `Habilitacion` en estado OTORGADA, nivel >= 1 y vigente.
"""
from django.db import migrations


SQLITE_UP = [
    """
    CREATE TRIGGER IF NOT EXISTS trg_auditoria_sin_update
    BEFORE UPDATE ON auditoria_registroauditoria
    BEGIN
        SELECT RAISE(ABORT, 'RegistroAuditoria es inmutable: UPDATE prohibido');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_auditoria_sin_delete
    BEFORE DELETE ON auditoria_registroauditoria
    BEGIN
        SELECT RAISE(ABORT, 'RegistroAuditoria es inmutable: DELETE prohibido');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_historial_hab_sin_update
    BEFORE UPDATE ON gobernanza_historialhabilitacion
    BEGIN
        SELECT RAISE(ABORT, 'HistorialHabilitacion es inmutable: UPDATE prohibido');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_historial_hab_sin_delete
    BEFORE DELETE ON gobernanza_historialhabilitacion
    BEGIN
        SELECT RAISE(ABORT, 'HistorialHabilitacion es inmutable: DELETE prohibido');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_precio_inmutable_publicado
    BEFORE UPDATE ON precios_precio
    WHEN OLD.estado = 'PUBLICADO' AND (
        NEW.precio_normal != OLD.precio_normal
        OR IFNULL(NEW.precio_oferta, -1) != IFNULL(OLD.precio_oferta, -1)
    )
    BEGIN
        SELECT RAISE(ABORT, 'Un precio PUBLICADO es inmutable: cree un registro nuevo que lo reemplace');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_precio_cuatro_ojos_ins
    BEFORE INSERT ON precios_precio
    WHEN NEW.regla_publicacion = 'APROBACION_MANUAL'
      AND NEW.revisado_por_id IS NOT NULL
      AND NEW.registrado_por_id IS NOT NULL
      AND NEW.revisado_por_id = NEW.registrado_por_id
    BEGIN
        SELECT RAISE(ABORT, 'Violación de cuatro ojos: el revisor no puede ser el mismo autor');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_precio_cuatro_ojos_upd
    BEFORE UPDATE ON precios_precio
    WHEN NEW.regla_publicacion = 'APROBACION_MANUAL'
      AND NEW.revisado_por_id IS NOT NULL
      AND NEW.registrado_por_id IS NOT NULL
      AND NEW.revisado_por_id = NEW.registrado_por_id
    BEGIN
        SELECT RAISE(ABORT, 'Violación de cuatro ojos: el revisor no puede ser el mismo autor');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_precio_requiere_habilitacion
    BEFORE INSERT ON precios_precio
    WHEN NEW.fuente IN ('COMERCIANTE', 'CARGA_MASIVA')
      AND NOT EXISTS (
        SELECT 1
        FROM comercios_sucursal s
        JOIN comercios_comercio c ON c.id = s.comercio_id
        JOIN gobernanza_habilitacion h ON h.comercio_id = c.id
        WHERE s.id = NEW.sucursal_id
          AND s.activa = 1
          AND c.activo = 1
          AND c.estado = 'ACTIVO'
          AND h.estado = 'OTORGADA'
          AND h.nivel >= 1
          AND (h.vigente_hasta IS NULL OR h.vigente_hasta >= date('now'))
      )
    BEGIN
        SELECT RAISE(ABORT, 'Comercio sin habilitación vigente para publicar precios');
    END;
    """,
]

SQLITE_DOWN = [
    "DROP TRIGGER IF EXISTS trg_auditoria_sin_update;",
    "DROP TRIGGER IF EXISTS trg_auditoria_sin_delete;",
    "DROP TRIGGER IF EXISTS trg_historial_hab_sin_update;",
    "DROP TRIGGER IF EXISTS trg_historial_hab_sin_delete;",
    "DROP TRIGGER IF EXISTS trg_precio_inmutable_publicado;",
    "DROP TRIGGER IF EXISTS trg_precio_cuatro_ojos_ins;",
    "DROP TRIGGER IF EXISTS trg_precio_cuatro_ojos_upd;",
    "DROP TRIGGER IF EXISTS trg_precio_requiere_habilitacion;",
]

PG_UP = """
CREATE OR REPLACE FUNCTION fn_bloquear_mutacion_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Tabla % es inmutable: no admite %', TG_TABLE_NAME, TG_OP USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auditoria_inmutable ON auditoria_registroauditoria;
CREATE TRIGGER trg_auditoria_inmutable
BEFORE UPDATE OR DELETE ON auditoria_registroauditoria
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_mutacion_inmutable();

DROP TRIGGER IF EXISTS trg_historial_hab_inmutable ON gobernanza_historialhabilitacion;
CREATE TRIGGER trg_historial_hab_inmutable
BEFORE UPDATE OR DELETE ON gobernanza_historialhabilitacion
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_mutacion_inmutable();

CREATE OR REPLACE FUNCTION fn_validar_precio_gobernanza() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.estado = 'PUBLICADO' THEN
        IF NEW.precio_normal <> OLD.precio_normal OR COALESCE(NEW.precio_oferta, -1) <> COALESCE(OLD.precio_oferta, -1) THEN
            RAISE EXCEPTION 'Un precio PUBLICADO es inmutable' USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF NEW.regla_publicacion = 'APROBACION_MANUAL'
       AND NEW.revisado_por_id IS NOT NULL
       AND NEW.registrado_por_id IS NOT NULL
       AND NEW.revisado_por_id = NEW.registrado_por_id THEN
        RAISE EXCEPTION 'Violación de cuatro ojos: revisor igual a autor' USING ERRCODE = 'check_violation';
    END IF;

    IF TG_OP = 'INSERT' AND NEW.fuente IN ('COMERCIANTE', 'CARGA_MASIVA') THEN
        IF NOT EXISTS (
            SELECT 1
            FROM comercios_sucursal s
            JOIN comercios_comercio c ON c.id = s.comercio_id
            JOIN gobernanza_habilitacion h ON h.comercio_id = c.id
            WHERE s.id = NEW.sucursal_id
              AND s.activa = TRUE
              AND c.activo = TRUE
              AND c.estado = 'ACTIVO'
              AND h.estado = 'OTORGADA'
              AND h.nivel >= 1
              AND (h.vigente_hasta IS NULL OR h.vigente_hasta >= CURRENT_DATE)
        ) THEN
            RAISE EXCEPTION 'Comercio sin habilitación vigente para publicar' USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_precio_gobernanza ON precios_precio;
CREATE TRIGGER trg_precio_gobernanza
BEFORE INSERT OR UPDATE ON precios_precio
FOR EACH ROW EXECUTE FUNCTION fn_validar_precio_gobernanza();
"""

PG_DOWN = """
DROP TRIGGER IF EXISTS trg_precio_gobernanza ON precios_precio;
DROP TRIGGER IF EXISTS trg_historial_hab_inmutable ON gobernanza_historialhabilitacion;
DROP TRIGGER IF EXISTS trg_auditoria_inmutable ON auditoria_registroauditoria;
DROP FUNCTION IF EXISTS fn_validar_precio_gobernanza();
DROP FUNCTION IF EXISTS fn_bloquear_mutacion_inmutable();
"""


def aplicar_controles(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        if schema_editor.connection.vendor == "postgresql":
            cur.execute(PG_UP)
        elif schema_editor.connection.vendor == "sqlite":
            for stmt in SQLITE_UP:
                cur.execute(stmt)


def revertir_controles(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        if schema_editor.connection.vendor == "postgresql":
            cur.execute(PG_DOWN)
        elif schema_editor.connection.vendor == "sqlite":
            for stmt in SQLITE_DOWN:
                cur.execute(stmt)


class Migration(migrations.Migration):
    dependencies = [
        ("gobernanza", "0001_initial"),
        ("precios", "0003_precio_muestreo_terreno_precio_regla_publicacion_and_more"),
        ("auditoria", "0002_registroauditoria_hash_actual_and_more"),
    ]

    operations = [
        migrations.RunPython(aplicar_controles, revertir_controles),
    ]
