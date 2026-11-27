from django.core.management.base import BaseCommand

from hotel.models import Cliente, Pago, Perro, Reserva, SolicitudContacto


class Command(BaseCommand):
    help = "Borra reservas, clientes, perros, vacunas y solicitudes de prueba. Deja las 30 habitaciones."

    def handle(self, *args, **options):
        Pago.objects.all().delete()
        r = Reserva.objects.all().delete()[0]  # incluye plan y tareas de cuidado
        Perro.objects.all().delete()  # incluye sus vacunas
        c = Cliente.objects.all().delete()[0]
        s = SolicitudContacto.objects.all().delete()[0]
        self.stdout.write(f"Reservas borradas: {r}. Clientes borrados: {c}. Solicitudes borradas: {s}.")
