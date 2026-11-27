"""Genera datos ficticios y reproducibles para probar reportes y Power BI. Todo cliente de demostración tiene un teléfono
que empieza por 8800 (ficticio), y solo eso se borra con --reemplazar."""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hotel.models import (Cliente, Habitacion, ItemPlan, Medicacion, NecesidadEspecial, Pago, Perro, PlanAlimentacion,
                          Reserva, SolicitudContacto, Tarea, Vacuna)
from hotel.views import crear_plan_base

PREFIJO = "8800"
NOMBRES = ["Andrea", "Carlos", "María", "José", "Daniela", "Luis", "Sofía", "Diego", "Valeria", "Andrés", "Paola", "Mauricio",
           "Karla", "Esteban", "Natalia", "Gabriel", "Fernanda", "Roberto", "Camila", "Jorge", "Lucía", "Pablo", "Mariana", "Felipe"]
APELLIDOS = ["Rojas", "Vargas", "Mora", "Jiménez", "Solano", "Araya", "Chaves", "Quesada", "Salazar", "Campos", "Brenes", "Calderón",
             "Murillo", "Cordero", "Valverde", "Segura", "Alvarado", "Núñez", "Barrantes", "Ulate"]
PERROS = ["Rocky", "Luna", "Max", "Bella", "Toby", "Nala", "Thor", "Kira", "Simba", "Coco", "Lola", "Zeus", "Mia", "Bruno", "Maya",
          "Duke", "Daisy", "Rex", "Canela", "Chispa", "Odie", "Molly", "Bobby", "Pelusa", "Nico", "Sasha", "Teo", "Lupe", "Apolo", "Frida"]
# raza, peso mínimo y máximo en kg, tamaño de habitación mínimo (1 pequeña, 2 mediana, 3 grande)
RAZAS = [("Chihuahua", 2, 4), ("Yorkshire", 2, 4), ("Poodle toy", 3, 6), ("Shih tzu", 5, 9), ("Pug", 7, 10),
         ("Schnauzer", 11, 16), ("Beagle", 10, 14), ("Cocker spaniel", 12, 16), ("Criollo", 8, 24), ("Bulldog francés", 9, 14),
         ("Border collie", 15, 22), ("Labrador", 25, 34), ("Golden retriever", 27, 36), ("Pastor alemán", 28, 40),
         ("Husky siberiano", 20, 27), ("Boxer", 25, 32), ("Rottweiler", 40, 50), ("Gran danés", 46, 60)]
ORIGENES = ["Instagram", "Facebook", "Recomendación de un amigo", "Veterinario", "Google", "Vivero Ryokuen"]
MOTIVOS = ["Viaje de trabajo", "Vacaciones familiares", "Fin de semana largo", "Mudanza", "Cirugía de un familiar", "Boda"]
ALIMENTOS = [("Pro Plan", "seco"), ("Hill's Science Diet", "seco"), ("Royal Canin", "seco"), ("Dog Chow", "seco"), ("Pedigree", "seco")]
MEDICINAS = [("Carprofeno", "1 tableta", "pastilla", "cada 12 h"), ("Apoquel", "1 tableta", "pastilla", "cada 12 h"),
             ("Gotas oftálmicas", "2 gotas", "gotas", "cada 8 h"), ("Prednisona", "½ tableta", "pastilla", "cada 12 h")]
OBS_PARTE = ["Dejó la mitad", "Comió con poco apetito", "Esperó a que se fuera el cuidador", "Comió solo los trozos grandes"]
OBS_NADA = ["Estaba nervioso", "Sin apetito esta toma", "No quiso salir de la cama"]
OBS_MED = ["Escupió la pastilla", "No aceptó la medicina", "Se escondió"]


def _pesos(rnd, lista, pesos):
    return rnd.choices(lista, weights=pesos, k=1)[0]


def _dt(fecha, hora):
    return timezone.make_aware(datetime.combine(fecha, hora))


