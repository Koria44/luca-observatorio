"""Formularios de comercios y sucursales (# REQ-02)."""
from django import forms

from apps.nucleo.validadores import normalizar_rut, normalizar_telefono_cl

from .models import Comercio, Sucursal


class FormularioComercio(forms.ModelForm):
    class Meta:
        model = Comercio
        fields = [
            "nombre_fantasia",
            "razon_social",
            "rut",
            "tipo",
            "telefono",
            "email",
            "sitio_web",
            "estado",
            "comercio_confiable",
            "activo",
        ]
        widgets = {
            "nombre_fantasia": forms.TextInput(attrs={"class": "campo-entrada"}),
            "razon_social": forms.TextInput(attrs={"class": "campo-entrada"}),
            "rut": forms.TextInput(attrs={"class": "campo-entrada", "data-validar": "rut"}),
            "tipo": forms.Select(attrs={"class": "campo-entrada"}),
            "telefono": forms.TextInput(attrs={"class": "campo-entrada", "data-validar": "telefono"}),
            "email": forms.EmailInput(attrs={"class": "campo-entrada", "data-validar": "correo"}),
            "sitio_web": forms.URLInput(attrs={"class": "campo-entrada"}),
            "estado": forms.Select(attrs={"class": "campo-entrada"}),
        }

    def clean_rut(self):
        return normalizar_rut(self.cleaned_data["rut"])

    def clean_telefono(self):
        tel = self.cleaned_data.get("telefono", "").strip()
        return normalizar_telefono_cl(tel) if tel else ""


class FormularioSucursal(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = [
            "nombre",
            "direccion",
            "direccion_normalizada",
            "sector",
            "latitud",
            "longitud",
            "origen_coordenada",
            "requiere_ajuste",
            "horario",
            "telefono",
            "activa",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "campo-entrada"}),
            "direccion": forms.TextInput(
                attrs={
                    "class": "campo-entrada",
                    "role": "combobox",
                    "aria-autocomplete": "list",
                    "aria-expanded": "false",
                    "aria-controls": "lista-sugerencias-direccion",
                    "autocomplete": "off",
                    "placeholder": "Ej: Av. Departamental 3800 o Feria La Victoria S/N",
                }
            ),
            "direccion_normalizada": forms.HiddenInput(),
            "sector": forms.Select(attrs={"class": "campo-entrada"}),
            "latitud": forms.NumberInput(attrs={"class": "campo-entrada", "step": "0.000001"}),
            "longitud": forms.NumberInput(attrs={"class": "campo-entrada", "step": "0.000001"}),
            "origen_coordenada": forms.HiddenInput(),
            "horario": forms.TextInput(attrs={"class": "campo-entrada"}),
            "telefono": forms.TextInput(attrs={"class": "campo-entrada", "data-validar": "telefono"}),
        }

    def clean(self):
        datos = super().clean()
        lat = datos.get("latitud")
        lng = datos.get("longitud")
        if lat is not None and not (-90 <= float(lat) <= 90):
            self.add_error("latitud", "La latitud debe estar entre -90 y 90.")
        if lng is not None and not (-180 <= float(lng) <= 180):
            self.add_error("longitud", "La longitud debe estar entre -180 y 180.")
        return datos
