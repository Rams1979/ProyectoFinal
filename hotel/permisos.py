from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

RECEPCION = "Recepción"
ADMIN = "Administrador"
ROLES = [RECEPCION, ADMIN]


def rol(usuario):
    """Rol efectivo del usuario, o None si no es personal del hotel."""
    if not usuario.is_authenticated or not usuario.is_active:
        return None
    if usuario.is_superuser:
        return ADMIN
    nombres = set(usuario.groups.values_list("name", flat=True))
    if ADMIN in nombres:
        return ADMIN
    if RECEPCION in nombres:
        return RECEPCION
    return None


def _exigir(permitidos):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if rol(request.user) not in permitidos:
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


personal = _exigir({RECEPCION, ADMIN})   # recepción y administrador
solo_admin = _exigir({ADMIN})
