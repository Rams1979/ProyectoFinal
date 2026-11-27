from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum


class Habitacion(models.Model):
    TAMANOS = [("pequena", "Pequeña (1 m²)"), ("mediana", "Mediana (2 m²)"), ("grande", "Grande (4 m²)")]
    numero = models.PositiveSmallIntegerField(unique=True)
    tarifa_noche = models.DecimalField(max_digits=8, decimal_places=2, default=30)
    en_limpieza = models.BooleanField(default=False)
    tamano = models.CharField(max_length=10, choices=TAMANOS, default="mediana")
    capacidad_perros = models.PositiveSmallIntegerField(default=1)  # 1 por defecto; las grandes admiten 2
    activa = models.BooleanField(default=True)  # una habitación inactiva no se ofrece ni aparece en el panel
    nota = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["numero"]
        verbose_name_plural = "habitaciones"

    # Clasificación del perro (documento del caso de uso) y la habitación mínima que necesita.
    TAMANOS_PERRO = [("pequeno", "Pequeño (hasta 10 kg)"), ("mediano", "Mediano (10 a 25 kg)"),
                     ("grande", "Grande (25 a 45 kg)"), ("gigante", "Gigante (más de 45 kg)")]
    ORDEN = {"pequena": 0, "mediana": 1, "grande": 2}
    MINIMA = {"pequeno": "pequena", "mediano": "mediana", "grande": "grande", "gigante": "grande"}

    @classmethod
    def tamanos_para(cls, tamano_perro):
        """Tamaños de habitación que admiten al perro: el suyo o uno mayor."""
        minimo = cls.ORDEN[cls.MINIMA[tamano_perro]]
        return [t for t, o in cls.ORDEN.items() if o >= minimo]

    PESOS = {"pequena": "Hasta 10 kg", "mediana": "Hasta 25 kg", "grande": "Desde 25 kg (admite gigantes)"}

    @property
    def peso_recomendado(self):
        """Peso aproximado del perro para el que está pensada, según la clasificación del documento del caso de uso."""
        return self.PESOS[self.tamano]

    def __str__(self):
        return f"Habitación {self.numero:02d}"


class BloqueoHabitacion(models.Model):
    """Habitación fuera de servicio (mantenimiento) entre dos fechas, ambas incluidas."""

    habitacion = models.ForeignKey(Habitacion, on_delete=models.CASCADE, related_name="bloqueos")
    desde = models.DateField()
    hasta = models.DateField()
    motivo = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["desde"]


