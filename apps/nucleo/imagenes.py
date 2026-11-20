"""
Servicio único y seguro de procesamiento y almacenamiento de imágenes (# REQ-01, 02, 12, 16).

# SEGURIDAD (Prompt 5 Sección 3.2):
- Valida el tipo REAL del archivo con Pillow (rechaza SVG, HTML, binarios renombrados a .jpg).
- Límite estricto <= 4 MB (compatible con cuerpo de petición de Vercel ~4,5 MB) y <= 6000 px.
- Protección contra decompression bomb (`Image.MAX_IMAGE_PIXELS`).
- Corrige orientación EXIF antes de re-codificar completamente la imagen SIN metadatos EXIF/GPS.
- Genera variantes WebP (200/480/960 px para productos; 240/480 px para logos) con nombres UUID.
- Separa bucket/directorio `pendientes` (privado) y `publico` (aprobadas con caché inmutable).
- Aplica límite de tasa de 10 subidas por hora por usuario.
"""
import time
import uuid
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps

# Protección contra decompression bomb
Image.MAX_IMAGE_PIXELS = 36_000_000

MAX_TAMANO_BYTES = 4 * 1024 * 1024  # 4 MB
MAX_LADO_PX = 6000
FORMATOS_PERMITIDOS = {"JPEG", "PNG", "WEBP"}

_SUBIDAS_POR_USUARIO: dict[str, list[float]] = defaultdict(list)


def verificar_limite_subidas(usuario, max_por_hora: int = 10) -> None:
    """Limita a 10 subidas por hora por usuario (# SEGURIDAD / Sección 3.2)."""
    if not getattr(settings, "RATELIMIT_SUBIDAS_ACTIVO", True):
        return
    clave = str(getattr(usuario, "id", "anon"))
    ahora = time.time()
    marcas = [t for t in _SUBIDAS_POR_USUARIO[clave] if ahora - t < 3600]
    if len(marcas) >= max_por_hora:
        raise ValidationError("Alcanzaste el límite de 10 imágenes por hora. Inténtalo más tarde.")
    marcas.append(ahora)
    _SUBIDAS_POR_USUARIO[clave] = marcas


def _dir_base_media() -> Path:
    return Path(getattr(settings, "MEDIA_ROOT", Path(settings.BASE_DIR) / "media"))


def _guardar_bytes(subruta: str, contenido: bytes, publico: bool) -> str:
    """
    Persiste los bytes procesados en `publico/` o `pendientes/` (local o S3 Supabase).
    Devuelve la ruta lógica relativa (`publico/...` o `pendientes/...`).
    """
    prefijo = "publico" if publico else "pendientes"
    ruta_rel = f"{prefijo}/{subruta.lstrip('/')}"

    if getattr(settings, "SUPABASE_S3_ENDPOINT", "") and getattr(settings, "SUPABASE_S3_KEY", ""):
        import boto3

        bucket = (
            getattr(settings, "SUPABASE_BUCKET_PUBLICO", "luca-publico")
            if publico
            else getattr(settings, "SUPABASE_BUCKET_PENDIENTES", "luca-pendientes")
        )
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.SUPABASE_S3_ENDPOINT,
            aws_access_key_id=settings.SUPABASE_S3_KEY,
            aws_secret_access_key=settings.SUPABASE_S3_SECRET,
        )
        extra = {"ContentType": "image/webp"}
        if publico:
            extra["CacheControl"] = "public, max-age=31536000, immutable"
        s3.put_object(Bucket=bucket, Key=subruta.lstrip("/"), Body=contenido, **extra)
        return ruta_rel

    destino = _dir_base_media() / ruta_rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return ruta_rel


def promover_a_publico(ruta_rel: str) -> str:
    """Copia una variante desde `pendientes/` hacia `publico/` al aprobarse (# Sección 3.2)."""
    if not ruta_rel or ruta_rel.startswith("publico/"):
        return ruta_rel
    subruta = ruta_rel.removeprefix("pendientes/")
    origen = _dir_base_media() / ruta_rel
    if origen.exists():
        return _guardar_bytes(subruta, origen.read_bytes(), publico=True)
    return f"publico/{subruta}"


def eliminar_de_publico(ruta_rel: str) -> None:
    """Elimina una variante del almacenamiento público al rechazar o retirar."""
    if not ruta_rel or not ruta_rel.startswith("publico/"):
        return
    archivo = _dir_base_media() / ruta_rel
    if archivo.exists():
        archivo.unlink(missing_ok=True)


def url_publica_imagen(ruta_rel: str) -> str:
    """Devuelve la URL pública servible para una imagen aprobada."""
    if not ruta_rel:
        return ""
    if ruta_rel.startswith("http://") or ruta_rel.startswith("https://") or ruta_rel.startswith("/"):
        return ruta_rel
    if getattr(settings, "SUPABASE_URL", "") and ruta_rel.startswith("publico/"):
        bucket = getattr(settings, "SUPABASE_BUCKET_PUBLICO", "luca-publico")
        sub = ruta_rel.removeprefix("publico/")
        return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/{sub}"
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    return f"{media_url.rstrip('/')}/{ruta_rel.lstrip('/')}"


