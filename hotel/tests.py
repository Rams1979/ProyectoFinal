from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from .disponibilidad import habitaciones_libres
from .models import Habitacion, Reserva


from django.contrib.auth.models import Group, User


def entrar(client, rol="Recepción", nombre=None):
    """Crea un usuario con el rol dado y abre sesión."""
    nombre = nombre or f"u-{rol[:3].lower()}"
    u = User.objects.create_user(nombre, password="clave-de-prueba-1")
    u.groups.add(Group.objects.get(name=rol))
    client.force_login(u)
    return u


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
        self.assertContains(self.client.get(r.url), "pagada")  # el visitante ve su propia confirmación
        entrar(self.client)
        self.assertContains(self.client.get("/reservaciones/"), "Ana")

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
        entrar(self.client, "Administrador")
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


from django.core.management import call_command


class RecorridoCompletoTests(TestCase):
    """Recorrido de la demostración: disponibilidad -> reserva -> lista -> chat sin clave."""

    def test_recorrido(self):
        d = timezone.localdate() + timedelta(days=10)
        entrada, salida = d.isoformat(), (d + timedelta(days=3)).isoformat()

        r = self.client.get("/disponibilidad/", {"entrada": entrada, "salida": salida})
        self.assertContains(r, "Habitaciones libres (30)")
        self.assertContains(r, "3 noches")

        r = self.client.get("/reservar/5/", {"entrada": entrada, "salida": salida})
        self.assertContains(r, "Total $90")
        r = self.client.post("/reservar/5/", {"entrada": entrada, "salida": salida, "nombre": "Luis", "telefono": "7000-0000"}, follow=True)
        self.assertContains(r, "Reserva confirmada")
        self.assertContains(r, "pagada")

        r = self.client.get("/disponibilidad/", {"entrada": entrada, "salida": salida})
        self.assertContains(r, "Habitaciones libres (29)")

        # Reserva contigua (entra el día que sale la otra): permitida
        r = self.client.post("/reservar/5/", {"entrada": salida, "salida": (d + timedelta(days=4)).isoformat(),
                                              "nombre": "Eva", "telefono": "7000-1111"})
        self.assertEqual(r.status_code, 302)

        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        r = self.client.post("/chat/mensaje/", json.dumps({"historial": [{"role": "user", "content": "hola"}]}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

        entrar(self.client)
        self.assertContains(self.client.get("/reservaciones/"), "Luis")

    def test_limpiar_demo_conserva_habitaciones(self):
        d = timezone.localdate() + timedelta(days=2)
        Reserva.objects.create(habitacion=Habitacion.objects.get(numero=1), nombre="A", telefono="1",
                               entrada=d, salida=d + timedelta(days=1))
        SolicitudContacto.objects.create(nombre="B", telefono="2")
        call_command("limpiar_demo")
        self.assertEqual(Reserva.objects.count(), 0)
        self.assertEqual(SolicitudContacto.objects.count(), 0)
        self.assertEqual(Habitacion.objects.count(), 30)


class OcupacionTests(TestCase):
    def setUp(self):
        entrar(self.client)
        self.hoy = timezone.localdate()
        self.h = Habitacion.objects.get(numero=3)

    def _reserva(self, entrada, salida, hab=None):
        return Reserva.objects.create(habitacion=hab or self.h, nombre="Ana", telefono="1", entrada=entrada, salida=salida)

    def test_panel_cuenta_estados(self):
        self._reserva(self.hoy, self.hoy + timedelta(days=2))
        r = self.client.get("/panel/")
        self.assertContains(r, "Llega hoy")
        self.assertContains(r, "<strong>29</strong> libres")

    def test_checkin_checkout_y_limpieza(self):
        res = self._reserva(self.hoy, self.hoy + timedelta(days=3))
        # sin nombre de perro no avanza
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"perro": ""}).status_code, 400)
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"perro": "Rocky"}).status_code, 302)
        res.refresh_from_db()
        self.assertEqual((res.estado, res.perro), ("activa", "Rocky"))
        self.assertContains(self.client.get("/panel/"), "perro Rocky")

        # check-out anticipado: cierra, libera fechas y deja la habitación en limpieza
        self.client.post(f"/checkout/{res.pk}/")
        res.refresh_from_db(); self.h.refresh_from_db()
        self.assertEqual(res.estado, "cerrada")
        self.assertEqual(res.salida, self.hoy)
        self.assertTrue(self.h.en_limpieza)
        self.assertContains(self.client.get("/panel/"), "En limpieza")
        # las fechas restantes quedan libres para otra reserva
        d = self.hoy + timedelta(days=1)
        self.assertIn(self.h, habitaciones_libres(d, d + timedelta(days=1)))

        # en limpieza no admite otro check-in hasta marcarla disponible
        nueva = self._reserva(self.hoy, self.hoy + timedelta(days=2))
        self.assertEqual(self.client.post(f"/checkin/{nueva.pk}/", {"perro": "Luna"}).status_code, 409)
        self.client.post(f"/limpieza/{self.h.pk}/")
        self.assertEqual(self.client.post(f"/checkin/{nueva.pk}/", {"perro": "Luna"}).status_code, 302)

    def test_no_checkin_antes_de_la_entrada_ni_doble(self):
        futura = self._reserva(self.hoy + timedelta(days=2), self.hoy + timedelta(days=4))
        self.assertEqual(self.client.post(f"/checkin/{futura.pk}/", {"perro": "X"}).status_code, 409)
        res = self._reserva(self.hoy, self.hoy + timedelta(days=1), Habitacion.objects.get(numero=4))
        self.client.post(f"/checkin/{res.pk}/", {"perro": "Rocky"})
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"perro": "Otro"}).status_code, 409)

    def test_sale_hoy_y_checkout_es_post(self):
        res = self._reserva(self.hoy - timedelta(days=2), self.hoy)
        Reserva.objects.filter(pk=res.pk).update(estado="activa", perro="Max")
        self.assertContains(self.client.get("/panel/"), "Sale hoy")
        self.assertEqual(self.client.get(f"/checkout/{res.pk}/").status_code, 405)


