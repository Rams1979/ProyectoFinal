from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from .disponibilidad import habitaciones_libres
from .models import Habitacion, Reserva
from .permisos import rol


from django.contrib.auth.models import User

from .models import Perfil, PerfilUsuario


def entrar(client, rol="Recepción", nombre=None):
    """Crea un usuario con el rol dado y abre sesión."""
    nombre = nombre or f"u-{rol[:3].lower()}"
    u = User.objects.create_user(nombre, password="clave-de-prueba-1")
    PerfilUsuario.objects.create(usuario=u, perfil=Perfil.objects.get(nombre=rol))
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
        self.assertContains(r, "Habitación 01 · Mediana · $60")


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
        self.assertContains(self.client.get(r.url), "se coordina con el hotel")  # el visitante ve su propia confirmación
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
        self.assertContains(r, "se coordina con el hotel")

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
        self.assertContains(self.client.get("/habitaciones/"), "Habitación 30")
        for url in ("/articulos/", "/perfiles/"):
            self.assertContains(r, f'href="{url}"')
            self.assertEqual(self.client.get(url).status_code, 200)


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
        PerfilUsuario.objects.create(usuario=u, perfil=Perfil.objects.get(nombre="Recepción"))
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
        PerfilUsuario.objects.create(usuario=u, perfil=Perfil.objects.get(nombre="Recepción"))
        for _ in range(5):
            self.client.post("/ingresar/", {"username": "beto", "password": "mala"})
        r = self.client.post("/ingresar/", {"username": "beto", "password": "clave-de-prueba-1"})
        self.assertContains(r, "Demasiados intentos", status_code=400)
        cache.clear()

    def test_admin_crea_y_desactiva_usuarios(self):
        admin = entrar(self.client, "Administrador")
        malo = self.client.post("/usuarios/", {"username": "nuevo", "nombre": "Nuevo Usuario", "password": "corta", "rol": "Recepción"})
        self.assertEqual(malo.status_code, 400)
        ok = self.client.post("/usuarios/", {"username": "nuevo", "nombre": "Nuevo Usuario", "password": "una-clave-larga-1", "rol": "Recepción"})
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


class CancelarEditarTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.d = self.hoy + timedelta(days=5)
        self.h1, self.h2 = Habitacion.objects.get(numero=1), Habitacion.objects.get(numero=2)

    def _reserva(self, hab=None, dias=2, **kw):
        return Reserva.objects.create(habitacion=hab or self.h1, nombre="Ana", telefono="1",
                                      entrada=self.d, salida=self.d + timedelta(days=dias), **kw)

    def test_cancelar_libera_la_habitacion(self):
        r = self._reserva()
        self.assertNotIn(self.h1, habitaciones_libres(self.d, self.d + timedelta(days=2)))
        u = entrar(self.client)
        self.assertEqual(self.client.post(f"/reserva/{r.pk}/cancelar/", {"motivo": "viaje"}).status_code, 302)
        r.refresh_from_db()
        self.assertEqual((r.estado, r.motivo_cancelacion, r.cancelada_por), ("cancelada", "viaje", u))
        self.assertIn(self.h1, habitaciones_libres(self.d, self.d + timedelta(days=2)))
        self.assertContains(self.client.get("/reservaciones/"), "Cancelada")
        # se puede volver a reservar esas fechas
        self.assertEqual(self._reserva().pk is not None, True)

    def test_no_se_cancela_una_reserva_en_hotel(self):
        r = self._reserva(estado="activa")
        entrar(self.client)
        self.client.post(f"/reserva/{r.pk}/cancelar/")
        r.refresh_from_db()
        self.assertEqual(r.estado, "activa")

    def test_visitante_cancela_solo_la_suya(self):
        ajena = self._reserva(self.h2)
        datos = {"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=2)).isoformat(), "nombre": "Luis", "telefono": "77"}
        propia = Reserva.objects.get(pk=int(self.client.post(f"/reservar/{self.h1.pk}/", datos).url.split("/")[2]))
        self.assertEqual(self.client.post(f"/reserva/{ajena.pk}/cancelar/").status_code, 403)
        r = self.client.post(f"/reserva/{propia.pk}/cancelar/", follow=True)
        self.assertContains(r, "Reserva cancelada")
        propia.refresh_from_db(); ajena.refresh_from_db()
        self.assertEqual((propia.estado, propia.cancelada_por, ajena.estado), ("cancelada", None, "confirmada"))
        self.assertEqual(self.client.get(f"/reserva/{propia.pk}/editar/").status_code, 302)  # editar es del personal

    def test_editar_fechas_y_habitacion(self):
        r = self._reserva()
        otra = self._reserva(self.h2)
        entrar(self.client)
        base = {"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=3)).isoformat(),
                "habitacion": self.h1.pk, "nombre": "Ana P.", "telefono": "1", "perro": "Rocky"}
        # la propia reserva no cuenta contra sí misma
        self.assertEqual(self.client.post(f"/reserva/{r.pk}/editar/", base).status_code, 302)
        r.refresh_from_db()
        self.assertEqual((r.salida, r.nombre, r.perro), (self.d + timedelta(days=3), "Ana P.", "Rocky"))
        # a una habitación ocupada: rechazado y sin cambios
        self.assertEqual(self.client.post(f"/reserva/{r.pk}/editar/", {**base, "habitacion": self.h2.pk}).status_code, 409)
        r.refresh_from_db()
        self.assertEqual(r.habitacion, self.h1)
        # fechas inválidas
        self.assertEqual(self.client.post(f"/reserva/{r.pk}/editar/", {**base, "salida": base["entrada"]}).status_code, 400)
        # cambio válido de habitación
        libre = Habitacion.objects.get(numero=3)
        self.assertEqual(self.client.post(f"/reserva/{r.pk}/editar/", {**base, "habitacion": libre.pk}).status_code, 302)
        r.refresh_from_db()
        self.assertEqual(r.habitacion, libre)
        self.assertContains(self.client.get(f"/reserva/{r.pk}/editar/"), "Guardar cambios")

    def test_en_hotel_solo_se_mueve_la_salida(self):
        r = Reserva.objects.create(habitacion=self.h1, nombre="Ana", telefono="1", entrada=self.hoy - timedelta(days=1),
                                   salida=self.hoy + timedelta(days=1), estado="activa", perro="Rocky")
        entrar(self.client)
        nueva = self.hoy + timedelta(days=4)
        self.client.post(f"/reserva/{r.pk}/editar/", {"salida": nueva.isoformat(), "nombre": "Cambiado"})
        r.refresh_from_db()
        self.assertEqual((r.salida, r.nombre), (nueva, "Ana"))
        # no se puede extender sobre otra reserva
        Reserva.objects.create(habitacion=self.h1, nombre="Z", telefono="2", entrada=self.hoy + timedelta(days=2), salida=self.hoy + timedelta(days=3))
        malo = self.client.post(f"/reserva/{r.pk}/editar/", {"salida": (self.hoy + timedelta(days=6)).isoformat()})
        self.assertEqual(malo.status_code, 409)

    def test_cerrada_y_cancelada_no_se_editan(self):
        entrar(self.client)
        for estado in ("cerrada", "cancelada"):
            r = self._reserva(self.h2, estado=estado)
            self.assertEqual(self.client.get(f"/reserva/{r.pk}/editar/").status_code, 409)
            r.delete()


from decimal import Decimal

from .models import Articulo, BloqueoHabitacion, ItemPlan, Pago, Tarea


class SegundoPerroTests(TestCase):
    def setUp(self):
        self.d = timezone.localdate() + timedelta(days=4)
        self.datos = {"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=2)).isoformat(),
                      "nombre": "Ana", "telefono": "8888", "perro": "Rocky"}

    def test_total_con_recargo_del_50_por_ciento(self):
        r = self.client.get("/reservar/1/", {k: self.datos[k] for k in ("entrada", "salida")})
        self.assertContains(r, "$90 en lugar de $60")
        r = self.client.post("/reservar/1/", {**self.datos, "perro2": "Max"}, follow=True)
        self.assertContains(r, "Total $90")
        self.assertContains(r, "perros Rocky y Max")
        res = Reserva.objects.get()
        self.assertEqual(res.total, Decimal("90"))
        self.assertEqual(res.perro2_ref.nombre, "Max")
        self.assertEqual(res.cliente.perros.count(), 2)

    def test_sin_segundo_perro_no_hay_recargo(self):
        self.client.post("/reservar/1/", self.datos)
        self.assertEqual(Reserva.objects.get().total, Decimal("60"))

    def test_checkin_revisa_requisitos_de_ambos_perros(self):
        self.client.post("/reservar/1/", {**self.datos, "perro2": "Max"})
        res = Reserva.objects.get()
        Reserva.objects.filter(pk=res.pk).update(entrada=timezone.localdate())
        entrar(self.client)
        r = self.client.get(f"/checkin/{res.pk}/")
        self.assertContains(r, "Rocky: Rabia")
        self.assertContains(r, "Max: Rabia")
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"autoriza": "1"}).status_code, 302)

    def test_editar_agrega_segundo_perro(self):
        self.client.post("/reservar/1/", self.datos)
        res = Reserva.objects.get()
        entrar(self.client)
        self.client.post(f"/reserva/{res.pk}/editar/", {**self.datos, "habitacion": 1, "perro2": "Luna"})
        res.refresh_from_db()
        self.assertEqual((res.perro2, res.total), ("Luna", Decimal("90")))


class CuidadoTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.u = entrar(self.client)
        self.res = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=1), nombre="Ana", telefono="1",
                                          entrada=self.hoy, salida=self.hoy + timedelta(days=2), perro="Rocky")

    def _checkin(self):
        self.client.post(f"/checkin/{self.res.pk}/", {"autoriza": "1"})
        self.res.refresh_from_db()

    def test_checkin_crea_plan_base_y_tareas_del_dia(self):
        self._checkin()
        self.assertEqual(self.res.plan.count(), 4)
        r = self.client.get("/cuidado/")
        self.assertContains(r, "Desayuno")
        self.assertContains(r, "4</strong> tareas pendientes")
        self.assertEqual(Tarea.objects.filter(fecha=self.hoy).count(), 4)
        self.client.get("/cuidado/")  # no duplica
        self.assertEqual(Tarea.objects.count(), 4)

    def test_marcar_hecha_y_deshacer(self):
        self._checkin()
        self.client.get("/cuidado/")
        t = Tarea.objects.first()
        self.client.post(f"/cuidado/tarea/{t.pk}/hecha/")
        t.refresh_from_db()
        self.assertEqual((t.hecha, t.hecha_por), (True, self.u))
        self.assertContains(self.client.get("/cuidado/"), "3</strong> tareas pendientes")
        self.client.post(f"/cuidado/tarea/{t.pk}/hecha/")
        t.refresh_from_db()
        self.assertFalse(t.hecha)

    def test_plan_medicacion_y_notas_del_perro(self):
        from .models import Cliente, Perro
        c = Cliente.objects.create(nombre="Ana", telefono="1")
        p = Perro.objects.create(cliente=c, nombre="Rocky", notas="Alérgico al pollo")
        Reserva.objects.filter(pk=self.res.pk).update(cliente=c, perro_ref=p)
        self._checkin()
        self.assertEqual(self.client.post(f"/cuidado/reserva/{self.res.pk}/", {"tipo": "medicacion", "detalle": ""}).status_code, 400)
        self.client.post(f"/cuidado/reserva/{self.res.pk}/", {"tipo": "medicacion", "detalle": "Apoquel 1 tableta", "hora": "08:00"})
        r = self.client.get("/cuidado/")
        self.assertContains(r, "Apoquel 1 tableta")
        self.assertContains(r, "Alérgico al pollo")
        item = ItemPlan.objects.get(tipo="medicacion")
        self.client.post(f"/cuidado/reserva/{self.res.pk}/", {"accion": "quitar", "item_id": item.pk})
        self.assertFalse(ItemPlan.objects.filter(tipo="medicacion").exists())

    def test_no_se_edita_plan_si_no_esta_en_hotel(self):
        self.assertEqual(self.client.get(f"/cuidado/reserva/{self.res.pk}/").status_code, 409)

    def test_visitante_no_ve_cuidado(self):
        self.client.logout()
        self.assertEqual(self.client.get("/cuidado/").status_code, 302)


class PagosTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.u = entrar(self.client)
        self.res = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=1), nombre="Ana", telefono="1",
                                          entrada=self.hoy + timedelta(days=3), salida=self.hoy + timedelta(days=5))  # total $60

    def _pagar(self, monto, metodo="sinpe", **extra):
        return self.client.post(f"/reserva/{self.res.pk}/pagos/", {"monto": monto, "metodo": metodo, **extra})

    def test_pago_parcial_y_total(self):
        self.assertEqual(self.res.estado_pago, "Pendiente")
        self.assertEqual(self._pagar("20", referencia="123").status_code, 302)
        self.assertEqual((self.res.estado_pago, self.res.saldo), ("Parcial", Decimal("40")))
        self._pagar("40", "efectivo")
        self.assertEqual((self.res.estado_pago, self.res.saldo), ("Pagada", Decimal("0")))
        self.assertContains(self.client.get("/reservaciones/"), "Pagada")

    def test_validaciones_de_pago(self):
        self.assertEqual(self._pagar("0").status_code, 400)
        self.assertEqual(self._pagar("abc").status_code, 400)
        self.assertEqual(self._pagar("10", "bitcoin").status_code, 400)
        self.assertContains(self._pagar("61"), "supera el saldo", status_code=400)
        self.assertEqual(self.res.pagos.count(), 0)

    def test_cancelada_con_pagos_exige_definir_devolucion(self):
        self._pagar("30")
        self.client.post(f"/reserva/{self.res.pk}/cancelar/")
        self.res.refresh_from_db()
        self.assertEqual(self.res.estado_pago, "Devolución por definir")
        self.assertContains(self.client.get(f"/reserva/{self.res.pk}/pagos/"), "política de devolución está por definir")
        self.assertEqual(self._pagar("10").status_code, 400)  # no se cobra sobre una cancelada
        self.assertEqual(self.client.post(f"/reserva/{self.res.pk}/pagos/", {"accion": "devolucion", "monto": "31", "metodo": "sinpe"}).status_code, 400)
        self.client.post(f"/reserva/{self.res.pk}/pagos/", {"accion": "devolucion", "monto": "30", "metodo": "sinpe", "referencia": "cancelación"})
        self.assertEqual((self.res.pagado, self.res.estado_pago), (Decimal("0"), "Sin pagos"))

    def test_caja_del_dia_por_metodo(self):
        self._pagar("20", "sinpe")
        self._pagar("10", "efectivo")
        self.client.post(f"/reserva/{self.res.pk}/pagos/", {"accion": "devolucion", "monto": "5", "metodo": "efectivo"})
        r = self.client.get("/caja/")
        self.assertContains(r, "<strong>$25,00</strong>")
        self.assertContains(self.client.get("/caja/", {"dia": "2020-01-01"}), "Sin movimientos ese día")

    def test_checkout_anticipado_deja_saldo_a_favor(self):
        Reserva.objects.filter(pk=self.res.pk).update(entrada=self.hoy - timedelta(days=1), salida=self.hoy + timedelta(days=2), estado="activa")
        self._pagar("90")
        self.client.post(f"/checkout/{self.res.pk}/")
        self.res.refresh_from_db()
        self.assertEqual((self.res.total, self.res.estado_pago), (Decimal("30"), "Saldo a favor del cliente"))

    def test_anticipo_configurable_y_visitante_sin_acceso(self):
        with self.settings(ANTICIPO_PORCENTAJE=30):
            self.assertEqual(self.res.anticipo_requerido, Decimal("18.00"))
            self.assertContains(self.client.get(f"/reserva/{self.res.pk}/pagos/"), "18,00")
        self.client.logout()
        self.assertEqual(self.client.get(f"/reserva/{self.res.pk}/pagos/").status_code, 302)
        self.assertEqual(self.client.get("/caja/").status_code, 302)

    def test_limpiar_demo_borra_pagos(self):
        self._pagar("10")
        call_command("limpiar_demo")
        self.assertEqual((Pago.objects.count(), Reserva.objects.count()), (0, 0))


class MantenimientoUsuariosTests(TestCase):
    def setUp(self):
        self.admin = entrar(self.client, "Administrador", "jefe")

    def _crear(self, usuario="rita", rol_="Recepción", nombre="Rita Mora", clave="una-clave-larga-1"):
        return self.client.post("/usuarios/", {"username": usuario, "nombre": nombre, "password": clave, "rol": rol_})

    def test_alta_con_nombre_y_perfil_y_exige_el_nombre(self):
        self.assertEqual(self._crear(nombre="").status_code, 400)
        self.assertEqual(self._crear().status_code, 302)
        u = User.objects.get(username="rita")
        self.assertEqual((u.first_name, u.perfil_hotel.perfil.nombre), ("Rita Mora", "Recepción"))
        self.assertContains(self.client.get("/usuarios/"), "Rita Mora")

    def test_editar_nombre_perfil_y_clave(self):
        self._crear()
        u = User.objects.get(username="rita")
        r = self.client.post(f"/usuarios/{u.pk}/", {"nombre": "Rita M.", "rol": "Administrador", "activo": "1", "password": ""})
        self.assertEqual(r.status_code, 302)
        u.refresh_from_db()
        self.assertEqual((u.first_name, rol(u)), ("Rita M.", "Administrador"))
        self.assertTrue(u.check_password("una-clave-larga-1"))  # clave vacía no la cambia
        self.assertEqual(self.client.post(f"/usuarios/{u.pk}/", {"nombre": "Rita M.", "rol": "Recepción", "activo": "1", "password": "corta"}).status_code, 400)
        self.client.post(f"/usuarios/{u.pk}/", {"nombre": "Rita M.", "rol": "Recepción", "activo": "1", "password": "clave-nueva-larga-2"})
        u.refresh_from_db()
        self.assertTrue(u.check_password("clave-nueva-larga-2"))
        self.assertEqual(rol(u), "Recepción")

    def test_desactivar_desde_la_edicion_bloquea_el_ingreso(self):
        self._crear()
        u = User.objects.get(username="rita")
        self.client.post(f"/usuarios/{u.pk}/", {"nombre": "Rita Mora", "rol": "Recepción"})  # sin "activo"
        u.refresh_from_db()
        self.assertFalse(u.is_active)
        self.client.post("/salir/")
        self.assertEqual(self.client.post("/ingresar/", {"username": "rita", "password": "una-clave-larga-1"}).status_code, 400)

    def test_no_se_cambia_su_propio_perfil_ni_se_deja_sin_administrador(self):
        r = self.client.post(f"/usuarios/{self.admin.pk}/", {"nombre": "Jefe", "rol": "Recepción"})
        self.assertContains(r, "propio perfil", status_code=400)
        # otro administrador que intenta degradar al único restante
        self._crear("ana", "Administrador", "Ana Gómez")
        ana = User.objects.get(username="ana")
        self.client.post("/salir/")
        self.client.force_login(ana)
        self.client.post(f"/usuarios/{self.admin.pk}/", {"nombre": "Jefe", "rol": "Recepción", "activo": "1"})  # queda ana: permitido
        self.assertEqual(rol(User.objects.get(pk=self.admin.pk)), "Recepción")
        # ana es ahora la única administradora: no se puede desactivar ni degradar a nadie más que lo deje en cero
        otro = User.objects.get(pk=self.admin.pk)
        self.client.post(f"/usuarios/{otro.pk}/", {"nombre": "Jefe", "rol": "Administrador", "activo": "1"})
        self.client.force_login(otro)
        r = self.client.post(f"/usuarios/{ana.pk}/", {"nombre": "Ana", "rol": "Recepción", "activo": "1"})
        self.assertEqual(r.status_code, 302)  # hay otro administrador (el propio)
        self.client.force_login(ana)  # ana ya es Recepción: sin acceso
        self.assertEqual(self.client.get("/usuarios/").status_code, 403)

    def test_ultimo_administrador_no_se_desactiva_ni_degrada(self):
        self._crear("ana", "Administrador", "Ana")
        ana = User.objects.get(username="ana")
        self.client.post(f"/usuarios/{ana.pk}/activo/")  # hay otro admin (jefe): se puede
        ana.refresh_from_db()
        self.assertFalse(ana.is_active)
        # jefe es el único activo: otro admin inactivo no cuenta; no puede quedar en cero
        self.client.post(f"/usuarios/{ana.pk}/activo/")
        ana.refresh_from_db()
        self.assertTrue(ana.is_active)
        self.client.force_login(ana)
        self.client.post(f"/usuarios/{self.admin.pk}/activo/")
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)  # ana sigue siendo admin activa
        r = self.client.post(f"/usuarios/{ana.pk}/", {"nombre": "Ana", "rol": "Administrador"})  # propia, sin 'activo': se mantiene activa
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.get(pk=ana.pk).is_active)

    def test_superusuario_degradado_deja_de_ser_administrador(self):
        su = User.objects.create_superuser("root", password="una-clave-larga-1")
        self.client.post(f"/usuarios/{su.pk}/", {"nombre": "Root", "rol": "Recepción", "activo": "1"})
        su.refresh_from_db()
        self.assertEqual((su.is_superuser, rol(su)), (False, "Recepción"))

    def test_cada_usuario_cambia_su_contrasena(self):
        self._crear()
        self.client.post("/salir/")
        self.client.post("/ingresar/", {"username": "rita", "password": "una-clave-larga-1"})
        self.assertContains(self.client.post("/clave/", {"actual": "mala", "nueva": "otra-clave-larga-3", "repite": "otra-clave-larga-3"}), "no es correcta", status_code=400)
        self.assertContains(self.client.post("/clave/", {"actual": "una-clave-larga-1", "nueva": "otra-clave-larga-3", "repite": "distinta-larga-4"}), "no coinciden", status_code=400)
        self.assertEqual(self.client.post("/clave/", {"actual": "una-clave-larga-1", "nueva": "corta", "repite": "corta"}).status_code, 400)
        r = self.client.post("/clave/", {"actual": "una-clave-larga-1", "nueva": "otra-clave-larga-3", "repite": "otra-clave-larga-3"})
        self.assertContains(r, "Contraseña actualizada")
        self.assertEqual(self.client.get("/panel/").status_code, 200)  # la sesión sigue abierta
        self.assertTrue(User.objects.get(username="rita").check_password("otra-clave-larga-3"))

    def test_recepcion_no_edita_usuarios(self):
        self.client.post("/salir/")
        entrar(self.client, "Recepción", "recep")
        self.assertEqual(self.client.get(f"/usuarios/{self.admin.pk}/").status_code, 403)
        self.assertEqual(self.client.post(f"/usuarios/{self.admin.pk}/", {"nombre": "X", "rol": "Recepción"}).status_code, 403)
        self.assertEqual(self.client.get("/clave/").status_code, 200)