class Cliente(models.Model):
    """Maestro de clientes según el CU-02 del documento del caso de uso."""

    TIPOS_ID = [("fisica", "Cédula física"), ("juridica", "Cédula jurídica"), ("dimex", "DIMEX"), ("pasaporte", "Pasaporte")]
    ESTADOS = [("activo", "Activo"), ("inactivo", "Inactivo"), ("bloqueado", "Bloqueado")]
    CANALES = [("whatsapp", "WhatsApp"), ("correo", "Correo electrónico"), ("ambos", "Ambos")]

    nombre = models.CharField(max_length=120)
    tipo_identificacion = models.CharField(max_length=10, choices=TIPOS_ID, blank=True)
    identificacion = models.CharField(max_length=30, blank=True)
    correo = models.EmailField(blank=True)
    telefono = models.CharField(max_length=30, unique=True)
    whatsapp = models.CharField("WhatsApp", max_length=30, blank=True)
    canal_preferido = models.CharField(max_length=10, choices=CANALES, default="ambos")
    direccion = models.CharField(max_length=250, blank=True)
    emergencia_nombre = models.CharField(max_length=120, blank=True)
    emergencia_parentesco = models.CharField(max_length=60, blank=True)
    emergencia_telefono = models.CharField(max_length=30, blank=True)
    retira_nombre = models.CharField("Persona autorizada para retirar", max_length=120, blank=True)
    retira_cedula = models.CharField(max_length=30, blank=True)
    retira_telefono = models.CharField(max_length=30, blank=True)
    vet_autoriza = models.BooleanField("Autoriza atención veterinaria de emergencia", default=False)
    vet_monto_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    acepta_terminos_en = models.DateField(null=True, blank=True)
    acepta_fotos_en = models.DateField(null=True, blank=True)
    acepta_datos_en = models.DateField(null=True, blank=True)  # tratamiento de datos, Ley 8968
    fact_razon_social = models.CharField(max_length=150, blank=True)
    fact_cedula_juridica = models.CharField(max_length=30, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="activo")
    notas_internas = models.TextField(blank=True)
    como_nos_conocio = models.CharField(max_length=100, blank=True)
    bano_estadias_largas = models.BooleanField("Autoriza baño en estadías de más de 7 días", default=False)
    descuento_pct = models.DecimalField("Descuento (%)", max_digits=5, decimal_places=2, default=0)  # solo lo aprueba el administrador
    creado = models.DateTimeField(auto_now_add=True)  # fecha de registro

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Perro(models.Model):
    """Ficha del perro según el CU-03 del documento del caso de uso (la foto y el carnet adjunto quedan pendientes)."""

    SEXOS = [("macho", "Macho"), ("hembra", "Hembra")]
    ALIMENTACION = [("seco", "Seco"), ("humedo", "Húmedo"), ("casero", "Casero"), ("especial", "Dieta especial")]
    TEMPERAMENTOS = [("amigable", "Amigable"), ("timido", "Tímido"), ("energetico", "Energético"), ("ansioso", "Ansioso")]
    CONVIVENCIA = [("si", "Convive bien"), ("no", "No convive con otros perros"), ("depende", "Depende del perro")]
    LIMITES_TAMANO = [(10, "pequeno"), (25, "mediano"), (45, "grande")]  # hasta ese peso inclusive; más es gigante

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="perros")
    # identificación
    nombre = models.CharField(max_length=80)
    sexo = models.CharField(max_length=6, choices=SEXOS, blank=True)
    raza = models.CharField("Raza o cruce", max_length=80, blank=True)
    nacimiento = models.DateField(null=True, blank=True)
    peso_kg = models.DecimalField("Peso (kg)", max_digits=5, decimal_places=1, null=True, blank=True)
    color_senas = models.CharField("Color y señas particulares", max_length=200, blank=True)
    microchip = models.CharField(max_length=30, blank=True)
    esterilizado = models.BooleanField(default=False)
    # salud
    ultimo_celo = models.DateField(null=True, blank=True)  # solo hembras no esterilizadas
    operaciones = models.TextField("Operaciones y cirugías (fecha y detalle)", blank=True)
    condiciones = models.TextField("Lesiones o condiciones crónicas", blank=True)
    alergias = models.TextField("Alergias (alimentarias y a medicamentos)", blank=True)
    vet_nombre = models.CharField("Veterinario de cabecera", max_length=120, blank=True)
    vet_clinica = models.CharField(max_length=120, blank=True)
    vet_telefono = models.CharField(max_length=30, blank=True)
    # alimentación habitual
    alimentacion_tipo = models.CharField(max_length=10, choices=ALIMENTACION, blank=True)
    alimento_marca = models.CharField(max_length=100, blank=True)
    alimento_cantidad = models.CharField("Cantidad por toma", max_length=40, blank=True)
    alimento_tomas = models.PositiveSmallIntegerField("Número de tomas por día", null=True, blank=True)
    alimento_horarios = models.CharField(max_length=100, blank=True)
    restricciones_premios = models.CharField("Restricciones y premios permitidos", max_length=250, blank=True)
    come_separado = models.BooleanField("Debe comer separado de otros perros", default=False)
    # comportamiento
    temperamento = models.CharField(max_length=12, choices=TEMPERAMENTOS, blank=True)
    mordidas = models.CharField("Historial de mordidas o agresión (con perros o personas)", max_length=250, blank=True)
    convivencia = models.CharField("Convivencia con otros perros", max_length=8, choices=CONVIVENCIA, blank=True)
    ansiedad_miedos = models.CharField("Ansiedad por separación y miedos (truenos, pólvora)", max_length=250, blank=True)
    socializacion_fecha = models.DateField("Prueba de socialización: fecha", null=True, blank=True)
    socializacion_obs = models.CharField("Prueba de socialización: observaciones", max_length=250, blank=True)
    hospedajes_anteriores = models.CharField("Hospedajes anteriores (dónde y cómo le fue)", max_length=250, blank=True)
    # cuidado
    bano_cada_dias = models.PositiveSmallIntegerField("Frecuencia de baño (cada cuántos días)", null=True, blank=True)
    notas = models.CharField(max_length=300, blank=True)  # cuidados varios

    @property
    def tamano(self):
        """Clasificación por peso: pequeno (hasta 10 kg), mediano (hasta 25), grande (hasta 45) o gigante. None si no hay peso."""
        if self.peso_kg is None:
            return None
        for limite, nombre in self.LIMITES_TAMANO:
            if self.peso_kg <= limite:
                return nombre
        return "gigante"

    @property
    def tamano_texto(self):
        return dict(Habitacion.TAMANOS_PERRO).get(self.tamano, "") if self.tamano else ""

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "perros"

    def __str__(self):
        return self.nombre

    def requisitos(self, fecha):
        """Estado de cada requisito sanitario a la fecha dada: vigente, vencida o falta."""
        ultimas = {}
        for v in self.vacunas.all():
            if v.tipo not in ultimas or v.vence > ultimas[v.tipo].vence:
                ultimas[v.tipo] = v
        filas = []
        for tipo, etiqueta in Vacuna.TIPOS:
            v = ultimas.get(tipo)
            if v is None:
                filas.append({"etiqueta": etiqueta, "estado": "falta", "vence": None})
            else:
                filas.append({"etiqueta": etiqueta, "estado": "vigente" if v.vence >= fecha else "vencida", "vence": v.vence})
        return filas

    def pendientes(self, fecha):
        return [f for f in self.requisitos(fecha) if f["estado"] != "vigente"]


