"""
Validadores y utilidades para Chile (RUT, teléfono, correo, precios y geolocalización).

# SEGURIDAD: Toda entrada de usuario se valida en el servidor con estas funciones.
# La validación en `static/js/validadores.js` replica exactamente estas mismas reglas
# solo para comodidad del usuario.
# REQ-01, REQ-02, REQ-03, REQ-05, REQ-08, REQ-09
"""
import math
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import validate_email as django_validate_email

# Dominios con errores de tipeo frecuentes en Chile para sugerencia amable
DOMINIOS_SUGERIDOS = {
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gnail.com": "gmail.com",
    "gmail.cl": "gmail.com",
    "gmail.con": "gmail.com",
    "hotmial.com": "hotmail.com",
    "hotmal.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "outlok.com": "outlook.com",
    "outllok.com": "outlook.com",
    "yaho.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
}

# Sectores y poblaciones referenciales de la comuna de Pedro Aguirre Cerda
SECTORES_PAC = [
    ("La Victoria", "Población La Victoria"),
    ("Dávila", "Población Dávila"),
    ("Villa Sur", "Villa Sur"),
    ("Lo Valledor", "Entorno Lo Valledor"),
    ("San Joaquín / Club Hípico", "Eje Club Hípico"),
    ("Departamental", "Eje Departamental"),
    ("Pedro Aguirre Cerda Centro", "Centro Cívico PAC"),
    ("La Marina", "Sector La Marina"),
    ("Santa Adriana", "Población Santa Adriana"),
    ("Bello Horizonte", "Sector Bello Horizonte"),
    ("Otro sector PAC", "Otro sector de Pedro Aguirre Cerda"),
]


def calcular_dv_rut(cuerpo: str) -> str:
    """Calcula el dígito verificador chileno (módulo 11) para un cuerpo numérico."""
    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def normalizar_rut(valor: str) -> str:
    """
    Limpia, valida y normaliza un RUT chileno al formato canónico `12345678-5`.
    Acepta puntos, guion, espacios y `k`/`K`. Rechaza cuerpos demasiado cortos
    (< 7 dígitos) o dígitos repetidos triviales inválidos (ej. 00000000-0).
    """
    if not valor or not isinstance(valor, str):
        raise ValidationError("Ingresa tu RUT (ejemplo: 12.345.678-5).")

    limpio = re.sub(r"[\s.\-]", "", valor.strip()).upper()
    if len(limpio) < 8 or len(limpio) > 9:
        raise ValidationError("El RUT debe tener entre 7 y 8 números más su dígito verificador.")

    cuerpo, dv = limpio[:-1], limpio[-1]
    if not cuerpo.isdigit() or (not dv.isdigit() and dv != "K"):
        raise ValidationError("El RUT solo puede contener números y la letra K al final.")

    # Rechazar cuerpos nulos o secuencias triviales de ceros
    if int(cuerpo) < 1_000_000 or set(cuerpo) == {"0"}:
        raise ValidationError("El RUT ingresado no es válido.")

    dv_esperado = calcular_dv_rut(cuerpo)
    if dv != dv_esperado:
        raise ValidationError("El dígito verificador del RUT no coincide. Revísalo por favor.")

    return f"{int(cuerpo)}-{dv}"


def formatear_rut(rut_normalizado: str) -> str:
    """Formatea `12345678-5` como `12.345.678-5` para mostrar en pantalla."""
    if not rut_normalizado or "-" not in rut_normalizado:
        return rut_normalizado or ""
    cuerpo, dv = rut_normalizado.split("-", 1)
    cuerpo_fmt = f"{int(cuerpo):,}".replace(",", ".")
    return f"{cuerpo_fmt}-{dv}"


def validar_rut(valor: str) -> None:
    """Validador compatible con campos de modelos y formularios de Django."""
    normalizar_rut(valor)


