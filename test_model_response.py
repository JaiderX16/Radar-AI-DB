#!/usr/bin/env python3
"""Script para probar cómo responde el modelo con el contexto mejorado"""

import os
import sys
import google.generativeai as genai
from config import GEMINI_API_KEY

def test_model_with_context():
    """Probar cómo responde el modelo con el contexto de imágenes"""
    
    # Obtener el contexto de la base de datos
    print("Obteniendo contexto de la base de datos...")
    from app_gemini import get_database_context
    context = get_database_context()
    
    print("\n=== CONTEXTO OBTENIDO ===")
    print(f"Longitud del contexto: {len(context)} caracteres")
    
    # Buscar líneas de imágenes
    print("\n=== IMÁGENES ENCONTRADAS ===")
    for line in context.split('\n'):
        if 'IMAGENES_' in line and 'http' in line:
            print(f"{line[:100]}...")
    
    # Configurar el modelo
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Crear el prompt con el contexto
    prompt = f"""
{context}

PREGUNTA ACTUAL: donde podria ir a dar un paseo al aire libre?

INSTRUCCIONES CRÍTICAS - LEER Y SEGUIR EXACTAMENTE:
1. **USAR ÚNICAMENTE** la información del contexto de base de datos proporcionado arriba
2. **NO inventar, suponer ni agregar** información que no esté en el contexto
3. **NO mencionar** lugares que no estén listados en el contexto
4. Si no hay información sobre algo en el contexto, **decir explícitamente** que no se tiene esa información
5. **NO dar recomendaciones genéricas** sobre Huancayo
6. **Citar específicamente** los lugares mencionados en el contexto
7. **NO MENCIONAR** problemas de conexión, bases de datos, problemas técnicos o limitaciones de acceso a datos
8. **ASUMIR** que tienes acceso completo y perfecto a toda la información del contexto

INSTRUCCIONES PARA INCLUIR IMÁGENES:
- Cuando menciones un lugar que tenga imágenes disponibles, SIEMPRE incluye las URLs de las imágenes
- Busca en el contexto las líneas que empiezan con "IMAGENES_" para encontrar las URLs de cada lugar
- Formato para imágenes: Usa ![descripción](URL) para insertar imágenes
- Si hay múltiples imágenes, crea una galería mostrando 2-3 imágenes principales
- Las imágenes deben aparecer después de la descripción del lugar
- Ejemplo: Para el Parque Constitución, busca "IMAGENES_PARQUE_CONSTITUCION:" en el contexto y usa esas URLs

INSTRUCCIONES DE FORMATO:
- Usa **negritas** para resaltar lugares importantes y categorías
- Organiza la información en párrafos separados (presiona ENTER dos veces)
- Usa listas con viñetas (*) para enumerar opciones o lugares
- Incluye saltos de línea reales entre secciones (no escribas \\n)
- Mantén un tono conversacional y amigable
- NO uses \\n ni caracteres de escape, usa saltos de línea reales
- IMPORTANTE: Cada nombre de lugar que menciones DEBE ir exactamente entre [[ y ]], por ejemplo: [[Cerrito de la Libertad]]. SOLO puedes encerrar entre [[ ]] nombres de lugares que existan en el contexto.
- Si el usuario pregunta por un lugar que no aparece en el contexto, responde claramente que NO hay información al respecto y no inventes nada.
- Cuando incluyas imágenes, usa el formato Markdown: ![descripción de la imagen](URL_de_la_imagen)

RESPONDE ÚNICAMENTE BASÁNDOTE EN LOS DATOS REALES DEL CONTEXTO. IMPORTANTE: NO MENCIONES PROBLEMAS TÉCNICOS NI DE CONEXIÓN.
"""
    
    print("\n=== PROBANDO MODELO ===")
    print("Enviando prompt al modelo...")
    
    try:
        response = model.generate_content(prompt)
        print("\n=== RESPUESTA DEL MODELO ===")
        print(response.text)
        
        # Verificar si incluye imágenes
        if '!' in response.text and 'http' in response.text:
            print("\n✅ El modelo está incluyendo imágenes!")
        else:
            print("\n❌ El modelo NO está incluyendo imágenes")
            print("Buscando menciones de imágenes...")
            if 'imagen' in response.text.lower():
                print("- El modelo menciona imágenes pero no las incluye")
            else:
                print("- El modelo no menciona imágenes")
                
    except Exception as e:
        print(f"Error al generar respuesta: {e}")

if __name__ == "__main__":
    test_model_with_context()