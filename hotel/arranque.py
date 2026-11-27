"""Tareas que se hacen al arrancar la aplicación, sin depender del comando de inicio de la plataforma.

Railway puede ignorar el Procfile y arrancar solo con `migrate` y `gunicorn`; por eso el
administrador inicial se prepara aquí y no solo en el Procfile.
"""
import sys
import traceback

from django.core.management import call_command
from django.db import connections


def preparar_administrador():
    """Crea o corrige el administrador inicial según las variables ADMIN_*. Nunca detiene el arranque."""
    try:
        call_command("crear_admin")
    except Exception:  # p. ej. tablas aún sin migrar: se registra y el sitio sigue arrancando
        print("arranque: no se pudo preparar el administrador:", file=sys.stderr)
        traceback.print_exc()
    finally:
        connections.close_all()