class Command(BaseCommand):
    help = "Crea clientes, mascotas, reservas (pasadas, en hotel y futuras), pagos y registros de cuidado ficticios."

    def add_arguments(self, p):
        p.add_argument("--clientes", type=int, default=60)
        p.add_argument("--meses", type=int, default=6, help="Meses de historia hacia atrás")
        p.add_argument("--semilla", type=int, default=2026)
        p.add_argument("--reemplazar", action="store_true", help="Borra antes los datos de demostración anteriores")

    def handle(self, *args, **o):
        hoy = timezone.localdate()
        if Cliente.objects.exclude(telefono__startswith=PREFIJO).exists():
            raise CommandError("Hay clientes que no son de demostración; no se genera nada para no mezclar datos reales.")
        if Cliente.objects.filter(telefono__startswith=PREFIJO).exists():
            if not o["reemplazar"]:
                raise CommandError("Ya hay datos de demostración. Use --reemplazar para regenerarlos.")
            self._borrar()
        if not Habitacion.objects.exists():
            raise CommandError("No hay habitaciones; ejecute migrate primero.")
        rnd = random.Random(o["semilla"])
        with transaction.atomic():
            clientes = self._clientes(rnd, o["clientes"], hoy)
            perros = self._perros(rnd, clientes, hoy)
            n = self._reservas(rnd, perros, hoy, o["meses"])
            self._solicitudes(rnd, hoy)
        self.stdout.write(f"Clientes: {len(clientes)}. Mascotas: {len(perros)}. Reservas: {n}. "
                          f"Pagos: {Pago.objects.count()}. Tareas de cuidado: {Tarea.objects.count()}.")

    def _borrar(self):
        cl = Cliente.objects.filter(telefono__startswith=PREFIJO)
        Pago.objects.filter(reserva__cliente__in=cl).delete()
        Reserva.objects.filter(cliente__in=cl).delete()
        Perro.objects.filter(cliente__in=cl).delete()
        cl.delete()
        SolicitudContacto.objects.filter(telefono__startswith=PREFIJO).delete()

    def _clientes(self, rnd, n, hoy):
        res = []
        for i in range(n):
            nombre = f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}"
            tel = f"{PREFIJO}-{i + 1:04d}"
            c = Cliente.objects.create(
                nombre=nombre, telefono=tel, whatsapp=tel, correo=f"cliente{i + 1}@ejemplo.test",
                canal_preferido=_pesos(rnd, ["whatsapp", "correo", "ambos"], [6, 1, 3]),
                como_nos_conocio=rnd.choice(ORIGENES), emergencia_nombre=f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)}",
                emergencia_parentesco=rnd.choice(["Pareja", "Hermano", "Madre", "Amigo"]), emergencia_telefono=f"{PREFIJO}-9{i:03d}",
                vet_autoriza=rnd.random() < 0.7, vet_monto_max=Decimal(rnd.choice([100, 150, 200, 300])),
                acepta_terminos_en=hoy - timedelta(days=rnd.randint(10, 200)), acepta_datos_en=hoy - timedelta(days=rnd.randint(10, 200)),
                acepta_fotos_en=hoy - timedelta(days=30) if rnd.random() < 0.6 else None,
                estado=_pesos(rnd, ["activo", "inactivo"], [9, 1]), descuento_pct=Decimal(rnd.choice([0, 0, 0, 0, 5, 10])))
            Cliente.objects.filter(pk=c.pk).update(creado=_dt(hoy - timedelta(days=rnd.randint(1, 210)), time(10, 0)))
            res.append(c)
        return res

    def _perros(self, rnd, clientes, hoy):
        perros, usados = [], 0
        for c in clientes:
            for _ in range(_pesos(rnd, [1, 2], [8, 2])):
                raza, pmin, pmax = rnd.choice(RAZAS)
                peso = Decimal(str(round(rnd.uniform(pmin, pmax), 1)))
                sexo = rnd.choice(["macho", "hembra"])
                p = Perro.objects.create(
                    cliente=c, nombre=PERROS[usados % len(PERROS)], sexo=sexo, raza=raza, peso_kg=peso,
                    nacimiento=hoy - timedelta(days=rnd.randint(300, 4500)), esterilizado=rnd.random() < 0.65,
                    alergias=rnd.choice(["", "", "", "Pollo", "Res", "Granos"]),
                    alimentacion_tipo="seco", alimento_marca=rnd.choice(ALIMENTOS)[0], alimento_cantidad=f"{rnd.choice([80, 120, 200, 300])} g",
                    alimento_tomas=2, temperamento=rnd.choice(["amigable", "amigable", "energetico", "timido", "ansioso"]),
                    convivencia=_pesos(rnd, ["si", "depende", "no"], [6, 3, 1]), come_separado=rnd.random() < 0.15,
                    bano_cada_dias=rnd.choice([None, 15, 30]))
                usados += 1
                self._ficha_sanitaria(rnd, p, hoy)
                perros.append(p)
        return perros

    def _ficha_sanitaria(self, rnd, p, hoy):
        for tipo in ("rabia", "multiple", "bordetella", "desparasitacion", "pulgas"):
            ap = hoy - timedelta(days=rnd.randint(20, 400))
            dias = 90 if tipo in ("desparasitacion", "pulgas") else 365
            if tipo == "bordetella" and rnd.random() < 0.15:
                continue  # algunos clientes llegan con requisitos sanitarios pendientes
            Vacuna.objects.create(perro=p, tipo=tipo, aplicada=ap, vence=ap + timedelta(days=dias))
        alimento = rnd.choice(ALIMENTOS)[0]
        PlanAlimentacion.objects.create(perro=p, alimento=alimento, cantidad_toma=p.alimento_cantidad, tomas_dia=2,
                                        horarios="7:00 y 17:00", desde=hoy - timedelta(days=240), restricciones=p.alergias)
        if rnd.random() < 0.18:
            m, dosis, via, horario = rnd.choice(MEDICINAS)
            Medicacion.objects.create(perro=p, medicamento=m, dosis=dosis, via=via, horario=horario, con_comida="con",
                                      desde=hoy - timedelta(days=30), origen=rnd.choice(["cliente", "hotel"]))
        if rnd.random() < 0.1:
            NecesidadEspecial.objects.create(perro=p, tipo="movilidad", detalle="No sube escalones")

    # -- reservas -----------------------------------------------------------------------------------------------------------------
    def _habitaciones_para(self, perro):
        tamanos = Habitacion.tamanos_para(perro.tamano)
        return [h for h in Habitacion.objects.filter(activa=True, tamano__in=tamanos)]

    def _libre(self, ocupadas, h, entrada, salida):
        return all(salida <= e or entrada >= s for e, s in ocupadas.get(h.pk, []))

    def _noches(self, rnd, fecha):
        # puentes y diciembre/julio: estadías más largas y más reservas
        return _pesos(rnd, [1, 2, 3, 4, 5, 7, 10, 14], [8, 20, 24, 14, 10, 12, 5, 2]) + (1 if fecha.month in (12, 7) else 0)

    def _reservas(self, rnd, perros, hoy, meses):
        ocupadas, total = {}, 0
        inicio = hoy - timedelta(days=30 * meses)
        dia = inicio
        while dia <= hoy + timedelta(days=45):
            base = 2.2 + (1.8 if dia.weekday() in (3, 4) else 0) + (1.5 if dia.month in (12, 7) else 0)
            for _ in range(int(base) + (1 if rnd.random() < base % 1 else 0)):
                total += self._una_reserva(rnd, perros, ocupadas, dia, hoy)
            dia += timedelta(days=1)
        return total

    def _una_reserva(self, rnd, perros, ocupadas, entrada, hoy):
        perro = rnd.choice(perros)
        salida = entrada + timedelta(days=self._noches(rnd, entrada))
        if salida > hoy + timedelta(days=60) or perro.cliente.estado != "activo" and rnd.random() < 0.7:
            return 0
        if Reserva.objects.filter(perro_ref=perro, entrada__lt=salida, salida__gt=entrada).exclude(estado="cancelada").exists():
            return 0
        libres = [h for h in self._habitaciones_para(perro) if self._libre(ocupadas, h, entrada, salida)]
        if not libres:
            return 0
        # los perros pequeños suelen ir a habitaciones pequeñas: se prefiere la de menor tamaño disponible
        libres.sort(key=lambda h: (Habitacion.ORDEN[h.tamano], rnd.random()))
        h = libres[0]
        cancelada = rnd.random() < 0.09
        if entrada + timedelta(days=0) <= hoy < salida and not cancelada:
            estado = Reserva.ACTIVA
        elif salida <= hoy:
            estado = Reserva.CANCELADA if cancelada else Reserva.CERRADA
        else:
            estado = Reserva.CANCELADA if cancelada else Reserva.CONFIRMADA
        c = perro.cliente
        anticipacion = rnd.randint(1, 40)
        r = Reserva.objects.create(
            habitacion=h, nombre=c.nombre, telefono=c.telefono, cliente=c, perro_ref=perro, perro=perro.nombre,
            entrada=entrada, salida=salida, estado=estado, tarifa_noche=h.tarifa_noche,
            hora_ingreso_estimada=time(rnd.choice([8, 9, 10, 14, 16]), rnd.choice([0, 30])))
        Reserva.objects.filter(pk=r.pk).update(creada=_dt(max(entrada - timedelta(days=anticipacion), hoy - timedelta(days=200)), time(11, 0)))
        r.refresh_from_db()
        if estado != Reserva.CANCELADA:
            ocupadas.setdefault(h.pk, []).append((entrada, salida))
        self._pagos(rnd, r, estado, hoy)
        if estado in (Reserva.ACTIVA, Reserva.CERRADA):
            self._cuidado(rnd, r, hoy)
        return 1

    def _pago(self, rnd, r, tipo, monto, cuando, ref=""):
        metodo = _pesos(rnd, ["efectivo", "sinpe", "tarjeta"], [3, 5, 2])
        p = Pago.objects.create(reserva=r, tipo=tipo, monto=Decimal(monto).quantize(Decimal("0.01")), metodo=metodo,
                                referencia=ref or (f"SINPE-{rnd.randint(100000, 999999)}" if metodo == "sinpe" else
                                                   f"AUT-{rnd.randint(1000, 9999)}" if metodo == "tarjeta" else ""))
        Pago.objects.filter(pk=p.pk).update(creado=_dt(cuando, time(rnd.randint(8, 17), rnd.randint(0, 59))))

    def _pagos(self, rnd, r, estado, hoy):
        total = r.total
        creada = timezone.localtime(r.creada).date()
        if estado == Reserva.CANCELADA:
            if rnd.random() < 0.5:
                anticipo = total * Decimal("0.3")
                self._pago(rnd, r, "pago", anticipo, creada)
                if rnd.random() < 0.6:  # devolución parcial o total
                    self._pago(rnd, r, "devolucion", anticipo, min(creada + timedelta(days=2), hoy), "Cancelación del cliente")
            r.motivo_cancelacion = rnd.choice(["Cambio de planes", "Viaje cancelado", "Mascota enferma"])
            r.cancelada_en = r.creada + timedelta(days=1)
            r.save(update_fields=["motivo_cancelacion", "cancelada_en"])
            return
        if estado == Reserva.CONFIRMADA:
            if rnd.random() < 0.7:
                self._pago(rnd, r, "pago", total * Decimal("0.3"), min(creada, hoy))
            return
        # en hotel o cerrada: anticipo y saldo (alguna con saldo pendiente)
        self._pago(rnd, r, "pago", total * Decimal("0.3"), min(creada, hoy))
        if estado == Reserva.CERRADA and rnd.random() < 0.93:
            self._pago(rnd, r, "pago", total * Decimal("0.7"), r.salida)
        elif estado == Reserva.ACTIVA and rnd.random() < 0.4:
            self._pago(rnd, r, "pago", total * Decimal("0.7"), r.entrada)

    # -- cuidado diario -----------------------------------------------------------------------------------------------------------
    def _cuidado(self, rnd, r, hoy):
        Reserva.objects.filter(pk=r.pk).update(checkin_en=_dt(r.entrada, r.hora_ingreso_estimada or time(10, 0)),
                                               pertenencias=rnd.choice(["Cama y correa", "Cama, juguete y correa", "Correa"]),
                                               estado_fisico_ingreso="Sin hallazgos",
                                               checkout_en=_dt(r.salida, time(12, 0)) if r.estado == Reserva.CERRADA else None)
        r.refresh_from_db()
        crear_plan_base(r)
        ahora = timezone.localtime()
        ultimo = min(r.salida - timedelta(days=1), hoy)
        dia = r.entrada
        while dia <= ultimo:
            if hoy - dia <= timedelta(days=75):  # solo se detalla el cuidado reciente
                for item in r.plan.all():
                    if item.hasta and item.hasta < dia:
                        continue
                    self._tarea(rnd, item, dia, ahora)
            dia += timedelta(days=1)

    def _tarea(self, rnd, item, dia, ahora):
        hora = item.hora or time(12, 0)
        momento = _dt(dia, hora)
        if momento > ahora:
            Tarea.objects.create(item=item, fecha=dia)
            return
        if rnd.random() < 0.04:
            Tarea.objects.create(item=item, fecha=dia)  # se quedó sin registrar
            return
        t = Tarea(item=item, fecha=dia, hecha=True, hecha_en=momento + timedelta(minutes=rnd.randint(0, 25)))
        if item.tipo == "alimentacion":
            consumo = _pesos(rnd, ["todo", "parte", "nada"], [80, 15, 5])
            t.consumo, t.consumo_en = consumo, t.hecha_en + timedelta(minutes=rnd.randint(30, 70))
            t.observaciones = rnd.choice(OBS_PARTE) if consumo == "parte" else rnd.choice(OBS_NADA) if consumo == "nada" else ""
            if rnd.random() < 0.05:
                t.porcion_motivo = "Porción reducida por poco apetito"
        elif item.tipo == "medicacion":
            res = _pesos(rnd, ["administrada", "rechazada", "no_administrada"], [93, 5, 2])
            t.resultado = res
            t.observaciones = "" if res == "administrada" else rnd.choice(OBS_MED)
        t.save()

    def _solicitudes(self, rnd, hoy):
        for i in range(8):
            s = SolicitudContacto.objects.create(nombre=f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)}", telefono=f"{PREFIJO}-7{i:03d}",
                                                 motivo=rnd.choice(["Quiere reservar y no encontró fechas", "Consulta por perro grande",
                                                                    "Pregunta por precios del baño", "Consulta por medicación"]))
            SolicitudContacto.objects.filter(pk=s.pk).update(creada=_dt(hoy - timedelta(days=rnd.randint(0, 40)), time(15, 0)))
