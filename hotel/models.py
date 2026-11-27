from django.conf import settings
from django.db import models


class Habitacion(models.Model):
    numero = models.PositiveSmallIntegerField(unique=True)
    tarifa_noche = models.DecimalField(max_digits=8, decimal_places=2, default=30)
    en_limpieza = models.BooleanField(default=False)

    class Meta:
        ordering = ["numero"]
        verbose_name_plural = "habitaciones"

    def __str__(self):
        return f"Habitación {self.numero:02d}"


class Cliente(models.Model):
    nombre = models.CharField(max_length=120)
    telefono = models.CharField(max_length=30, unique=True)
    correo = models.EmailField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Perro(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="perros")
    nombre = models.CharField(max_length=80)
    raza = models.CharField(max_length=80, blank=True)
    nacimiento = models.DateField(null=True, blank=True)
    notas = models.CharField(max_length=300, blank=True)  # alimentación, medicación, cuidados

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
    estado = models.CharField(max_length=12, choices=ESTADOS, default=CONFIRMADA)
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.PROTECT, related_name="reservas")
    perro_ref = models.ForeignKey(Perro, null=True, blank=True, on_delete=models.PROTECT, related_name="reservas")
    perro = models.CharField(max_length=80, blank=True)  # nombre; si no vino en la reserva se pide en el check-in
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")  # vacío si reservó el cliente solo
    checkin_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    checkout_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")  # vacío si canceló el cliente
    motivo_cancelacion = models.CharField(max_length=200, blank=True)
    checkin_en = models.DateTimeField(null=True, blank=True)
    checkout_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["entrada", "habitacion__numero"]

    def __str__(self):
        return f"{self.habitacion} {self.entrada} a {self.salida}"


class SolicitudContacto(models.Model):
    """Datos que deja un cliente en el chat para que la persona de turno lo contacte."""

    nombre = models.CharField(max_length=120)
    telefono = models.CharField(max_length=30)
    motivo = models.CharField(max_length=300, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]
        verbose_name_plural = "solicitudes de contacto"
