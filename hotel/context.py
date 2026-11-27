from .permisos import areas_de, rol


def rol_actual(request):
    if not hasattr(request, "user"):
        return {"rol": None, "areas": set()}
    return {"rol": rol(request.user), "areas": areas_de(request.user)}