class Vacuna(models.Model):
    TIPOS = [
        ("rabia", "Rabia"),
        ("multiple", "Vacuna múltiple"),
        ("bordetella", "Bordetella"),
        ("desparasitacion", "Desparasitación interna"),
        ("pulgas", "Pulgas y garrapatas"),
    ]
    perro = models.ForeignKey(Perro, on_delete=models.CASCADE, related_name="vacunas")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    aplicada = models.DateField()
    vence = models.DateField()


class Reserva(models.Model):
    """Reserva confirmada automáticamente (el prototipo la da por pagada)."""

    CONFIRMADA, ACTIVA, CERRADA, CANCELADA = "confirmada", "activa", "cerrada", "cancelada"
    ESTADOS = [(CONFIRMADA, "Confirmada"), (ACTIVA, "En hotel"), (CERRADA, "Cerrada"), (CANCELADA, "Cancelada")]

    habitacion = models.ForeignKey(Habitacion, on_delete=models.PROTECT, related_name="reservas")
    nombre = models.CharField(max_length=120)
    telefono = models.CharField(max_length=30)
    entrada = models.DateField()
    salida = models.DateField()
    creada = models.DateTimeField(auto_now_add=True)
    tarifa_noche = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # la de la habitación al reservar
    estado = models.CharField(max_length=12, choices=ESTADOS, default=CONFIRMADA)
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.PROTECT, related_name="reservas")
    perro_ref = models.ForeignKey(Perro, null=True, blank=True, on_delete=models.PROTECT, related_name="reservas")
    perro = models.CharField(max_length=80, blank=True)  # nombre; si no vino en la reserva se pide en el check-in
    perro2 = models.CharField(max_length=80, blank=True)  # segundo perro en la misma habitación (+50 %)
    perro2_ref = models.ForeignKey(Perro, null=True, blank=True, on_delete=models.PROTECT, related_name="reservas_como_segundo")
    # Reserva grupal: más de dos perros del mismo cliente se reservan en varias habitaciones (máximo 2 por habitación);
    # cada habitación es una reserva y las adicionales apuntan a la primera.
    principal = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="adicionales")
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")  # vacío si reservó el cliente solo
    checkin_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    checkout_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")  # vacío si canceló el cliente
    motivo_cancelacion = models.CharField(max_length=200, blank=True)
    checkin_en = models.DateTimeField(null=True, blank=True)
    hora_ingreso_estimada = models.TimeField(null=True, blank=True)
    pertenencias = models.CharField("Pertenencias entregadas (cama, juguetes, correa)", max_length=250, blank=True)
    estado_fisico_ingreso = models.CharField("Estado físico al ingreso", max_length=250, blank=True)
    checkout_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["entrada", "habitacion__numero"]

    def __str__(self):
        return f"{self.habitacion} {self.entrada} a {self.salida}"

    def save(self, *args, **kwargs):
        if self.tarifa_noche is None:  # se congela la tarifa vigente: un cambio posterior no altera esta reserva
            self.tarifa_noche = self.habitacion.tarifa_noche
        super().save(*args, **kwargs)

    @property
    def noches(self):
        return (self.salida - self.entrada).days

    @property
    def total(self):
        """Habitación × noches; el segundo perro suma el recargo sobre la tarifa de la habitación."""
        base = (self.tarifa_noche if self.tarifa_noche is not None else self.habitacion.tarifa_noche) * self.noches
        if self.perro2:
            base += base * Decimal(settings.RECARGO_SEGUNDO_PERRO) / 100
        return base

    @property
    def perros_texto(self):
        if self.perro and self.perro2:
            return f"perros {self.perro} y {self.perro2}"
        if self.perro or self.perro2:
            return f"perro {self.perro or self.perro2}"
        return ""

    @property
    def grupo(self):
        """Todas las reservas del mismo grupo (incluida esta), en orden de habitación; vacío si no es grupal."""
        raiz = self.principal or self
        ids = [raiz.pk] + list(raiz.adicionales.values_list("pk", flat=True))
        if len(ids) == 1:
            return Reserva.objects.none()
        return Reserva.objects.filter(pk__in=ids).select_related("habitacion").order_by("habitacion__numero")

    @property
    def mascotas_texto(self):
        if self.perro and self.perro2:
            return f"mascotas {self.perro} y {self.perro2}"
        if self.perro or self.perro2:
            return f"mascota {self.perro or self.perro2}"
        return ""

    @property
    def pagado(self):
        """Pagos menos devoluciones."""
        pagos = self.pagos.aggregate(
            p=Sum("monto", filter=models.Q(tipo=Pago.PAGO)), d=Sum("monto", filter=models.Q(tipo=Pago.DEVOLUCION)))
        return (pagos["p"] or Decimal("0")) - (pagos["d"] or Decimal("0"))

    @property
    def saldo(self):
        return Decimal("0") if self.estado == self.CANCELADA else self.total - self.pagado

    @property
    def anticipo_requerido(self):
        return (self.total * settings.ANTICIPO_PORCENTAJE / 100).quantize(Decimal("0.01"))

    @property
    def estado_pago(self):
        pagado = self.pagado
        if self.estado == self.CANCELADA:
            return "Devolución por definir" if pagado > 0 else "Sin pagos"
        if pagado <= 0:
            return "Pendiente"
        if pagado < self.total:
            return "Parcial"
        return "Pagada" if pagado == self.total else "Saldo a favor del cliente"