class ClientesTests(TestCase):
    def setUp(self):
        entrar(self.client)
        self.hoy = timezone.localdate()

    def _reservar(self, perro="Rocky", tel="8888", hab=1):
        d = {"entrada": str(self.hoy), "salida": str(self.hoy + timedelta(days=2)), "nombre": "Ana", "telefono": tel, "perro": perro}
        return self.client.post(f"/reservar/{hab}/", d)

    def test_reserva_registra_cliente_y_perro_sin_duplicar(self):
        self._reservar()
        self._reservar(tel="8888", hab=2)  # misma persona y mismo perro, otra habitación
        from hotel.models import Cliente, Perro
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertEqual(Perro.objects.count(), 1)
        self.assertEqual(Reserva.objects.count(), 2)

    def test_alta_cliente_perro_y_vacunas(self):
        from hotel.models import Cliente
        r = self.client.post("/clientes/nuevo/", {"nombre": "Luis", "telefono": "7777"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.post("/clientes/nuevo/", {"nombre": "X", "telefono": "7777"}).status_code, 400)
        c = Cliente.objects.get(telefono="7777")
        self.client.post(f"/clientes/{c.pk}/", {"accion": "perro", "nombre": "Luna"})
        p = c.perros.get()
        self.assertEqual(len(p.pendientes(self.hoy)), 5)
        for tipo in ("rabia", "multiple", "bordetella", "desparasitacion", "pulgas"):
            self.client.post(f"/clientes/{c.pk}/", {"accion": "vacuna", "perro_id": p.pk, "tipo": tipo,
                             "aplicada": str(self.hoy - timedelta(days=30)), "vence": str(self.hoy + timedelta(days=300))})
        self.assertEqual(p.pendientes(self.hoy), [])
        self.assertEqual(p.pendientes(self.hoy + timedelta(days=400))[0]["estado"], "vencida")
        malo = self.client.post(f"/clientes/{c.pk}/", {"accion": "vacuna", "perro_id": p.pk, "tipo": "rabia",
                                "aplicada": str(self.hoy), "vence": str(self.hoy - timedelta(days=1))})
        self.assertEqual(malo.status_code, 400)

    def test_checkin_exige_autorizacion_si_faltan_requisitos(self):
        self._reservar()
        res = Reserva.objects.get()
        self.assertContains(self.client.get(f"/checkin/{res.pk}/"), "Requisitos sanitarios pendientes")
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {}).status_code, 400)
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"autoriza": "1"}).status_code, 302)
        res.refresh_from_db()
        self.assertEqual((res.estado, res.perro), ("activa", "Rocky"))

    def test_checkin_sin_perro_en_reserva_lo_registra(self):
        from hotel.models import Perro
        self._reservar(perro="")
        res = Reserva.objects.get()
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"perro": "Max"}).status_code, 302)
        self.assertEqual(Perro.objects.get().nombre, "Max")
        self.assertContains(self.client.get("/clientes/?q=max"), "Ana")


class MenuTests(TestCase):
    def test_menu_enlaza_todas_las_pantallas(self):
        entrar(self.client, "Administrador")
        r = self.client.get("/")
        for url in ("/panel/", "/disponibilidad/", "/reservaciones/", "/clientes/", "/chat/", "/solicitudes/", "/habitaciones/", "/usuarios/"):
            self.assertContains(r, f'href="{url}"')
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get("/habitaciones/"), "Habitaciones (30)")


