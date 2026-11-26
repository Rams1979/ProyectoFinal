from django.db import migrations

CANTIDAD = 30
TARIFA = 30


def crear_habitaciones(apps, schema_editor):
    Habitacion = apps.get_model("hotel", "Habitacion")
    for numero in range(1, CANTIDAD + 1):
        Habitacion.objects.get_or_create(numero=numero, defaults={"tarifa_noche": TARIFA})


def borrar_habitaciones(apps, schema_editor):
    apps.get_model("hotel", "Habitacion").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("hotel", "0001_initial")]
    operations = [migrations.RunPython(crear_habitaciones, borrar_habitaciones)]
