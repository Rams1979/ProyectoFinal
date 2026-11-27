from django.db import migrations

AREAS = ["panel", "reservas", "caja", "clientes", "cuidado", "habitaciones", "solicitudes", "usuarios"]
SERVICIOS = [
    ("Hospedaje por períodos prolongados", "por noche"),
    ("Guardería por horas (daycare)", "por hora"),
    ("Alimentación durante la estadía", "por día"),
    ("Paseos y actividades recreativas", "por paseo"),
    ("Juegos y socialización con otros perros", "por sesión"),
    ("Baño y peluquería canina (grooming)", "por servicio"),
    ("Administración de medicamentos", "por día"),
    ("Atención veterinaria o emergencias", "por atención"),
    ("Transporte de mascotas", "por viaje"),
    ("Cámaras para observar a los perros", "por estadía"),
]


def sembrar(apps, schema_editor):
    Perfil = apps.get_model("hotel", "Perfil")
    PerfilUsuario = apps.get_model("hotel", "PerfilUsuario")
    User = apps.get_model("auth", "User")
    Reserva = apps.get_model("hotel", "Reserva")
    Articulo = apps.get_model("hotel", "Articulo")

    admin, _ = Perfil.objects.get_or_create(nombre="Administrador", defaults={"areas": AREAS, "es_sistema": True})
    recepcion, _ = Perfil.objects.get_or_create(
        nombre="Recepción", defaults={"areas": ["panel", "reservas", "caja", "clientes", "cuidado"]})
    Perfil.objects.get_or_create(nombre="Cuidador", defaults={"areas": ["cuidado"]})

    # Usuarios existentes: el grupo que tenían pasa a ser su perfil.
    for u in User.objects.all():
        nombres = set(u.groups.values_list("name", flat=True))
        if u.is_superuser or "Administrador" in nombres:
            PerfilUsuario.objects.get_or_create(usuario=u, defaults={"perfil": admin})
        elif "Recepción" in nombres:
            PerfilUsuario.objects.get_or_create(usuario=u, defaults={"perfil": recepcion})

    # Reservas existentes conservan la tarifa que tenían.
    for r in Reserva.objects.filter(tarifa_noche__isnull=True).select_related("habitacion"):
        r.tarifa_noche = r.habitacion.tarifa_noche
        r.save(update_fields=["tarifa_noche"])

    # Lista de precios: los servicios que dio el hotel; los precios quedan por definir.
    for n, (nombre, unidad) in enumerate(SERVICIOS, start=1):
        Articulo.objects.get_or_create(codigo=f"SRV-{n:03d}", defaults={"nombre": nombre, "unidad": unidad, "tipo": "servicio"})


class Migration(migrations.Migration):
    dependencies = [
        ("hotel", "0011_articulo_perfil_habitacion_activa_habitacion_nota_and_more"),
        ("auth", "0001_initial"),
    ]
    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
