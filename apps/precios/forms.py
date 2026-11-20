"""Formularios de ingreso de precios y ofertas (# REQ-03)."""
from django import forms
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.comercios.models import Sucursal

from .models import Precio


class FormularioPrecio(forms.ModelForm):
    """Formulario guiado para registrar o actualizar el precio de un producto."""

    class Meta:
        model = Precio
        fields = [
            "producto",
            "sucursal",
            "precio_normal",
            "precio_oferta",
            "vigencia_desde",
            "vigencia_hasta",
            "compra_minima",
            "medio_pago",
            "requiere_membresia",
            "nombre_membresia",
            "condiciones",
            "stock_confirmado",
        ]
        widgets = {
            "producto": forms.Select(attrs={"class": "campo-entrada"}),
            "sucursal": forms.Select(attrs={"class": "campo-entrada"}),
            "precio_normal": forms.NumberInput(attrs={"class": "campo-entrada", "min": "1", "inputmode": "numeric"}),
            "precio_oferta": forms.NumberInput(attrs={"class": "campo-entrada", "min": "1", "inputmode": "numeric"}),
            "vigencia_desde": forms.DateInput(attrs={"class": "campo-entrada", "type": "date"}),
            "vigencia_hasta": forms.DateInput(attrs={"class": "campo-entrada", "type": "date"}),
            "compra_minima": forms.NumberInput(attrs={"class": "campo-entrada", "min": "1"}),
            "medio_pago": forms.TextInput(attrs={"class": "campo-entrada", "placeholder": "Ej: Débito, Efectivo, Tarjeta tienda"}),
            "nombre_membresia": forms.TextInput(attrs={"class": "campo-entrada", "placeholder": "Ej: Club Vecino"}),
            "condiciones": forms.Textarea(attrs={"class": "campo-entrada", "rows": 2}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = Producto.objects.filter(activo=True).select_related("marca")
        self.fields["vigencia_desde"].initial = timezone.localdate()
        if usuario and usuario.rol == "COMERCIANTE":
            # SEGURIDAD: El comerciante solo puede elegir sus propias sucursales
            self.fields["sucursal"].queryset = Sucursal.objects.filter(
                comercio__propietario=usuario, activa=True
            ).select_related("comercio")
        else:
            self.fields["sucursal"].queryset = Sucursal.objects.filter(activa=True).select_related("comercio")

    def clean(self):
        datos = super().clean()
        normal = datos.get("precio_normal")
        oferta = datos.get("precio_oferta")
        desde = datos.get("vigencia_desde")
        hasta = datos.get("vigencia_hasta")
        if normal and oferta and oferta >= normal:
            self.add_error("precio_oferta", "El precio de oferta debe ser menor que el precio normal.")
        if desde and hasta and hasta < desde:
            self.add_error("vigencia_hasta", "La fecha de término debe ser igual o posterior a la fecha de inicio.")
        return datos
