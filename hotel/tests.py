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
        self.assertContains(r, "Habitación 01 · $60")


class ReservaTests(TestCase):
    def setUp(self):
        self.d = timezone.localdate() + timedelta(days=5)
        self.datos = {"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=2)).isoformat(),
                      "nombre": "Ana", "telefono": "8888-0000"}
        self.h1 = Habitacion.objects.get(numero=1)

    def test_reservar_crea_reserva_y_la_lista(self):
        r = self.client.post(f"/reservar/{self.h1.pk}/", self.datos)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertContains(self.client.get("/reservaciones/"), "Ana")
        self.assertContains(self.client.get(r.url), "pagada")

    def test_no_se_puede_reservar_dos_veces_las_mismas_fechas(self):
        self.client.post(f"/reservar/{self.h1.pk}/", self.datos)
        r = self.client.post(f"/reservar/{self.h1.pk}/", self.datos)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Reserva.objects.count(), 1)
        r = self.client.get("/disponibilidad/", {"entrada": self.datos["entrada"], "salida": self.datos["salida"]})
        self.assertContains(r, "Habitaciones libres (29)")

    def test_exige_nombre_y_telefono(self):
        r = self.client.post(f"/reservar/{self.h1.pk}/", {**self.datos, "nombre": ""})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Reserva.objects.count(), 0)

    def test_formulario_get_muestra_el_total(self):
        r = self.client.get(f"/reservar/{self.h1.pk}/", {"entrada": self.datos["entrada"], "salida": self.datos["salida"]})
        self.assertContains(r, "Total $60")
        self.assertContains(r, "Confirmar reserva")
