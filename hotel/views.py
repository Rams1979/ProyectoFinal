from datetime import date

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .disponibilidad import habitaciones_libres
from .models import Habitacion, Reserva


def inicio(request):
    habitaciones = Habitacion.objects.all()
    return render(request, "hotel/inicio.html", {"habitaciones": habitaciones})


def _fecha(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def _validar_fechas(entrada, salida):
    if not entrada or not salida:
        return "Indique la fecha de entrada y la de salida."
    if entrada < timezone.localdate():
        return "La entrada no puede ser una fecha pasada."
    if salida <= entrada:
        return "La salida debe ser posterior a la entrada."
    return None


def disponibilidad(request):
    contexto = {"hoy": timezone.localdate().isoformat()}
    if request.GET:
        entrada = _fecha(request.GET.get("entrada"))
        salida = _fecha(request.GET.get("salida"))
        contexto.update(entrada_txt=request.GET.get("entrada", ""), salida_txt=request.GET.get("salida", ""))
        error = _validar_fechas(entrada, salida)
        if error:
            contexto["error"] = error
        else:
            noches = (salida - entrada).days
            libres = list(habitaciones_libres(entrada, salida))
            contexto.update(
                buscado=True,
                noches=noches,
                libres=[(h, h.tarifa_noche * noches) for h in libres],
            )
    return render(request, "hotel/disponibilidad.html", contexto)


def reservar(request, habitacion_id):
    """Reserva confirmada automáticamente; se da por pagada (prototipo)."""
    datos = request.POST if request.method == "POST" else request.GET
    entrada_txt, salida_txt = datos.get("entrada", ""), datos.get("salida", "")
    entrada, salida = _fecha(entrada_txt), _fecha(salida_txt)
    contexto = {"entrada_txt": entrada_txt, "salida_txt": salida_txt}

    error = _validar_fechas(entrada, salida)
    if error:
        contexto["error"] = error
        return render(request, "hotel/reservar.html", contexto, status=400)

    noches = (salida - entrada).days
    nombre = datos.get("nombre", "").strip()
    telefono = datos.get("telefono", "").strip()

    with transaction.atomic():
        # Se bloquea la habitación para que dos reservas simultáneas no se traslapen.
        habitacion = get_object_or_404(Habitacion.objects.select_for_update(), pk=habitacion_id)
        libre = habitaciones_libres(entrada, salida).filter(pk=habitacion.pk).exists()
        contexto.update(habitacion=habitacion, noches=noches, total=habitacion.tarifa_noche * noches,
                        nombre=nombre, telefono=telefono)
        if not libre:
            contexto["error"] = "Esa habitación ya no está libre para esas fechas. Elija otra."
            contexto["bloqueado"] = True
            return render(request, "hotel/reservar.html", contexto, status=409)
        if request.method == "POST":
            if not nombre or not telefono:
                contexto["error"] = "Escriba su nombre y su teléfono."
                return render(request, "hotel/reservar.html", contexto, status=400)
            reserva = Reserva.objects.create(
                habitacion=habitacion, nombre=nombre, telefono=telefono, entrada=entrada, salida=salida
            )
            return redirect("reserva_confirmada", reserva_id=reserva.pk)
    return render(request, "hotel/reservar.html", contexto)


def reserva_confirmada(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    noches = (reserva.salida - reserva.entrada).days
    return render(request, "hotel/confirmada.html",
                  {"reserva": reserva, "noches": noches, "total": reserva.habitacion.tarifa_noche * noches})


def reservaciones(request):
    filas = [
        (r, (r.salida - r.entrada).days, r.habitacion.tarifa_noche * (r.salida - r.entrada).days)
        for r in Reserva.objects.select_related("habitacion")
    ]
    return render(request, "hotel/reservaciones.html", {"filas": filas})