class AccesoTests(TestCase):
    PRIVADAS = ["/panel/", "/reservaciones/", "/clientes/", "/clientes/nuevo/", "/habitaciones/", "/solicitudes/", "/usuarios/"]

    def test_visitante_solo_ve_disponibilidad_y_chat(self):
        for url in self.PRIVADAS:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/ingresar/", r.url)
        for url in ("/", "/disponibilidad/", "/chat/", "/ingresar/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertNotContains(self.client.get("/"), "Panel de ocupación")
        # check-in y check-out no se pueden hacer sin sesión
        d = timezone.localdate()
        res = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=1), nombre="A", telefono="1", entrada=d, salida=d + timedelta(days=1))
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"perro": "X"}).status_code, 302)
        self.assertEqual(self.client.post(f"/checkout/{res.pk}/").status_code, 302)
        res.refresh_from_db()
        self.assertEqual(res.estado, "confirmada")

    def test_confirmacion_solo_para_quien_reservo(self):
        d = timezone.localdate() + timedelta(days=3)
        ajena = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=2), nombre="Otra", telefono="9", entrada=d, salida=d + timedelta(days=1))
        self.assertEqual(self.client.get(f"/reserva/{ajena.pk}/").status_code, 403)

    def test_recepcion_no_ve_solicitudes_ni_usuarios(self):
        entrar(self.client, "Recepción")
        self.assertEqual(self.client.get("/panel/").status_code, 200)
        self.assertEqual(self.client.get("/solicitudes/").status_code, 403)
        self.assertEqual(self.client.get("/usuarios/").status_code, 403)
        self.assertNotContains(self.client.get("/"), "Solicitudes de contacto")

    def test_usuario_sin_rol_no_entra(self):
        User.objects.create_user("sinrol", password="clave-de-prueba-1")
        r = self.client.post("/ingresar/", {"username": "sinrol", "password": "clave-de-prueba-1"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/panel/").status_code, 302)

    def test_login_logout_y_auditoria(self):
        u = User.objects.create_user("rita", password="clave-de-prueba-1")
        u.groups.add(Group.objects.get(name="Recepción"))
        self.assertEqual(self.client.post("/ingresar/", {"username": "rita", "password": "mala"}).status_code, 400)
        r = self.client.post("/ingresar/?next=/panel/", {"username": "rita", "password": "clave-de-prueba-1"})
        self.assertEqual((r.status_code, r.url), (302, "/panel/"))
        # redirección externa no permitida
        self.client.post("/salir/")
        r = self.client.post("/ingresar/?next=//evil.com", {"username": "rita", "password": "clave-de-prueba-1"})
        self.assertEqual(r.url, "/")
        d = timezone.localdate()
        res = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=1), nombre="A", telefono="1", entrada=d, salida=d + timedelta(days=1))
        self.client.post(f"/checkin/{res.pk}/", {"perro": "Rocky"})
        self.client.post(f"/checkout/{res.pk}/")
        res.refresh_from_db()
        self.assertEqual((res.checkin_por, res.checkout_por), (u, u))
        self.client.post("/salir/")
        self.assertEqual(self.client.get("/panel/").status_code, 302)

    def test_bloqueo_tras_intentos_fallidos(self):
        from django.core.cache import cache
        cache.clear()
        u = User.objects.create_user("beto", password="clave-de-prueba-1")
        u.groups.add(Group.objects.get(name="Recepción"))
        for _ in range(5):
            self.client.post("/ingresar/", {"username": "beto", "password": "mala"})
        r = self.client.post("/ingresar/", {"username": "beto", "password": "clave-de-prueba-1"})
        self.assertContains(r, "Demasiados intentos", status_code=400)
        cache.clear()

    def test_admin_crea_y_desactiva_usuarios(self):
        admin = entrar(self.client, "Administrador")
        malo = self.client.post("/usuarios/", {"username": "nuevo", "password": "corta", "rol": "Recepción"})
        self.assertEqual(malo.status_code, 400)
        ok = self.client.post("/usuarios/", {"username": "nuevo", "password": "una-clave-larga-1", "rol": "Recepción"})
        self.assertEqual(ok.status_code, 302)
        nuevo = User.objects.get(username="nuevo")
        self.client.post(f"/usuarios/{nuevo.pk}/activo/")
        nuevo.refresh_from_db()
        self.assertFalse(nuevo.is_active)
        self.client.post(f"/usuarios/{admin.pk}/activo/")  # no se desactiva a sí mismo
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)

    def test_crear_admin_desde_variables(self):
        import os
        from io import StringIO
        os.environ.update(ADMIN_USERNAME="jefe", ADMIN_PASSWORD="otra-clave-larga-1")
        try:
            call_command("crear_admin", stdout=StringIO())
            call_command("crear_admin", stdout=StringIO())  # idempotente
        finally:
            os.environ.pop("ADMIN_USERNAME"); os.environ.pop("ADMIN_PASSWORD")
        self.assertEqual(User.objects.filter(username="jefe", is_superuser=True).count(), 1)
