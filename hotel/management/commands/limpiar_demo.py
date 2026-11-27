from django.core.management.base import BaseCommand

from hotel.models import Reserva, SolicitudContacto


class Command(BaseCommand):
    help = "Borra las reservas y solicitudes de contacto de prueba. Deja las 30 habitaciones."

    def handle(self, *args, **options):
        r = Reserva.objects.all().delete()[0]
        s = SolicitudContacto.objects.all().delete()[0]
        self.stdout.write(f"Reservas borradas: {r}. Solicitudes borradas: {s}.")
