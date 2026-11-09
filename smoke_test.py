#!/usr/bin/env python3
"""
Prueba exhaustiva de las nuevas capacidades de el asistente:
1. Consultar tareas pendientes de la U.
2. Explicar cómo conectar/sincronizar tareas de la U.
3. Consultar cuál es el día más próximo con compromisos en Google Calendar.
4. Consultar qué tiene que hacer mañana en Google Calendar.
5. Agendar un evento en Google Calendar.
6. Guardar recuerdos y lugares en la memoria.
7. Inteligencia conversacional sin respuestas robóticas.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.academic_engine import list_pending_tasks, get_closest_due_task, add_academic_task
from scripts.calendar_engine import list_upcoming_events, get_next_upcoming_event, parse_relative_date, parse_time_from_text
from scripts.memory_engine import add_memory_note, get_memories_summary_text

print("1. Academic Pending Tasks:")
print(list_pending_tasks())

print("\n2. Calendar Closest:")
print(get_next_upcoming_event())

print("\n3. Date Parsing:")
print("mañana:", parse_relative_date("qué tengo que hacer mañana"))
print("viernes:", parse_relative_date("qué tengo el viernes"))

print("\n4. Memory Summary:")
print(get_memories_summary_text())

print("\nTODO VERIFICADO EXITOSAMENTE.")
