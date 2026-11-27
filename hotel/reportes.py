"""Cálculo de los reportes: ocupación, ingresos, reservas y movimientos próximos."""
import csv
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Cliente, Habitacion, Pago, Perro, Reserva

MAX_DIAS = 366
VIGENTES = [Reserva.CONFIRMADA, Reserva.ACTIVA, Reserva.CERRADA]  # reservas que ocupan o ocuparon la habitación


def rango_por_defecto(hoy):
    """El mes en curso completo."""
    return hoy.replace(day=1), hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])


def validar_rango(desde, hasta):
    if desde is None or hasta is None:
        return "Indique las dos fechas del período."
    if hasta < desde:
        return "La fecha final no puede ser anterior a la inicial."
    if (hasta - desde).days + 1 > MAX_DIAS:
        return f"El período no puede pasar de {MAX_DIAS} días."
    return None


def ocupacion(desde, hasta):
    """Noches ocupadas por día en [desde, hasta]. Una reserva ocupa de la entrada hasta la víspera de la salida."""
    capacidad = Habitacion.objects.filter(activa=True).count()
    por_dia = {desde + timedelta(days=i): 0 for i in range((hasta - desde).days + 1)}
    reservas = Reserva.objects.filter(estado__in=VIGENTES, entrada__lte=hasta, salida__gt=desde)
    for r in reservas:
        for d in range((max(r.entrada, desde) - desde).days, (min(r.salida - timedelta(days=1), hasta) - desde).days + 1):
            por_dia[desde + timedelta(days=d)] += 1
    dias = [{"fecha": f, "ocupadas": n, "libres": max(capacidad - n, 0),
             "pct": round(100 * n / capacidad) if capacidad else 0} for f, n in por_dia.items()]
    noches = sum(d["ocupadas"] for d in dias)
    disponibles = capacidad * len(dias)
    return {"dias": dias, "capacidad": capacidad, "noches": noches,
            "pct": round(100 * noches / disponibles, 1) if disponibles else 0,
            "pico": max(dias, key=lambda d: d["ocupadas"]) if dias else None}


def _pagado(reserva):
    """Pagos menos devoluciones, usando los pagos ya cargados (sin consultas extra)."""
    return sum((p.monto if p.tipo == Pago.PAGO else -p.monto for p in reserva.pagos.all()), Decimal("0"))


def reservas_del_periodo(desde, hasta):
    """Reservas cuya entrada cae en el período, con su valor y su estado de cobro."""
    qs = (Reserva.objects.filter(entrada__gte=desde, entrada__lte=hasta)
          .select_related("habitacion", "creada_por").prefetch_related("pagos").order_by("entrada", "habitacion__numero"))
    filas, por_estado = [], {k: 0 for k, _ in Reserva.ESTADOS}
    reservado = cobrado_de_ellas = Decimal("0")
    for r in qs:
        por_estado[r.estado] += 1
        pagado = _pagado(r)
        filas.append({"r": r, "total": r.total, "pagado": pagado})
        if r.estado != Reserva.CANCELADA:
            reservado += r.total
            cobrado_de_ellas += pagado
    cancel = por_estado[Reserva.CANCELADA]
    total = len(filas)
    return {
        "filas": filas, "total": total,
        "por_estado": [(etiqueta, por_estado[k]) for k, etiqueta in Reserva.ESTADOS],
        "reservado": reservado, "pagado": cobrado_de_ellas, "por_cobrar": reservado - cobrado_de_ellas,
        "cancelaciones": cancel, "tasa_cancelacion": round(100 * cancel / total, 1) if total else 0,
        "en_linea": sum(1 for f in filas if f["r"].creada_por_id is None),
        "por_el_personal": sum(1 for f in filas if f["r"].creada_por_id is not None),
    }


