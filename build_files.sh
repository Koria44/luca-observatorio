#!/usr/bin/env bash
# Script de build para Vercel: instala dependencias Python y recolecta estáticos con WhiteNoise.
# Nota: `static/css/salida.css` viene precompilado y commiteado desde local (# ADR-004).
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 manage.py collectstatic --noinput --settings=config.settings.produccion
