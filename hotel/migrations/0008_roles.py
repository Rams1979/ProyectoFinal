from django.db import migrations


def crear_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nombre in ("Recepción", "Administrador"):
        Group.objects.get_or_create(name=nombre)


class Migration(migrations.Migration):
    dependencies = [
        ("hotel", "0007_reserva_checkin_por_reserva_checkout_por_and_more"),
        ("auth", "0001_initial"),
    ]
    operations = [migrations.RunPython(crear_roles, migrations.RunPython.noop)]
