import json
from datetime import date, time
from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .chat import responder as chat_responder
from . import acceso
from .disponibilidad import habitaciones_libres
from .permisos import ADMIN, RECEPCION, ROLES, personal, rol, solo_admin
from .models import Cliente, Habitacion, ItemPlan, Pago, Perro, Reserva, SolicitudContacto, Tarea, Vacuna


def inicio(request):
    """Visitante: página pública. Personal: menú principal según su rol."""
    mi_rol = rol(request.user)
    if mi_rol is None:
        return render(request, "hotel/publica.html")
    hoy = timezone.localdate()
    ocupadas = Reserva.objects.filter(estado=Reserva.ACTIVA).count()
    llegan = Reserva.objects.filter(estado=Reserva.CONFIRMADA, entrada=hoy).count()
    menu = [
        ("panel", "Panel de ocupación", f"{ocupadas} ocupadas · {llegan} llegan hoy", "Estado de las habitaciones hoy, check-in y check-out."),
        ("disponibilidad", "Disponibilidad", "Buscar por fechas", "Habitaciones libres y reserva."),
        ("reservaciones", "Reservaciones", f"{Reserva.objects.exclude(estado__in=[Reserva.CERRADA, Reserva.CANCELADA]).count()} vigentes", "Lista de reservas con su estado."),
        ("cuidado", "Cuidado diario", f"{_pendientes_cuidado(hoy)} tareas pendientes hoy", "Alimentación, medicación, paseos y limpieza por perro."),
        ("caja", "Caja del día", "Pagos y devoluciones", "Cobros por método de pago."),
        ("clientes", "Clientes y perros", f"{Cliente.objects.count()} clientes", "Fichas, perros y requisitos sanitarios."),
        ("chat", "Chat", "Asistente del hotel", "Preguntas frecuentes y disponibilidad."),
        ("habitaciones", "Habitaciones", f"{Habitacion.objects.count()} habitaciones", "Lista y tarifa por noche."),
    ]
    if mi_rol == ADMIN:
        menu.insert(5, ("solicitudes", "Solicitudes de contacto", f"{SolicitudContacto.objects.count()} recibidas", "Datos que dejaron clientes en el chat."))
        menu.append(("usuarios", "Usuarios", f"{User.objects.filter(is_active=True).count()} activos", "Crear y desactivar usuarios del personal."))
    return render(request, "hotel/inicio.html", {"menu": menu, "hoy": hoy})


def _pendientes_cuidado(hoy):
    total = ItemPlan.objects.filter(reserva__estado=Reserva.ACTIVA).count()
    hechas = Tarea.objects.filter(fecha=hoy, hecha=True, item__reserva__estado=Reserva.ACTIVA).count()
    return total - hechas


@personal
def habitaciones(request):
    return render(request, "hotel/habitaciones.html", {"habitaciones": Habitacion.objects.all()})


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
    """Reserva confirmada automáticamente; el pago se registra aparte (ver pagos)."""
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
    perro2_nombre = datos.get("perro2", "").strip()[:80]
    recargo = Decimal(settings.RECARGO_SEGUNDO_PERRO) / 100

    with transaction.atomic():
        # Se bloquea la habitación para que dos reservas simultáneas no se traslapen.
        habitacion = get_object_or_404(Habitacion.objects.select_for_update(), pk=habitacion_id)
        libre = habitaciones_libres(entrada, salida).filter(pk=habitacion.pk).exists()
        base = habitacion.tarifa_noche * noches
        contexto.update(habitacion=habitacion, noches=noches, nombre=nombre, telefono=telefono,
                        perro=perro_nombre, perro2=perro2_nombre, recargo=settings.RECARGO_SEGUNDO_PERRO,
                        total=base * (1 + recargo) if perro2_nombre else base, total_con_segundo=base * (1 + recargo),
                        total_base=base, anticipo=settings.ANTICIPO_PORCENTAJE)
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
            perro2_ref = None
            if perro2_nombre:
                perro2_ref = cliente.perros.filter(nombre__iexact=perro2_nombre).first() or \
                    Perro.objects.create(cliente=cliente, nombre=perro2_nombre)
            reserva = Reserva.objects.create(
                habitacion=habitacion, nombre=nombre, telefono=telefono, entrada=entrada, salida=salida,
                cliente=cliente, perro_ref=perro_ref, perro=perro_nombre,
                perro2_ref=perro2_ref, perro2=perro2_nombre,
                creada_por=request.user if rol(request.user) else None,
            )
            propias = request.session.get("reservas_propias", [])
            request.session["reservas_propias"] = (propias + [reserva.pk])[-20:]
            return redirect("reserva_confirmada", reserva_id=reserva.pk)
    return render(request, "hotel/reservar.html", contexto)