class SolicitudContacto(models.Model):
    """Datos que deja un cliente en el chat para que la persona de turno lo contacte."""

    nombre = models.CharField(max_length=120)
    telefono = models.CharField(max_length=30)
    motivo = models.CharField(max_length=300, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]
        verbose_name_plural = "solicitudes de contacto"


class Pago(models.Model):
    """Pago o devolución registrado por el personal (no hay cobro en línea)."""

    PAGO, DEVOLUCION = "pago", "devolucion"
    TIPOS = [(PAGO, "Pago"), (DEVOLUCION, "Devolución")]
    METODOS = [("efectivo", "Efectivo"), ("sinpe", "SINPE"), ("tarjeta", "Tarjeta")]

    reserva = models.ForeignKey(Reserva, on_delete=models.PROTECT, related_name="pagos")
    tipo = models.CharField(max_length=10, choices=TIPOS, default=PAGO)
    monto = models.DecimalField(max_digits=8, decimal_places=2)
    metodo = models.CharField(max_length=10, choices=METODOS)
    referencia = models.CharField(max_length=60, blank=True)  # n.º de SINPE, aprobación de tarjeta, motivo
    creado = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-creado"]


class ItemPlan(models.Model):
    """Tarea que se repite cada día mientras el perro está en el hotel."""

    TIPOS = [("alimentacion", "Alimentación"), ("medicacion", "Medicación"), ("paseo", "Paseo"),
             ("limpieza", "Limpieza"), ("otro", "Otro")]
    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name="plan")
    tipo = models.CharField(max_length=14, choices=TIPOS)
    detalle = models.CharField(max_length=200, blank=True)
    hora = models.TimeField(null=True, blank=True)
    hasta = models.DateField(null=True, blank=True)  # última fecha en que rige (medicación con fin); vacío = toda la estancia

    class Meta:
        ordering = ["hora", "pk"]


