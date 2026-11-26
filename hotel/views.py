from datetime import date

from django.shortcuts import render
from django.utils import timezone

from .disponibilidad import habitaciones_libres
from .models import Habitacion


def inicio(request):
    habitaciones = Habitacion.objects.all()
    return render(request, "hotel/inicio.html", {"habitaciones": habitaciones})


def _fecha(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def disponibilidad(request):
    contexto = {"hoy": timezone.localdate().isoformat()}
    if request.GET:
        entrada = _fecha(request.GET.get("entrada"))
        salida = _fecha(request.GET.get("salida"))
        contexto.update(entrada_txt=request.GET.get("entrada", ""), salida_txt=request.GET.get("salida", ""))
        if not entrada or not salida:
            contexto["error"] = "Indique la fecha de entrada y la de salida."
        elif entrada < timezone.localdate():
            contexto["error"] = "La entrada no puede ser una fecha pasada."
        elif salida <= entrada:
            contexto["error"] = "La salida debe ser posterior a la entrada."
        else:
            noches = (salida - entrada).days
            libres = list(habitaciones_libres(entrada, salida))
            contexto.update(
                buscado=True,
                noches=noches,
                libres=[(h, h.tarifa_noche * noches) for h in libres],
            )
    return render(request, "hotel/disponibilidad.html", contexto)
