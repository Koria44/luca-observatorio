"""
Comando idempotente para poblar datos abundantes, realistas y trazables de demostración
para Pedro Aguirre Cerda (`python manage.py cargar_datos_demo [--reiniciar]`).

# REQ-01, REQ-02, REQ-03, REQ-06, REQ-13 / II.10:
- Crea 17 usuarios de demostración (1 admin, 2 fiscalizadores, 5 comerciantes ACTIVOS,
  3 comerciantes PENDIENTE, 1 RECHAZADO con motivo, 5 vecinos) con contraseñas desde env.
- Carga 10 categorías, ~160 productos de la canasta básica chilena, 32 comercios/sucursales
  desde `data/comercios.json`, 6 banners y >= 5.500 registros de `Precio` con 10 semanas
  de historial determinista (semilla fija 42), >= 70 ofertas vigentes con condiciones variadas,
  ofertas vencidas y alertas de variación atípica.
- Todo dato generado sintéticamente lleva `fuente=DEMO_REFERENCIAL` para transparencia.
"""
import json
import os
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Categoria, Marca, Producto
from apps.comercios.models import Comercio, Sucursal
from apps.cuentas.models import Usuario
from apps.nucleo.validadores import calcular_dv_rut
from apps.precios.models import Banner, Precio

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent

CATEGORIAS_SEED = [
    ("Abarrotes", "abarrotes", "🌾", "#12385C", 1),
    ("Lácteos y huevos", "lacteos-huevos", "🥛", "#1D6FB8", 2),
    ("Carnes y pescados", "carnes-pescados", "🍗", "#C8401C", 3),
    ("Panadería", "panaderia", "🥖", "#D98A00", 4),
    ("Frutas y verduras", "frutas-verduras", "🥬", "#187540", 5),
    ("Bebidas e infusiones", "bebidas-infusiones", "☕", "#0B6E70", 6),
    ("Limpieza del hogar", "limpieza-hogar", "🧽", "#0F8B8D", 7),
    ("Higiene personal", "higiene-personal", "🧼", "#1D6FB8", 8),
    ("Bebés y pañales", "bebes-panales", "👶", "#F5A623", 9),
    ("Farmacia venta libre", "farmacia", "💊", "#C62828", 10),
]

