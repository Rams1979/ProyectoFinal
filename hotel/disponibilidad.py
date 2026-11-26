from datetime import date

from .models import Habitacion


def habitaciones_libres(entrada: date, salida: date):
    """Habitaciones sin reservas traslapadas con [entrada, salida).

    El día de salida queda libre para una nueva entrada.
    """
    ocupadas = Habitacion.objects.filter(
        reservas__entrada__lt=salida, reservas__salida__gt=entrada
    ).values("pk")
    return Habitacion.objects.exclude(pk__in=ocupadas)