class Tarea(models.Model):
    """Tarea de un día. Alimentación: servida y consumo (CU-06). Medicación: resultado de la administración (CU-07)."""

    CONSUMOS = [("todo", "Todo"), ("parte", "Parte"), ("nada", "Nada")]
    RESULTADOS = [("administrada", "Administrada"), ("rechazada", "Rechazada"), ("no_administrada", "No administrada")]
    item = models.ForeignKey(ItemPlan, on_delete=models.CASCADE, related_name="tareas")
    fecha = models.DateField()
    hecha = models.BooleanField(default=False)
    hecha_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hecha_en = models.DateTimeField(null=True, blank=True)  # en alimentación: cuándo se sirvió; en medicación: cuándo se registró
    porcion_motivo = models.CharField(max_length=250, blank=True)  # solo si la porción servida difiere del plan
    consumo = models.CharField(max_length=5, choices=CONSUMOS, blank=True)
    consumo_en = models.DateTimeField(null=True, blank=True)
    consumo_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resultado = models.CharField(max_length=16, choices=RESULTADOS, blank=True)
    observaciones = models.CharField(max_length=250, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "fecha"], name="una_tarea_por_dia")]


AREAS = [
    ("panel", "Panel, check-in y check-out"),
    ("reservas", "Reservaciones: editar y cancelar"),
    ("caja", "Pagos y caja"),
    ("clientes", "Clientes y perros"),
    ("cuidado", "Cuidado diario"),
    ("habitaciones", "Habitaciones, tarifas y artículos"),
    ("reportes", "Reportes y exportación"),
    ("solicitudes", "Solicitudes de contacto"),
    ("usuarios", "Usuarios y perfiles"),
]


class Perfil(models.Model):
    """Conjunto de pantallas a las que puede entrar un usuario del personal."""

    nombre = models.CharField(max_length=60, unique=True)
    areas = models.JSONField(default=list, blank=True)
    es_sistema = models.BooleanField(default=False)  # Administrador: siempre tiene todo y no se edita

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "perfiles"

    def __str__(self):
        return self.nombre

    def tiene(self, area):
        return self.es_sistema or area in self.areas

    @property
    def areas_texto(self):
        if self.es_sistema:
            return "Todas"
        nombres = dict(AREAS)
        return ", ".join(nombres[a] for a, _ in AREAS if a in self.areas) or "Ninguna"


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_hotel")
    perfil = models.ForeignKey(Perfil, on_delete=models.PROTECT, related_name="usuarios")


class Articulo(models.Model):
    """Maestro de artículos: lista de precios de servicios y productos (sin inventario)."""

    TIPOS = [("alimento", "Alimento"), ("medicina", "Medicina"), ("habitacion", "Habitación"), ("servicio", "Servicio")]  # categoría
    CON_INVENTARIO = {"alimento", "medicina"}
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=120)
    tipo = models.CharField("Categoría", max_length=12, choices=TIPOS, default="servicio")
    control_inventario = models.BooleanField(default=False)  # sí para alimento y medicina; no para habitación
    tamano_perro = models.CharField("Tamaño de perro (para precios por tamaño, ej. baño)", max_length=8, blank=True,
                                    choices=Habitacion.TAMANOS_PERRO)
    descripcion = models.CharField(max_length=200, blank=True)
    unidad = models.CharField(max_length=30, blank=True)  # por noche, por hora, por baño...
    precio = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # vacío = por definir
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]


