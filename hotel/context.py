from .permisos import ADMIN, rol


def rol_actual(request):
    r = rol(request.user) if hasattr(request, "user") else None
    return {"rol": r, "es_admin": r == ADMIN}
