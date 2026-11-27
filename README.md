# Inu no Hoteru 犬のホテル — prototipo conceptual

Prototipo con datos de ejemplo (no es un sistema para operar el hotel). Django + PostgreSQL en Railway.

## Etapa 5: check-in, check-out y panel de ocupación
- `/panel/`: las 30 habitaciones con su estado de hoy (ocupada, sale hoy, por llegar, en limpieza, libre) y los totales.
- Check-in desde el panel (pide el nombre del perro); check-out cierra la estancia y deja la habitación en limpieza hasta marcarla disponible.
- El check-out anticipado libera las fechas restantes. No se hace check-in antes de la fecha de entrada ni si la habitación está en limpieza.

## Etapa 6: registro de clientes y perros
- `/clientes/`: búsqueda por nombre, teléfono o perro; alta manual y ficha con sus perros.
- Reservar crea o reutiliza al cliente (por teléfono) y al perro (por nombre) si se escribe; si no, el check-in lo pide y lo registra.
- Requisitos sanitarios por perro (rabia, múltiple, Bordetella, desparasitación, pulgas y garrapatas) con fecha de vencimiento.
- El check-in avisa si falta o venció algún requisito a la fecha de salida y exige marcar la autorización de recepción para continuar.
- `limpiar_demo` también borra clientes, perros y vacunas.

## Etapa 3: chatbot sencillo
- `/chat/`: responde con la información de `hotel/conocimiento.md`, consulta disponibilidad y toma nombre y teléfono para la persona de turno (`/solicitudes/`). No crea reservas.
- Lo que dice POR DEFINIR en `conocimiento.md` el chat no lo inventa: lo deriva a la persona de turno. Al completar ese archivo el chat responde con los datos nuevos.
- Variable en Railway: `ANTHROPIC_API_KEY` (opcional `CHAT_MODEL`). Sin la clave, el chat avisa que no está disponible y el resto del sitio funciona.

## Etapa 2: reserva y reservaciones
- Botón Reservar en cada habitación libre; el cliente escribe nombre y teléfono y confirma.
- La reserva queda confirmada y se da por pagada. La habitación se bloquea para evitar reservas traslapadas.
- `/reservaciones/`: lista de todas las reservaciones (sin inicio de sesión).

## Etapa 1: disponibilidad por fechas
- `/disponibilidad/`: entrada y salida, lista las habitaciones libres con el total de las noches.
- Una habitación con reserva traslapada no aparece; el día de salida queda libre.
- Modelo `Reserva` (la pantalla de reserva llega en la etapa 2).

## Etapa 0: fundamentos
- Esqueleto Django con conexión a PostgreSQL (`DATABASE_URL`).
- 30 habitaciones pequeñas a $30 por noche, cargadas por migración.
- Página de inicio que las lista.

## Railway
1. Conectar este repositorio y agregar un servicio PostgreSQL al proyecto.
2. Variables del servicio web: `DATABASE_URL` (referencia al PostgreSQL) y `SECRET_KEY`.
3. El arranque (`Procfile`) aplica las migraciones y levanta gunicorn.

## Local
```
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
