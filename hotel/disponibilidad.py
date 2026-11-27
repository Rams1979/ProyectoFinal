from datetime import date

from .models import Habitacion, Reserva


def habitaciones_libres(entrada: date, salida: date, excluir=None):
    """Habitaciones sin reservas traslapadas con [entrada, salida).

    El día de salida queda libre para una nueva entrada. Las reservas canceladas no ocupan.
    `excluir` es el id de una reserva que se está editando y no debe contarse.
    """
    traslapadas = Reserva.objects.filter(entrada__lt=salida, salida__gt=entrada).exclude(estado=Reserva.CANCELADA)
    if excluir:
        traslapadas = traslapadas.exclude(pk=excluir)
    return Habitacion.objects.exclude(pk__in=traslapadas.values("habitacion_id"))
