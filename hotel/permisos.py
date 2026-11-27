from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

ADMIN = "Administrador"  # perfil de sistema: siempre tiene todas las áreas


def _perfil(usuario):
    """Perfil del usuario, o None si no es personal del hotel."""
    if not usuario.is_authenticated or not usuario.is_active:
        return None
    pu = getattr(usuario, "perfil_hotel", None)
    if pu is not None:
        return pu.perfil
    if usuario.is_superuser:  # superusuario creado por consola, sin perfil asignado
        from .models import Perfil
        return Perfil.objects.filter(es_sistema=True).first()
    return None


def rol(usuario):
    """Nombre del perfil del usuario, o None si no es personal."""
    p = _perfil(usuario)
    return p.nombre if p else None


def es_administrador(usuario):
    p = _perfil(usuario)
    return bool(p and p.es_sistema)


def puede(usuario, area):
    p = _perfil(usuario)
    return bool(p and p.tiene(area))


def areas_de(usuario):
    from .models import AREAS
    p = _perfil(usuario)
    return {a for a, _ in AREAS if p and p.tiene(a)}


def con_area(area):
    """Exige sesión y que el perfil del usuario incluya el área."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not puede(request.user, area):
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


def personal(vista):
    """Cualquier usuario con perfil (para pantallas comunes, como cambiar la contraseña)."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if rol(request.user) is None:
            raise PermissionDenied
        return vista(request, *args, **kwargs)
    return envoltura
