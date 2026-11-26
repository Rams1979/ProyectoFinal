from django.urls import path

from hotel import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("disponibilidad/", views.disponibilidad, name="disponibilidad"),
    path("reservar/<int:habitacion_id>/", views.reservar, name="reservar"),
    path("reserva/<int:reserva_id>/", views.reserva_confirmada, name="reserva_confirmada"),
    path("reservaciones/", views.reservaciones, name="reservaciones"),
]