def reserva_confirmada(request, reserva_id):
    # Un visitante solo ve las confirmaciones de las reservas que hizo en esta sesión.
    if rol(request.user) is None and reserva_id not in request.session.get("reservas_propias", []):
        raise PermissionDenied
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    return render(request, "hotel/confirmada.html",
                  {"reserva": reserva, "noches": reserva.noches, "total": reserva.total,
                   "anticipo": reserva.anticipo_requerido if settings.ANTICIPO_PORCENTAJE else None,
                   "anticipo_pct": settings.ANTICIPO_PORCENTAJE})


@personal
def reservaciones(request):
    hoy = timezone.localdate()
    filas = [(r, r.noches, r.total) for r in Reserva.objects.select_related("habitacion", "creada_por", "checkin_por", "checkout_por", "cancelada_por")]
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


@solo_admin
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


@personal
def panel(request):
    hoy = timezone.localdate()
    filas = _estado_habitaciones(hoy)
    cuenta = {k: sum(1 for f in filas if f["clave"] == k) for k in ("ocupada", "llega", "limpieza", "libre")}
    cuenta["sale_hoy"] = sum(1 for f in filas if f.get("sale_hoy"))
    return render(request, "hotel/panel.html", {"filas": filas, "cuenta": cuenta, "hoy": hoy})


@personal
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
        contexto["pendientes"] = [
            {**f, "perro": ref.nombre}
            for ref in (reserva.perro_ref, reserva.perro2_ref) if ref
            for f in ref.pendientes(reserva.salida)
        ]
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
            if reserva.perro2 and reserva.perro2_ref is None and reserva.cliente:
                reserva.perro2_ref = reserva.cliente.perros.filter(nombre__iexact=reserva.perro2).first() or \
                    Perro.objects.create(cliente=reserva.cliente, nombre=reserva.perro2)
            reserva.estado = Reserva.ACTIVA
            reserva.perro = perro[:80]
            reserva.checkin_en = timezone.now()
            reserva.checkin_por = request.user
            reserva.save()
            crear_plan_base(reserva)
            return redirect("panel")
    return render(request, "hotel/checkin.html", contexto)


@personal
@require_POST
def checkout(request, reserva_id):
    hoy = timezone.localdate()
    with transaction.atomic():
        reserva = get_object_or_404(Reserva.objects.select_related("habitacion").select_for_update(), pk=reserva_id)
        if reserva.estado == Reserva.ACTIVA:
            reserva.estado = Reserva.CERRADA
            reserva.checkout_en = timezone.now()
            reserva.checkout_por = request.user
            if reserva.salida > hoy:  # salida anticipada: libera las fechas restantes
                reserva.salida = hoy
            reserva.save()
            reserva.habitacion.en_limpieza = True
            reserva.habitacion.save(update_fields=["en_limpieza"])
    return redirect("panel")


@personal
@require_POST
def limpieza_lista(request, habitacion_id):
    Habitacion.objects.filter(pk=habitacion_id).update(en_limpieza=False)
    return redirect("panel")


@personal
def clientes(request):
    q = request.GET.get("q", "").strip()
    lista = Cliente.objects.prefetch_related("perros")
    if q:
        lista = lista.filter(Q(nombre__icontains=q) | Q(telefono__icontains=q) | Q(perros__nombre__icontains=q)).distinct()
    return render(request, "hotel/clientes.html", {"clientes": lista, "q": q})


@personal
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


@personal
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


def login_vista(request):
    if rol(request.user):
        return redirect("inicio")
    form = AuthenticationForm(request, data=request.POST or None)
    error = None
    if request.method == "POST":
        usuario = request.POST.get("username", "")
        if acceso.bloqueado(usuario):
            error = "Demasiados intentos fallidos. Espere 15 minutos."
        else:
            u = authenticate(request, username=usuario, password=request.POST.get("password", ""))
            if u is not None and rol(u):
                acceso.limpiar(usuario)
                login(request, u)
                destino = request.GET.get("next", "")
                if destino.startswith("/") and not destino.startswith("//"):
                    return redirect(destino)
                return redirect("inicio")
            acceso.registrar_fallo(usuario)
            error = "Usuario o contraseña incorrectos."
    return render(request, "hotel/login.html", {"error": error}, status=400 if error else 200)


