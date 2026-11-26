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
    path("reservaciones/", views.reservaciones, name="reservaciones"),
]
