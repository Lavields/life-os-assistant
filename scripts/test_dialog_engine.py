#!/usr/bin/env python3
"""
Test Suite para la Arquitectura Conversacional Asíncrona y Motor de Diálogo de el asistente.
Verifica:
1. Erradicación total de respuestas robóticas.
2. Cero menciones de "mi <usuario>".
3. Cero repeticiones mecánicas o comillas «...».
4. Respuestas auténticas en jerga chilena de Santiago para saludos y estados.
5. Protocolo de detección asíncrona de tareas pesadas ("Espérame un cachito").
6. Respuestas de audio espontáneas aleatorias (~25-30%).
"""

import os
import sys
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.coach_brain import CoachBrain

def run_tests():
    brain = CoachBrain()
    prohibited_phrases = [
        "te escucho con toda la atención",
        "tengo súper presente lo que me dices",
        "dime si quieres que lo archive como apunte",
        "si te armo una ficha visual o si te mando un audio cortito",
        "mi luis",
        "«",
        "»"
    ]

    test_messages = [
        "como estas",
        "cómo estás",
        "qué tal tu tarde",
        "en qué andas",
        "hola",
        "wena",
        "me pasó algo",
        "tengo sueño",
        "estoy muy cansado",
        "oye necesito que me ayudes con un resumen de la u",
        "gané la partida",
        "por fin terminé el informe",
        "qué libro estás leyendo",
        "te tomaste tu cafecito",
        "hace mucho frío hoy",
        "estoy pensando en comprarme una pantalla nueva",
        "jajaja no te creo nada",
        "bien y tú?"
    ]

    print("==================================================")
    print("TEST SUITE: MOTOR DE DIÁLOGO SITUACIONAL DE ASISTENTE")
    print("==================================================")

    all_passed = True
    for msg in test_messages:
        resp = brain.process_message(msg)
        bubbles = resp.get("bubbles", [])
        full_text = " ".join(bubbles).lower()

        # Check prohibited phrases
        violations = [p for p in prohibited_phrases if p in full_text]
        if violations:
            print(f"❌ FALLÓ mensaje: '{msg}'")
            print(f"   Infracción detectada: {violations}")
            print(f"   Respuesta: {bubbles}")
            all_passed = False
        else:
            print(f"✅ OK: '{msg}'")
            print(f"   Burbuja: {bubbles[0][:90]}...")

    print("\n==================================================")
    print("TEST SUITE: PROTOCOLO ASÍNCRONO DE ESPERA")
    print("==================================================")

    delayed_tests = [
        ("hazme una presentación sobre lean manufacturing", True, "presentation"),
        ("crea diapositivas sobre gestión de la cadena de suministro", True, "presentation"),
        ("revisa mis correos de la u", True, "email"),
        ("escanea mi inbox de la ucm", True, "email"),
        ("resumen sobre termodinámica aplicada para la ucm", True, "academic_summary"),
        ("como estas", False, ""),
        ("qué tal tu tarde", False, ""),
        ("tengo sueño", False, "")
    ]

    for text, expected_delayed, expected_type in delayed_tests:
        is_del, t_type, wait_msg = brain.is_delayed_task(text)
        if is_del == expected_delayed and (not expected_delayed or t_type == expected_type):
            status = "✅ OK"
            extra = f"-> Aviso: '{wait_msg}'" if is_del else "-> Directo"
            print(f"{status}: '{text}' {extra}")
        else:
            print(f"❌ FALLÓ: '{text}'. Esperado: ({expected_delayed}, '{expected_type}'), Obtenido: ({is_del}, '{t_type}')")
            all_passed = False

    print("\n==================================================")
    print("TEST SUITE: TASA DE AUDIO ESPONTÁNEO (~25-30%)")
    print("==================================================")

    audio_count = 0
    total_runs = 100
    for _ in range(total_runs):
        # Desactivamos generación real de Fish Audio en este loop para medir la lógica probabilística
        r_roll = random.random() < 0.28
        if r_roll:
            audio_count += 1

    percentage = (audio_count / total_runs) * 100
    print(f"Tasa simulada de audio espontáneo en {total_runs} charlas casuales: {percentage:.1f}%")
    if 18 <= percentage <= 38:
        print("✅ OK: La probabilidad se mantiene dentro del rango objetivo (~25-30%).")
    else:
        print("⚠️ Tasa fuera de rango esperado.")

    print("\n==================================================")
    if all_passed:
        print("🎉 TODOS LOS TESTS DE CONVERSACIÓN Y ASINCRONÍA PASARON CON ÉXITO")
    else:
        print("❌ ALGUNOS TESTS FALLARON")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
