"""
Configuración base de Django para Luca — Observatorio de Precios del Comercio Local (PAC).

Define las opciones compartidas entre desarrollo local y producción en Vercel + Supabase.
Todos los secretos y parámetros dependientes de entorno se leen desde variables de entorno.
# SEGURIDAD: Nunca definir credenciales reales en este archivo.
# REQ-08, REQ-12, REQ-16: Autenticación propia, django-axes, CSP estricta y control de sesión.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# SEGURIDAD: En producción SECRET_KEY es obligatoria; en local usa clave efímera de desarrollo.
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "clave-insegura-solo-desarrollo-local-luca-pac-2026-no-usar-en-produccion",
)

DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes", "si")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,.vercel.app").split(",")
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Seguridad (# REQ-16)
    "axes",
    "csp",
    # Apps de dominio Luca
    "apps.nucleo",
    "apps.cuentas",
    "apps.catalogo",
    "apps.comercios",
    "apps.precios",
    "apps.auditoria",
    "apps.portal",
    "apps.panel",
    "apps.reportes",
    "apps.verificacion",
    "apps.gobernanza",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.nucleo.middleware.ControlSesionYLatidoMiddleware",
    "apps.nucleo.middleware.LimitePeticionesIPMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Modelo de usuario propio (# ADR-002 / REQ-08)
AUTH_USER_MODEL = "cuentas.Usuario"
LOGIN_URL = "/cuenta/ingresar/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Validación de contraseñas (# SEGURIDAD / II.6)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# django-axes: bloqueo temporal tras 5 intentos fallidos (# SEGURIDAD / II.7)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # 15 minutos
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "cuentas/bloqueado.html"
AXES_USERNAME_FORM_FIELD = "email"

# Política CSP estricta con django-csp 4.0 (# SEGURIDAD / ADR-005 / REQ-16)
# MapLibre GL JS se sirve vendorizado desde 'self' (sin CDN ni blob:).
# Solo se abre maps.geoapify.com para estilos/tiles vectoriales.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.jsdelivr.net",
        ],
        "worker-src": ["'self'"],
        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "https://maps.geoapify.com",
        ],
        "font-src": ["'self'", "https://maps.geoapify.com", "data:"],
        "img-src": [
            "'self'",
            "data:",
            "https://maps.geoapify.com",
        ],
        "connect-src": [
            "'self'",
            "https://maps.geoapify.com",
        ],
        "frame-ancestors": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    }
}

# Configuración de Mapas (MapLibre + Geoapify) y límites (# ADR-005 / Prompt 5)
# SEGURIDAD: GEOAPIFY_KEY_SERVIDOR nunca se expone al navegador ni en plantillas.
PROVEEDOR_MAPAS = os.environ.get("PROVEEDOR_MAPAS", "geoapify")
GEOAPIFY_KEY_NAVEGADOR = os.environ.get("GEOAPIFY_KEY_NAVEGADOR", "").strip()
GEOAPIFY_KEY_SERVIDOR = os.environ.get("GEOAPIFY_KEY_SERVIDOR", "").strip()
GEOAPIFY_ESTILO = os.environ.get("GEOAPIFY_ESTILO", "osm-bright").strip()
GEO_TOPE_DIARIO_PROXY = int(os.environ.get("GEO_TOPE_DIARIO_PROXY", "1500"))
VALIDAR_LIMITE_COMUNA = True

# Buckets de imágenes (público aprobadas / privado pendientes) (# Prompt 5 Sección 3)
SUPABASE_BUCKET_PUBLICO = os.environ.get("SUPABASE_BUCKET_PUBLICO", "luca-publico")
SUPABASE_BUCKET_PENDIENTES = os.environ.get("SUPABASE_BUCKET_PENDIENTES", "luca-pendientes")

# Internacionalización — Español de Chile
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

# Archivos estáticos (Tailwind compilado en local + WhiteNoise en producción)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Control de sesión (# SEGURIDAD / II.7 / ADR-003)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_AGE = 1800  # 30 min por defecto (15 min staff en middleware)

# Tolerancias configurables del latido de sesión (segundos)
LATIDO_TOLERANCIA_STAFF = int(os.environ.get("LATIDO_TOLERANCIA_STAFF", "300"))
LATIDO_TOLERANCIA_PUBLICO = int(os.environ.get("LATIDO_TOLERANCIA_PUBLICO", "900"))
RATELIMIT_ACTIVO = True

# Correo electrónico
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-responder@luca-pac.cl")

# Modo demostración (solo habilitar en local o staging)
DEMO_MODE = os.environ.get("DEMO_MODE", "False").lower() in ("1", "true", "yes", "si")
CRON_SECRET = os.environ.get("CRON_SECRET", "")

# Configuración de Superadmin, elevación temporal y admin técnico (# Prompt 8)
SUPERADMIN_REQUIERE_ELEVACION = os.environ.get("SUPERADMIN_REQUIERE_ELEVACION", "True").lower() in ("1", "true", "yes", "si")
SUPERADMIN_CORREO_CONTROL = os.environ.get("SUPERADMIN_CORREO_CONTROL", "control.didese@luca-pac.cl")
DJANGO_ADMIN_URL = os.environ.get("DJANGO_ADMIN_URL", "interno-dj-8f4a2c/").strip("/") + "/"

# Cabeceras de seguridad básicas (# REQ-16)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
