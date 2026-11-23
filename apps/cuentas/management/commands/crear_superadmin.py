"""
Comando exclusivo de CLI para crear una cuenta SUPERADMIN con contraseña interactiva,
secreto TOTP y 8 códigos de recuperación de un solo uso (# Prompt 8 Sección 4.1).

# SEGURIDAD: No existe alta de SUPERADMIN por interfaz web. La contraseña jamás se recibe por argumento.
"""
import getpass

from django.core.management.base import BaseCommand, CommandError

from apps.cuentas.models import Usuario
from apps.nucleo.permisos_catalogo import sincronizar_grupos_django
from apps.nucleo.totp import generar_codigos_recuperacion, generar_secreto_totp


class Command(BaseCommand):
    help = "Crea una cuenta SUPERADMIN exclusivamente por línea de comandos con TOTP y códigos de recuperación."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Correo institucional del superadministrador.")
        parser.add_argument("--nombres", required=True, help="Nombres.")
        parser.add_argument("--apellidos", required=True, help="Apellidos.")
        parser.add_argument("--rut", required=True, help="RUT chileno válido (ej. 15.111.222-3).")
        parser.add_argument("--telefono", default="+56900000000", help="Teléfono de contacto.")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if Usuario.objects.filter(email=email).exists():
            raise CommandError(f"Ya existe un usuario con el correo {email}.")

        pw1 = getpass.getpass("Contraseña del SUPERADMIN (mín. 12 caracteres): ")
        pw2 = getpass.getpass("Confirmar contraseña: ")
        if pw1 != pw2:
            raise CommandError("Las contraseñas no coinciden.")
        if len(pw1) < 12:
            raise CommandError("La contraseña del SUPERADMIN debe tener al menos 12 caracteres.")

        secreto = generar_secreto_totp()
        planos, hashes = generar_codigos_recuperacion(8)

        usuario = Usuario.objects.create_superuser(
            email=email,
            password=pw1,
            nombres=options["nombres"].strip(),
            apellidos=options["apellidos"].strip(),
            rut=options["rut"].strip(),
            telefono=options["telefono"].strip(),
            totp_secreto=secreto,
            totp_activo=True,
            codigos_recuperacion=hashes,
        )
        sincronizar_grupos_django()

        self.stdout.write(self.style.SUCCESS(f"SUPERADMIN creado correctamente: {usuario.email}"))
        self.stdout.write(f"Secreto TOTP (ingresar en app autenticadora): {secreto}")
        self.stdout.write("Códigos de recuperación de un solo uso (guardar fuera de línea):")
        for c in planos:
            self.stdout.write(f"  - {c}")
