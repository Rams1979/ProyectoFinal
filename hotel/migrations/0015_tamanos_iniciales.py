from django.db import migrations


def asignar(apps, schema_editor):
    Habitacion = apps.get_model("hotel", "Habitacion")
    Habitacion.objects.filter(numero__lte=10).update(tamano="pequena")
    Habitacion.objects.filter(numero__gte=11, numero__lte=20).update(tamano="mediana")
    Habitacion.objects.filter(numero__gte=21).update(tamano="grande")


class Migration(migrations.Migration):
    dependencies = [("hotel", "0014_tamanos_con_metros")]
    operations = [migrations.RunPython(asignar, migrations.RunPython.noop)]
