"""Chatbot sencillo: responde con la información aprobada, consulta disponibilidad
y toma datos de contacto. No crea ni confirma reservas."""
import os
from datetime import date
from pathlib import Path

from django.utils import timezone

from .disponibilidad import habitaciones_libres
from .models import Articulo, Habitacion, SolicitudContacto

MODELO = os.environ.get("CHAT_MODEL", "claude-sonnet-5-5")
CONOCIMIENTO = (Path(__file__).parent / "conocimiento.md").read_text(encoding="utf-8")
MAX_MENSAJE = 500
MAX_HISTORIAL = 10
SIN_CLAVE = ("El chat no está disponible por ahora. Puede ver las habitaciones libres y reservar "
             "en la página de disponibilidad.")

INSTRUCCIONES = f"""Eres el asistente del hotel canino Inu no Hoteru. Respondes en español, breve y amable.

REGLAS
- Usa SOLO la información de abajo y los resultados de las herramientas. Nunca inventes datos,
  precios, horarios ni políticas.
- Si algo dice POR DEFINIR o no está en la información, dilo con claridad ("eso lo confirma la persona de
  turno") y ofrece tomar nombre y teléfono con la herramienta registrar_contacto.
- No puedes crear, confirmar ni garantizar reservas. Para reservar, el cliente usa la página de
  disponibilidad (/disponibilidad/). Distingue siempre una consulta de disponibilidad de una reserva confirmada.
- Para disponibilidad usa consultar_disponibilidad con fechas AAAA-MM-DD. Hoy es {{hoy}}.
- Para pasar a una persona, pide nombre y teléfono y usa registrar_contacto.
- No des consejos veterinarios; ante una emergencia o enfermedad, deriva a la persona de turno.

INFORMACIÓN DEL HOTEL
{CONOCIMIENTO}

PRECIOS VIGENTES (del sistema, tienen prioridad sobre cualquier otro dato)
{{precios}}"""

HERRAMIENTAS = [
    {
        "name": "consultar_disponibilidad",
        "description": "Cuenta las habitaciones libres entre dos fechas y calcula el total de hospedaje por habitación.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entrada": {"type": "string", "description": "Fecha de entrada AAAA-MM-DD"},
                "salida": {"type": "string", "description": "Fecha de salida AAAA-MM-DD, posterior a la entrada"},
                "tamano_perro": {"type": "string", "enum": ["pequeno", "mediano", "grande", "gigante"],
                                 "description": "Tamaño del perro: pequeño hasta 10 kg, mediano 10 a 25, grande 25 a 45, gigante más de 45. Solo se ofrecen habitaciones de su tamaño o mayor."},
            },
            "required": ["entrada", "salida"],
        },
    },
    {
        "name": "registrar_contacto",
        "description": "Guarda nombre y teléfono del cliente para que la persona de turno lo contacte.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "telefono": {"type": "string"},
                "motivo": {"type": "string", "description": "Qué necesita el cliente, en pocas palabras"},
            },
            "required": ["nombre", "telefono"],
        },
    },
]


def consultar_disponibilidad(entrada: str, salida: str, tamano_perro: str = None) -> dict:
    try:
        e, s = date.fromisoformat(entrada), date.fromisoformat(salida)
    except (TypeError, ValueError):
        return {"error": "Fechas inválidas; use AAAA-MM-DD."}
    if e < timezone.localdate():
        return {"error": "La entrada no puede ser una fecha pasada."}
    if s <= e:
        return {"error": "La salida debe ser posterior a la entrada."}
    noches = (s - e).days
    if tamano_perro and tamano_perro not in dict(Habitacion.TAMANOS_PERRO):
        return {"error": "Tamaño de perro inválido; use pequeno, mediano, grande o gigante."}
    disponibles = habitaciones_libres(e, s, tamano_perro=tamano_perro)
    libres = disponibles.count()
    tarifa = disponibles.order_by("tarifa_noche").values_list("tarifa_noche", flat=True).first() or 0  # la más baja entre las libres
    por_tamano = {}
    for h in disponibles:
        por_tamano[h.get_tamano_display()] = por_tamano.get(h.get_tamano_display(), 0) + 1
    return {
        "habitaciones_libres": libres,
        "libres_por_tamano": por_tamano,
        "noches": noches,
        "tarifa_noche_usd": float(tarifa),
        "total_por_habitacion_usd": float(tarifa * noches),
        "nota": "La tarifa indicada es la más baja entre las habitaciones libres. Es una consulta, no una reserva. Se reserva en /disponibilidad/.",
    }


