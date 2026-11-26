from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from .disponibilidad import habitaciones_libres
from .models import Habitacion, Reserva


class DisponibilidadTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.h1 = Habitacion.objects.get(numero=1)

    def test_sin_reservas_hay_30_libres(self):
        d = self.hoy + timedelta(days=5)
        self.assertEqual(habitaciones_libres(d, d + timedelta(days=2)).count(), 30)

    def test_reserva_traslapada_oculta_la_habitacion(self):
        d = self.hoy + timedelta(days=5)
        Reserva.objects.create(habitacion=self.h1, nombre="A", telefono="1", entrada=d, salida=d + timedelta(days=3))
        libres = habitaciones_libres(d + timedelta(days=1), d + timedelta(days=2))
        self.assertNotIn(self.h1, libres)
        self.assertEqual(libres.count(), 29)

    def test_dia_de_salida_queda_libre(self):
        d = self.hoy + timedelta(days=5)
        Reserva.objects.create(habitacion=self.h1, nombre="A", telefono="1", entrada=d, salida=d + timedelta(days=3))
        self.assertIn(self.h1, habitaciones_libres(d + timedelta(days=3), d + timedelta(days=4)))

    def test_vista_valida_fechas(self):
        r = self.client.get("/disponibilidad/", {"entrada": "2020-01-01", "salida": "2020-01-03"})
        self.assertContains(r, "fecha pasada")
        d = self.hoy + timedelta(days=5)
        r = self.client.get("/disponibilidad/", {"entrada": d.isoformat(), "salida": d.isoformat()})
        self.assertContains(r, "posterior")
        r = self.client.get("/disponibilidad/", {"entrada": d.isoformat(), "salida": (d + timedelta(days=2)).isoformat()})
        self.assertContains(r, "Habitaciones libres (30)")
        self.assertContains(r, "$60 total")