class PerfilesPropiosTests(TestCase):
    def setUp(self):
        self.admin = entrar(self.client, "Administrador", "jefe")

    def test_perfiles_de_origen(self):
        self.assertEqual(set(Perfil.objects.values_list("nombre", flat=True)), {"Administrador", "Recepción", "Cuidador"})
        self.assertTrue(Perfil.objects.get(nombre="Administrador").es_sistema)

    def test_crear_perfil_y_asignarlo(self):
        r = self.client.post("/perfiles/", {"nombre": "Contador", "areas": ["caja", "reservas"]})
        self.assertEqual(r.status_code, 302)
        p = Perfil.objects.get(nombre="Contador")
        self.assertEqual(p.areas, ["reservas", "caja"])  # en el orden del catálogo
        self.client.post("/usuarios/", {"username": "cony", "nombre": "Cony", "password": "una-clave-larga-1", "rol": "Contador"})
        self.client.post("/salir/")
        self.client.post("/ingresar/", {"username": "cony", "password": "una-clave-larga-1"})
        self.assertEqual(self.client.get("/caja/").status_code, 200)
        self.assertEqual(self.client.get("/reservaciones/").status_code, 200)
        for url in ("/panel/", "/clientes/", "/cuidado/", "/habitaciones/", "/articulos/", "/solicitudes/", "/usuarios/", "/perfiles/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        menu = self.client.get("/")
        self.assertContains(menu, "Caja del día")
        self.assertNotContains(menu, "Panel de ocupación")

    def test_cuidador_solo_ve_cuidado(self):
        self.client.post("/salir/")
        entrar(self.client, "Cuidador", "cuido")
        self.assertEqual(self.client.get("/cuidado/").status_code, 200)
        self.assertEqual(self.client.get("/caja/").status_code, 403)
        d = timezone.localdate()
        res = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=1), nombre="A", telefono="1", entrada=d, salida=d + timedelta(days=1))
        self.assertEqual(self.client.post(f"/checkin/{res.pk}/", {"perro": "X"}).status_code, 403)
        self.assertEqual(self.client.post(f"/reserva/{res.pk}/cancelar/").status_code, 403)

    def test_validaciones_y_edicion(self):
        self.assertEqual(self.client.post("/perfiles/", {"nombre": "", "areas": ["caja"]}).status_code, 400)
        self.assertEqual(self.client.post("/perfiles/", {"nombre": "Vacío"}).status_code, 400)
        self.assertEqual(self.client.post("/perfiles/", {"nombre": "recepción", "areas": ["caja"]}).status_code, 400)
        self.client.post("/perfiles/", {"nombre": "Contador", "areas": ["caja", "inventada"]})
        p = Perfil.objects.get(nombre="Contador")
        self.assertEqual(p.areas, ["caja"])  # un área inexistente se ignora
        self.client.post(f"/perfiles/{p.pk}/", {"nombre": "Contabilidad", "areas": ["caja", "clientes"]})
        p.refresh_from_db()
        self.assertEqual((p.nombre, p.areas), ("Contabilidad", ["caja", "clientes"]))

    def test_administrador_no_se_edita_ni_borra_y_perfil_en_uso_no_se_borra(self):
        adm = Perfil.objects.get(nombre="Administrador")
        self.assertEqual(self.client.get(f"/perfiles/{adm.pk}/").status_code, 409)
        self.assertEqual(self.client.post(f"/perfiles/{adm.pk}/", {"nombre": "X", "areas": ["caja"]}).status_code, 409)
        self.client.post(f"/perfiles/{adm.pk}/borrar/")
        self.assertTrue(Perfil.objects.filter(pk=adm.pk).exists())
        rec = Perfil.objects.get(nombre="Recepción")
        entrar(self.client, "Recepción", "rita")
        self.client.force_login(self.admin)
        self.client.post(f"/perfiles/{rec.pk}/borrar/")
        self.assertTrue(Perfil.objects.filter(pk=rec.pk).exists())  # tiene un usuario
        vacio = Perfil.objects.get(nombre="Cuidador")
        self.client.post(f"/perfiles/{vacio.pk}/borrar/")
        self.assertFalse(Perfil.objects.filter(pk=vacio.pk).exists())

    def test_cambio_de_areas_aplica_de_inmediato(self):
        rec = Perfil.objects.get(nombre="Recepción")
        entrar(self.client, "Recepción", "rita")
        self.assertEqual(self.client.get("/caja/").status_code, 200)
        rec.areas = ["panel"]
        rec.save()
        self.assertEqual(self.client.get("/caja/").status_code, 403)

    def test_usuario_con_perfil_degradado_pierde_el_acceso_de_admin(self):
        su = User.objects.create_superuser("root", password="una-clave-larga-1")
        PerfilUsuario.objects.create(usuario=su, perfil=Perfil.objects.get(nombre="Administrador"))
        self.client.post(f"/usuarios/{su.pk}/", {"nombre": "Root", "rol": "Cuidador", "activo": "1"})
        su.refresh_from_db()
        self.assertFalse(su.is_superuser)
        self.assertEqual(su.perfil_hotel.perfil.nombre, "Cuidador")


class TarifasYHabitacionesTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.u = entrar(self.client, "Administrador")
        self.h1 = Habitacion.objects.get(numero=1)
        self.d = self.hoy + timedelta(days=10)

    def _reserva(self, hab=None, dias=2, desde=None):
        desde = desde or self.d
        return Reserva.objects.create(habitacion=hab or self.h1, nombre="Ana", telefono="1", entrada=desde, salida=desde + timedelta(days=dias))

    def test_cambio_de_tarifa_no_altera_reservas_hechas(self):
        r = self._reserva()
        self.assertEqual(r.total, Decimal("60"))
        self.client.post(f"/habitaciones/{self.h1.pk}/", {"accion": "guardar", "tarifa": "40", "activa": "1"})
        self.h1.refresh_from_db()
        r.refresh_from_db()
        self.assertEqual((r.tarifa_noche, r.total), (Decimal("30.00"), Decimal("60.00")))
        nueva = self._reserva(dias=1, desde=self.d + timedelta(days=5))
        self.assertEqual(nueva.total, Decimal("40"))

    def test_tarifa_a_todas_y_validaciones(self):
        self.assertEqual(self.client.post("/habitaciones/", {"accion": "tarifa_todas", "tarifa": "0"}).status_code, 400)
        self.assertEqual(self.client.post("/habitaciones/", {"accion": "tarifa_todas", "tarifa": "abc"}).status_code, 400)
        self.client.post("/habitaciones/", {"accion": "tarifa_todas", "tarifa": "35,50"})
        self.assertEqual(set(Habitacion.objects.values_list("tarifa_noche", flat=True)), {Decimal("35.50")})
        r = self.client.get("/disponibilidad/", {"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=2)).isoformat()})
        self.assertContains(r, "71")  # 2 noches a 35,50

    def test_nueva_habitacion(self):
        self.assertEqual(self.client.post("/habitaciones/", {"accion": "nueva", "numero": "1", "tarifa": "30"}).status_code, 400)
        self.assertEqual(self.client.post("/habitaciones/", {"accion": "nueva", "numero": "31", "tarifa": "45"}).status_code, 302)
        self.assertEqual(Habitacion.objects.get(numero=31).tarifa_noche, Decimal("45.00"))
        self.assertIn(Habitacion.objects.get(numero=31), habitaciones_libres(self.d, self.d + timedelta(days=1)))

    def test_desactivar_exige_no_tener_reservas_vigentes(self):
        self._reserva()
        r = self.client.post(f"/habitaciones/{self.h1.pk}/", {"accion": "guardar", "tarifa": "30"})
        self.assertContains(r, "reserva(s) vigente(s)", status_code=409)
        h2 = Habitacion.objects.get(numero=2)
        self.client.post(f"/habitaciones/{h2.pk}/", {"accion": "guardar", "tarifa": "30"})
        h2.refresh_from_db()
        self.assertFalse(h2.activa)
        self.assertNotIn(h2, habitaciones_libres(self.d, self.d + timedelta(days=1)))
        self.assertNotContains(self.client.get("/panel/"), "Habitación 02")

    def test_mantenimiento_bloquea_fechas_y_reservas(self):
        hasta = self.d + timedelta(days=2)
        r = self.client.post(f"/habitaciones/{self.h1.pk}/", {"accion": "bloqueo", "desde": self.d.isoformat(), "hasta": hasta.isoformat(), "motivo": "pintura"})
        self.assertEqual(r.status_code, 302)
        # ambas fechas incluidas: ocupa hasta el día "hasta"
        self.assertNotIn(self.h1, habitaciones_libres(self.d, self.d + timedelta(days=1)))
        self.assertNotIn(self.h1, habitaciones_libres(hasta, hasta + timedelta(days=1)))
        self.assertIn(self.h1, habitaciones_libres(hasta + timedelta(days=1), hasta + timedelta(days=2)))
        self.assertIn(self.h1, habitaciones_libres(self.d - timedelta(days=2), self.d))  # sale el día que empieza
        # no se puede reservar en el rango
        datos = {"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=1)).isoformat(), "nombre": "Luis", "telefono": "7"}
        self.assertEqual(self.client.post(f"/reservar/{self.h1.pk}/", datos).status_code, 409)
        # quitar el bloqueo la libera
        b = BloqueoHabitacion.objects.get()
        self.client.post(f"/habitaciones/{self.h1.pk}/", {"accion": "quitar_bloqueo", "bloqueo_id": b.pk})
        self.assertIn(self.h1, habitaciones_libres(self.d, self.d + timedelta(days=1)))

    def test_no_se_bloquea_con_reservas_en_esas_fechas(self):
        self._reserva()
        r = self.client.post(f"/habitaciones/{self.h1.pk}/", {"accion": "bloqueo", "desde": self.d.isoformat(), "hasta": (self.d + timedelta(days=1)).isoformat()})
        self.assertContains(r, "reserva(s) en esas fechas", status_code=409)
        self.assertEqual(self.client.post(f"/habitaciones/{self.h1.pk}/", {"accion": "bloqueo", "desde": self.d.isoformat(), "hasta": (self.d - timedelta(days=1)).isoformat()}).status_code, 400)
        self.assertEqual(BloqueoHabitacion.objects.count(), 0)
        # sí se puede justo después de que sale
        self.assertEqual(self.client.post(f"/habitaciones/{self.h1.pk}/", {"accion": "bloqueo", "desde": (self.d + timedelta(days=2)).isoformat(), "hasta": (self.d + timedelta(days=3)).isoformat()}).status_code, 302)

    def test_panel_muestra_mantenimiento_y_checkin_se_bloquea(self):
        BloqueoHabitacion.objects.create(habitacion=self.h1, desde=self.hoy, hasta=self.hoy + timedelta(days=1))
        r = self.client.get("/panel/")
        self.assertContains(r, "En mantenimiento hasta el")
        self.assertContains(r, "<strong>1</strong> en mantenimiento")
        res = self._reserva(desde=self.hoy)  # reserva anterior al bloqueo (creada directo)
        self.assertContains(self.client.post(f"/checkin/{res.pk}/", {"perro": "Rocky"}), "mantenimiento hoy", status_code=409)

    def test_cambiar_de_habitacion_en_reserva_usa_la_tarifa_vigente_de_la_nueva(self):
        h3 = Habitacion.objects.get(numero=3)
        h3.tarifa_noche = Decimal("50")
        h3.save()
        r = self._reserva()
        self.client.post(f"/reserva/{r.pk}/editar/", {"entrada": self.d.isoformat(), "salida": (self.d + timedelta(days=2)).isoformat(),
                         "habitacion": h3.pk, "nombre": "Ana", "telefono": "1", "perro": ""})
        r.refresh_from_db()
        self.assertEqual((r.habitacion, r.total), (h3, Decimal("100.00")))

    def test_perfil_sin_area_habitaciones_no_entra(self):
        self.client.post("/salir/")
        entrar(self.client, "Recepción", "rita")
        for url in ("/habitaciones/", f"/habitaciones/{self.h1.pk}/", "/articulos/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)


class ArticulosTests(TestCase):
    def setUp(self):
        entrar(self.client, "Administrador")

    def test_servicios_de_origen_con_precio_por_definir(self):
        self.assertEqual(Articulo.objects.count(), 10)
        self.assertFalse(Articulo.objects.filter(precio__isnull=False).exists())
        self.assertContains(self.client.get("/articulos/"), "Por definir")

    def test_alta_edicion_y_desactivar(self):
        r = self.client.post("/articulos/", {"nombre": "Baño premium", "tipo": "servicio", "precio": "15", "unidad": "por baño"})
        self.assertEqual(r.status_code, 302)
        a = Articulo.objects.get(nombre="Baño premium")
        self.assertTrue(a.codigo.startswith("ART-"))
        self.assertEqual(a.precio, Decimal("15.00"))
        self.assertEqual(self.client.post("/articulos/", {"nombre": "X", "tipo": "servicio", "precio": "-3"}).status_code, 400)
        self.assertEqual(self.client.post("/articulos/", {"nombre": "Y", "tipo": "otro"}).status_code, 400)
        self.assertEqual(self.client.post("/articulos/", {"nombre": "Z", "tipo": "producto", "codigo": a.codigo}).status_code, 400)
        self.client.post(f"/articulos/{a.pk}/", {"codigo": a.codigo, "nombre": "Baño premium", "tipo": "servicio", "precio": "", "activo": "1"})
        a.refresh_from_db()
        self.assertIsNone(a.precio)  # vacío = por definir
        self.client.post(f"/articulos/{a.pk}/", {"codigo": a.codigo, "nombre": "Baño premium", "tipo": "servicio", "precio": "18"})
        a.refresh_from_db()
        self.assertFalse(a.activo)

    def test_chat_usa_precios_vigentes(self):
        from . import chat as chat_mod
        Articulo.objects.filter(codigo="SRV-006").update(precio=Decimal("20"))
        Articulo.objects.filter(codigo="SRV-001").update(activo=False)
        texto = chat_mod.texto_precios()
        self.assertIn("Hospedaje por noche: $30.00", texto)
        self.assertIn("Baño y peluquería canina (grooming): $20.00 por servicio", texto)
        self.assertIn("Transporte de mascotas: POR DEFINIR", texto)
        self.assertNotIn("Hospedaje por períodos prolongados", texto)
        Habitacion.objects.filter(numero=1).update(tarifa_noche=Decimal("40"))
        self.assertIn("desde $30.00 hasta $40.00", chat_mod.texto_precios())

    def test_chat_consulta_disponibilidad_con_la_tarifa_mas_baja(self):
        from . import chat as chat_mod
        Habitacion.objects.update(tarifa_noche=Decimal("50"))
        Habitacion.objects.filter(numero=2).update(tarifa_noche=Decimal("35"))
        d = timezone.localdate() + timedelta(days=3)
        r = chat_mod.consultar_disponibilidad(d.isoformat(), (d + timedelta(days=2)).isoformat())
        self.assertEqual((r["tarifa_noche_usd"], r["total_por_habitacion_usd"]), (35.0, 70.0))

    def test_solo_perfil_con_area_habitaciones_entra(self):
        self.client.post("/salir/")
        entrar(self.client, "Cuidador", "cuido")
        self.assertEqual(self.client.get("/articulos/").status_code, 403)


class CrearAdminTests(TestCase):
    """Valores ficticios: nunca poner aquí credenciales reales (el repositorio es público)."""

    USUARIO = "admin-prueba"
    CLAVE_1 = "clave-ficticia-uno-1"
    CLAVE_2 = "clave-ficticia-dos-2"

    def _correr(self, **env):
        import os
        from io import StringIO
        antes = {k: os.environ.pop(k, None) for k in ("ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_RESTABLECER")}
        os.environ.update(env)
        salida = StringIO()
        try:
            call_command("crear_admin", stdout=salida)
        finally:
            for k in antes:
                os.environ.pop(k, None)
                if antes[k] is not None:
                    os.environ[k] = antes[k]
        return salida.getvalue()

    def test_crea_el_administrador_y_entra(self):
        self.assertIn("creado", self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_1))
        r = self.client.post("/ingresar/", {"username": self.USUARIO, "password": self.CLAVE_1})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/usuarios/").status_code, 200)

    def test_limpia_espacios_y_comillas_de_las_variables(self):
        self._correr(ADMIN_USERNAME=f' "{self.USUARIO}" ', ADMIN_PASSWORD=f" '{self.CLAVE_1}' ")
        self.assertTrue(User.objects.get(username=self.USUARIO).check_password(self.CLAVE_1))

    def test_un_usuario_que_nunca_ingreso_toma_la_clave_de_la_variable(self):
        self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_1)
        salida = self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_2)
        self.assertIn("restablecido", salida)
        self.assertTrue(User.objects.get(username=self.USUARIO).check_password(self.CLAVE_2))
        self.assertEqual(self.client.post("/ingresar/", {"username": self.USUARIO, "password": self.CLAVE_2}).status_code, 302)

    def test_tras_ingresar_la_clave_ya_no_se_cambia_salvo_restablecer(self):
        self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_1)
        self.client.post("/ingresar/", {"username": self.USUARIO, "password": self.CLAVE_1})  # primer ingreso
        salida = self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_2)
        self.assertIn("ya ingresó antes", salida)
        self.assertIn("ADMIN_RESTABLECER=1", salida)
        self.assertTrue(User.objects.get(username=self.USUARIO).check_password(self.CLAVE_1))
        salida = self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_2, ADMIN_RESTABLECER="1")
        self.assertIn("ADMIN_RESTABLECER=1", salida)
        self.assertTrue(User.objects.get(username=self.USUARIO).check_password(self.CLAVE_2))

    def test_borra_la_cuenta_duplicada_con_espacios_y_crea_la_limpia(self):
        User.objects.create_superuser(username=self.USUARIO + " ", password=self.CLAVE_1)  # lo que dejaba un valor mal pegado
        salida = self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_1)
        self.assertIn("duplicada", salida)
        self.assertEqual(list(User.objects.values_list("username", flat=True)), [self.USUARIO])
        self.assertEqual(self.client.post("/ingresar/", {"username": self.USUARIO, "password": self.CLAVE_1}).status_code, 302)

    def test_informa_la_base_de_datos_sin_credenciales(self):
        salida = self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_1)
        self.assertIn("base de datos", salida)
        self.assertNotIn(self.CLAVE_1, salida)

    def test_restablecer_reactiva_y_devuelve_el_perfil(self):
        self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_1)
        u = User.objects.get(username=self.USUARIO)
        u.is_active = False
        u.save()
        PerfilUsuario.objects.filter(usuario=u).update(perfil=Perfil.objects.get(nombre="Cuidador"))
        self._correr(ADMIN_USERNAME=self.USUARIO, ADMIN_PASSWORD=self.CLAVE_2, ADMIN_RESTABLECER="1")
        r = self.client.post("/ingresar/", {"username": self.USUARIO, "password": self.CLAVE_2})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/usuarios/").status_code, 200)

    def test_sin_variables_avisa_y_no_falla(self):
        self.assertIn("faltan ADMIN_USERNAME", self._correr())


