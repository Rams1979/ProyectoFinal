# Inu no Hoteru 犬のホテル — prototipo conceptual

Prototipo con datos de ejemplo (no es un sistema para operar el hotel). Django + PostgreSQL en Railway.

## Etapa 5: check-in, check-out y panel de ocupación
- `/panel/`: las 30 habitaciones con su estado de hoy (ocupada, sale hoy, por llegar, en limpieza, libre) y los totales.
- Check-in desde el panel (pide el nombre del perro); check-out cierra la estancia y deja la habitación en limpieza hasta marcarla disponible.
- El check-out anticipado libera las fechas restantes. No se hace check-in antes de la fecha de entrada ni si la habitación está en limpieza.

## Etapa 7: inicio de sesión y roles
- Público (sin sesión): inicio, disponibilidad, reserva y su confirmación (solo la que el visitante hizo en su sesión) y chat.
- **Recepción:** panel, check-in/out, reservaciones, clientes y habitaciones.
- **Administrador:** lo anterior más solicitudes de contacto y usuarios.
- Cada reserva guarda quién la creó y quién hizo el check-in y el check-out (se ve en Reservaciones).
- Contraseñas de 10 o más caracteres, sesión de 12 horas y bloqueo de 15 minutos tras 5 intentos fallidos por usuario.
- Primer administrador: variables `ADMIN_USERNAME` y `ADMIN_PASSWORD` en Railway; el arranque lo crea una sola vez (`crear_admin`). Luego se pueden quitar las variables.

## Etapa 8: cancelar y editar reservas
- Cancelar (estado "Cancelada"): libera la habitación, guarda motivo, fecha y quién canceló. Solo reservas confirmadas; con el perro en el hotel se hace check-out.
- El personal cancela desde Reservaciones; el visitante cancela solo la que hizo en su sesión, desde su confirmación.
- Editar (solo personal): reserva confirmada permite fechas, habitación, nombre, teléfono y perro; con el perro en el hotel solo se mueve la salida. Revisa disponibilidad sin contarse a sí misma y bloquea la habitación.
- Reservas cerradas o canceladas no se editan. No hay reactivación: se crea una reserva nueva.

## Etapa 9: segundo perro
- Una reserva admite un segundo perro en la misma habitación; suma 50 % de la tarifa de la habitación (`RECARGO_SEGUNDO_PERRO` en `settings.py`). Se pide al reservar o lo agrega el personal al editar.
- El check-in revisa los requisitos sanitarios de los dos perros.

## Etapa 10: cuidado diario
- Al hacer el check-in se crea un plan diario base (desayuno, paseo, limpieza, cena). El personal agrega o quita tareas, incluida la medicación con dosis, desde `/cuidado/reserva/<id>/`.
- `/cuidado/` muestra las tareas de hoy por habitación, ordenadas por hora, con los cuidados del perro destacados; cada tarea se marca como hecha o se deshace y guarda quién y cuándo.

## Etapa 11: pagos y anticipo
- Ya no se da por pagada la reserva. El personal registra pagos (efectivo, SINPE o tarjeta, con referencia) y devoluciones en `/reserva/<id>/pagos/`; hay estado Pendiente, Parcial, Pagada o Saldo a favor.
- `/caja/` resume por día y método lo cobrado, devuelto y neto.
- Anticipo opcional: variable `ANTICIPO_PORCENTAJE` (0 por defecto = sin anticipo); solo se muestra, no bloquea.
- No hay cobro en línea: el sistema solo registra lo que el personal recibe.

## Mantenimiento de usuarios
- `/usuarios/` (administrador): lista con usuario, nombre, perfil, estado y último ingreso; alta con usuario, nombre completo, contraseña y perfil (Recepción o Administrador).
- Editar (`/usuarios/<id>/`): nombre, perfil, nueva contraseña (opcional) y activo. No se puede cambiar el propio perfil ni desactivarse, y siempre debe quedar un administrador activo. Los usuarios no se borran, se desactivan, para conservar el historial.
- `/clave/`: cada usuario cambia su propia contraseña sin cerrar su sesión.

## Etapa 12: perfiles propios
- `/perfiles/` (pantalla Usuarios y perfiles): el administrador crea perfiles marcando las pantallas que cada uno puede usar. Vienen tres: Administrador (de sistema, siempre todo, no se edita), Recepción y Cuidador (solo cuidado diario).
- Las áreas son: panel y check-in/out, reservaciones (editar y cancelar), pagos y caja, clientes, cuidado, habitaciones/tarifas/artículos, solicitudes y usuarios/perfiles. Disponibilidad y chat son para todos.
- Un perfil en uso no se borra; los cambios de pantallas aplican de inmediato. Los usuarios que ya existían pasaron a su perfil según el rol que tenían.

## Etapa 13: habitaciones y tarifas
- `/habitaciones/`: tarifa por noche por habitación, cambio de tarifa para todas, alta de habitaciones y activar/desactivar (no se desactiva con reservas vigentes).
- Mantenimiento por rango de fechas (ambas incluidas): la habitación no se ofrece, no admite check-in y se ve en el panel. No se bloquea si hay reservas en esas fechas.
- Cada reserva congela la tarifa con que se hizo: un cambio posterior no altera sus totales. Si se cambia de habitación, rige la tarifa vigente de la nueva.

## Etapa 14: maestro de artículos (lista de precios)
- `/articulos/`: código, nombre, tipo (servicio o producto), unidad, precio y activo. Vienen cargados los 10 servicios del hotel con el precio por definir. Sin inventario ni facturación.
- El chat lee la tarifa por noche y esta lista en cada respuesta: lo que no tiene precio lo deriva a la persona de turno.

## Etapa 15: reportes
- `/reportes/` (área "Reportes y exportación", solo Administrador por defecto): período a elegir (mes en curso por defecto, hasta 366 días).
- Ocupación por día con barras, % del período, noches ocupadas y día pico; ingresos netos por método de pago y valor por cobrar; reservas por estado, tasa de cancelación, origen (cliente en línea o personal), clientes nuevos y perros alojados; y los próximos 7 días con llegadas, salidas y requisitos sanitarios pendientes.
- Exportación a CSV (ocupación diaria, reservas y pagos) listo para Excel o Power BI; los textos que empiezan con `=`, `+`, `-` o `@` se neutralizan para que no se ejecuten como fórmulas.
- Para dar el acceso a otro perfil, marcar "Reportes y exportación" en Perfiles.

## Menú principal
- `/` es el menú con acceso a todas las pantallas y un dato vivo en cada una. La lista de habitaciones pasó a `/habitaciones/`.

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
- `/reservaciones/`: lista de todas las reservaciones.

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