class Medicacion(models.Model):
    """Medicación de un perro (CU-07)."""

    VIAS = [("pastilla", "Pastilla"), ("gotas", "Gotas"), ("inyeccion", "Inyección"), ("topico", "Tópico")]
    COMIDA = [("con", "Con comida"), ("sin", "Sin comida"), ("indiferente", "Indiferente")]
    ORIGENES = [("cliente", "Cliente"), ("hotel", "Hotel")]

    perro = models.ForeignKey(Perro, on_delete=models.CASCADE, related_name="medicaciones")
    medicamento = models.CharField(max_length=120)
    dosis = models.CharField(max_length=80, blank=True)
    via = models.CharField(max_length=10, choices=VIAS, blank=True)
    horario = models.CharField("Horario (cada cuántas horas)", max_length=80, blank=True)
    desde = models.DateField(null=True, blank=True)
    hasta = models.DateField(null=True, blank=True)
    con_comida = models.CharField(max_length=12, choices=COMIDA, default="indiferente")
    origen = models.CharField(max_length=8, choices=ORIGENES, default="cliente")  # si es del hotel, se cobra como producto
    cantidad_recibida = models.CharField(max_length=60, blank=True)  # para verificar que alcance para la estancia
    indicacion = models.CharField("Indicación médica (receta o instrucción)", max_length=250, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["-activa", "medicamento"]
        verbose_name_plural = "medicaciones"

    def __str__(self):
        return f"{self.medicamento} ({self.perro})"


class NecesidadEspecial(models.Model):
    """Necesidad especial de un perro (CU-07): médica, dieta, movilidad, comportamiento, manejo o ambiente."""

    TIPOS = [("medica", "Médica"), ("dieta", "Dieta"), ("movilidad", "Movilidad"), ("comportamiento", "Comportamiento"),
             ("manejo", "Manejo"), ("ambiente", "Ambiente")]

    perro = models.ForeignKey(Perro, on_delete=models.CASCADE, related_name="necesidades")
    tipo = models.CharField(max_length=14, choices=TIPOS)
    detalle = models.CharField(max_length=250)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["-activa", "tipo"]
        verbose_name_plural = "necesidades especiales"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.detalle}"


class PlanAlimentacion(models.Model):
    """Plan de alimentación de un perro (CU-05). Un cambio crea un plan nuevo y conserva el histórico."""

    ORIGENES = [("cliente", "Cliente"), ("hotel", "Hotel")]

    perro = models.ForeignKey(Perro, on_delete=models.CASCADE, related_name="planes")
    alimento = models.CharField(max_length=120)
    origen = models.CharField(max_length=8, choices=ORIGENES, default="cliente")  # define si se cobra
    cantidad_toma = models.CharField("Cantidad por toma (gramos o tazas)", max_length=40, blank=True)
    tomas_dia = models.PositiveSmallIntegerField("Tomas por día", default=2)
    horarios = models.CharField(max_length=100, blank=True)  # ejemplo: 7:00 y 17:00
    desde = models.DateField()
    hasta = models.DateField(null=True, blank=True)
    complementos = models.CharField("Complementos y premios", max_length=200, blank=True)
    restricciones = models.CharField("Restricciones y alergias", max_length=200, blank=True)
    instrucciones = models.CharField(max_length=250, blank=True)  # ejemplo: humedecer el alimento, comer separado
    cantidad_recibida = models.CharField("Cantidad de alimento recibida (si es del cliente)", max_length=60, blank=True)

    class Meta:
        ordering = ["-desde", "-id"]
        verbose_name_plural = "planes de alimentación"

    def __str__(self):
        return f"{self.alimento} ({self.perro})"
