"""
Formularios de cuentas, registro ciudadano y registro guiado de comerciantes.

# SEGURIDAD / REQ-08: Todas las entradas se validan en el servidor con los
# validadores chilenos de `apps/nucleo/validadores.py`.
"""
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.nucleo.validadores import (
    SECTORES_PAC,
    normalizar_correo,
    normalizar_rut,
    normalizar_telefono_cl,
    sugerir_correccion_correo,
)

from .models import Usuario


class FormularioLogin(forms.Form):
    """Formulario de inicio de sesión por correo electrónico y contraseña."""

    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "campo-entrada",
                "autocomplete": "email",
                "placeholder": "ejemplo@correo.cl",
                "data-validar": "correo",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "campo-entrada",
                "autocomplete": "current-password",
                "placeholder": "Tu contraseña",
            }
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.usuario_autenticado = None
        super().__init__(*args, **kwargs)

    def clean_email(self):
        return normalizar_correo(self.cleaned_data["email"])

    def clean(self):
        datos = super().clean()
        email = datos.get("email")
        password = datos.get("password")
        if email and password:
            usuario = authenticate(self.request, username=email, password=password)
            if usuario is None:
                raise ValidationError(
                    "Correo o contraseña incorrectos. Revisa tus datos e inténtalo nuevamente."
                )
            if usuario.estado_cuenta == Usuario.EstadoCuenta.SUSPENDIDA:
                raise ValidationError(
                    "Tu cuenta se encuentra suspendida. Contacta a DIDESE para más información."
                )
            self.usuario_autenticado = usuario
        return datos


