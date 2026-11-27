"""Límite de intentos fallidos de inicio de sesión (por usuario)."""
from django.core.cache import cache

MAX_INTENTOS = 5
VENTANA = 15 * 60  # segundos


def _clave(usuario):
    return f"login-fallos:{usuario.strip().lower()}"


def bloqueado(usuario):
    return cache.get(_clave(usuario), 0) >= MAX_INTENTOS


def registrar_fallo(usuario):
    clave = _clave(usuario)
    cache.add(clave, 0, VENTANA)
    try:
        cache.incr(clave)
    except ValueError:
        cache.set(clave, 1, VENTANA)


def limpiar(usuario):
    cache.delete(_clave(usuario))
