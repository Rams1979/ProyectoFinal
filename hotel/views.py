import json
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .chat import responder as chat_responder
from .disponibilidad import habitaciones_libres
from .models import Cliente, Habitacion, Perro, Reserva, SolicitudContacto, Vacuna


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
    perro_nombre = datos.get("perro", "").strip()[:80]

    with transaction.atomic():
        # Se bloquea la habitación para que dos reservas simultáneas no se traslapen.
        habitacion = get_object_or_404(Habitacion.objects.select_for_update(), pk=habitacion_id)
        libre = habitaciones_libres(entrada, salida).filter(pk=habitacion.pk).exists()
        contexto.update(habitacion=habitacion, noches=noches, total=habitacion.tarifa_noche * noches,
                        nombre=nombre, telefono=telefono, perro=perro_nombre)
        if not libre:
            contexto["error"] = "Esa habitación ya no está libre para esas fechas. Elija otra."
            contexto["bloqueado"] = True
            return render(request, "hotel/reservar.html", contexto, status=409)
        if request.method == "POST":
            if not nombre or not telefono:
                contexto["error"] = "Escriba su nombre y su teléfono."
                return render(request, "hotel/reservar.html", contexto, status=400)
            cliente, _ = Cliente.objects.get_or_create(telefono=telefono, defaults={"nombre": nombre})
            perro_ref = None
            if perro_nombre:
                perro_ref = cliente.perros.filter(nombre__iexact=perro_nombre).first() or \
                    Perro.objects.create(cliente=cliente, nombre=perro_nombre)
            reserva = Reserva.objects.create(
                habitacion=habitacion, nombre=nombre, telefono=telefono, entrada=entrada, salida=salida,
                cliente=cliente, perro_ref=perro_ref, perro=perro_nombre,
            )
            return redirect("reserva_confirmada", reserva_id=reserva.pk)
    return render(request, "hotel/reservar.html", contexto)