class ArranqueTests(TestCase):
    def test_prepara_el_administrador_al_arrancar(self):
        import os
        from .arranque import preparar_administrador
        os.environ.update(ADMIN_USERNAME="admin-prueba", ADMIN_PASSWORD="clave-ficticia-uno-1")
        try:
            preparar_administrador()
        finally:
            os.environ.pop("ADMIN_USERNAME"); os.environ.pop("ADMIN_PASSWORD")
        self.assertEqual(self.client.post("/ingresar/", {"username": "admin-prueba", "password": "clave-ficticia-uno-1"}).status_code, 302)

    def test_un_error_no_detiene_el_arranque(self):
        from unittest import mock
        from .arranque import preparar_administrador
        with mock.patch("hotel.arranque.call_command", side_effect=RuntimeError("sin tablas")):
            preparar_administrador()  # no debe lanzar


import csv as _csv
from io import StringIO as _StringIO

from . import reportes as rep


class ReportesTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.u = entrar(self.client, "Administrador")
        self.d0 = self.hoy.replace(day=1)
        h = lambda n: Habitacion.objects.get(numero=n)
        # A: hab 1, noches d0 y d0+1 (cerrada cuenta); B: hab 2, d0+1 a d0+3; C: cancelada, no cuenta
        self.a = Reserva.objects.create(habitacion=h(1), nombre="Ana", telefono="1", entrada=self.d0, salida=self.d0 + timedelta(days=2), estado="cerrada")
        self.b = Reserva.objects.create(habitacion=h(2), nombre="Beto", telefono="2", entrada=self.d0 + timedelta(days=1), salida=self.d0 + timedelta(days=4), creada_por=self.u)
        self.c = Reserva.objects.create(habitacion=h(3), nombre="Cris", telefono="3", entrada=self.d0, salida=self.d0 + timedelta(days=5), estado="cancelada")

    def test_ocupacion_por_dia(self):
        o = rep.ocupacion(self.d0, self.d0 + timedelta(days=4))
        self.assertEqual([d["ocupadas"] for d in o["dias"]], [1, 2, 1, 1, 0])  # la salida no cuenta; la cancelada tampoco
        self.assertEqual((o["noches"], o["capacidad"], o["pct"]), (5, 30, 3.3))
        self.assertEqual(o["pico"]["ocupadas"], 2)
        # un período que corta una reserva solo cuenta sus días dentro
        o2 = rep.ocupacion(self.d0 + timedelta(days=2), self.d0 + timedelta(days=3))
        self.assertEqual([d["ocupadas"] for d in o2["dias"]], [1, 1])

    def test_ocupacion_no_cuenta_habitaciones_inactivas_en_la_capacidad(self):
        Habitacion.objects.filter(numero__gt=20).update(activa=False)
        self.assertEqual(rep.ocupacion(self.d0, self.d0)["capacidad"], 20)

    def test_ingresos_por_metodo(self):
        Pago.objects.create(reserva=self.b, monto=Decimal("20"), metodo="sinpe")
        Pago.objects.create(reserva=self.b, monto=Decimal("30"), metodo="efectivo")
        Pago.objects.create(reserva=self.b, tipo="devolucion", monto=Decimal("5"), metodo="efectivo")
        i = rep.ingresos(self.d0, self.d0 + timedelta(days=30))
        por = {m["etiqueta"]: (m["cobrado"], m["devuelto"], m["neto"]) for m in i["metodos"]}
        self.assertEqual(por["SINPE"], (Decimal("20"), Decimal("0"), Decimal("20")))
        self.assertEqual(por["Efectivo"], (Decimal("30"), Decimal("5"), Decimal("25")))
        self.assertEqual((i["cobrado"], i["devuelto"], i["neto"]), (Decimal("50"), Decimal("5"), Decimal("45")))
        # fuera del período no entra
        self.assertEqual(rep.ingresos(self.d0 - timedelta(days=40), self.d0 - timedelta(days=30))["neto"], Decimal("0"))

    def test_reservas_del_periodo(self):
        Pago.objects.create(reserva=self.b, monto=Decimal("40"), metodo="sinpe")
        r = rep.reservas_del_periodo(self.d0, self.d0 + timedelta(days=10))
        self.assertEqual(r["total"], 3)
        self.assertEqual(dict(r["por_estado"]), {"Confirmada": 1, "En hotel": 0, "Cerrada": 1, "Cancelada": 1})
        self.assertEqual((r["cancelaciones"], r["tasa_cancelacion"]), (1, 33.3))
        self.assertEqual(r["reservado"], Decimal("60") + Decimal("90"))  # A (2 noches) + B (3 noches); la cancelada no
        self.assertEqual((r["pagado"], r["por_cobrar"]), (Decimal("40"), Decimal("110")))
        self.assertEqual((r["en_linea"], r["por_el_personal"]), (2, 1))

    def test_proximos_movimientos_y_requisitos(self):
        from .models import Cliente, Perro
        cli = Cliente.objects.create(nombre="Dora", telefono="9")
        perro = Perro.objects.create(cliente=cli, nombre="Max")
        entra = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=5), nombre="Dora", telefono="9", cliente=cli,
                                       perro_ref=perro, perro="Max", entrada=self.hoy + timedelta(days=2), salida=self.hoy + timedelta(days=4))
        sale = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=6), nombre="Eli", telefono="8",
                                      entrada=self.hoy - timedelta(days=1), salida=self.hoy + timedelta(days=1), estado="activa")
        lejos = Reserva.objects.create(habitacion=Habitacion.objects.get(numero=7), nombre="Fer", telefono="7",
                                       entrada=self.hoy + timedelta(days=20), salida=self.hoy + timedelta(days=22))
        p = rep.proximos_movimientos(self.hoy)
        self.assertEqual([l["r"].pk for l in p["llegadas"]], [entra.pk])
        self.assertEqual(p["llegadas"][0]["pendientes"], 5)  # ningún requisito registrado
        self.assertIn(sale.pk, [r.pk for r in p["salidas"]])
        self.assertNotIn(lejos.pk, [r.pk for r in p["salidas"]])

    def test_pagina_y_filtros(self):
        r = self.client.get("/reportes/", {"desde": self.d0.isoformat(), "hasta": (self.d0 + timedelta(days=4)).isoformat()})
        self.assertContains(r, "Ocupación")
        self.assertContains(r, "noches ocupadas")
        self.assertContains(r, "Exportar reservas CSV")
        self.assertEqual(self.client.get("/reportes/").status_code, 200)  # mes en curso por defecto
        self.assertEqual(self.client.get("/reportes/", {"desde": "2026-05-10", "hasta": "2026-05-01"}).status_code, 400)
        self.assertContains(self.client.get("/reportes/", {"desde": "2020-01-01", "hasta": "2026-01-01"}), "no puede pasar de", status_code=400)

    def test_exportar_csv_y_proteccion_contra_formulas(self):
        Reserva.objects.create(habitacion=Habitacion.objects.get(numero=8), nombre="=HYPERLINK(\"http://x\")", telefono="+506",
                               entrada=self.d0, salida=self.d0 + timedelta(days=1))
        Pago.objects.create(reserva=self.b, monto=Decimal("12.50"), metodo="tarjeta", referencia="@cmd")
        q = {"desde": self.d0.isoformat(), "hasta": (self.d0 + timedelta(days=30)).isoformat()}
        r = self.client.get("/reportes/exportar/reservas/", q)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        self.assertIn("attachment", r["Content-Disposition"])
        texto = r.content.decode("utf-8")
        self.assertTrue(texto.startswith("\ufeff"))
        filas = list(_csv.reader(_StringIO(texto.lstrip("\ufeff"))))
        self.assertEqual(filas[0][:3], ["id", "habitacion", "cliente"])
        nombres = [f[2] for f in filas[1:]]
        self.assertIn("'=HYPERLINK(\"http://x\")", nombres)  # neutralizada
        self.assertIn("'+506", [f[3] for f in filas[1:]])
        pagos = list(_csv.reader(_StringIO(self.client.get("/reportes/exportar/pagos/", q).content.decode("utf-8").lstrip("\ufeff"))))
        self.assertEqual((pagos[1][6], pagos[1][8]), ("12.50", "'@cmd"))  # monto y referencia neutralizada
        occ = list(_csv.reader(_StringIO(self.client.get("/reportes/exportar/ocupacion/", q).content.decode("utf-8").lstrip("\ufeff"))))
        self.assertEqual(len(occ), 1 + 31)
        self.assertEqual(self.client.get("/reportes/exportar/otro/", q).status_code, 404)
        # fechas ilegibles: se usa el mes en curso, igual que en la página
        self.assertEqual(self.client.get("/reportes/exportar/pagos/", {"desde": "x", "hasta": "y"}).status_code, 200)
        self.assertEqual(self.client.get("/reportes/exportar/pagos/", {"desde": q["hasta"], "hasta": q["desde"]}).status_code, 400)

    def test_permisos(self):
        self.client.post("/salir/")
        entrar(self.client, "Recepción", "rita")
        self.assertEqual(self.client.get("/reportes/").status_code, 403)
        self.assertEqual(self.client.get("/reportes/exportar/pagos/").status_code, 403)
        Perfil.objects.filter(nombre="Recepción").update(areas=["panel", "reportes"])
        self.assertEqual(self.client.get("/reportes/").status_code, 200)
        self.client.post("/salir/")
        self.assertEqual(self.client.get("/reportes/").status_code, 302)