def leer_bytes_pendiente(ruta_rel: str) -> bytes | None:
    """Lee una imagen pendiente desde el almacenamiento privado para revisión autorizada."""
    if not ruta_rel or not ruta_rel.startswith("pendientes/"):
        return None
    archivo = _dir_base_media() / ruta_rel
    if archivo.exists() and archivo.is_file():
        return archivo.read_bytes()
    return None


def validar_y_abrir_imagen(archivo) -> Image.Image:
    """Valida tamaño, formato real con Pillow (sin confiar en extensión) y dimensiones."""
    if archivo is None:
        raise ValidationError("Debes seleccionar una imagen.")

    datos = archivo.read() if hasattr(archivo, "read") else bytes(archivo)
    if len(datos) == 0:
        raise ValidationError("El archivo de imagen está vacío.")
    if len(datos) > MAX_TAMANO_BYTES:
        raise ValidationError("La imagen supera el máximo permitido de 4 MB.")

    # Rechazar SVG u otros archivos XML/texto explícitamente (# SEGURIDAD)
    cabecera = datos[:256].lstrip().lower()
    if b"<svg" in cabecera or cabecera.startswith(b"<?xml") or b"<html" in cabecera:
        raise ValidationError("Por seguridad no se permiten archivos SVG ni HTML. Sube JPG, PNG o WebP.")

    try:
        with Image.open(BytesIO(datos)) as img_check:
            formato = (img_check.format or "").upper()
            if formato not in FORMATOS_PERMITIDOS:
                raise ValidationError("Formato no admitido. Sube únicamente imágenes JPG, PNG o WebP.")
            img_check.verify()

        # Reabrir tras verify() para procesar y aplicar transposición EXIF
        img = Image.open(BytesIO(datos))
        img.load()
        if img.width > MAX_LADO_PX or img.height > MAX_LADO_PX:
            raise ValidationError(f"La imagen excede el máximo de {MAX_LADO_PX} píxeles por lado.")
        img = ImageOps.exif_transpose(img)
        return img
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("El archivo no es una imagen válida o está dañado.") from exc


def _codificar_webp_sin_exif(img: Image.Image, max_lado: int, conservar_alfa: bool = False) -> tuple[bytes, int, int]:
    """
    Redimensiona manteniendo proporción y re-codifica a WebP en un lienzo limpio,
    eliminando 100 % de metadatos EXIF y GPS (# SEGURIDAD / Sección 3.2).
    """
    copia = img.copy()
    copia.thumbnail((max_lado, max_lado), Image.Resampling.LANCZOS)

    modo = "RGBA" if (conservar_alfa and copia.mode in ("RGBA", "LA", "P")) else "RGB"
    limpia = Image.new(modo, copia.size)
    limpia.paste(copia.convert(modo))

    salida = BytesIO()
    limpia.save(salida, format="WEBP", quality=82, method=4)
    return salida.getvalue(), limpia.width, limpia.height


def procesar_imagen_producto(archivo, publico: bool = False) -> dict:
    """Procesa una foto de producto y genera variantes WebP 200, 480 y 960 px sin EXIF/GPS."""
    img = validar_y_abrir_imagen(archivo)
    uid = uuid.uuid4().hex

    b_mini, _, _ = _codificar_webp_sin_exif(img, 200, conservar_alfa=False)
    b_media, _, _ = _codificar_webp_sin_exif(img, 480, conservar_alfa=False)
    b_grande, ancho, alto = _codificar_webp_sin_exif(img, 960, conservar_alfa=False)

    return {
        "archivo_miniatura": _guardar_bytes(f"productos/{uid}_200.webp", b_mini, publico=publico),
        "archivo_media": _guardar_bytes(f"productos/{uid}_480.webp", b_media, publico=publico),
        "archivo_grande": _guardar_bytes(f"productos/{uid}_960.webp", b_grande, publico=publico),
        "ancho": ancho,
        "alto": alto,
        "tamano_bytes": len(b_grande),
    }


def procesar_logo_comercio(archivo, publico: bool = False) -> dict:
    """Procesa un logo de comercio en variantes 240 y 480 px WebP conservando transparencia."""
    img = validar_y_abrir_imagen(archivo)
    uid = uuid.uuid4().hex

    b_240, _, _ = _codificar_webp_sin_exif(img, 240, conservar_alfa=True)
    b_480, ancho, alto = _codificar_webp_sin_exif(img, 480, conservar_alfa=True)

    return {
        "logo_miniatura": _guardar_bytes(f"logos/{uid}_240.webp", b_240, publico=publico),
        "logo": _guardar_bytes(f"logos/{uid}_480.webp", b_480, publico=publico),
        "ancho": ancho,
        "alto": alto,
    }
