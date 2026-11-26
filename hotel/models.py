from django.db import models


class Habitacion(models.Model):
    numero = models.PositiveSmallIntegerField(unique=True)
    tarifa_noche = models.DecimalField(max_digits=8, decimal_places=2, default=30)

    class Meta:
        ordering = ["numero"]
        verbose_name_plural = "habitaciones"

    def __str__(self):
        return f"Habitación {self.numero:02d}"
