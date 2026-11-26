# Inu no Hoteru 犬のホテル — prototipo conceptual

Prototipo con datos de ejemplo (no es un sistema para operar el hotel). Django + PostgreSQL en Railway.

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