@require_POST
def logout_vista(request):
    logout(request)
    return redirect("inicio")


@solo_admin
def usuarios(request):
    error = None
    if request.method == "POST":
        nombre = request.POST.get("username", "").strip()
        clave = request.POST.get("password", "")
        nombre_rol = request.POST.get("rol")
        if not nombre or nombre_rol not in ROLES:
            error = "Indique usuario y rol."
        elif User.objects.filter(username__iexact=nombre).exists():
            error = "Ese usuario ya existe."
        else:
            try:
                validate_password(clave)
            except ValidationError as e:
                error = " ".join(e.messages)
        if not error:
            u = User.objects.create_user(username=nombre, password=clave)
            u.groups.add(Group.objects.get_or_create(name=nombre_rol)[0])
            return redirect("usuarios")
    filas = [{"u": u, "rol": rol(u) or "Sin rol"} for u in User.objects.order_by("username")]
    return render(request, "hotel/usuarios.html", {"filas": filas, "roles": ROLES, "error": error},
                  status=400 if error else 200)


@solo_admin
@require_POST
def usuario_activo(request, usuario_id):
    u = get_object_or_404(User, pk=usuario_id)
    if u.pk != request.user.pk:  # nadie se desactiva a sí mismo
        u.is_active = not u.is_active
        u.save(update_fields=["is_active"])
    return redirect("usuarios")


def _puede_gestionar(request, reserva_id):
    """Personal siempre; un visitante solo sobre las reservas que hizo en su sesión."""
    return rol(request.user) is not None or reserva_id in request.session.get("reservas_propias", [])


@require_POST
def cancelar(request, reserva_id):
    if not _puede_gestionar(request, reserva_id):
        raise PermissionDenied
    with transaction.atomic():
        reserva = get_object_or_404(Reserva.objects.select_for_update(), pk=reserva_id)
        if reserva.estado == Reserva.CONFIRMADA:
            reserva.estado = Reserva.CANCELADA
            reserva.cancelada_en = timezone.now()
            reserva.cancelada_por = request.user if rol(request.user) else None
            reserva.motivo_cancelacion = request.POST.get("motivo", "").strip()[:200]
            reserva.save()
    if rol(request.user):
        return redirect("reservaciones")
    return redirect("reserva_confirmada", reserva_id=reserva.pk)


@personal
def editar_reserva(request, reserva_id):
    hoy = timezone.localdate()
    with transaction.atomic():
        reserva = get_object_or_404(Reserva.objects.select_related("habitacion").select_for_update(), pk=reserva_id)
        if reserva.estado not in (Reserva.CONFIRMADA, Reserva.ACTIVA):
            return render(request, "hotel/editar.html", {"reserva": reserva, "bloqueado": True,
                          "error": "Esta reserva ya no se puede editar."}, status=409)
        solo_salida = reserva.estado == Reserva.ACTIVA  # con el perro en el hotel solo se mueve la salida
        contexto = {"reserva": reserva, "solo_salida": solo_salida}
        if request.method == "POST":
            d = request.POST
            nueva_entrada = reserva.entrada if solo_salida else _fecha(d.get("entrada", ""))
            nueva_salida = _fecha(d.get("salida", ""))
            hab_id = reserva.habitacion_id if solo_salida else d.get("habitacion")
            nombre = reserva.nombre if solo_salida else d.get("nombre", "").strip()
            telefono = reserva.telefono if solo_salida else d.get("telefono", "").strip()
            perro = reserva.perro if solo_salida else d.get("perro", "").strip()[:80]
            perro2 = reserva.perro2 if solo_salida else d.get("perro2", "").strip()[:80]
            if solo_salida:
                error = None if nueva_salida and nueva_salida >= hoy and nueva_salida > nueva_entrada else \
                    "La salida debe ser hoy o después, y posterior a la entrada."
            else:
                error = _validar_fechas(nueva_entrada, nueva_salida)
                if not error and (not nombre or not telefono):
                    error = "Escriba nombre y teléfono."
            habitacion = None
            if not error:
                habitacion = Habitacion.objects.select_for_update().filter(pk=hab_id).first()
                if habitacion is None:
                    error = "Elija una habitación."
                elif not habitaciones_libres(nueva_entrada, nueva_salida, excluir=reserva.pk).filter(pk=habitacion.pk).exists():
                    error = "Esa habitación no está libre en esas fechas."
            if error:
                contexto.update(error=error, datos=d, libres=_libres_para_editar(reserva, nueva_entrada, nueva_salida))
                return render(request, "hotel/editar.html", contexto, status=409 if "libre" in error else 400)
            reserva.habitacion, reserva.entrada, reserva.salida = habitacion, nueva_entrada, nueva_salida
            reserva.nombre, reserva.telefono = nombre, telefono
            if perro2 != reserva.perro2 and not solo_salida:
                reserva.perro2 = perro2
                reserva.perro2_ref = None
                if perro2 and reserva.cliente:
                    reserva.perro2_ref = reserva.cliente.perros.filter(nombre__iexact=perro2).first() or \
                        Perro.objects.create(cliente=reserva.cliente, nombre=perro2)
            if perro != reserva.perro and not solo_salida:
                reserva.perro = perro
                reserva.perro_ref = None
                if perro and reserva.cliente:
                    reserva.perro_ref = reserva.cliente.perros.filter(nombre__iexact=perro).first() or \
                        Perro.objects.create(cliente=reserva.cliente, nombre=perro)
            reserva.save()
            return redirect("reservaciones")
        contexto["libres"] = _libres_para_editar(reserva, reserva.entrada, reserva.salida)
    return render(request, "hotel/editar.html", contexto)