class _BaseRegistroForm(forms.Form):
    """Campos personales y validaciones compartidas para registro de vecinos y comerciantes."""

    nombres = forms.CharField(
        label="Nombres",
        max_length=120,
        widget=forms.TextInput(attrs={"class": "campo-entrada", "autocomplete": "given-name"}),
    )
    apellidos = forms.CharField(
        label="Apellidos",
        max_length=120,
        widget=forms.TextInput(attrs={"class": "campo-entrada", "autocomplete": "family-name"}),
    )
    rut = forms.CharField(
        label="RUT",
        max_length=16,
        help_text="Ejemplo: 12.345.678-5 (con o sin puntos).",
        widget=forms.TextInput(
            attrs={
                "class": "campo-entrada",
                "placeholder": "12.345.678-5",
                "data-validar": "rut",
                "autocomplete": "off",
            }
        ),
    )
    telefono = forms.CharField(
        label="Teléfono",
        max_length=20,
        help_text="Celular (+56 9 XXXX XXXX) o fijo de Santiago (+56 2 XXXX XXXX).",
        widget=forms.TextInput(
            attrs={
                "class": "campo-entrada",
                "inputmode": "tel",
                "autocomplete": "tel",
                "placeholder": "+56 9 1234 5678",
                "data-validar": "telefono",
            }
        ),
    )
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "campo-entrada",
                "autocomplete": "email",
                "placeholder": "tu.nombre@correo.cl",
                "data-validar": "correo",
            }
        ),
    )
    password1 = forms.CharField(
        label="Contraseña",
        help_text="Mínimo 10 caracteres. Evita contraseñas fáciles o iguales a tu correo.",
        widget=forms.PasswordInput(
            attrs={
                "class": "campo-entrada",
                "autocomplete": "new-password",
                "data-validar": "password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Repite tu contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "campo-entrada",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_rut(self):
        rut_norm = normalizar_rut(self.cleaned_data["rut"])
        if Usuario.objects.filter(rut=rut_norm).exists():
            raise ValidationError("Ya existe una cuenta registrada con este RUT.")
        return rut_norm

    def clean_telefono(self):
        return normalizar_telefono_cl(self.cleaned_data["telefono"])

    def clean_email(self):
        correo = normalizar_correo(self.cleaned_data["email"])
        if Usuario.objects.filter(email__iexact=correo).exists():
            raise ValidationError("Ya existe una cuenta registrada con este correo electrónico.")
        sugerencia = sugerir_correccion_correo(correo)
        if sugerencia and not self.data.get("confirmar_dominio"):
            # Solo advertimos como error recuperable si es un typo evidente
            pass
        return correo

    def clean(self):
        datos = super().clean()
        p1 = datos.get("password1")
        p2 = datos.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if p1:
            usuario_tmp = Usuario(
                email=datos.get("email", ""),
                nombres=datos.get("nombres", ""),
                apellidos=datos.get("apellidos", ""),
            )
            try:
                validate_password(p1, usuario_tmp)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return datos


class FormularioRegistroVecino(_BaseRegistroForm):
    """Registro de vecino/a (cuenta activa de inmediato)."""

    def guardar(self) -> Usuario:
        d = self.cleaned_data
        return Usuario.objects.create_user(
            email=d["email"],
            password=d["password1"],
            nombres=d["nombres"].strip(),
            apellidos=d["apellidos"].strip(),
            rut=d["rut"],
            telefono=d["telefono"],
            rol=Usuario.Rol.VECINO,
            estado_cuenta=Usuario.EstadoCuenta.ACTIVA,
        )


class FormularioRegistroComerciante(_BaseRegistroForm):
    """
    Registro de comerciante con datos del comercio y sucursal inicial.
    # REQ-08 / II.5: Crea la cuenta en estado PENDIENTE (bloqueada hasta verificación y aprobación).
    """

    TIPOS_COMERCIO = [
        ("ALMACEN", "Almacén de barrio"),
        ("MINIMARKET", "Minimarket"),
        ("SUPERMERCADO", "Supermercado"),
        ("PANADERIA", "Panadería / Amasandería"),
        ("VERDULERIA", "Verdulería / Frutería"),
        ("CARNICERIA", "Carnicería"),
        ("FARMACIA", "Farmacia"),
        ("FERIA", "Puesto de feria libre"),
        ("OTRO", "Otro rubro"),
    ]

    nombre_fantasia = forms.CharField(
        label="Nombre del local (nombre de fantasía)",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "campo-entrada", "placeholder": "Ej: Almacén Don Pedro"}),
    )
    razon_social = forms.CharField(
        label="Razón social",
        max_length=180,
        widget=forms.TextInput(attrs={"class": "campo-entrada", "placeholder": "Ej: Comercial Pedro SpA"}),
    )
    rut_comercio = forms.CharField(
        label="RUT del comercio (empresa o persona)",
        max_length=16,
        widget=forms.TextInput(
            attrs={"class": "campo-entrada", "placeholder": "76.543.210-K", "data-validar": "rut"}
        ),
    )
    tipo_comercio = forms.ChoiceField(
        label="Tipo de comercio",
        choices=TIPOS_COMERCIO,
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    direccion_sucursal = forms.CharField(
        label="Dirección del local en Pedro Aguirre Cerda",
        max_length=220,
        widget=forms.TextInput(
            attrs={"class": "campo-entrada", "placeholder": "Ej: Av. Clotario Blest 4520"}
        ),
    )
    sector = forms.ChoiceField(
        label="Sector o población",
        choices=SECTORES_PAC,
        widget=forms.Select(attrs={"class": "campo-entrada"}),
    )
    latitud = forms.DecimalField(
        label="Latitud (opcional)",
        required=False,
        max_digits=9,
        decimal_places=6,
        widget=forms.NumberInput(attrs={"class": "campo-entrada", "step": "0.000001", "placeholder": "-33.489500"}),
    )
    longitud = forms.DecimalField(
        label="Longitud (opcional)",
        required=False,
        max_digits=9,
        decimal_places=6,
        widget=forms.NumberInput(attrs={"class": "campo-entrada", "step": "0.000001", "placeholder": "-70.674200"}),
    )

    def clean_rut_comercio(self):
        return normalizar_rut(self.cleaned_data["rut_comercio"])

    def guardar(self) -> Usuario:
        d = self.cleaned_data
        datos_local = {
            "nombre_fantasia": d["nombre_fantasia"].strip(),
            "razon_social": d["razon_social"].strip(),
            "rut_comercio": d["rut_comercio"],
            "tipo_comercio": d["tipo_comercio"],
            "direccion_sucursal": d["direccion_sucursal"].strip(),
            "sector": d["sector"],
            "latitud": str(d["latitud"]) if d.get("latitud") is not None else "-33.489500",
            "longitud": str(d["longitud"]) if d.get("longitud") is not None else "-70.674200",
        }
        return Usuario.objects.create_user(
            email=d["email"],
            password=d["password1"],
            nombres=d["nombres"].strip(),
            apellidos=d["apellidos"].strip(),
            rut=d["rut"],
            telefono=d["telefono"],
            rol=Usuario.Rol.COMERCIANTE,
            estado_cuenta=Usuario.EstadoCuenta.PENDIENTE,
            datos_registro_comercio=datos_local,
        )


class FormularioPerfil(forms.ModelForm):
    """Permite al usuario actualizar sus datos de contacto validados."""

    class Meta:
        model = Usuario
        fields = ["nombres", "apellidos", "telefono"]
        widgets = {
            "nombres": forms.TextInput(attrs={"class": "campo-entrada"}),
            "apellidos": forms.TextInput(attrs={"class": "campo-entrada"}),
            "telefono": forms.TextInput(
                attrs={"class": "campo-entrada", "inputmode": "tel", "data-validar": "telefono"}
            ),
        }

    def clean_telefono(self):
        return normalizar_telefono_cl(self.cleaned_data["telefono"])