def normalizar_telefono_cl(valor: str) -> str:
    """
    Valida y normaliza teléfonos chilenos a formato E.164 (`+569XXXXXXXX` o `+562XXXXXXXX`).
    Acepta entradas como `9 1234 5678`, `+56912345678`, `56912345678`, `0912345678`, `2 2345 6789`.
    """
    if not valor or not isinstance(valor, str):
        raise ValidationError("Ingresa un teléfono chileno válido (ejemplo: +56 9 1234 5678).")

    crudo = valor.strip()
    if re.search(r"[A-Za-z]", crudo):
        raise ValidationError("El teléfono no debe contener letras.")

    solo_digitos = re.sub(r"\D", "", crudo)

    # Quitar prefijo país 56 si está presente
    if solo_digitos.startswith("56") and len(solo_digitos) == 11:
        solo_digitos = solo_digitos[2:]
    elif solo_digitos.startswith("0") and len(solo_digitos) == 10:
        solo_digitos = solo_digitos[1:]

    if len(solo_digitos) != 9:
        raise ValidationError(
            "El teléfono chileno debe tener 9 dígitos (celular empezando en 9 o fijo RM empezando en 2)."
        )

    if solo_digitos[0] not in ("9", "2"):
        raise ValidationError(
            "Ingresa un celular chileno (empieza con 9) o teléfono fijo de Santiago (empieza con 2)."
        )

    return f"+56{solo_digitos}"


def validar_telefono_cl(valor: str) -> None:
    """Validador de teléfono chileno para modelos y formularios Django."""
    normalizar_telefono_cl(valor)


def sugerir_correccion_correo(correo: str) -> str | None:
    """Devuelve una sugerencia de dominio si detecta un error común de tipeo."""
    if not correo or "@" not in correo:
        return None
    usuario, dominio = correo.strip().lower().rsplit("@", 1)
    if dominio in DOMINIOS_SUGERIDOS:
        return f"{usuario}@{DOMINIOS_SUGERIDOS[dominio]}"
    return None


def normalizar_correo(valor: str) -> str:
    """Limpia espacios, pasa a minúsculas y valida sintaxis del correo."""
    if not valor or not isinstance(valor, str):
        raise ValidationError("Ingresa un correo electrónico válido.")
    limpio = valor.strip().lower()
    if " " in limpio:
        raise ValidationError("El correo electrónico no puede contener espacios.")
    try:
        django_validate_email(limpio)
    except ValidationError as exc:
        raise ValidationError("El correo electrónico no tiene un formato válido (ejemplo: nombre@correo.cl).") from exc
    return limpio


def validar_precio_clp(valor: int) -> None:
    """Valida que un precio en pesos chilenos sea un entero positivo y razonable."""
    if valor is None:
        raise ValidationError("Ingresa el precio en pesos chilenos.")
    try:
        monto = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValidationError("El precio debe ser un número entero en pesos chilenos.") from exc
    if monto <= 0:
        raise ValidationError("El precio debe ser mayor a $0.")
    if monto > 5_000_000:
        raise ValidationError("El precio supera el límite permitido para un producto de consumo local.")


def calcular_variacion_porcentual(precio_anterior: int | Decimal, precio_nuevo: int | Decimal) -> float:
    """Calcula la variación porcentual entre un precio anterior y uno nuevo."""
    if not precio_anterior or float(precio_anterior) <= 0:
        return 0.0
    return round(((float(precio_nuevo) - float(precio_anterior)) / float(precio_anterior)) * 100.0, 2)


def es_variacion_atipica(precio_anterior: int | Decimal, precio_nuevo: int | Decimal, umbral: float = 40.0) -> bool:
    """
    Detecta variaciones atípicas superiores a ±40 % respecto al precio anterior.
    # REQ-09: Alerta de anomalía simple que envía el precio a revisión manual.
    """
    if not precio_anterior or float(precio_anterior) <= 0:
        return False
    return abs(calcular_variacion_porcentual(precio_anterior, precio_nuevo)) > umbral


def distancia_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia en kilómetros entre dos coordenadas geográficas usando Haversine.
    # ADR-001 / REQ-05: Alternativa precisa y libre de GDAL para Vercel.
    """
    radio_tierra_km = 6371.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(radio_tierra_km * c, 2)
