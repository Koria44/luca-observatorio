"""Formularios de gestión del catálogo maestro (# REQ-01)."""
from django import forms

from .models import Categoria, Marca, Producto


class FormularioProducto(forms.ModelForm):
    """Alta y edición de productos maestros evitando duplicados."""

    class Meta:
        model = Producto
        fields = [
            "nombre",
            "categoria",
            "marca",
            "formato",
            "contenido",
            "unidad_medida",
            "codigo_barras",
            "es_canasta_basica",
            "es_estrella",
            "activo",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "campo-entrada"}),
            "categoria": forms.Select(attrs={"class": "campo-entrada"}),
            "marca": forms.Select(attrs={"class": "campo-entrada"}),
            "formato": forms.TextInput(attrs={"class": "campo-entrada", "placeholder": "bolsa, botella, caja…"}),
            "contenido": forms.NumberInput(attrs={"class": "campo-entrada", "step": "0.01", "min": "0.01"}),
            "unidad_medida": forms.Select(attrs={"class": "campo-entrada"}),
            "codigo_barras": forms.TextInput(attrs={"class": "campo-entrada", "placeholder": "EAN opcional"}),
        }


class FormularioCategoria(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "icono", "color", "orden", "activa"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "campo-entrada"}),
            "icono": forms.TextInput(attrs={"class": "campo-entrada"}),
            "color": forms.TextInput(attrs={"class": "campo-entrada", "type": "color"}),
            "orden": forms.NumberInput(attrs={"class": "campo-entrada"}),
        }


class FormularioMarca(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ["nombre"]
        widgets = {"nombre": forms.TextInput(attrs={"class": "campo-entrada"})}
