from django.urls import path

from hotel import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("disponibilidad/", views.disponibilidad, name="disponibilidad"),
    path("reservar/<int:habitacion_id>/", views.reservar, name="reservar"),
    path("reserva/<int:reserva_id>/", views.reserva_confirmada, name="reserva_confirmada"),
    path("chat/", views.chat, name="chat"),
    path("chat/mensaje/", views.chat_mensaje, name="chat_mensaje"),
    path("solicitudes/", views.solicitudes, name="solicitudes"),
    path("panel/", views.panel, name="panel"),
    path("checkin/<int:reserva_id>/", views.checkin, name="checkin"),
    path("checkout/<int:reserva_id>/", views.checkout, name="checkout"),
    path("limpieza/<int:habitacion_id>/", views.limpieza_lista, name="limpieza_lista"),
    path("ingresar/", views.login_vista, name="login"),
    path("salir/", views.logout_vista, name="logout"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/<int:usuario_id>/activo/", views.usuario_activo, name="usuario_activo"),
    path("habitaciones/", views.habitaciones, name="habitaciones"),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente_nuevo, name="cliente_nuevo"),
    path("clientes/<int:cliente_id>/", views.cliente, name="cliente"),
    path("reserva/<int:reserva_id>/cancelar/", views.cancelar, name="cancelar"),
    path("reserva/<int:reserva_id>/editar/", views.editar_reserva, name="editar_reserva"),
    path("reservaciones/", views.reservaciones, name="reservaciones"),
]
