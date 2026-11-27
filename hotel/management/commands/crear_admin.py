import os

from django.contrib.auth.models import Group, User
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
        u.groups.add(Group.objects.get_or_create(name="Administrador")[0])
        self.stdout.write(f"Administrador '{nombre}' creado.")