def _libres_para_editar(reserva, entrada, salida):
    if not entrada or not salida or salida <= entrada:
        return [reserva.habitacion]
    return list(habitaciones_libres(entrada, salida, excluir=reserva.pk))


# ---------------------------------------------------------------- cuidado diario
PLAN_BASE = [
    ("alimentacion", "Desayuno", time(7, 0)),
    ("paseo", "Paseo de la mañana", time(10, 0)),
    ("limpieza", "Limpieza de la habitación", time(12, 0)),
    ("alimentacion", "Cena", time(17, 0)),
]


def crear_plan_base(reserva):
    """Plan mínimo al hacer el check-in; el personal agrega medicación y cuidados especiales."""
    if not reserva.plan.exists():
        ItemPlan.objects.bulk_create([ItemPlan(reserva=reserva, tipo=t, detalle=d, hora=h) for t, d, h in PLAN_BASE])


def _tareas_de_hoy(hoy):
    """Crea las tareas de hoy que falten y devuelve, por estancia activa, su lista ordenada."""
    reservas = list(Reserva.objects.filter(estado=Reserva.ACTIVA).select_related("habitacion", "perro_ref", "perro2_ref")
                    .prefetch_related("plan").order_by("habitacion__numero"))
    existentes = {(t.item_id): t for t in Tarea.objects.filter(fecha=hoy, item__reserva__in=reservas).select_related("hecha_por")}
    nuevas = [Tarea(item=i, fecha=hoy) for r in reservas for i in r.plan.all() if i.pk not in existentes]
    if nuevas:
        Tarea.objects.bulk_create(nuevas, ignore_conflicts=True)
        existentes = {t.item_id: t for t in Tarea.objects.filter(fecha=hoy, item__reserva__in=reservas).select_related("hecha_por")}
    filas = []
    for r in reservas:
        pares = sorted(((i, existentes[i.pk]) for i in r.plan.all() if i.pk in existentes),
                       key=lambda par: (par[0].hora is None, par[0].hora or time(0), par[0].pk))
        tareas = [{"item": i, "tarea": t} for i, t in pares]
        notas = [(ref.nombre, ref.notas) for ref in (r.perro_ref, r.perro2_ref) if ref and ref.notas]
        filas.append({"reserva": r, "tareas": tareas, "notas": notas,
                      "pendientes": sum(1 for _, t in pares if not t.hecha)})
    return filas


@personal
def cuidado(request):
    hoy = timezone.localdate()
    filas = _tareas_de_hoy(hoy)
    return render(request, "hotel/cuidado.html", {"filas": filas, "hoy": hoy,
                                                  "pendientes": sum(f["pendientes"] for f in filas)})


@personal
@require_POST
def tarea_hecha(request, tarea_id):
    with transaction.atomic():
        t = get_object_or_404(Tarea.objects.select_for_update(), pk=tarea_id)
        t.hecha = not t.hecha
        t.hecha_por, t.hecha_en = (request.user, timezone.now()) if t.hecha else (None, None)
        t.save()
    return redirect("cuidado")


