import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Prepara el administrador inicial al arrancar, sin importar qué comando use la plataforma.
from hotel.arranque import preparar_administrador  # noqa: E402

preparar_administrador()