class LogosTests(TestCase):
    def test_logo_aleatorio_en_publico_y_personal_y_se_sirve(self):
        import re
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        urls = set(re.findall(r'src="(/static/hotel/logos/logo-\d\.webp)"', r.content.decode()))
        self.assertEqual(len(urls), 1)  # el mismo logo en la cabecera y en el grande
        vistos = set()
        for _ in range(40):
            vistos |= set(re.findall(r'logos/(logo-\d)\.webp', self.client.get("/").content.decode()))
        self.assertGreater(len(vistos), 1)  # varía entre visitas
        entrar(self.client, "Administrador")
        self.assertContains(self.client.get("/"), "logos/logo-")
        for n in range(1, 6):
            self.assertEqual(self.client.get(f"/static/hotel/logos/logo-{n}.webp").status_code, 200)


class TamanoHabitacionTests(TestCase):
    def test_tamano_por_defecto_edicion_y_alta(self):
        from .models import Habitacion
        self.assertEqual(Habitacion.objects.get(numero=1).tamano, "mediana")
        entrar(self.client, "Administrador")
        h = Habitacion.objects.get(numero=1)
        r = self.client.post(f"/habitaciones/{h.pk}/", {"accion": "guardar", "tarifa": "30", "tamano": "grande", "activa": "1"})
        self.assertEqual(r.status_code, 302)
        h.refresh_from_db()
        self.assertEqual(h.tamano, "grande")
        self.assertEqual(self.client.post(f"/habitaciones/{h.pk}/", {"accion": "guardar", "tarifa": "30", "tamano": "enorme", "activa": "1"}).status_code, 400)
        self.assertEqual(self.client.post("/habitaciones/", {"accion": "nueva", "numero": "31", "tarifa": "40", "tamano": "pequena"}).status_code, 302)
        self.assertEqual(Habitacion.objects.get(numero=31).tamano, "pequena")
        self.assertEqual(self.client.post("/habitaciones/", {"accion": "nueva", "numero": "32", "tarifa": "40", "tamano": "x"}).status_code, 400)
        self.assertContains(self.client.get("/habitaciones/"), "Pequeña")

    def test_se_muestra_en_disponibilidad_y_panel_y_chat(self):
        from . import chat
        from .models import Habitacion
        Habitacion.objects.filter(numero=1).update(tamano="grande")
        e = timezone.localdate() + timedelta(days=3)
        s = e + timedelta(days=2)
        self.assertContains(self.client.get("/disponibilidad/", {"entrada": e.isoformat(), "salida": s.isoformat()}), "Grande")
        r = chat.consultar_disponibilidad(e.isoformat(), s.isoformat())
        self.assertEqual(r["libres_por_tamano"], {"Grande": 1, "Mediana": 29})
        entrar(self.client, "Administrador")
        self.assertContains(self.client.get("/panel/"), "Grande")