@personal
def plan_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva.objects.select_related("habitacion"), pk=reserva_id)
    error = None
    if reserva.estado != Reserva.ACTIVA:
        return render(request, "hotel/plan.html", {"reserva": reserva, "tipos": ItemPlan.TIPOS,
                      "error": "El plan de cuidado solo se edita mientras el perro está en el hotel.", "bloqueado": True}, status=409)
    if request.method == "POST":
        if request.POST.get("accion") == "quitar":
            ItemPlan.objects.filter(pk=request.POST.get("item_id"), reserva=reserva).delete()
            return redirect("plan_reserva", reserva_id=reserva.pk)
        tipo, detalle = request.POST.get("tipo"), request.POST.get("detalle", "").strip()[:200]
        hora_txt = request.POST.get("hora", "")
        try:
            hora = time.fromisoformat(hora_txt) if hora_txt else None
        except ValueError:
            hora, error = None, "La hora no es válida."
        if tipo not in dict(ItemPlan.TIPOS):
            error = "Elija el tipo de tarea."
        elif tipo == "medicacion" and not detalle:
            error = "Escriba la medicación y la dosis."
        if not error:
            ItemPlan.objects.create(reserva=reserva, tipo=tipo, detalle=detalle, hora=hora)
            return redirect("plan_reserva", reserva_id=reserva.pk)
    return render(request, "hotel/plan.html", {"reserva": reserva, "tipos": ItemPlan.TIPOS, "error": error,
                                               "items": reserva.plan.all()}, status=400 if error else 200)


# ---------------------------------------------------------------- pagos
def _monto(texto):
    try:
        m = Decimal(texto.replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        return None
    return m if m > 0 else None


@personal
def pagos_reserva(request, reserva_id):
    error = None
    with transaction.atomic():
        reserva = get_object_or_404(Reserva.objects.select_related("habitacion").select_for_update(), pk=reserva_id)
        if request.method == "POST":
            tipo = Pago.DEVOLUCION if request.POST.get("accion") == "devolucion" else Pago.PAGO
            monto, metodo = _monto(request.POST.get("monto", "")), request.POST.get("metodo")
            if monto is None or metodo not in dict(Pago.METODOS):
                error = "Indique un monto mayor que cero y el método."
            elif tipo == Pago.PAGO and reserva.estado == Reserva.CANCELADA:
                error = "La reserva está cancelada: no se registran pagos nuevos."
            elif tipo == Pago.PAGO and monto > reserva.saldo:
                error = f"El pago supera el saldo pendiente (${reserva.saldo:.2f})."
            elif tipo == Pago.DEVOLUCION and monto > reserva.pagado:
                error = f"La devolución supera lo pagado (${reserva.pagado:.2f})."
            else:
                Pago.objects.create(reserva=reserva, tipo=tipo, monto=monto, metodo=metodo,
                                    referencia=request.POST.get("referencia", "").strip()[:60], registrado_por=request.user)
                return redirect("pagos_reserva", reserva_id=reserva.pk)
    return render(request, "hotel/pagos.html", {
        "reserva": reserva, "pagos": reserva.pagos.select_related("registrado_por"), "metodos": Pago.METODOS,
        "error": error, "anticipo": reserva.anticipo_requerido if settings.ANTICIPO_PORCENTAJE else None,
        "anticipo_pct": settings.ANTICIPO_PORCENTAJE}, status=400 if error else 200)


@personal
def caja(request):
    dia = _fecha(request.GET.get("dia", "")) or timezone.localdate()
    pagos = Pago.objects.filter(creado__date=dia).select_related("reserva__habitacion", "registrado_por").order_by("creado")
    resumen = []
    for clave, etiqueta in Pago.METODOS:
        cobrado = sum((p.monto for p in pagos if p.metodo == clave and p.tipo == Pago.PAGO), Decimal("0"))
        devuelto = sum((p.monto for p in pagos if p.metodo == clave and p.tipo == Pago.DEVOLUCION), Decimal("0"))
        resumen.append({"etiqueta": etiqueta, "cobrado": cobrado, "devuelto": devuelto, "neto": cobrado - devuelto})
    return render(request, "hotel/caja.html", {"dia": dia, "pagos": pagos, "resumen": resumen,
                  "neto_total": sum((r["neto"] for r in resumen), Decimal("0"))})
