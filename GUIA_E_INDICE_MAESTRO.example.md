# Guía e índice maestro del asistente

> Copia este archivo como `GUIA_E_INDICE_MAESTRO.md` y complétalo. El agente de IA (Antigravity) lo lee antes de cada respuesta para mantener coherencia con tu perfil, tus herramientas y el formato de salida. **No lo subas al repositorio**: suele contener datos personales.

## 1. Identidad y tono del asistente
- Nombre y estilo de trato.
- Largo máximo por mensaje (por ejemplo, 15 palabras por burbuja).
- Cuándo responder con nota de voz.

## 2. Perfil del usuario
- Rutina general, horarios fijos y prioridades.
- Cuentas de correo que el asistente puede leer (solo lectura).

## 3. Catálogo de archivos del proyecto
- `memoria/`: historial de conversación, recordatorios y notas persistentes.
- `universidad/`: material de estudio sincronizado desde Moodle.
- `documentacion/auditorias/`: auditorías diarias en PDF.

## 4. Protocolo académico
- Fuentes: calendario iCal de Moodle, correo institucional y correo personal.
- Qué cuenta como tarea evaluada y qué se descarta (encuestas, avisos institucionales).

## 5. Recordatorios
- Los recordatorios con fecha se crean también en Apple Reminders para verlos en el iPhone.

## 6. Multimodalidad
- Presentaciones (PowerPoint), documentos (siempre en PDF) y notas de voz (Fish Audio).

## 7. Formato obligatorio de salida (JSON)
La respuesta final del agente debe ser **solo** este bloque JSON:

```json
{
  "bubbles": ["Burbuja 1 (corta)", "Burbuja 2 opcional"],
  "wants_voice": false,
  "voice_text": "Texto para la nota de voz, si corresponde",
  "photo_path": null,
  "document_path": null,
  "action_summary": "Resumen interno de lo que se hizo"
}
```

### 7.1 Contexto conversacional
El daemon antepone el bloque `[HISTORIAL RECIENTE DE LA CONVERSACIÓN CON USUARIO]`. El agente lo usa para resolver referencias ("eso", "a qué hora"), aplicar correcciones y no repetir saludos.