def registrar_contacto(nombre: str, telefono: str, motivo: str = "") -> dict:
    nombre, telefono = (nombre or "").strip(), (telefono or "").strip()
    if not nombre or not telefono:
        return {"error": "Faltan el nombre o el teléfono."}
    SolicitudContacto.objects.create(nombre=nombre[:120], telefono=telefono[:30], motivo=(motivo or "")[:300])
    return {"ok": True, "mensaje": "Datos guardados; la persona de turno lo contactará."}


def _ejecutar(nombre, datos):
    if nombre == "consultar_disponibilidad":
        return consultar_disponibilidad(datos.get("entrada"), datos.get("salida"), datos.get("tamano_perro"))
    if nombre == "registrar_contacto":
        return registrar_contacto(datos.get("nombre"), datos.get("telefono"), datos.get("motivo", ""))
    return {"error": "Herramienta desconocida."}


def texto_precios() -> str:
    """Tarifa por noche y lista de precios actuales, leídas de la base de datos."""
    tarifas = sorted(set(Habitacion.objects.filter(activa=True).values_list("tarifa_noche", flat=True)))
    if not tarifas:
        noche = "- Hospedaje por noche: POR DEFINIR."
    elif len(tarifas) == 1:
        noche = f"- Hospedaje por noche: ${tarifas[0]:.2f} por habitación."
    else:
        noche = f"- Hospedaje por noche: desde ${tarifas[0]:.2f} hasta ${tarifas[-1]:.2f}, según la habitación."
    lineas = [noche, "- Un segundo perro en la misma habitación suma 50 % de la tarifa de la habitación."]
    for a in Articulo.objects.filter(activo=True):
        precio = f"${a.precio:.2f}{' ' + a.unidad if a.unidad else ''}" if a.precio is not None else "POR DEFINIR"
        lineas.append(f"- {a.nombre}: {precio}")
    return "\n".join(lineas)


def _cliente():
    clave = os.environ.get("ANTHROPIC_API_KEY")
    if not clave:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=clave)


def responder(historial: list[dict]) -> str:
    """historial: [{role: 'user'|'assistant', content: str}], el último del usuario."""
    import json

    mensajes = [
        {"role": m["role"], "content": str(m["content"])[:MAX_MENSAJE]}
        for m in historial[-MAX_HISTORIAL:]
        if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()
    ]
    while mensajes and mensajes[0]["role"] != "user":
        mensajes.pop(0)
    if not mensajes or mensajes[-1]["role"] != "user":
        return "Escriba su pregunta, por favor."

    cliente = _cliente()
    if cliente is None:
        return SIN_CLAVE
    sistema = INSTRUCCIONES.replace("{hoy}", timezone.localdate().isoformat()).replace("{precios}", texto_precios())
    try:
        for _ in range(5):
            r = cliente.messages.create(model=MODELO, max_tokens=700, system=sistema,
                                        tools=HERRAMIENTAS, messages=mensajes)
            if r.stop_reason != "tool_use":
                texto = "".join(b.text for b in r.content if b.type == "text").strip()
                return texto or "No pude responder; ¿puede reformular la pregunta?"
            mensajes.append({"role": "assistant", "content": [b.model_dump() for b in r.content]})
            resultados = [
                {"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(_ejecutar(b.name, b.input))}
                for b in r.content if b.type == "tool_use"
            ]
            mensajes.append({"role": "user", "content": resultados})
    except Exception:
        return "Tuve un problema para responder. Intente de nuevo o deje su teléfono en la página de contacto."
    return "No pude completar la consulta; ¿puede reformular la pregunta?"
