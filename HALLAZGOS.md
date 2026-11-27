# Hallazgos del prototipo (para la siguiente fase)

Resultado de las pruebas del recorrido completo. Lo que el prototipo hace a propósito sin resolver, y lo que se vio al probar.

## Pendientes para revisar (anotados el 26/11/2026)
- Política de devolución al cancelar y anticipo: por definir; hoy la cancelación solo libera la habitación.
- Reservas falsas desde el sitio público: sin límite de uso ni confirmación; hoy el personal las cancela una por una.
- Cancelación por el visitante: depende de su sesión; si cierra el navegador debe llamar al hotel.
- Reactivar una reserva cancelada por error: no existe; se crea una nueva.
- Recuperación de contraseña por olvido: no existe; el administrador la restablece desde Usuarios.
- Bloqueo de login por usuario y en memoria de cada proceso (ver observaciones técnicas).
- Chat sin límite de uso: consume saldo de la API; clave de Anthropic sin configurar todavía.
- Repositorio público con teléfono y correo del hotel: decidir si pasa a privado.
- Requisitos sanitarios finales con el veterinario y datos "POR DEFINIR" de `hotel/conocimiento.md`.

- Segundo perro: el documento dice que solo las habitaciones grandes admiten dos perros; en el prototipo todas son iguales y se admite en cualquiera. Falta definir si el recargo del 50 % aplica igual en habitaciones pequeñas.
- Cuidado diario: el plan base (desayuno, paseo, limpieza, cena) es una propuesta mía, sin validar. Las tareas no cumplidas de días anteriores no se arrastran, no hay alertas de tarea vencida y el alimento propio del perro no tiene campo aparte (va en "cuidados").
- Pagos: el anticipo solo se muestra, no bloquea el check-in ni la reserva. Un check-out anticipado reduce el total y puede dejar saldo a favor del cliente; la devolución se registra a mano. Los montos se muestran con coma decimal (formato de Costa Rica) y todo está en dólares: falta el tipo de cambio si se cobra en colones.

- Perfiles: los permisos son por pantalla, no por acción; quien ve Reservaciones también edita y cancela, y quien ve Habitaciones cambia tarifas. No hay "solo lectura".
- Tarifas: sin historial ni vigencias por fecha o temporada; el cambio rige para reservas nuevas desde que se guarda. El descuento por períodos prolongados no existe.
- Artículos: es solo la lista de precios; no se asocia a reservas ni a la caja. Todos los precios de servicios quedaron por definir.

- Reportes: la capacidad es el número de habitaciones activas hoy; no descuenta los días de mantenimiento ni cambios históricos de habitaciones. Todo está en dólares y sin impuestos. Un ingreso se cuenta por la fecha en que se registró el pago, y el valor de una reserva por su fecha de entrada, así que ambas cifras no cuadran mes a mes.

- Maestro de clientes: ya tiene los campos del CU-02 del documento (identificación, WhatsApp, dirección, contacto de emergencia, persona autorizada para retirar, autorización veterinaria con monto máximo, consentimientos con fechas, facturación, estado, cómo nos conoció, baño en estadías largas, descuento y canal preferido). Solo nombre y teléfono son obligatorios, aunque el documento marca otros como "Base" (identificación, correo, dirección, contacto de emergencia), para no frenar las reservas rápidas. El descuento solo lo edita el administrador, pero todavía no se aplica a ningún total (no hay facturación); un cliente "bloqueado" solo muestra un aviso, no impide reservar; los avisos por WhatsApp o correo y su historial no existen.

- Tamaño del perro: la búsqueda de disponibilidad y el chat filtran por el tamaño del perro (pequeño, mediano, grande, gigante) y ofrecen su habitación o una mayor; la reserva lo valida. El perro registrado todavía no guarda peso ni tamaño (el cliente lo elige al buscar) y no hay límite de dos perros por tamaño de habitación.

## Decisiones del prototipo (no son errores)
- Sin registro de clientes ni de perros; la reserva pide nombre y teléfono y el nombre del perro se anota en el check-in.
- Sin validación de vacunas ni fotos de recepción.
- Tamaños de habitación: pequeña 1 m², mediana 2 m², grande 4 m²; son informativos, no cambian la tarifa. Habitaciones 1 a 10 pequeñas, 11 a 20 medianas y 21 a 30 grandes; todas en $30 por noche; la tarifa es un valor de ejemplo en la base.
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
- Etapa 7: el administrador restablece contraseñas desde Usuarios; sin recuperación de contraseña por correo. El bloqueo por intentos usa la memoria de cada proceso, así que con varios procesos el límite real es mayor; va por usuario, por lo que alguien podría bloquear a un usuario conocido 15 minutos. El chat y la reserva siguen públicos y sin límite de uso: pueden llenar la agenda de reservas falsas y consumir saldo de la API.
- Etapa 8: la política de devolución sigue POR DEFINIR; la cancelación solo libera la habitación y avisa que el hotel se comunicará. El visitante pierde la opción de cancelar si cierra el navegador (la reserva queda ligada a su sesión); entonces debe llamar al hotel. Cualquier visitante puede seguir creando reservas falsas, ahora el personal las cancela una por una.
