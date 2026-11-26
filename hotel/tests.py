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


import json
from types import SimpleNamespace
from unittest import mock

from . import chat as chat_mod
from .models import SolicitudContacto


class _Bloque(SimpleNamespace):
    def model_dump(self):
        return dict(self.__dict__)


def _resp(stop, *bloques):
    return SimpleNamespace(stop_reason=stop, content=list(bloques))


class ChatTests(TestCase):
    def setUp(self):
        self.d = timezone.localdate() + timedelta(days=5)

    def _post(self, historial):
        return self.client.post("/chat/mensaje/", json.dumps({"historial": historial}), content_type="application/json")

    def test_sin_clave_responde_aviso_y_no_falla(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            r = self._post([{"role": "user", "content": "hola"}])
        self.assertEqual(r.status_code, 200)
        self.assertIn("no está disponible", r.json()["respuesta"])

    def test_herramienta_disponibilidad(self):
        r = chat_mod.consultar_disponibilidad(self.d.isoformat(), (self.d + timedelta(days=2)).isoformat())
        self.assertEqual(r["habitaciones_libres"], 30)
        self.assertEqual(r["total_por_habitacion_usd"], 60.0)
        self.assertIn("error", chat_mod.consultar_disponibilidad("2020-01-01", "2020-01-02"))
        self.assertIn("error", chat_mod.consultar_disponibilidad("x", "y"))

    def test_herramienta_contacto(self):
        self.assertTrue(chat_mod.registrar_contacto("Ana", "8888-0000", "dudas")["ok"])
        self.assertEqual(SolicitudContacto.objects.count(), 1)
        self.assertIn("error", chat_mod.registrar_contacto("", ""))
        self.assertContains(self.client.get("/solicitudes/"), "Ana")

    def test_ciclo_con_herramienta(self):
        uso = _Bloque(type="tool_use", id="t1", name="consultar_disponibilidad",
                      input={"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=2)).isoformat()})
        fake = mock.Mock()
        fake.messages.create.side_effect = [
            _resp("tool_use", uso),
            _resp("end_turn", _Bloque(type="text", text="Hay 30 habitaciones libres.")),
        ]
        with mock.patch.object(chat_mod, "_cliente", return_value=fake):
            r = self._post([{"role": "user", "content": "¿Hay espacio?"}])
        self.assertEqual(r.json()["respuesta"], "Hay 30 habitaciones libres.")
        enviado = fake.messages.create.call_args_list[1].kwargs["messages"]
        self.assertEqual(enviado[-1]["content"][0]["type"], "tool_result")
        self.assertIn("POR DEFINIR", fake.messages.create.call_args_list[0].kwargs["system"])

    def test_solicitud_invalida_y_pagina(self):
        self.assertEqual(self.client.post("/chat/mensaje/", "no json", content_type="application/json").status_code, 400)
        self.assertEqual(self._post("x").status_code, 400)
        self.assertContains(self.client.get("/chat/"), "Chat del hotel")
