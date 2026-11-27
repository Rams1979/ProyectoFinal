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
    path("habitaciones/", views.habitaciones, name="habitaciones"),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente_nuevo, name="cliente_nuevo"),
    path("clientes/<int:cliente_id>/", views.cliente, name="cliente"),
    path("reservaciones/", views.reservaciones, name="reservaciones"),
]
