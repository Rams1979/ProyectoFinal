from django.db import models


class Habitacion(models.Model):
    numero = models.PositiveSmallIntegerField(unique=True)
    tarifa_noche = models.DecimalField(max_digits=8, decimal_places=2, default=30)

    class Meta:
        ordering = ["numero"]
        verbose_name_plural = "habitaciones"

    def __str__(self):
        return f"Habitación {self.numero:02d}"


class Reserva(models.Model):
    """Reserva confirmada automáticamente (el prototipo la da por pagada)."""

    habitacion = models.ForeignKey(Habitacion, on_delete=models.PROTECT, related_name="reservas")
    nombre = models.CharField(max_length=120)
    telefono = models.CharField(max_length=30)
    entrada = models.DateField()
    salida = models.DateField()
    creada = models.DateTimeField(auto_now_add=True)

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