def reserva_confirmada(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    noches = (reserva.salida - reserva.entrada).days
    return render(request, "hotel/confirmada.html",
                  {"reserva": reserva, "noches": noches, "total": reserva.habitacion.tarifa_noche * noches})


def reservaciones(request):
    hoy = timezone.localdate()
    filas = [
        (r, (r.salida - r.entrada).days, r.habitacion.tarifa_noche * (r.salida - r.entrada).days)
        for r in Reserva.objects.select_related("habitacion")
    ]
    return render(request, "hotel/reservaciones.html", {"filas": filas})


def chat(request):
    return render(request, "hotel/chat.html")


@require_POST
def chat_mensaje(request):
    try:
        historial = json.loads(request.body).get("historial", [])
    except (ValueError, AttributeError):
        return JsonResponse({"error": "Solicitud inválida."}, status=400)
    if not isinstance(historial, list):
        return JsonResponse({"error": "Solicitud inválida."}, status=400)
    return JsonResponse({"respuesta": chat_responder(historial)})


def solicitudes(request):
    return render(request, "hotel/solicitudes.html", {"solicitudes": SolicitudContacto.objects.all()})


def _estado_habitaciones(hoy):
    """Estado de cada habitación hoy: en hotel, pendiente de check-in, limpieza o libre."""
    activas = {r.habitacion_id: r for r in Reserva.objects.filter(estado=Reserva.ACTIVA)}
    pendientes = {}
    for r in Reserva.objects.filter(estado=Reserva.CONFIRMADA, entrada__lte=hoy, salida__gt=hoy):
        pendientes.setdefault(r.habitacion_id, r)
    filas = []
    for h in Habitacion.objects.all():
        if h.pk in activas:
            r = activas[h.pk]
            etiqueta = "Sale hoy" if r.salida <= hoy else "Ocupada"
            filas.append({"hab": h, "clave": "ocupada", "etiqueta": etiqueta, "reserva": r, "sale_hoy": r.salida <= hoy})
        elif h.pk in pendientes:
            r = pendientes[h.pk]
            etiqueta = "Llega hoy" if r.entrada == hoy else "Pendiente de check-in"
            filas.append({"hab": h, "clave": "llega", "etiqueta": etiqueta, "reserva": r})
        elif h.en_limpieza:
            filas.append({"hab": h, "clave": "limpieza", "etiqueta": "En limpieza"})
        else:
            filas.append({"hab": h, "clave": "libre", "etiqueta": "Libre"})
    return filas


def panel(request):
    hoy = timezone.localdate()
    filas = _estado_habitaciones(hoy)
    cuenta = {k: sum(1 for f in filas if f["clave"] == k) for k in ("ocupada", "llega", "limpieza", "libre")}
    cuenta["sale_hoy"] = sum(1 for f in filas if f.get("sale_hoy"))
    return render(request, "hotel/panel.html", {"filas": filas, "cuenta": cuenta, "hoy": hoy})


def checkin(request, reserva_id):
    hoy = timezone.localdate()
    with transaction.atomic():
        reserva = get_object_or_404(Reserva.objects.select_related("habitacion").select_for_update(), pk=reserva_id)
        contexto = {"reserva": reserva}
        error = None
        if reserva.estado != Reserva.CONFIRMADA:
            error = "Esta reserva ya no está pendiente de check-in."
        elif reserva.entrada > hoy:
            error = f"La entrada es el {reserva.entrada:%d/%m/%Y}; todavía no se puede hacer el check-in."
        elif reserva.salida <= hoy:
            error = "La fecha de salida de esta reserva ya pasó."
        elif reserva.habitacion.en_limpieza:
            error = "La habitación está en limpieza. Márquela como disponible en el panel."
        elif Reserva.objects.filter(habitacion=reserva.habitacion, estado=Reserva.ACTIVA).exists():
            error = "La habitación todavía tiene otro perro en el hotel."
        if error:
            contexto["error"] = error
            contexto["bloqueado"] = True
            return render(request, "hotel/checkin.html", contexto, status=409)
        contexto["pendientes"] = reserva.perro_ref.pendientes(reserva.salida) if reserva.perro_ref else None
        if request.method == "POST":
            perro = request.POST.get("perro", "").strip() or reserva.perro
            if not perro:
                contexto["error"] = "Escriba el nombre del perro."
                return render(request, "hotel/checkin.html", contexto, status=400)
            if contexto["pendientes"] and not request.POST.get("autoriza"):
                contexto["error"] = "Faltan requisitos sanitarios. Marque la autorización de recepción para continuar."
                return render(request, "hotel/checkin.html", contexto, status=400)
            if reserva.perro_ref is None:
                if reserva.cliente is None:
                    reserva.cliente, _ = Cliente.objects.get_or_create(
                        telefono=reserva.telefono, defaults={"nombre": reserva.nombre})
                reserva.perro_ref = reserva.cliente.perros.filter(nombre__iexact=perro).first() or \
                    Perro.objects.create(cliente=reserva.cliente, nombre=perro[:80])
            reserva.estado = Reserva.ACTIVA
            reserva.perro = perro[:80]
            reserva.checkin_en = timezone.now()
            reserva.save()
            return redirect("panel")
    return render(request, "hotel/checkin.html", contexto)


@require_POST
def checkout(request, reserva_id):
    hoy = timezone.localdate()
    with transaction.atomic():
        reserva = get_object_or_404(Reserva.objects.select_related("habitacion").select_for_update(), pk=reserva_id)
        if reserva.estado == Reserva.ACTIVA:
            reserva.estado = Reserva.CERRADA
            reserva.checkout_en = timezone.now()
            if reserva.salida > hoy:  # salida anticipada: libera las fechas restantes
                reserva.salida = hoy
            reserva.save()
            reserva.habitacion.en_limpieza = True
            reserva.habitacion.save(update_fields=["en_limpieza"])
    return redirect("panel")


@require_POST
def limpieza_lista(request, habitacion_id):
    Habitacion.objects.filter(pk=habitacion_id).update(en_limpieza=False)
    return redirect("panel")


def clientes(request):
    q = request.GET.get("q", "").strip()
    lista = Cliente.objects.prefetch_related("perros")
    if q:
        lista = lista.filter(Q(nombre__icontains=q) | Q(telefono__icontains=q) | Q(perros__nombre__icontains=q)).distinct()
    return render(request, "hotel/clientes.html", {"clientes": lista, "q": q})


def cliente_nuevo(request):
    error, datos = None, request.POST
    if request.method == "POST":
        nombre, telefono = datos.get("nombre", "").strip(), datos.get("telefono", "").strip()
        if not nombre or not telefono:
            error = "Nombre y teléfono son obligatorios."
        elif Cliente.objects.filter(telefono=telefono).exists():
            error = "Ya existe un cliente con ese teléfono."
        else:
            c = Cliente.objects.create(nombre=nombre, telefono=telefono, correo=datos.get("correo", "").strip())
            return redirect("cliente", cliente_id=c.pk)
    return render(request, "hotel/cliente_nuevo.html", {"error": error, "datos": datos if request.method == "POST" else {}},
                  status=400 if error else 200)


def cliente(request, cliente_id):
    c = get_object_or_404(Cliente.objects.prefetch_related("perros__vacunas"), pk=cliente_id)
    hoy = timezone.localdate()
    error = None
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "perro":
            nombre = request.POST.get("nombre", "").strip()
            nac = _fecha(request.POST.get("nacimiento", ""))
            if not nombre:
                error = "Escriba el nombre del perro."
            else:
                Perro.objects.create(cliente=c, nombre=nombre[:80], raza=request.POST.get("raza", "").strip()[:80],
                                     nacimiento=nac, notas=request.POST.get("notas", "").strip()[:300])
                return redirect("cliente", cliente_id=c.pk)
        elif accion == "vacuna":
            perro = get_object_or_404(Perro, pk=request.POST.get("perro_id"), cliente=c)
            tipo = request.POST.get("tipo")
            aplicada, vence = _fecha(request.POST.get("aplicada", "")), _fecha(request.POST.get("vence", ""))
            if tipo not in dict(Vacuna.TIPOS) or not aplicada or not vence:
                error = "Indique tipo, fecha de aplicación y fecha de vencimiento."
            elif vence < aplicada:
                error = "El vencimiento no puede ser anterior a la aplicación."
            else:
                Vacuna.objects.create(perro=perro, tipo=tipo, aplicada=aplicada, vence=vence)
                return redirect("cliente", cliente_id=c.pk)
    perros = [{"perro": p, "requisitos": p.requisitos(hoy)} for p in c.perros.all()]
    return render(request, "hotel/cliente.html",
                  {"c": c, "perros": perros, "tipos": Vacuna.TIPOS, "error": error, "hoy": hoy},
                  status=400 if error else 200)
