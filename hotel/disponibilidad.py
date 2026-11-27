from datetime import date

from .models import BloqueoHabitacion, Habitacion, Reserva


def habitaciones_libres(entrada: date, salida: date, excluir=None):
    """Habitaciones activas, sin reservas traslapadas ni mantenimiento en [entrada, salida).

    El día de salida queda libre para una nueva entrada. Las reservas canceladas no ocupan.
    `excluir` es el id de una reserva que se está editando y no debe contarse.
    """
    traslapadas = Reserva.objects.filter(entrada__lt=salida, salida__gt=entrada).exclude(estado=Reserva.CANCELADA)
    if excluir:
        traslapadas = traslapadas.exclude(pk=excluir)
    en_mantenimiento = BloqueoHabitacion.objects.filter(desde__lt=salida, hasta__gte=entrada)
    return (Habitacion.objects.filter(activa=True)
            .exclude(pk__in=traslapadas.values("habitacion_id"))
            .exclude(pk__in=en_mantenimiento.values("habitacion_id")))