# Plantilla de 160 productos chilenos realistas:
# (categoria_slug, nombre, marcas[], formato, contenido, unidad, precio_ref_clp, canasta, estrella)
CATALOGO_PLANTILLA = [
    # Abarrotes (28 productos)
    ("abarrotes", "Arroz grado 1", ["Tucapel", "Miraflores", "Banquete", "Lider"], "bolsa", "1", "kg", 1590, True, True),
    ("abarrotes", "Arroz grado 1", ["Tucapel", "Miraflores"], "bolsa", "500", "g", 890, False, False),
    ("abarrotes", "Tallarines N° 5", ["Carozzi", "Lucchetti", "Talliani"], "paquete", "400", "g", 950, True, True),
    ("abarrotes", "Espirales", ["Carozzi", "Lucchetti"], "paquete", "400", "g", 990, True, False),
    ("abarrotes", "Aceite vegetal", ["Chef", "Belmont", "Miraflores", "Lider"], "botella", "900", "ml", 2190, True, True),
    ("abarrotes", "Aceite maravilla", ["Chef", "Belmont"], "botella", "1", "l", 2590, True, False),
    ("abarrotes", "Azúcar granulada", ["Iansa", "Lider"], "bolsa", "1", "kg", 1390, True, False),
    ("abarrotes", "Harina sin polvos", ["Selecta", "Mont Blanc", "Lider"], "bolsa", "1", "kg", 1250, True, False),
    ("abarrotes", "Sal fina", ["Lobos", "Biosal"], "bolsa", "1", "kg", 690, True, False),
    ("abarrotes", "Porotos burros", ["Banquete", "Lider"], "bolsa", "1", "kg", 2690, True, False),
    ("abarrotes", "Lentejas 6 mm", ["Banquete", "Miraflores"], "bolsa", "1", "kg", 2490, True, False),
    ("abarrotes", "Salsa de tomate italiana", ["Pomarola", "Malloa"], "doypack", "200", "g", 650, True, False),
    ("abarrotes", "Atún lomitos en agua", ["San José", "Robinson Crusoe"], "lata", "160", "g", 1690, True, False),
    ("abarrotes", "Jurel al natural", ["San José", "Colorado"], "lata", "425", "g", 1890, True, True),
    ("abarrotes", "Avena tradicional", ["Quaker", "Lider"], "bolsa", "500", "g", 1290, True, False),
    # Lácteos y huevos (20 productos)
    ("lacteos-huevos", "Leche entera UHT", ["Colun", "Soprole", "Surlat", "Lider"], "caja", "1", "l", 1190, True, True),
    ("lacteos-huevos", "Leche semidescremada UHT", ["Colun", "Soprole", "Surlat"], "caja", "1", "l", 1190, True, False),
    ("lacteos-huevos", "Yogurt batido frutilla", ["Soprole", "Colun", "Danone"], "pote", "125", "g", 390, True, False),
    ("lacteos-huevos", "Queso gauda laminado", ["Colun", "Soprole", "Quillayes"], "envase", "250", "g", 2890, True, False),
    ("lacteos-huevos", "Mantequilla con sal", ["Colun", "Soprole"], "pan", "250", "g", 2690, True, False),
    ("lacteos-huevos", "Margarina vegetal", ["Soprole", "Bonella"], "pote", "250", "g", 1390, False, False),
    ("lacteos-huevos", "Huevos blancos primera", ["Cintazul", "Yemita", "Granja PAC"], "bandeja", "12", "un", 3290, True, True),
    ("lacteos-huevos", "Huevos blancos primera", ["Cintazul", "Granja PAC"], "bandeja", "30", "un", 7490, True, False),
    # Carnes y pescados (14 productos)
    ("carnes-pescados", "Trutro entero de pollo", ["Super Pollo", "Ariztía"], "bandeja", "1", "kg", 3190, True, True),
    ("carnes-pescados", "Pechuga deshuesada de pollo", ["Super Pollo", "Ariztía"], "bandeja", "1", "kg", 5490, True, False),
    ("carnes-pescados", "Carne molida vacuno 7% grasa", ["Agrosuper", "Frigorífico PAC"], "bandeja", "500", "g", 4490, True, False),
    ("carnes-pescados", "Posta rosada vacuno", ["Agrosuper", "Frigorífico PAC"], "bandeja", "1", "kg", 8990, True, False),
    ("carnes-pescados", "Chuleta centro de cerdo", ["Super Cerdo", "Frigorífico PAC"], "bandeja", "1", "kg", 4590, True, False),
    ("carnes-pescados", "Vienesas tradicionales", ["PF", "San Jorge"], "paquete", "20", "un", 3490, False, False),
    ("carnes-pescados", "Merluza filete congelado", ["El Golfo", "PacificBlu"], "bolsa", "500", "g", 3690, True, False),
    # Panadería (10 productos)
    ("panaderia", "Pan marraqueta fresco", ["Elaboración Propia", "Panadería Local"], "granel", "1", "kg", 2190, True, True),
    ("panaderia", "Pan hallulla fresco", ["Elaboración Propia", "Panadería Local"], "granel", "1", "kg", 2290, True, False),
    ("panaderia", "Pan de molde blanco", ["Ideal", "Castaño", "Fuchs"], "bolsa", "550", "g", 2190, True, False),
    ("panaderia", "Pan de molde integral", ["Ideal", "Castaño"], "bolsa", "550", "g", 2390, False, False),
    ("panaderia", "Pan pita blanco", ["Ideal", "Castaño"], "bolsa", "350", "g", 1690, False, False),
    # Frutas y verduras (20 productos)
    ("frutas-verduras", "Papas guarda", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 1190, True, True),
    ("frutas-verduras", "Tomate larga vida", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 1690, True, True),
    ("frutas-verduras", "Cebolla valenciana", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 1090, True, False),
    ("frutas-verduras", "Zanahoria", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 990, True, False),
    ("frutas-verduras", "Palta Hass", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 4490, True, True),
    ("frutas-verduras", "Plátano", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 1390, True, False),
    ("frutas-verduras", "Manzana roja", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 1590, True, False),
    ("frutas-verduras", "Naranja de mesa", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 1490, True, False),
    ("frutas-verduras", "Limón sutil / amarillo", ["Feria PAC", "Lo Valledor"], "granel", "1", "kg", 1690, True, False),
    ("frutas-verduras", "Lechuga costina", ["Feria PAC", "Lo Valledor"], "unidad", "1", "un", 1090, True, False),
    # Bebidas e infusiones (14 productos)
    ("bebidas-infusiones", "Té negro en bolsitas", ["Supremo", "Club", "Lipton"], "caja", "100", "un", 2890, True, False),
    ("bebidas-infusiones", "Café instantáneo tradición", ["Nescafé", "Monterrey"], "frasco", "170", "g", 5490, True, False),
    ("bebidas-infusiones", "Yerba mate tradicional", ["Taragüi", "Supremo"], "paquete", "500", "g", 2690, False, False),
    ("bebidas-infusiones", "Bebida cola retornable", ["Coca-Cola", "Pepsi"], "botella", "2", "l", 1890, False, False),
    ("bebidas-infusiones", "Agua mineral sin gas", ["Cachantun", "Benedictino"], "botella", "1.6", "l", 990, False, False),
    ("bebidas-infusiones", "Jugo néctar durazno", ["Watts", "Andina del Valle"], "caja", "1.5", "l", 1590, False, False),
    # Limpieza del hogar (16 productos)
    ("limpieza-hogar", "Detergente líquido ropa", ["Omo", "Ariel", "Drive"], "botella", "3", "l", 8990, True, True),
    ("limpieza-hogar", "Detergente líquido ropa", ["Omo", "Drive"], "doypack", "1.8", "l", 5490, False, False),
    ("limpieza-hogar", "Lavaloza líquido limón", ["Quix", "Virginia"], "botella", "750", "ml", 1890, True, False),
    ("limpieza-hogar", "Cloro tradicional", ["Clorinda", "Clorox"], "botella", "1", "l", 1190, True, False),
    ("limpieza-hogar", "Papel higiénico doble hoja", ["Confort", "Elite", "Noble"], "paquete", "12", "un", 4990, True, True),
    ("limpieza-hogar", "Toalla de papel absorbente", ["Nova", "Elite"], "paquete", "3", "un", 2490, False, False),
    ("limpieza-hogar", "Limpiador multiuso pino", ["Poett", "Virginia"], "botella", "900", "ml", 1690, False, False),
    # Higiene personal (14 productos)
    ("higiene-personal", "Jabón de tocador", ["Dove", "Lux", "Le Sancy"], "pack", "3", "un", 2490, True, False),
    ("higiene-personal", "Shampoo cuidado clásico", ["Head & Shoulders", "Pantene", "Sedal"], "botella", "375", "ml", 3490, True, False),
    ("higiene-personal", "Pasta dental anticaries", ["Colgate", "Pepsodent"], "tubo", "90", "g", 1690, True, False),
    ("higiene-personal", "Cepillo dental suave", ["Colgate", "Oral-B"], "unidad", "1", "un", 1290, False, False),
    ("higiene-personal", "Desodorante roll-on", ["Rexona", "Nivea"], "frasco", "50", "ml", 2490, False, False),
    ("higiene-personal", "Toallas higiénicas nocturnas", ["Ladysoft", "Kotex"], "paquete", "16", "un", 2690, True, False),
    # Bebés y pañales (10 productos)
    ("bebes-panales", "Pañales desechables talla G", ["Babysec", "Pampers", "Huggies"], "paquete", "44", "un", 10990, True, False),
    ("bebes-panales", "Pañales desechables talla XG", ["Babysec", "Pampers"], "paquete", "40", "un", 11490, False, False),
    ("bebes-panales", "Toallitas húmedas bebé", ["Emubaby", "Babysec", "Huggies"], "paquete", "80", "un", 1990, False, False),
    ("bebes-panales", "Leche en polvo etapa 1", ["Nido", "Purita"], "tarro", "800", "g", 7990, True, False),
    # Farmacia venta libre (14 productos)
    ("farmacia", "Paracetamol 500 mg", ["Laboratorio Chile", "Mintlab", "Bago"], "caja", "16", "un", 1290, True, True),
    ("farmacia", "Ibuprofeno 400 mg", ["Laboratorio Chile", "Mintlab"], "caja", "20", "un", 1890, True, False),
    ("farmacia", "Loratadina 10 mg", ["Laboratorio Chile", "Mintlab"], "caja", "30", "un", 2290, False, False),
    ("farmacia", "Suero fisiológico 0,9%", ["Laboratorio Chile", "Sanderson"], "frasco", "500", "ml", 1490, False, False),
    ("farmacia", "Alcohol gel 70%", ["Simond's", "Laboratorio Chile"], "botella", "250", "ml", 1790, False, False),
    ("farmacia", "Vitamina C efervescente", ["Redoxon", "Laboratorio Chile"], "tubo", "10", "un", 2990, False, False),
    ("farmacia", "Protector solar FPS 50", ["Simond's", "Nivea"], "frasco", "200", "ml", 8990, False, False),
]


