from django.db import migrations


def datos(apps, schema_editor):
    Habitacion = apps.get_model("hotel", "Habitacion")
    Articulo = apps.get_model("hotel", "Articulo")
    Habitacion.objects.filter(tamano="grande").update(capacidad_perros=2)  # las grandes admiten 2 perros
    Articulo.objects.filter(tipo="producto").update(tipo="alimento")  # antes solo había servicio o producto
    Articulo.objects.filter(tipo__in=["alimento", "medicina"]).update(control_inventario=True)


class Migration(migrations.Migration):
    dependencies = [("hotel", "0017_fichas_completas")]
    operations = [migrations.RunPython(datos, migrations.RunPython.noop)]
