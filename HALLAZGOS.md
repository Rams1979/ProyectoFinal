# Hallazgos del prototipo (para la siguiente fase)

Resultado de las pruebas del recorrido completo. Lo que el prototipo hace a propósito sin resolver, y lo que se vio al probar.

## Decisiones del prototipo (no son errores)
- Sin registro de clientes ni de perros; la reserva pide nombre y teléfono y el nombre del perro se anota en el check-in.
- Sin validación de vacunas ni fotos de recepción.
- Todas las habitaciones son iguales (pequeñas, $30 por noche); la tarifa es un valor de ejemplo en la base.
- La reserva se da por pagada: no hay anticipo, cobro ni facturación.
- El chat no crea reservas; necesita `ANTHROPIC_API_KEY` y, sin ella, avisa que no está disponible.

## Pendientes de contenido (el chat los deriva a la persona de turno)
Hora de dejar y recoger, domingos y feriados, llegada tarde, cambios de fecha, condiciones de admisión (cachorros, edad,
castración, celo, tamaño y peso, tratamientos), descuentos, anticipo y cancelación, dirección, Google Maps, web y redes.
Se completan en `hotel/conocimiento.md`.

## Observaciones técnicas
- El chat y las páginas son públicos: sin límite de uso por visitante, el chat puede consumir saldo de la API. Antes de producción: inicio de sesión, límite por IP y tope de gasto.
- El repositorio es público y contiene el teléfono y correo del hotel.
- Dos reservas simultáneas de la misma habitación se evitan bloqueando la fila (PostgreSQL); en SQLite local no aplica el bloqueo.
- No hay cancelación ni edición de reservas.
- `limpiar_demo` borra las reservas y solicitudes de prueba antes de la demostración (`python manage.py limpiar_demo`).

- Etapa 6: los requisitos sanitarios (5 tipos) son los del chat; la versión final del veterinario sigue POR DEFINIR. Sin adjuntar carné ni fotos. Clientes identificados solo por teléfono, sin edición ni borrado.
- Etapa 7: sin cambio de contraseña propio (el administrador crea un usuario nuevo o desactiva el anterior); sin recuperación de contraseña. El bloqueo por intentos usa la memoria de cada proceso, así que con varios procesos el límite real es mayor; va por usuario, por lo que alguien podría bloquear a un usuario conocido 15 minutos. El chat y la reserva siguen públicos y sin límite de uso: pueden llenar la agenda de reservas falsas y consumir saldo de la API.
- Etapa 8: la política de devolución sigue POR DEFINIR; la cancelación solo libera la habitación y avisa que el hotel se comunicará. El visitante pierde la opción de cancelar si cierra el navegador (la reserva queda ligada a su sesión); entonces debe llamar al hotel. Cualquier visitante puede seguir creando reservas falsas, ahora el personal las cancela una por una.