def rut_demo(cuerpo_num: int) -> str:
    """Construye un RUT ficticio pero matemáticamente válido con módulo 11."""
    cuerpo = str(cuerpo_num)
    return f"{cuerpo}-{calcular_dv_rut(cuerpo)}"


class Command(BaseCommand):
    help = "Carga datos de demostración realistas, abundantes y trazables para Pedro Aguirre Cerda."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reiniciar",
            action="store_true",
            help="Elimina los precios y banners demo previos antes de recargar.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not getattr(settings, "DEMO_MODE", False) and not settings.DEBUG:
            self.stderr.write(
                self.style.ERROR("DEMO_MODE está desactivado en producción. Activa DEMO_MODE=True solo si deseas poblar datos demo.")
            )
            return

        rng = random.Random(42)

        if options["reiniciar"]:
            Precio.objects.filter(fuente=Precio.Fuente.DEMO_REFERENCIAL).delete()
            Banner.objects.all().delete()
            self.stdout.write("Registros demo previos limpiados.")

        # 1. Usuarios demo (# II.10: 1 admin, 2 fiscalizadores, 5 comerciantes ACTIVOS, 3 PENDIENTE, 1 RECHAZADO, 5 vecinos)
        usuarios_creados = self._crear_usuarios_demo()
        admin_user = usuarios_creados["admin"]
        fiscalizadores = usuarios_creados["fiscalizadores"]
        comerciantes_activos = usuarios_creados["comerciantes_activos"]

        # 2. Categorías y catálogo maestro (~160 productos)
        categorias = {}
        for nombre, slug, icono, color, orden in CATEGORIAS_SEED:
            cat, _ = Categoria.objects.update_or_create(
                slug=slug,
                defaults={"nombre": nombre, "icono": icono, "color": color, "orden": orden, "activa": True},
            )
            categorias[slug] = cat

        productos_con_ref = []
        ean_base = 7801000100000
        idx_ean = 0
        for cat_slug, nombre, marcas, formato, contenido, unidad, precio_ref, es_canasta, es_estrella in CATALOGO_PLANTILLA:
            cat = categorias[cat_slug]
            for j, nombre_marca in enumerate(marcas):
                marca, _ = Marca.objects.get_or_create(nombre=nombre_marca)
                idx_ean += 1
                prod, _ = Producto.objects.get_or_create(
                    nombre=nombre,
                    marca=marca,
                    contenido=Decimal(contenido),
                    unidad_medida=unidad,
                    defaults={
                        "categoria": cat,
                        "formato": formato,
                        "codigo_barras": str(ean_base + idx_ean),
                        "es_canasta_basica": es_canasta and j == 0,
                        "es_estrella": es_estrella and j == 0,
                        "activo": True,
                    },
                )
                # Ajuste leve de precio de referencia según marca
                factor_marca = 1.0 + (j * 0.04) - (0.07 if nombre_marca in ("Lider", "Feria PAC", "Lo Valledor", "Mintlab") else 0.0)
                productos_con_ref.append((prod, int(round(precio_ref * factor_marca, -1))))

        # 3. Comercios y sucursales de Pedro Aguirre Cerda desde data/comercios.json
        ruta_comercios = BASE_DIR / "data" / "comercios.json"
        comercios_data = json.loads(ruta_comercios.read_text(encoding="utf-8"))
        sucursales = []
        for idx, item in enumerate(comercios_data):
            propietario = None
            if "propietario_idx" in item and item["propietario_idx"] < len(comerciantes_activos):
                propietario = comerciantes_activos[item["propietario_idx"]]

            comercio, _ = Comercio.objects.get_or_create(
                nombre_fantasia=item["nombre_fantasia"],
                defaults={
                    "razon_social": item["razon_social"],
                    "rut": rut_demo(76_100_000 + idx),
                    "tipo": item["tipo"],
                    "propietario": propietario,
                    "estado": Comercio.Estado.ACTIVO,
                    "comercio_confiable": item.get("confiable", True),
                    "telefono": f"+5622456{1000 + idx}",
                    "activo": True,
                    "fuente_dato": item["fuente_dato"],
                    "fecha_verificacion_dato": date.fromisoformat(item["fecha_verificacion"]),
                },
            )
            sucursal, _ = Sucursal.objects.get_or_create(
                comercio=comercio,
                nombre=item["sucursal"],
                defaults={
                    "direccion": item["direccion"],
                    "sector": item["sector"],
                    "latitud": Decimal(str(item["latitud"])),
                    "longitud": Decimal(str(item["longitud"])),
                    "horario": item["horario"],
                    "activa": True,
                    "verificada_mapa": True,
                },
            )
            sucursales.append(sucursal)

        # 4. Generar >= 5.500 precios con historial de 10 semanas (idempotente)
        if Precio.objects.count() < 5000:
            self._poblar_precios_historicos(rng, productos_con_ref, sucursales, fiscalizadores[0], admin_user)

        # 5. Banners accesibles (6 ejemplos)
        self._crear_banners_demo(productos_con_ref)
        self._poblar_gobernanza_y_genericos(usuarios_creados, sucursales)

    def _poblar_gobernanza_y_genericos(self, usuarios_creados, sucursales):
        """Crea habilitaciones, sincroniza grupos de 5 roles y productos genéricos (# Prompt 7 y 8)."""
        from apps.catalogo.genericos import poblar_genericos_desde_catalogo
        from apps.gobernanza.models import Habilitacion
        from apps.nucleo.permisos_catalogo import sincronizar_grupos_django

        sincronizar_grupos_django()
        admin_user = usuarios_creados["admin"]
        hoy = timezone.localdate()
        vistos = set()
        for suc in sucursales:
            com = suc.comercio
            if com.id in vistos:
                continue
            vistos.add(com.id)
            if com.estado == Comercio.Estado.ACTIVO and not Habilitacion.objects.filter(comercio=com).exists():
                nivel = Habilitacion.Nivel.CONFIABLE if com.comercio_confiable else Habilitacion.Nivel.SUPERVISADO
                Habilitacion.objects.create(
                    comercio=com,
                    nivel=nivel,
                    estado=Habilitacion.Estado.OTORGADA,
                    otorgada_por=admin_user,
                    fecha_otorgamiento=timezone.now(),
                    vigente_hasta=hoy + timedelta(days=365),
                    motivo="Habilitación inicial de demostración",
                    checklist={"datos_coinciden": True, "documentos_legibles": True},
                )
        poblar_genericos_desde_catalogo()

        self.stdout.write(
            self.style.SUCCESS(
                f"Datos demo cargados correctamente: "
                f"{Usuario.objects.count()} usuarios, "
                f"{Comercio.objects.count()} comercios, "
                f"{Sucursal.objects.count()} sucursales, "
                f"{Producto.objects.count()} productos, "
                f"{Precio.objects.count()} precios "
                f"({Precio.objects.ofertas_vigentes().count()} ofertas vigentes)."
            )
        )

    def _crear_usuarios_demo(self) -> dict:
        pw_super = os.environ.get("DEMO_PASSWORD_SUPERADMIN", "LucaSuper2026!")
        pw_admin = os.environ.get("DEMO_PASSWORD_ADMIN", "LucaAdmin2026!")
        pw_fisc = os.environ.get("DEMO_PASSWORD_FISCALIZADOR", "LucaFiscal2026!")
        pw_com = os.environ.get("DEMO_PASSWORD_COMERCIANTE", "LucaComercio2026!")
        pw_vec = os.environ.get("DEMO_PASSWORD_VECINO", "LucaVecino2026!")

        def asegurar_usuario(email, password, nombres, apellidos, cuerpo_rut, telefono, rol, estado, **extra):
            u, creado = Usuario.objects.get_or_create(
                email=email,
                defaults={
                    "nombres": nombres,
                    "apellidos": apellidos,
                    "rut": rut_demo(cuerpo_rut),
                    "telefono": telefono,
                    "rol": rol,
                    "estado_cuenta": estado,
                    **extra,
                },
            )
            if creado:
                u.set_password(password)
                u.save(update_fields=["password"])
            return u

        superadmin = asegurar_usuario(
            "superadmin@luca-pac.cl", pw_super, "Equipo", "Seguridad PAC", 13100001, "+56910000001",
            Usuario.Rol.SUPERADMIN, Usuario.EstadoCuenta.ACTIVA, is_staff=True, is_superuser=True
        )
        admin = asegurar_usuario(
            "admin.didese@luca-pac.cl", pw_admin, "Carolina", "Méndez", 14200100, "+56910001001",
            Usuario.Rol.ADMIN, Usuario.EstadoCuenta.ACTIVA, is_staff=True
        )
        admin2 = asegurar_usuario(
            "admin2.didese@luca-pac.cl", pw_admin, "Patricio", "Araya", 14200102, "+56910001002",
            Usuario.Rol.ADMIN, Usuario.EstadoCuenta.ACTIVA, is_staff=True
        )
        fisc1 = asegurar_usuario(
            "fiscal1@luca-pac.cl", pw_fisc, "Rodrigo", "Valenzuela", 15300201, "+56910002001",
            Usuario.Rol.FISCALIZADOR, Usuario.EstadoCuenta.ACTIVA
        )
        fisc2 = asegurar_usuario(
            "fiscal2@luca-pac.cl", pw_fisc, "Marcela", "Sepúlveda", 16400202, "+56910002002",
            Usuario.Rol.FISCALIZADOR, Usuario.EstadoCuenta.ACTIVA
        )

        comerciantes_activos = []
        nombres_com = [
            ("Tito", "Morales", "almacen.tito@luca-pac.cl"),
            ("Sandra", "Paredes", "minimarket.davila@luca-pac.cl"),
            ("Héctor", "Riquelme", "panaderia.trigo@luca-pac.cl"),
            ("Jorge", "Cáceres", "carniceria.buencorte@luca-pac.cl"),
            ("Rosa", "Fuentes", "verduleria.rosa@luca-pac.cl"),
        ]
        for i, (nom, ape, mail) in enumerate(nombres_com):
            c = asegurar_usuario(
                mail, pw_com, nom, ape, 17100300 + i, f"+5691000300{i}",
                Usuario.Rol.COMERCIANTE, Usuario.EstadoCuenta.ACTIVA,
                verificada_por=fisc1, aprobada_por=admin,
                fecha_verificacion=timezone.now() - timedelta(days=20),
                fecha_aprobacion=timezone.now() - timedelta(days=18),
            )
            comerciantes_activos.append(c)

        # 3 comerciantes PENDIENTE y 1 RECHAZADO
        for i in range(3):
            asegurar_usuario(
                f"comercio.pendiente{i+1}@luca-pac.cl", pw_com, f"Comerciante {i+1}", "En Revisión",
                18100400 + i, f"+5691000400{i}", Usuario.Rol.COMERCIANTE, Usuario.EstadoCuenta.PENDIENTE,
                datos_registro_comercio={
                    "nombre_fantasia": f"Almacén Barrio PAC {i+1}",
                    "direccion_sucursal": f"Av. Clotario Blest {5100 + i*20}, Pedro Aguirre Cerda",
                    "sector": "La Victoria",
                },
            )
        asegurar_usuario(
            "comercio.rechazado@luca-pac.cl", pw_com, "Esteban", "Lagos", 18900499, "+56910004999",
            Usuario.Rol.COMERCIANTE, Usuario.EstadoCuenta.RECHAZADA,
            motivo_rechazo="La dirección indicada no pertenece a la comuna de Pedro Aguirre Cerda.",
            verificada_por=fisc2, fecha_verificacion=timezone.now() - timedelta(days=3),
        )

        # 5 vecinos
        for i in range(5):
            asegurar_usuario(
                f"vecino{i+1}@luca-pac.cl", pw_vec, f"Vecino {i+1}", "PAC", 19200500 + i, f"+5691000500{i}",
                Usuario.Rol.VECINO, Usuario.EstadoCuenta.ACTIVA,
            )

        return {
            "superadmin": superadmin,
            "admin": admin,
            "admin2": admin2,
            "fiscalizadores": [fisc1, fisc2],
            "comerciantes_activos": comerciantes_activos,
        }

    def _poblar_precios_historicos(self, rng, productos_con_ref, sucursales, fiscalizador, admin_user):
        """
        Genera ~5.800 registros de `Precio` con 10 semanas de evolución determinista,
        ofertas vigentes con condiciones variadas, ofertas vencidas y 4 alzas atípicas.
        """
        hoy = timezone.localdate()
        # Mapa afinidad rubro comercio -> categorías que suele vender
        afinidad = {
            "SUPERMERCADO": None,  # Vende casi todo
            "MINIMARKET": {"abarrotes", "lacteos-huevos", "panaderia", "bebidas-infusiones", "limpieza-hogar", "higiene-personal"},
            "ALMACEN": {"abarrotes", "lacteos-huevos", "panaderia", "bebidas-infusiones", "limpieza-hogar"},
            "FERIA": {"frutas-verduras", "lacteos-huevos"},
            "VERDULERIA": {"frutas-verduras"},
            "PANADERIA": {"panaderia", "lacteos-huevos", "bebidas-infusiones"},
            "CARNICERIA": {"carnes-pescados"},
            "FARMACIA": {"farmacia", "higiene-personal", "bebes-panales"},
            "OTRO": {"limpieza-hogar", "higiene-personal"},
        }
        # Multiplicador de nivel de precio por tipo de comercio
        factor_tipo = {
            "FERIA": 0.86,
            "SUPERMERCADO": 0.97,
            "VERDULERIA": 0.93,
            "PANADERIA": 0.96,
            "CARNICERIA": 0.98,
            "FARMACIA": 0.95,
            "ALMACEN": 1.06,
            "MINIMARKET": 1.09,
            "OTRO": 0.94,
        }
        condiciones_pool = [
            {"compra_minima": 3, "medio_pago": "", "requiere_membresia": False, "nombre_membresia": "", "condiciones": "Llevando 3 unidades o más."},
            {"compra_minima": None, "medio_pago": "Tarjeta de débito / efectivo", "requiere_membresia": False, "nombre_membresia": "", "condiciones": "Válido pagando con débito o efectivo."},
            {"compra_minima": None, "medio_pago": "Tarjeta de crédito tienda", "requiere_membresia": False, "nombre_membresia": "", "condiciones": "Descuento exclusivo con tarjeta del comercio."},
            {"compra_minima": None, "medio_pago": "", "requiere_membresia": True, "nombre_membresia": "Club Vecino Ahorro", "condiciones": "Presentando RUT inscrito en club."},
            {"compra_minima": 2, "medio_pago": "", "requiere_membresia": False, "nombre_membresia": "", "condiciones": "Promoción válida hasta agotar stock en sala."},
        ]

        lote = []
        contador_ofertas = 0
        contador_atipicas = 0

        for prod, precio_ref in productos_con_ref:
            cat_slug = prod.categoria.slug
            candidatas = [
                s for s in sucursales
                if afinidad.get(s.comercio.tipo) is None or cat_slug in afinidad[s.comercio.tipo]
            ]
            # Seleccionar hasta 6 sucursales representativas por producto para lograr ~5.800 filas (10 semanas)
            elegidas = rng.sample(candidatas, min(len(candidatas), 6))

            for s_idx, suc in enumerate(elegidas):
                base_suc = precio_ref * factor_tipo.get(suc.comercio.tipo, 1.0) * rng.uniform(0.92, 1.10)
                precio_anterior = None

                # 6 observaciones históricas (semanas -9 a -1) + 1 observación vigente (semana 0)
                semanas = [9, 7, 5, 3, 2, 1, 0]
                for sem in semanas:
                    fecha_obs = hoy - timedelta(days=sem * 7 + rng.randint(0, 2))
                    # Estacionalidad suave para frutas/verduras
                    estac = 1.0 + (0.06 * (sem / 9.0) if cat_slug == "frutas-verduras" else rng.uniform(-0.03, 0.03))
                    p_normal = max(150, int(round((base_suc * estac) / 10.0) * 10))

                    es_actual = sem == 0
                    p_oferta = None
                    vig_desde = fecha_obs
                    vig_hasta = None
                    cond = {"compra_minima": None, "medio_pago": "", "requiere_membresia": False, "nombre_membresia": "", "condiciones": ""}
                    estado = Precio.Estado.PUBLICADO if es_actual else Precio.Estado.REEMPLAZADO
                    alerta = False
                    var_pct = None

                    if precio_anterior:
                        var_pct = Decimal(str(round(((p_normal - precio_anterior) / precio_anterior) * 100.0, 2)))

                    # Crear ofertas vigentes (~90) en la semana actual
                    if es_actual and ((s_idx == 0 and (prod.es_estrella or rng.random() < 0.45)) or (s_idx == 1 and rng.random() < 0.12)):
                        descuento = rng.choice([0.12, 0.15, 0.18, 0.22, 0.25, 0.30])
                        p_oferta = max(100, int(round((p_normal * (1 - descuento)) / 10.0) * 10))
                        if p_oferta < p_normal:
                            vig_desde = hoy - timedelta(days=rng.randint(0, 3))
                            vig_hasta = hoy + timedelta(days=rng.randint(3, 14))
                            cond = rng.choice(condiciones_pool)
                            contador_ofertas += 1

                    # Crear algunas ofertas ya vencidas para probar REQ-09 (desaparecen automáticamente)
                    elif sem == 2 and s_idx == 1 and rng.random() < 0.12:
                        p_oferta = max(100, int(round((p_normal * 0.80) / 10.0) * 10))
                        vig_desde = fecha_obs
                        vig_hasta = fecha_obs + timedelta(days=5)
                        estado = Precio.Estado.VENCIDO

                    # Inyectar 4 alertas de variación atípica (> +45%) pendientes de revisión para el dashboard
                    if es_actual and contador_atipicas < 4 and s_idx == 2 and prod.es_canasta_basica and precio_anterior:
                        p_normal = int(round((precio_anterior * 1.52) / 10.0) * 10)
                        var_pct = Decimal("52.00")
                        alerta = True
                        estado = Precio.Estado.PENDIENTE
                        contador_atipicas += 1

                    lote.append(
                        Precio(
                            producto=prod,
                            sucursal=suc,
                            precio_normal=p_normal,
                            precio_oferta=p_oferta,
                            vigencia_desde=vig_desde,
                            vigencia_hasta=vig_hasta,
                            compra_minima=cond["compra_minima"],
                            medio_pago=cond["medio_pago"],
                            requiere_membresia=cond["requiere_membresia"],
                            nombre_membresia=cond["nombre_membresia"],
                            condiciones=cond["condiciones"],
                            fuente=Precio.Fuente.DEMO_REFERENCIAL,
                            fuente_detalle="Serie determinista de demostración basada en precios de referencia RM / ODEPA 2026.",
                            fecha_observacion=fecha_obs,
                            stock_confirmado=(s_idx % 2 == 0),
                            estado=estado,
                            registrado_por=fiscalizador,
                            revisado_por=admin_user if estado == Precio.Estado.PUBLICADO else None,
                            fecha_revision=timezone.now() if estado == Precio.Estado.PUBLICADO else None,
                            alerta_variacion=alerta,
                            variacion_porcentual=var_pct,
                        )
                    )
                    precio_anterior = p_normal

        Precio.objects.bulk_create(lote, batch_size=500)

    def _crear_banners_demo(self, productos_con_ref):
        if Banner.objects.exists():
            return
        hoy = timezone.localdate()
        estrella = next((p for p, _ in productos_con_ref if p.es_estrella), None)
        banners = [
            ("Ofertas de la semana en Pedro Aguirre Cerda", "Compara descuentos reales con condiciones claras antes de salir de casa.", Banner.Tipo.OFERTA, estrella, "/ofertas/", "coral", 1),
            ("Canasta básica: ahorra hasta 22% comparando", "Revisa el precio por kilo y litro entre almacenes, ferias y supermercados.", Banner.Tipo.PRODUCTO_ESTRELLA, estrella, "/buscar/?canasta=1", "marino", 2),
            ("Ferias libres de la comuna esta semana", "Consulta horarios y ubicaciones de La Victoria, Dávila, Villa Sur y Santa Adriana.", Banner.Tipo.INFORMATIVO, None, "/mapa/?tipo=FERIA", "turquesa", 3),
            ("¿Tienes un almacén o verdulería en PAC?", "Registra tu comercio gratis y publica tus precios para llegar a más vecinos.", Banner.Tipo.INFORMATIVO, None, "/cuenta/registro/comerciante/", "ambar", 4),
            ("Medicamentos y farmacia cerca de ti", "Compara precios de venta libre en Farmacia Popular PAC y farmacias locales.", Banner.Tipo.PRODUCTO_ESTRELLA, None, "/buscar/?categoria=farmacia", "marino", 5),
            ("Transparencia en cada precio publicado", "Conoce de dónde viene cada dato, su fecha de observación y metodología.", Banner.Tipo.INFORMATIVO, None, "/transparencia/", "turquesa", 6),
        ]
        for titulo, subtitulo, tipo, prod, enlace, color, orden in banners:
            Banner.objects.create(
                titulo=titulo,
                subtitulo=subtitulo,
                tipo=tipo,
                producto=prod,
                enlace=enlace,
                esquema_color=color,
                orden=orden,
                desde=hoy - timedelta(days=1),
                hasta=hoy + timedelta(days=30),
                activo=True,
            )
