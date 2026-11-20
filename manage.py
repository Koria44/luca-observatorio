#!/usr/bin/env python
"""
Utilidad de línea de comandos de Django para Luca — Observatorio de Precios (PAC).
Por defecto carga la configuración local (`config.settings.local`) para desarrollo seguro.
"""
import os
import sys


def main():
    """Punto de entrada para tareas administrativas de Django."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Verifica que el entorno virtual (.venv) esté activo "
            "y que las dependencias de requirements-dev.txt estén instaladas."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
