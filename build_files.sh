#!/usr/bin/env bash
# Script de build para Vercel: usa un entorno virtual temporal (compatible con PEP 668 / uv)
# para instalar dependencias Python y recolectar estáticos en `staticfiles/`.
# Nota: `static/css/salida.css` viene precompilado y commiteado desde local (# ADR-004).
set -euo pipefail

python3 -m venv .venv_build
.venv_build/bin/python -m pip install --upgrade pip
.venv_build/bin/python -m pip install -r requirements.txt
.venv_build/bin/python manage.py collectstatic --noinput --settings=config.settings.produccion
rm -rf .venv_build
