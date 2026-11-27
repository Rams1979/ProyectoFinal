from datetime import date

from .models import BloqueoHabitacion, Habitacion, Reserva


def habitaciones_libres(entrada: date, salida: date, excluir=None, tamano_perro=None):
    """Habitaciones activas, sin reservas traslapadas ni mantenimiento en [entrada, salida).

    El día de salida queda libre para una nueva entrada. Las reservas canceladas no ocupan.
    `excluir` es el id de una reserva que se está editando y no debe contarse.
    `tamano_perro` (pequeno, mediano, grande o gigante) deja solo las habitaciones de su tamaño o mayor.
    """
    traslapadas = Reserva.objects.filter(entrada__lt=salida, salida__gt=entrada).exclude(estado=Reserva.CANCELADA)
    if excluir:
        traslapadas = traslapadas.exclude(pk=excluir)
    en_mantenimiento = BloqueoHabitacion.objects.filter(desde__lt=salida, hasta__gte=entrada)
    libres = (Habitacion.objects.filter(activa=True)
              .exclude(pk__in=traslapadas.values("habitacion_id"))
              .exclude(pk__in=en_mantenimiento.values("habitacion_id")))
    if tamano_perro in dict(Habitacion.TAMANOS_PERRO):
        libres = libres.filter(tamano__in=Habitacion.tamanos_para(tamano_perro))
    return libres