def ingresos(desde, hasta):
    """Cobros y devoluciones registrados en el período (por fecha del movimiento), por método."""
    pagos = list(Pago.objects.filter(creado__date__gte=desde, creado__date__lte=hasta)
                 .select_related("reserva__habitacion", "registrado_por").order_by("creado"))
    metodos = []
    for clave, etiqueta in Pago.METODOS:
        cobrado = sum((p.monto for p in pagos if p.metodo == clave and p.tipo == Pago.PAGO), Decimal("0"))
        devuelto = sum((p.monto for p in pagos if p.metodo == clave and p.tipo == Pago.DEVOLUCION), Decimal("0"))
        metodos.append({"etiqueta": etiqueta, "cobrado": cobrado, "devuelto": devuelto, "neto": cobrado - devuelto})
    return {"pagos": pagos, "metodos": metodos,
            "cobrado": sum((m["cobrado"] for m in metodos), Decimal("0")),
            "devuelto": sum((m["devuelto"] for m in metodos), Decimal("0")),
            "neto": sum((m["neto"] for m in metodos), Decimal("0"))}


def clientes_y_perros(desde, hasta):
    nuevos = Cliente.objects.filter(creado__date__gte=desde, creado__date__lte=hasta).count()
    perros = Perro.objects.filter(
        reservas__estado__in=VIGENTES, reservas__entrada__lte=hasta, reservas__salida__gt=desde).distinct().count()
    return {"clientes_nuevos": nuevos, "perros_alojados": perros}


def proximos_movimientos(hoy, dias=7):
    """Llegadas y salidas de los próximos días, con los requisitos sanitarios que faltan en las llegadas."""
    fin = hoy + timedelta(days=dias - 1)
    llegadas = []
    for r in (Reserva.objects.filter(estado=Reserva.CONFIRMADA, entrada__gte=hoy, entrada__lte=fin)
              .select_related("habitacion", "perro_ref", "perro2_ref").order_by("entrada", "habitacion__numero")):
        pendientes = sum(len(ref.pendientes(r.salida)) for ref in (r.perro_ref, r.perro2_ref) if ref)
        llegadas.append({"r": r, "pendientes": pendientes, "sin_perro": not (r.perro_ref or r.perro2_ref)})
    salidas = list(Reserva.objects.filter(estado__in=[Reserva.CONFIRMADA, Reserva.ACTIVA], salida__gte=hoy, salida__lte=fin)
                   .select_related("habitacion").order_by("salida", "habitacion__numero"))
    return {"desde": hoy, "hasta": fin, "llegadas": llegadas, "salidas": salidas}


# ---- exportación CSV (para Excel o Power BI)
def _seguro(valor):
    """Evita que Excel interprete como fórmula un texto que escribió un cliente (=, +, -, @)."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


def escribir_csv(respuesta, encabezados, filas):
    respuesta.write("\ufeff")  # para que Excel reconozca las tildes
    w = csv.writer(respuesta)
    w.writerow(encabezados)
    for f in filas:
        w.writerow([_seguro(v) for v in f])


def filas_ocupacion(desde, hasta):
    o = ocupacion(desde, hasta)
    return (["fecha", "habitaciones_ocupadas", "habitaciones_libres", "ocupacion_pct"],
            [[d["fecha"].isoformat(), d["ocupadas"], d["libres"], d["pct"]] for d in o["dias"]])


def filas_reservas(desde, hasta):
    datos = reservas_del_periodo(desde, hasta)
    return (["id", "habitacion", "cliente", "telefono", "perros", "entrada", "salida", "noches", "tarifa_noche",
             "total", "pagado", "saldo", "estado", "origen"],
            [[f["r"].pk, f["r"].habitacion.numero, f["r"].nombre, f["r"].telefono, f["r"].perros_texto,
              f["r"].entrada.isoformat(), f["r"].salida.isoformat(), f["r"].noches, f["r"].tarifa_noche, f["total"],
              f["pagado"], 0 if f["r"].estado == Reserva.CANCELADA else f["total"] - f["pagado"],
              f["r"].get_estado_display(), "personal" if f["r"].creada_por_id else "cliente en línea"]
             for f in datos["filas"]])


def filas_pagos(desde, hasta):
    datos = ingresos(desde, hasta)
    return (["fecha", "hora", "reserva", "habitacion", "cliente", "tipo", "monto", "metodo", "referencia", "registro"],
            [[timezone.localtime(p.creado).date().isoformat(), timezone.localtime(p.creado).strftime("%H:%M"), p.reserva_id,
              p.reserva.habitacion.numero, p.reserva.nombre, p.get_tipo_display(), p.monto, p.get_metodo_display(),
              p.referencia, p.registrado_por.username if p.registrado_por else ""] for p in datos["pagos"]])
