"""
Autenticación en dos pasos TOTP (RFC 6238) sin dependencias externas frágiles (# Prompt 7 Sección 1.4).
Obligatoria para SUPERADMIN y personal municipal (ADMIN, FISCALIZADOR) y opcional para comerciantes.
Incluye códigos de recuperación de un solo uso almacenados como hash SHA-256.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time


def generar_secreto_totp() -> str:
    """Genera un secreto aleatorio Base32 de 160 bits para apps autenticadoras."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _codigo_totp_para_contador(secreto_b32: str, contador: int, digitos: int = 6) -> str:
    pad = "=" * ((8 - len(secreto_b32) % 8) % 8)
    clave = base64.b32decode(secreto_b32.upper() + pad, casefold=True)
    msg = struct.pack(">Q", contador)
    digest = hmac.new(clave, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    codigo = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(codigo % (10**digitos)).zfill(digitos)


def generar_codigo_totp(secreto_b32: str, ahora: float | None = None, paso: int = 30) -> str:
    """Devuelve el código TOTP de 6 dígitos vigente en el instante `ahora`."""
    ts = int(ahora if ahora is not None else time.time())
    return _codigo_totp_para_contador(secreto_b32, ts // paso)


def verificar_codigo_totp(secreto_b32: str, codigo: str, ventana: int = 1, paso: int = 30) -> bool:
    """Verifica un código TOTP de 6 dígitos con tolerancia de ±`ventana` intervalos de 30 s."""
    limpio = (codigo or "").strip().replace(" ", "")
    if not secreto_b32 or len(limpio) != 6 or not limpio.isdigit():
        return False
    contador_actual = int(time.time()) // paso
    for delta in range(-ventana, ventana + 1):
        esperado = _codigo_totp_para_contador(secreto_b32, contador_actual + delta)
        if hmac.compare_digest(esperado, limpio):
            return True
    return False


def generar_codigos_recuperacion(cantidad: int = 8) -> tuple[list[str], list[str]]:
    """
    Genera `cantidad` códigos de recuperación de un solo uso.
    Devuelve `(codigos_en_claro_para_mostrar_una_vez, hashes_para_guardar_en_bd)`.
    """
    planos = [f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}" for _ in range(cantidad)]
    hashes = [hashlib.sha256(c.encode("utf-8")).hexdigest() for c in planos]
    return planos, hashes


def consumir_codigo_recuperacion(usuario, codigo: str) -> bool:
    """Verifica y consume (un solo uso) un código de recuperación del usuario."""
    limpio = (codigo or "").strip().upper()
    if not limpio or not usuario.codigos_recuperacion:
        return False
    h = hashlib.sha256(limpio.encode("utf-8")).hexdigest()
    for idx, guardado in enumerate(usuario.codigos_recuperacion):
        if hmac.compare_digest(guardado, h):
            restantes = list(usuario.codigos_recuperacion)
            restantes.pop(idx)
            usuario.codigos_recuperacion = restantes
            usuario.save(update_fields=["codigos_recuperacion"])
            return True
    return False
