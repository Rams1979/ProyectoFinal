import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection

from hotel.models import Perfil, PerfilUsuario


def _variable(nombre):
    """Valor de una variable de entorno sin espacios ni comillas de más."""
    return os.environ.get(nombre, "").strip().strip("\"'").strip()


class Command(BaseCommand):
    help = ("Crea el primer administrador desde ADMIN_USERNAME y ADMIN_PASSWORD (variables de entorno). "
            "Mientras ese usuario no haya ingresado nunca, la contraseña de la variable manda: se puede corregir "
            "y redesplegar. Con ADMIN_RESTABLECER=1 también se restablece después de que haya ingresado.")

    def handle(self, *args, **options):
        cfg = connection.settings_dict  # sin credenciales: solo para saber a qué base se conectó
        self.stdout.write(f"crear_admin: base de datos {connection.vendor}, host '{cfg.get('HOST') or 'archivo local'}', "
                          f"nombre '{cfg.get('NAME')}', {User.objects.count()} usuario(s).")
        nombre, clave = _variable("ADMIN_USERNAME"), _variable("ADMIN_PASSWORD")
        restablecer = _variable("ADMIN_RESTABLECER") == "1"
        if not nombre or not clave:
            self.stdout.write("crear_admin: faltan ADMIN_USERNAME o ADMIN_PASSWORD; no se crea ni cambia nada.")
            return
        perfil = Perfil.objects.get(es_sistema=True)

        # Cuentas que quedaron con espacios de más en el nombre por un valor mal pegado y nunca se usaron.
        for u in User.objects.exclude(username=nombre):
            if u.username.strip() == nombre and u.last_login is None:
                u.delete()
                self.stdout.write(f"crear_admin: se borró una cuenta duplicada con espacios en el nombre ('{u.username}').")

        u = User.objects.filter(username=nombre).first()
        if u is None:
            u = User.objects.create_superuser(username=nombre, password=clave, first_name="Administrador")
            PerfilUsuario.objects.create(usuario=u, perfil=perfil)
            self.stdout.write(f"crear_admin: administrador '{nombre}' creado.")
        elif restablecer or u.last_login is None:
            u.set_password(clave)
            u.is_active, u.is_superuser, u.is_staff = True, True, True
            u.save()
            PerfilUsuario.objects.update_or_create(usuario=u, defaults={"perfil": perfil})
            motivo = "ADMIN_RESTABLECER=1" if restablecer else "nunca ha ingresado; manda la contraseña de la variable"
            self.stdout.write(f"crear_admin: administrador '{nombre}' restablecido ({motivo}).")
        else:
            self.stdout.write(f"crear_admin: el usuario '{nombre}' ya ingresó antes; no se cambia su contraseña. "
                              "Para restablecerla agregue ADMIN_RESTABLECER=1 y redespliegue.")
