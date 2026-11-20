# Luca — Observatorio de Precios del Comercio Local (Pedro Aguirre Cerda)

Aplicación web para comparar precios del comercio local en Pedro Aguirre Cerda (almacenes, ferias libres, farmacias, panaderías y supermercados), armar listas de compras optimizadas por local y gestionar precios e indicadores desde paneles por rol.

## Qué incluye este repositorio

- **Portal ciudadano (`apps/portal/`):**
  - Buscador y comparador de precios por producto, categoría, sector y precio por unidad (`$/kg`, `$/L`, `$/un`) con historial gráfico.
  - **Mi Lista de Compras** (privada por vecino): compara producto por producto y arma rutas óptimas combinando 1, 2, 3 o más locales con desglose por parada y envío agrupado por WhatsApp.
  - **Ofertas vigentes** (expiración automática), **Ferias libres abiertas hoy**, **Alertas de baja de precio** y **Mapa interactivo** con MapLibre GL JS + Geoapify.
- **Paneles por rol (`apps/panel/`, `apps/cuentas/`, `apps/comercios/`, `apps/precios/`, `apps/catalogo/`):**
  - **Vecino:** lista privada, alertas de precio y reportes de discrepancia en sala.
  - **Comerciante:** gestión de sucursales, publicación de precios y ofertas, carga masiva Excel/CSV, logo del local, afiche PDF con código QR, confirmación de vigencia en 1 clic y comparativa privada vs. promedio comunal.
  - **Fiscalizador:** registro de precios en terreno (con escáner EAN), revisión de comercios, precios e imágenes.
  - **Administración DIDESE:** dashboard de indicadores, mapa de cobertura territorial, auditoría y exportación a Excel/PDF (`apps/reportes/`, `apps/auditoria/`).
- **Configuración de despliegue (`api/`, `config/`, `vercel.json`, `build_files.sh`):** listo para **Vercel** (Python serverless + WhiteNoise) y **Supabase** (PostgreSQL + PostGIS + Storage S3).

## Estructura del proyecto

```text
api/            Punto de entrada WSGI para Vercel (api/index.py)
apps/           Aplicaciones Django (portal, cuentas, catalogo, comercios, precios, panel, reportes, auditoria, nucleo)
config/         Configuración Django (base.py, local.py, produccion.py) y rutas principales
data/           Límite comunal GeoJSON de Pedro Aguirre Cerda
static/         CSS compilado (salida.css), JS, íconos, marca y MapLibre GL vendorizado
templates/      Plantillas HTML (Tailwind CSS + Modo oscuro + accesibilidad)
manage.py       CLI de Django
requirements.txt Dependencias Python de producción
vercel.json     Configuración de rutas, build y cron diario en Vercel
```

## Cómo ejecutarlo en local

### Requisitos
- Python 3.12+
- Node.js 20+ *(solo si vas a modificar estilos Tailwind CSS)*

### 1. Clonar e instalar dependencias

```bash
git clone <URL_DE_TU_REPOSITORIO>
cd <CARPETA_DEL_REPO>
python -m venv .venv
```

Activar entorno virtual e instalar paquetes:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Linux / macOS
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copia `.env.example` a `.env` y completa los valores:

```bash
cp .env.example .env
```

Variables principales:
- `SECRET_KEY`: clave secreta de Django.
- `DEBUG`: `True` en local, `False` en producción.
- `DATABASE_URL`: déjala vacía en local para usar SQLite (`db.sqlite3`), o pega la cadena PostgreSQL de Supabase.
- `GEOAPIFY_KEY_NAVEGADOR` y `GEOAPIFY_KEY_SERVIDOR`: claves de Geoapify para el mapa interactivo y el buscador de direcciones.
- `DEMO_MODE=True`: habilita la carga de datos de demostración.

### 3. Migrar base de datos y cargar datos iniciales

```bash
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py cargar_imagenes_demo
```

### 4. Levantar el servidor local

```bash
python manage.py runserver
```

Abre `http://127.0.0.1:8000` en tu navegador.

### Compilar CSS (solo si editas `static/src/entrada.css` o plantillas)

```bash
npm install
npm run build:css
```

## Despliegue en Supabase + Vercel

1. **Supabase:**
   - Crea un proyecto en Supabase y activa la extensión **`postgis`** (*Database → Extensions*).
   - Ejecuta las migraciones y la carga inicial apuntando a la conexión directa (puerto `5432`):
     ```bash
     DATABASE_URL="postgresql://..." python manage.py migrate --settings=config.settings.produccion
     DATABASE_URL="postgresql://..." python manage.py cargar_datos_demo --settings=config.settings.produccion
     ```
   - *(Opcional)* Crea un bucket privado `luca-archivos` en Supabase Storage si habilitarás carga de logos/fotos en producción.

2. **Vercel:**
   - Importa este repositorio en Vercel y configura las variables de entorno:
     - `DJANGO_SETTINGS_MODULE=config.settings.produccion`
     - `SECRET_KEY`
     - `DATABASE_URL` *(Transaction Pooler de Supabase, puerto `6543`)*
     - `ALLOWED_HOSTS=.vercel.app`
     - `CSRF_TRUSTED_ORIGINS=https://<tu-proyecto>.vercel.app`
     - `GEOAPIFY_KEY_NAVEGADOR` y `GEOAPIFY_KEY_SERVIDOR`
     - `DEMO_MODE=True`
     - `CRON_SECRET`
     - *(Opcional Storage)* `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_KEY`, `SUPABASE_S3_SECRET`, `SUPABASE_BUCKET`
   - Despliega el proyecto; Vercel ejecutará `build_files.sh` y publicará la aplicación vía `api/index.py`.

## Licencia

Ver archivo [LICENSE](LICENSE).
