"""Vistas de administración del catálogo maestro de productos (# REQ-01)."""
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.nucleo.permisos import rol_requerido, solo_admin

from .forms import FormularioProducto
from .models import Categoria, Producto


@solo_admin
def lista_productos(request):
    """Listado filtrable del catálogo maestro para administradores DIDESE."""
    q = request.GET.get("q", "").strip()
    cat_id = request.GET.get("categoria", "").strip()
    productos = Producto.objects.select_related("categoria", "marca")
    if q:
        productos = productos.filter(
            Q(nombre__icontains=q) | Q(marca__nombre__icontains=q) | Q(codigo_barras__icontains=q)
        )
    if cat_id.isdigit():
        productos = productos.filter(categoria_id=int(cat_id))

    return render(
        request,
        "catalogo/lista.html",
        {
            "productos": productos[:200],
            "total": productos.count(),
            "categorias": Categoria.objects.filter(activa=True),
            "q": q,
            "cat_id": cat_id,
        },
    )


@solo_admin
def crear_producto(request):
    form = FormularioProducto(request.POST or None)
    if request.method == "POST" and form.is_valid():
        prod = form.save()
        messages.success(request, f"Producto '{prod.nombre_completo}' agregado al catálogo.")
        return redirect("catalogo:lista")
    return render(request, "catalogo/formulario.html", {"form": form, "titulo": "Nuevo producto"})


@solo_admin
def editar_producto(request, pk):
    prod = get_object_or_404(Producto, pk=pk)
    form = FormularioProducto(request.POST or None, instance=prod)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Producto '{prod.nombre_completo}' actualizado.")
        return redirect("catalogo:lista")
    return render(request, "catalogo/formulario.html", {"form": form, "titulo": f"Editar {prod.nombre_completo}"})


@rol_requerido("COMERCIANTE", "FISCALIZADOR", "ADMIN")
def api_buscar_por_ean(request, codigo):
    """Busca un producto activo por código de barras EAN para el escáner móvil."""
    limpio = "".join(c for c in str(codigo) if c.isdigit())
    prod = Producto.objects.filter(codigo_barras=limpio, activo=True).select_related("marca", "categoria").first()
    if not prod:
        return JsonResponse({"encontrado": False}, status=404)
    return JsonResponse(
        {
            "encontrado": True,
            "producto": {
                "id": prod.id,
                "nombre_completo": prod.nombre_completo,
                "categoria": prod.categoria.nombre,
                "codigo_barras": prod.codigo_barras,
            },
        }
    )
