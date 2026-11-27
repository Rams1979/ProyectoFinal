import os

from django.contrib.auth.models import User

from hotel.models import Perfil, PerfilUsuario
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crea el primer administrador desde ADMIN_USERNAME y ADMIN_PASSWORD (variables de entorno). No cambia usuarios existentes."

    def handle(self, *args, **options):
        nombre, clave = os.environ.get("ADMIN_USERNAME"), os.environ.get("ADMIN_PASSWORD")
        if not nombre or not clave:
            if not User.objects.exists():
                self.stdout.write("Aviso: no hay usuarios. Defina ADMIN_USERNAME y ADMIN_PASSWORD para crear el administrador.")
            return
        if User.objects.filter(username=nombre).exists():
            return
        u = User.objects.create_superuser(username=nombre, password=clave, first_name="Administrador")
        PerfilUsuario.objects.create(usuario=u, perfil=Perfil.objects.get(es_sistema=True))
        self.stdout.write(f"Administrador '{nombre}' creado.")
