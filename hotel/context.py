import random

from .permisos import areas_de, rol


LOGOS = [f"hotel/logos/logo-{n}.webp" for n in range(1, 6)]


def rol_actual(request):
    if not hasattr(request, "user"):
        return {"rol": None, "areas": set(), "logo": random.choice(LOGOS)}
    return {"rol": rol(request.user), "areas": areas_de(request.user), "logo": random.choice(LOGOS)}
