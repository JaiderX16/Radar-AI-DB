#!/usr/bin/env python3
"""Script para probar la API del chatbot y verificar que incluya imágenes"""

import requests
import json
import time

def test_chatbot_api():
    """Probar el chatbot a través de la API"""
    
    url = "http://127.0.0.1:5000/api/chat"
    
    # Prueba 1: Preguntar por lugares para pasear
    print("=== PRUEBA 1: Lugares para pasear ===")
    data1 = {
        "message": "¿Dónde puedo ir a dar un paseo al aire libre?",
        "user_id": "test_user_1"
    }
    
    try:
        response1 = requests.post(url, json=data1)
        if response1.status_code == 200:
            result1 = response1.json()
            print("Respuesta del chatbot:")
            print(result1.get('response', 'Sin respuesta'))
            
            # Verificar si incluye imágenes
            if '!' in result1.get('response', '') and 'http' in result1.get('response', ''):
                print("\n✅ La respuesta incluye imágenes!")
            else:
                print("\n❌ La respuesta NO incluye imágenes")
        else:
            print(f"Error en la API: {response1.status_code}")
    except Exception as e:
        print(f"Error al conectar con la API: {e}")
    
    time.sleep(2)  # Esperar entre pruebas
    
    # Prueba 2: Preguntar específicamente por un lugar
    print("\n=== PRUEBA 2: Información sobre Parque Constitución ===")
    data2 = {
        "message": "Cuéntame sobre el Parque Constitución",
        "user_id": "test_user_2"
    }
    
    try:
        response2 = requests.post(url, json=data2)
        if response2.status_code == 200:
            result2 = response2.json()
            print("Respuesta del chatbot:")
            print(result2.get('response', 'Sin respuesta'))
            
            # Verificar si incluye imágenes
            if '!' in result2.get('response', '') and 'http' in result2.get('response', ''):
                print("\n✅ La respuesta incluye imágenes!")
            else:
                print("\n❌ La respuesta NO incluye imágenes")
        else:
            print(f"Error en la API: {response2.status_code}")
    except Exception as e:
        print(f"Error al conectar con la API: {e}")

if __name__ == "__main__":
    test_chatbot_api()