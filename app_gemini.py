import mysql.connector
import config
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, Response
import json
from decimal import Decimal
from datetime import datetime, date
import os
import re
import unicodedata
from dotenv import load_dotenv

# Configurar Flask
app = Flask(__name__)

# Cargar variables de entorno desde .env
load_dotenv()

# Configurar API Key de Google Gemini
api_key = getattr(config, 'GEMINI_API_KEY', None) or os.getenv('GEMINI_API_KEY') or ''
if not api_key:
    print("ADVERTENCIA: GEMINI_API_KEY no está configurada; el chat no podrá generar respuestas de IA.")
else:
    genai.configure(api_key=api_key)

# Mensaje de inicio
print("Iniciando chatbot con IA real (Google Gemini)...")
print("Conectando a MySQL...")
print("API Key de Gemini configurada")

# Configurar modelo para respuestas completas y de calidad
generation_config = {
    "temperature": 0.7,  # Valor equilibrado para creatividad y coherencia
    "top_p": 0.9,      # Menos restrictivo para respuestas más variadas
    "top_k": 40,       # Valor más alto para mayor diversidad
    "max_output_tokens": 1024,  # Permitir respuestas mucho más largas
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config
)

# Configurar base de datos MySQL
def get_db_connection():
    """Conectar a la base de datos MySQL de XAMPP"""
    try:
        connection = mysql.connector.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset='utf8mb4'
        )
        return connection
    except mysql.connector.Error as e:
        print(f"Error al conectar a MySQL: {e}")
        return None

def check_database_connection():
    """Verificar si hay conexión activa a MySQL"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return True
        return False
    except:
        return False

def get_db_connection_with_fallback():
    """Solo conectar a MySQL, sin fallback a SQLite"""
    # Solo intentar MySQL
    mysql_conn = get_db_connection()
    if mysql_conn:
        print("✅ Conectado a MySQL")
        return mysql_conn, 'mysql'
    
    print("❌ No se pudo conectar a MySQL - Verifica que XAMPP esté ejecutándose")
    return None, 'none'

# Caché para el contexto de la base de datos
context_cache = None
cache_timestamp = None
CACHE_DURATION = 300  # 5 minutos en segundos

# Caché para respuestas de IA (para reducir llamadas al API)
response_cache = {}
RESPONSE_CACHE_DURATION = 3600  # 1 hora en segundos

# Contador de requests para manejar límites
daily_requests = 0
MAX_DAILY_REQUESTS = 45  # Un poco menos del límite de 50 para tener margen

# Memoria conversacional por usuario
conversation_memory = {}  # {user_id: [mensajes]}
MAX_CONVERSATION_LENGTH = 10  # Máximo 10 mensajes en memoria

# Información del sistema para el dashboard
system_info = {
    'start_time': None,
    'total_requests': 0,
    'cached_responses_count': 0,
    'avg_response_time': 0,
    'response_times': []
}

def detect_simple_message(message):
    """Detectar mensajes simples que no requieren contexto de base de datos"""
    # Desactivamos la detección de mensajes simples para usar siempre la API de Gemini
    # y evitar respuestas predefinidas
    return None
    
    # Código original comentado:
    """
    message_lower = message.lower().strip()
    
    # Saludos comunes
    greetings = ['hola', 'hello', 'hi', 'hey', 'buenos días', 'buenas tardes', 'buenas noches']
    # Respuestas simples
    simple_responses = ['gracias', 'thanks', 'ok', 'vale', 'perfecto', 'entendido']
    # Despedidas
    farewells = ['adiós', 'hasta luego', 'chao', 'bye', 'nos vemos']
    
    # Detectar tipo de mensaje
    if any(greet in message_lower for greet in greetings):
        return 'greeting'
    elif any(resp in message_lower for resp in simple_responses):
        return 'response'
    elif any(farewell in message_lower for farewell in farewells):
        return 'farewell'
    elif len(message.split()) <= 2 and ('?' not in message):
        return 'simple'
    
    return None
    """

def get_simple_response(message_type, original_message):
    """Obtener respuesta simple para mensajes básicos"""
    responses = {
        'greeting': [
            '¡Hola! ¿En qué te puedo ayudar?',
            'Hola, soy tu asistente sobre Huancayo. ¿Qué te gustaría saber?',
            '¡Buen día! Pregúntame cualquier cosa sobre lugares en Huancayo.'
        ],
        'response': [
            '¡De nada! ¿Hay algo más que te gustaría saber?',
            'Con gusto. ¿Otra pregunta?',
            'Estoy aquí para ayudarte.'
        ],
        'farewell': [
            '¡Hasta luego! Que tengas un buen día.',
            '¡Adiós! Vuelve cuando quieras saber más sobre Huancayo.',
            'Nos vemos pronto. ¡Disfruta tu visita a Huancayo!'
        ],
        'simple': [
            '¿Podrías ser más específico? Estoy aquí para ayudarte sobre lugares en Huancayo.',
            'Dime más detalles sobre lo que quieres saber de Huancayo.',
            'Estoy listo para ayudarte. ¿Sobre qué lugar de Huancayo quieres información?'
        ]
    }
    
    import random
    return random.choice(responses.get(message_type, ['¿En qué te puedo ayudar?']))

def get_user_id():
    """Obtener un ID único para el usuario (basado en IP por simplicidad)"""
    return request.remote_addr or 'anonymous'

def get_conversation_context(user_id):
    """Obtener el contexto de la conversación actual"""
    if user_id not in conversation_memory:
        return ""
    
    # Obtener los últimos 5 mensajes para el contexto
    recent_messages = conversation_memory[user_id][-5:]
    context = "CONVERSACIÓN RECIENTE:\n"
    
    for msg in recent_messages:
        try:
            role = "Usuario" if msg.get('is_user', False) else "Asistente"
            text = msg.get('text', '') or msg.get('message', '')  # Manejar ambas claves por compatibilidad
            if text:  # Solo agregar si hay texto
                context += f"{role}: {text}\n"
        except Exception as e:
            print(f"Error procesando mensaje de conversación: {e}, msg: {msg}")
            continue  # Saltar mensajes con errores
    
    return context

def add_to_conversation(user_id, message, is_user):
    """Agrega un mensaje a la memoria conversacional"""
    if user_id not in conversation_memory:
        conversation_memory[user_id] = []
    
    conversation_memory[user_id].append({
        'text': message,  # Cambiado de 'message' a 'text' para consistencia
        'is_user': is_user,
        'timestamp': datetime.now()
    })
    
    # Mantener solo los últimos mensajes
    if len(conversation_memory[user_id]) > MAX_CONVERSATION_LENGTH:
        conversation_memory[user_id] = conversation_memory[user_id][-MAX_CONVERSATION_LENGTH:]

def format_response(text):
    """Formatea la respuesta con mejor presentación visual, incluyendo imágenes"""
    if not text:
        return text
    
    # Reemplazar asteriscos por negritas HTML
    import re
    
    # Convertir imágenes Markdown (![alt](url)) a etiquetas HTML img
    text = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', r'<img src="\2" alt="\1" style="max-width: 100%; height: auto; border-radius: 8px; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">', text)
    
    # Manejar listas con viñetas
    # Convertir líneas que comienzan con * o - en listas HTML
    lines = text.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        # Detectar líneas de lista
        if re.match(r'^\s*[*\-]\s+', line):
            if not in_list:
                formatted_lines.append('<ul>')
                in_list = True
            content = re.sub(r'^\s*[*\-]\s+', '', line)
            # Aplicar negritas dentro del contenido de la lista
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
            # Procesar imágenes dentro de listas
            content = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', r'<img src="\2" alt="\1" style="max-width: 100%; height: auto; border-radius: 8px; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">', content)
            formatted_lines.append(f'<li>{content}</li>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            
            # Aplicar negritas a texto entre asteriscos dobles
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            
            # Procesar imágenes en líneas normales
            line = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', r'<img src="\2" alt="\1" style="max-width: 100%; height: auto; border-radius: 8px; margin: 10px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">', line)
            
            # Manejar títulos con ### o ## al inicio
            if re.match(r'^###\s+', line):
                content = re.sub(r'^###\s+', '', line)
                formatted_lines.append(f'<h4>{content}</h4>')
            elif re.match(r'^##\s+', line):
                content = re.sub(r'^##\s+', '', line)
                formatted_lines.append(f'<h3>{content}</h3>')
            elif re.match(r'^#\s+', line):
                content = re.sub(r'^#\s+', '', line)
                formatted_lines.append(f'<h2>{content}</h2>')
            else:
                formatted_lines.append(line)
    
    if in_list:
        formatted_lines.append('</ul>')
    
    # Unir líneas y mantener saltos de línea como <br>
    result = '\n'.join(formatted_lines)
    result = result.replace('\n', '<br>')
    
    return result

def get_database_context(category=None, place_name=None):
    """Obtener TODA la información real de la base de datos MySQL con caché"""
    global context_cache, cache_timestamp
    
    # No usar caché cuando se filtra por nombre específico
    import time
    if not place_name and context_cache and cache_timestamp and (time.time() - cache_timestamp) < CACHE_DURATION:
        return context_cache
    
    try:
        conn = get_db_connection()
        if not conn:
            # Devolver contexto predeterminado cuando no hay conexión MySQL
            context_cache = "HUANCAYO: Sin conexión a MySQL."
            cache_timestamp = time.time()
            return context_cache
            
        cursor = conn.cursor()
        
        # Construir consulta con filtros
        query = "SELECT * FROM locaciones"
        params = []
        conditions = []
        
        if category:
            # Mapear categorías en español
            category_map = {
                'parques': 'parque',
                'plazas': 'plaza',
                'miradores': 'mirador',
                'centros-comerciales': 'centro comercial'
            }
            
            category_es = category_map.get(category, category)
            conditions.append("(LOWER(categoria) LIKE LOWER(%s) OR LOWER(nombre) LIKE LOWER(%s))")
            params.extend([f'%{category_es}%', f'%{category_es}%'])
        

        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY nombre"
        
        cursor.execute(query, params)
        lugares = cursor.fetchall()
        
        # Obtener información de las columnas para entender la estructura
        cursor.execute("DESCRIBE locaciones")
        columnas_info = cursor.fetchall()
        nombres_columnas = [col[0] for col in columnas_info]
        
        conn.close()
        
        # Construir contexto con TODA la información real
        context = f"BASE DE DATOS HUANCAYO - {len(lugares)} lugares encontrados:\n\n"
        
        if lugares:
            for lugar in lugares:
                # Construir información completa de cada lugar
                info_lugar = []
                nombre_lugar = None
                
                # Primero extraer el nombre para usarlo como referencia
                for i, valor in enumerate(lugar):
                    if valor is not None and nombres_columnas[i] == 'nombre':
                        nombre_lugar = valor
                        info_lugar.append(f"LUGAR: {valor}")
                        break
                
                # Luego procesar el resto de columnas
                for i, valor in enumerate(lugar):
                    if valor is not None:  # Solo incluir datos no nulos
                        nombre_columna = nombres_columnas[i]
                        
                        if nombre_columna == 'nombre':
                            continue  # Ya procesado arriba
                        elif nombre_columna == 'descripcion':
                            info_lugar.append(f"DESCRIPCIÓN: {valor}")
                        elif nombre_columna == 'latitud':
                            # Buscar longitud
                            longitud_idx = nombres_columnas.index('longitud') if 'longitud' in nombres_columnas else -1
                            if longitud_idx >= 0 and longitud_idx < len(lugar):
                                info_lugar.append(f"UBICACIÓN: {valor}, {lugar[longitud_idx]}")
                        elif nombre_columna == 'longitud':
                            # Ya procesado con latitud
                            continue
                        elif nombre_columna == 'categoria':
                            info_lugar.append(f"CATEGORÍA: {valor}")
                        else:
                            # Cualquier otra columna con información relevante
                            info_lugar.append(f"{nombre_columna.upper()}: {valor}")
                
                # Unir toda la información del lugar
                if info_lugar:
                    context += " | ".join(info_lugar) + "\n"
        else:
            # Cuando no hay lugares, proporcionar un contexto útil pero vacío
            context += "No se encontraron lugares en la categoría especificada."
            if category:
                context += f" (Búsqueda: {category})"
            context += "\n"
        
        # Agregar información de las imágenes si existen
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                
                # Obtener información detallada de imágenes por lugar
                cursor.execute("""
                    SELECT l.nombre, li.url_imagen, li.descripcion 
                    FROM locacion_imagenes li
                    JOIN locaciones l ON li.locacion_id = l.id
                    ORDER BY l.nombre
                """)
                imagenes = cursor.fetchall()
                
                if imagenes:
                    context += f"\nIMÁGENES DISPONIBLES: {len(imagenes)} imágenes asociadas a lugares.\n"
                    
                    # Agrupar imágenes por lugar
                    imagenes_por_lugar = {}
                    for nombre, url_imagen, descripcion in imagenes:
                        if nombre not in imagenes_por_lugar:
                            imagenes_por_lugar[nombre] = []
                        imagenes_por_lugar[nombre].append({
                            'url': url_imagen,
                            'descripcion': descripcion or 'Imagen del lugar'
                        })
                    
                    # Agregar información de imágenes al contexto
                    for lugar, imgs in imagenes_por_lugar.items():
                        context += f"IMAGENES_{lugar.upper().replace(' ', '_')}: "
                        for img in imgs:
                            context += f"[URL: {img['url']}, DESC: {img['descripcion']}] "
                        context += "\n"
                
                conn.close()
        except Exception as e:
            print(f"Error al obtener imágenes: {e}")
            pass  # Si hay error con las imágenes, continuar sin ellas
        
        # Guardar en caché
        context_cache = context
        cache_timestamp = time.time()
        
        return context
        
    except Exception as e:
        # Devolver contexto predeterminado cuando hay errores
        print(f"Error al obtener contexto de BD: {e}")
        context_cache = "HUANCAYO: Error en MySQL."
        cache_timestamp = time.time()
        return context_cache

def get_cached_response(message):
    """Obtener respuesta del caché si existe"""
    import time
    cache_key = message.lower().strip()
    if cache_key in response_cache:
        cached_data = response_cache[cache_key]
        if time.time() - cached_data['timestamp'] < RESPONSE_CACHE_DURATION:
            return cached_data['response']
    return None

def cache_response(message, response):
    """Guardar respuesta en caché"""
    import time
    cache_key = message.lower().strip()
    response_cache[cache_key] = {
        'response': response,
        'timestamp': time.time()
    }

@app.route('/')
def index():
    return render_template('chat_gemini.html')

@app.route('/api/stats')
def stats():
    """Obtener estadísticas REALES de la base de datos"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'error': 'No hay conexión a la base de datos',
                'total_lugares': 0,
                'total_imagenes': 0,
                'categorias': [],
                'estado': 'sin_mysql'
            })
            
        cursor = conn.cursor()
        
        # Contar lugares
        cursor.execute("SELECT COUNT(*) FROM locaciones")
        total_lugares = cursor.fetchone()[0]
        
        # Contar imágenes
        cursor.execute("SELECT COUNT(*) FROM locacion_imagenes")
        total_imagenes = cursor.fetchone()[0]
        
        # Obtener todos los nombres de lugares para análisis
        cursor.execute("SELECT nombre FROM locaciones")
        nombres_lugares = [row[0] for row in cursor.fetchall()]
        
        # Analizar patrones en los nombres para categorizar
        categorias_reales = {}
        
        for nombre in nombres_lugares:
            nombre_lower = nombre.lower()
            
            # Categorizar basado en palabras clave en los nombres
            if any(palabra in nombre_lower for palabra in ['parque', 'bosque', 'montaña', 'laguna', 'cascada', 'río']):
                categoria = 'Naturaleza'
            elif any(palabra in nombre_lower for palabra in ['plaza', 'iglesia', 'templo', 'museo', 'monumento']):
                categoria = 'Cultura'
            elif any(palabra in nombre_lower for palabra in ['ruinas', 'pirámide', 'fortaleza', 'cerro']):
                categoria = 'Historia'
            elif any(palabra in nombre_lower for palabra in ['mercado', 'restaurante', 'comida', 'picantería']):
                categoria = 'Gastronomía'
            elif any(palabra in nombre_lower for palabra in ['mirador', 'sendero', 'camino', 'trekking']):
                categoria = 'Aventura'
            else:
                categoria = 'Otros'
            
            categorias_reales[categoria] = categorias_reales.get(categoria, 0) + 1
        
        # Convertir a lista de categorías con conteos
        categorias_lista = []
        for cat, count in categorias_reales.items():
            categorias_lista.append(f"{cat} ({count})")
        
        # Si no se encontraron categorías, usar las básicas
        if not categorias_lista:
            categorias_lista = ['Naturaleza', 'Cultura', 'Historia', 'Gastronomía', 'Aventura']
        
        conn.close()
        
        return jsonify({
            'total_lugares': total_lugares,
            'total_imagenes': total_imagenes,
            'categorias': categorias_lista,
            'estado': 'con_mysql'
        })
        
    except Exception as e:
        print(f"Error en stats: {e}")
        return jsonify({
            'error': f'Error al obtener estadísticas: {str(e)}',
            'total_lugares': 0,
            'total_imagenes': 0,
            'categorias': [],
            'estado': 'error_mysql'
        })

def detect_category_intent(text: str) -> str | None:
    """
    Detecta si el usuario quiere filtrar por una categoría.
    Devuelve la categoría normalizada o None si no hay intención clara.
    """
    if not text:
        return None
    t = text.lower()  # Simple normalización (puedes usar _norm_cat si existe)
    keywords = {
        "parque": "Parque",
        "plaza": "Parque",
        "naturaleza": "Naturaleza",
        "reserva": "Naturaleza",
        "patrimonio": "Patrimonio",
        "iglesia": "Patrimonio",
        "templo": "Patrimonio",
        "centro comercial": "centros-comerciales",
        "mall": "centros-comerciales",
        "shopping": "centros-comerciales",
        "tienda": "centros-comerciales",
        "compras": "centros-comerciales",
        "estadio": "Estadio",
    }
    for phrase, cat in keywords.items():
        if phrase in t:
            return cat
    return None

def detect_place_name(text: str) -> str | None:
    """
    Detecta si el usuario menciona un nombre específico de lugar.
    Devuelve el nombre del lugar o None si no se detecta ninguno.
    """
    if not text:
        return None
    
    # Lista de lugares conocidos en Huancayo
    lugares_conocidos = [
        "Plaza Constitución", "Plaza Huamanmarca", "Parque de la Identidad", 
        "Cerrito de la Libertad", "Parque Inmaculada", "Torre Torre",
        "Real Plaza", "Open Plaza", "Mall Center", "Plaza Vea",
        "Catedral de Huancayo", "Feria Dominical", "Nevado Huaytapallana",
        "Wariwillka", "Estadio Huancayo"
    ]
    
    # Normalizar texto
    t = text.lower()
    
    # Buscar menciones de lugares conocidos
    for lugar in lugares_conocidos:
        lugar_lower = lugar.lower()
        # Verificar si el nombre del lugar está en el texto como palabra completa
        if lugar_lower in t:
            # Verificar si es una palabra completa o parte de otra palabra
            # Buscar el índice donde aparece el lugar
            idx = t.find(lugar_lower)
            # Verificar si es una palabra completa (está al inicio, al final, o rodeada de espacios)
            if (idx == 0 or not t[idx-1].isalnum()) and (idx + len(lugar_lower) == len(t) or not t[idx + len(lugar_lower)].isalnum()):
                return lugar
    
    return None

def extract_places_from_response(response_text: str) -> list:
    """
    Extrae nombres de lugares mencionados en la respuesta de la IA.
    Devuelve una lista de nombres de lugares encontrados.
    """
    if not response_text:
        return []
    
    # Lista de lugares conocidos en Huancayo
    lugares_conocidos = [
        "Plaza Constitución", "Plaza Huamanmarca", "Parque de la Identidad", 
        "Cerrito de la Libertad", "Parque Inmaculada", "Torre Torre",
        "Real Plaza", "Open Plaza", "Mall Center", "Plaza Vea",
        "Catedral de Huancayo", "Feria Dominical", "Nevado Huaytapallana",
        "Wariwillka", "Estadio Huancayo"
    ]
    
    # Obtener todos los lugares de la base de datos para una detección más completa
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT nombre FROM locaciones")
            lugares_db = cursor.fetchall()
            conn.close()
            
            # Agregar lugares de la base de datos a la lista de lugares conocidos
            for lugar_db in lugares_db:
                if lugar_db[0] and lugar_db[0] not in lugares_conocidos:
                    lugares_conocidos.append(lugar_db[0])
    except Exception as e:
        print(f"Error al obtener lugares de la base de datos: {str(e)}")
    
    # Normalizar texto
    t = response_text.lower()
    
    # Lista para almacenar los lugares encontrados
    lugares_encontrados = []
    
    # Buscar menciones de lugares conocidos
    for lugar in lugares_conocidos:
        lugar_lower = lugar.lower()
        # Verificar si el nombre del lugar está en el texto como palabra completa
        if lugar_lower in t:
            # Verificar si es una palabra completa o parte de otra palabra
            # Buscar todas las ocurrencias del lugar
            start_idx = 0
            while True:
                idx = t.find(lugar_lower, start_idx)
                if idx == -1:
                    break
                    
                # Verificar si es una palabra completa (está al inicio, al final, o rodeada de espacios o puntuación)
                is_word_boundary_before = (idx == 0 or not t[idx-1].isalnum())
                is_word_boundary_after = (idx + len(lugar_lower) == len(t) or not t[idx + len(lugar_lower)].isalnum())
                
                if is_word_boundary_before and is_word_boundary_after:
                    if lugar not in lugares_encontrados:
                        lugares_encontrados.append(lugar)
                        break  # Una vez encontrado, no necesitamos más ocurrencias del mismo lugar
                
                start_idx = idx + 1
    
    return lugares_encontrados



@app.route('/api/chat', methods=['POST'])
def chat():
    global daily_requests
    start_time = datetime.now()
    user_message = request.json.get('message', '')
    stream_mode = request.json.get('stream', False)
    category = request.json.get('category', None)  # Filtro de categoría
    auto_filter = request.json.get('auto_filter', False)  # Nuevo parámetro para filtrado automático
    
    # Detectar intenciones si no se proporcionan explícitamente o si se solicita filtrado automático
    if category is None or auto_filter:
        category = detect_category_intent(user_message)
    
    # Detectar nombre de lugar si se solicita filtrado automático
    place_name = None
    if auto_filter:
        place_name = detect_place_name(user_message)
    
    # Obtener ID del usuario
    user_id = get_user_id()
    
    # Verificar límite diario
    if daily_requests >= MAX_DAILY_REQUESTS:
        response_time = (datetime.now() - start_time).total_seconds()
        system_info['total_requests'] += 1
        system_info['response_times'].append(response_time)
        places = []
        return jsonify({'response': '⚠️ Hemos alcanzado el límite diario de consultas. Por favor, intenta nuevamente mañana o prueba con preguntas similares que ya hayan sido respondidas.', 'places': places})
    
    # Detectar mensajes simples y responder directamente
    message_type = detect_simple_message(user_message)
    if message_type:
        simple_response = get_simple_response(message_type, user_message)
        response_time = (datetime.now() - start_time).total_seconds()
        system_info['total_requests'] += 1
        system_info['response_times'].append(response_time)
        
        # Agregar a la conversación
        add_to_conversation(user_id, user_message, True)
        add_to_conversation(user_id, simple_response, False)
        
        if stream_mode:
            # Devolver respuesta simple en modo streaming
            def generate_simple():
                words = simple_response.split()
                for word in words:
                    json_data = json.dumps({'chunk': word + ' ', 'done': False})
                    yield f"data: {json_data}\n\n"
                # Extraer lugares mencionados en la respuesta
                lugares_mencionados = extract_places_from_response(simple_response)
                
                # Si se encontraron lugares en la respuesta, usarlos directamente para filtrar
                if lugares_mencionados:
                    places = get_places_filtered(category, None, lugares_mencionados)
                    # Usar el primer lugar mencionado como place_name para la UI
                    place_name = lugares_mencionados[0] if not place_name else place_name
                else:
                    # Si no hay lugares mencionados, usar el filtrado normal
                    places = get_places_filtered(category, place_name)
                
                yield f"data: {json.dumps({'chunk': '', 'done': True, 'places': places, 'category': category, 'place_name': place_name, 'lugares_mencionados': lugares_mencionados})}\n\n"
            return Response(generate_simple(), mimetype='text/event-stream')
        else:
            # Extraer lugares mencionados en la respuesta
            lugares_mencionados = extract_places_from_response(simple_response)
            
            # Si se encontraron lugares en la respuesta, usarlos directamente para filtrar
            if lugares_mencionados:
                places = get_places_filtered(category, None, lugares_mencionados)
                # Usar el primer lugar mencionado como place_name para la UI
                place_name = lugares_mencionados[0] if not place_name else place_name
            else:
                # Si no hay lugares mencionados, usar el filtrado normal
                places = get_places_filtered(category, place_name)
                
            return jsonify({'response': simple_response, 'places': places, 'category': category, 'place_name': place_name, 'lugares_mencionados': lugares_mencionados})
    
    # Verificar si tenemos una respuesta en caché
    cached_response = get_cached_response(user_message)
    if cached_response:
        response_time = (datetime.now() - start_time).total_seconds()
        system_info['total_requests'] += 1
        system_info['cached_responses_count'] += 1
        system_info['response_times'].append(response_time)
        
        # Agregar a la conversación
        add_to_conversation(user_id, user_message, True)
        add_to_conversation(user_id, cached_response, False)
        
        # Extraer lugares mencionados en la respuesta en caché
        lugares_mencionados = extract_places_from_response(cached_response)
        
        if stream_mode:
            # Devolver respuesta en caché en modo streaming
            def generate_cached():
                chunks = cached_response.split()
                for chunk in chunks:
                    json_data = json.dumps({'chunk': chunk + ' ', 'done': False})
                    yield f"data: {json_data}\n\n"
                    
                # Si se encontraron lugares en la respuesta, usarlos directamente para filtrar
                if lugares_mencionados:
                    places = get_places_filtered(category, None, lugares_mencionados)
                    # Usar el primer lugar mencionado como place_name para la UI
                    place_name_final = lugares_mencionados[0] if not place_name else place_name
                else:
                    # Si no hay lugares mencionados, usar el filtrado normal
                    places = get_places_filtered(category, place_name)
                    place_name_final = place_name
                    
                yield f"data: {json.dumps({'chunk': '', 'done': True, 'places': places, 'category': category, 'place_name': place_name_final, 'lugares_mencionados': lugares_mencionados})}\n\n"
            return Response(generate_cached(), mimetype='text/event-stream')
        else:
            # Si se encontraron lugares en la respuesta, usarlos directamente para filtrar
            if lugares_mencionados:
                places = get_places_filtered(category, None, lugares_mencionados)
                # Usar el primer lugar mencionado como place_name para la UI
                place_name_final = lugares_mencionados[0] if not place_name else place_name
            else:
                # Si no hay lugares mencionados, usar el filtrado normal
                places = get_places_filtered(category, place_name)
                place_name_final = place_name
                
            return jsonify({'response': cached_response, 'places': places, 'category': category, 'place_name': place_name_final, 'lugares_mencionados': lugares_mencionados})
    
    # Detectar si el usuario quiere ver todos los lugares
    mostrar_todos = False
    if any(frase in user_message.lower() for frase in ['todos los lugares', 'mostrar todos', 'todos los sitios', 'ver todos']):
        mostrar_todos = True
        category = None  # Eliminar filtro de categoría
    
    # Obtener contexto real de la base de datos y conversación (con filtros)
    db_context = get_database_context(category, place_name)
    conversation_context = get_conversation_context(user_id)
    
    # Extraer lugares reales del contexto para validación
    lugares_reales = []
    for linea in db_context.split('\n'):
        if 'LUGAR:' in linea:
            # Extraer el nombre del lugar
            partes = linea.split('LUGAR:')
            if len(partes) > 1:
                lugar = partes[1].split('|')[0].strip()
                lugares_reales.append(lugar)
    
    # Si no hay datos reales disponibles, proporcionar una respuesta útil
    if not lugares_reales:
        # Verificar si es un problema de conexión o simplemente no hay datos
        if "Sin conexión" in db_context or "Error" in db_context:
            safe_msg = (
                'En este momento no tengo datos listos para mostrar. Ahora contamos con la columna de categoría para filtrar mejor. '
                'Dime una categoría (por ejemplo: Parques, Patrimonio, Naturaleza, Centro Comercial, Estadio) '
                'o escribe "mostrar todos" para ver todo el listado.'
            )
        else:
            # No hay lugares en la categoría especificada
            if mostrar_todos:
                # El usuario solicitó todos los lugares pero no hay ninguno
                safe_msg = (
                    'Actualmente no tengo lugares registrados en mi base de datos. '
                    'Te sugiero probar con estas categorías populares:\n'
                    '* Parques\n'
                    '* Plazas\n'
                    '* Miradores\n'
                    '* Iglesias\n'
                    '* Museos\n'
                    '* Mercados\n'
                    '¿Qué tipo de lugar te gustaría conocer?'
                )
            elif category:
                # Buscar categorías similares o alternativas
                safe_msg = (
                    f'No encontré lugares en la categoría "{category}" en mi base de datos actual. '
                    'Te sugiero probar con estas categorías populares:\n'
                    '* Parques\n'
                    '* Plazas\n'
                    '* Miradores\n'
                    '* Iglesias\n'
                    '* Museos\n'
                    '* Mercados\n'
                    '¿Te gustaría que busque en alguna de estas categorías?'
                )
            else:
                safe_msg = (
                    'Actualmente no tengo lugares registrados en mi base de datos. '
                    'Te sugiero probar con estas categorías populares:\n'
                    '* Parques\n'
                    '* Plazas\n'
                    '* Miradores\n'
                    '* Iglesias\n'
                    '* Museos\n'
                    '* Mercados\n'
                    '¿Qué tipo de lugar te gustaría conocer?'
                )
        
        add_to_conversation(user_id, user_message, True)
        add_to_conversation(user_id, safe_msg, False)
        if stream_mode:
            def generate_no_data():
                for chunk in safe_msg.split():
                    json_data = json.dumps({'chunk': chunk + ' ', 'done': False})
                    yield f"data: {json_data}\n\n"
                places = get_places_filtered(category, place_name)
                yield f"data: {json.dumps({'chunk': '', 'done': True, 'places': places, 'category': category, 'place_name': place_name})}\n\n"
            return Response(generate_no_data(), mimetype='text/event-stream')
        else:
            places = get_places_filtered(category, place_name)
            return jsonify({'response': safe_msg, 'places': places, 'category': category, 'place_name': place_name})

    # Crear prompt con contexto de conversación - MUY IMPORTANTE: USAR SOLO DATOS REALES
    prompt = f"""CONTEXTO DE BASE DE DATOS HUANCAYO (USAR SOLO ESTA INFORMACIÓN):
{db_context}

HISTORIAL DE CONVERSACIÓN:
{conversation_context}

PREGUNTA ACTUAL:{user_message}

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
- Cuando menciones un lugar que tenga imágenes disponibles, incluye las URLs de las imágenes
- Formato para imágenes: Usa ![descripción](URL) para insertar imágenes
- Si hay múltiples imágenes, crea una galería mostrando 2-3 imágenes principales
- Las imágenes deben aparecer después de la descripción del lugar
- **IMPORTANTE**: Las URLs de imágenes deben estar completas, sin cortar, sin saltos de línea en medio de la URL

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

RESPONDE ÚNICAMENTE BASÁNDOTE EN LOS DATOS REALES DEL CONTEXTO. IMPORTANTE: NO MENCIONES PROBLEMAS TÉCNICOS NI DE CONEXIÓN."""

    try:
        daily_requests += 1
        
        if stream_mode:
            # Modo streaming con mejor manejo de tiempos
            def generate():
                try:
                    response_stream = model.generate_content(prompt, stream=True)
                    chunk_count = 0
                    max_chunks = 500  # Máximo límite para respuestas completas sin cortes
                    full_response = ""
                    
                    for chunk in response_stream:
                        if chunk.text and chunk_count < max_chunks:
                            # Acumular el texto para formatear al final
                            full_response += chunk.text
                            
                            # Para el streaming, enviar el texto con saltos de línea reales
                            escaped_text = chunk.text.replace('\\', '\\\\').replace('"', '\\"').replace('\r', '\\r').replace('\t', '\\t')
                            # No escapar \n, dejar que los saltos de línea lleguen como caracteres reales
                            json_data = json.dumps({'chunk': escaped_text, 'done': False})
                            yield f"data: {json_data}\n\n"
                            
                            chunk_count += 1
                    
                    # Guardar respuesta completa en caché y en memoria conversacional
                    formatted_response = format_response(full_response)
                    
                    # Validar que la respuesta use solo datos reales
                    respuesta_validada = validar_respuesta_real(formatted_response, lugares_reales)
                    
                    # Extraer lugares mencionados en la respuesta
                    lugares_mencionados = extract_places_from_response(respuesta_validada)
                    
                    cache_response(user_message, respuesta_validada)
                    add_to_conversation(user_id, user_message, True)
                    add_to_conversation(user_id, respuesta_validada, False)
                    
                    # Si se encontraron lugares en la respuesta, usarlos directamente para filtrar
                    if lugares_mencionados:
                        places = get_places_filtered(category, None, lugares_mencionados)
                        # Usar el primer lugar mencionado como place_name para la UI
                        place_name = lugares_mencionados[0] if not place_name else place_name
                    else:
                        # Si no hay lugares mencionados, usar el filtrado normal
                        places = get_places_filtered(category, place_name)
                        
                    yield f"data: {json.dumps({'chunk': '', 'done': True, 'places': places, 'category': category, 'place_name': place_name, 'lugares_mencionados': lugares_mencionados})}\n\n"
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    if "quota" in str(e).lower() or "429" in str(e):
                        error_msg = "⚠️ Límite de consultas alcanzado. Intenta con preguntas similares a las anteriores o vuelve mañana."
                    elif "timeout" in str(e).lower() or "deadline" in str(e).lower():
                        error_msg = "Error: La respuesta está tomando demasiado tiempo. Intenta con una pregunta más específica."
                    yield f"data: {json.dumps({'chunk': error_msg, 'done': False})}\n\n"
                    yield f"data: {json.dumps({'chunk': '', 'done': True})}\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        else:
            # Modo normal (no streaming) con timeout implícito
            response = model.generate_content(prompt)
            
            # Validar que la respuesta use solo datos reales
            respuesta_validada = validar_respuesta_real(response.text, lugares_reales)
            
            # Extraer lugares mencionados en la respuesta
            lugares_mencionados = extract_places_from_response(respuesta_validada)
            
            cache_response(user_message, respuesta_validada)
            
            # Guardar en memoria conversacional
            add_to_conversation(user_id, user_message, True)
            add_to_conversation(user_id, respuesta_validada, False)
            
            # Si se encontraron lugares en la respuesta, usarlos directamente para filtrar
            if lugares_mencionados:
                places = get_places_filtered(category, None, lugares_mencionados)
                # Usar el primer lugar mencionado como place_name para la UI
                place_name = lugares_mencionados[0] if not place_name else place_name
            else:
                # Si no hay lugares mencionados, usar el filtrado normal
                places = get_places_filtered(category, place_name)
                
            return jsonify({'response': respuesta_validada, 'places': places, 'category': category, 'place_name': place_name, 'lugares_mencionados': lugares_mencionados})
    except Exception as e:
        error_msg = f'Error al procesar la consulta: {str(e)}'
        if "quota" in str(e).lower() or "429" in str(e):
            error_msg = '⚠️ Límite de consultas alcanzado. Intenta con preguntas similares a las anteriores.'
        elif "timeout" in str(e).lower() or "deadline" in str(e):
            error_msg = '⏰ La respuesta está tomando demasiado tiempo. Intenta con una pregunta más específica.'
        elif "api" in str(e).lower():
            error_msg = '🔧 Problema con la conexión a la API de Gemini. Por favor, intenta nuevamente en unos momentos.'
        else:
            error_msg = '❌ Error al procesar tu mensaje. Por favor, intenta nuevamente o reformula tu pregunta.'
        places = []
        return jsonify({'response': error_msg, 'places': places})

def get_places_filtered(category=None, place_name=None, lugares_mencionados=None):
    """Obtener lugares filtrados por categoría, nombre o lista de lugares mencionados"""
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = conn.cursor()
    
    # Si tenemos lugares mencionados, usamos esos directamente con búsqueda mejorada
    if lugares_mencionados and isinstance(lugares_mencionados, list) and len(lugares_mencionados) > 0:
        # Construir consulta para múltiples lugares usando LIKE para cada lugar
        # con coincidencias más precisas
        conditions = []
        params = []
        
        for lugar in lugares_mencionados:
            # Buscar coincidencias exactas primero (prioridad alta)
            conditions.append("(nombre = %s OR nombre LIKE %s OR nombre LIKE %s OR nombre LIKE %s)")
            params.extend([lugar, f"{lugar}%", f"% {lugar}", f"%{lugar}%"])
        
        # Unir condiciones con OR
        where_clause = " OR ".join(conditions)
        query = f"SELECT nombre, descripcion, latitud, longitud, categoria FROM locaciones WHERE {where_clause}"
        
        # Agregar filtro de categoría si existe
        if category:
            query += " AND categoria LIKE %s"
            params.append(f"%{category}%")
            
        # Ordenar por relevancia (coincidencia exacta primero)
        query += " ORDER BY CASE WHEN nombre IN ("
        query += ", ".join(["%s"] * len(lugares_mencionados))
        query += ") THEN 0 ELSE 1 END, nombre"
        params.extend(lugares_mencionados)
        
        cursor.execute(query, params)
    else:
        # Construir la consulta base (comportamiento original mejorado)
        base_query = "SELECT nombre, descripcion, latitud, longitud, categoria FROM locaciones WHERE 1=1"
        params = []
        
        # Agregar filtro de categoría si existe
        if category:
            base_query += " AND categoria LIKE %s"
            params.append(f"%{category}%")
        
        # Agregar filtro de nombre si existe con búsqueda mejorada
        if place_name:
            base_query += " AND (nombre = %s OR nombre LIKE %s OR nombre LIKE %s OR nombre LIKE %s)"
            params.extend([place_name, f"{place_name}%", f"% {place_name}", f"%{place_name}%"])
            # Ordenar por relevancia (coincidencia exacta primero)
            base_query += " ORDER BY CASE WHEN nombre = %s THEN 0 ELSE 1 END, nombre"
            params.append(place_name)
        
        # Ejecutar la consulta
        if params:
            cursor.execute(base_query, params)
        else:
            cursor.execute(base_query.replace("WHERE 1=1", ""))
    
    lugares = cursor.fetchall()
    places = []
    
    for l in lugares:
        nombre = l[0]
        # Obtener imagen del lugar
        cursor.execute("""
            SELECT url_imagen 
            FROM locacion_imagenes 
            WHERE locacion_id = (SELECT id FROM locaciones WHERE nombre = %s LIMIT 1) 
            ORDER BY id 
            LIMIT 1
        """, (nombre,))
        imagen = cursor.fetchone()
        imagen_url = imagen[0] if imagen else None
        
        place = {
            'nombre': nombre,
            'descripcion': l[1],
            'categoria': l[4],
            'imagen_url': imagen_url,
            'ubicacion': f"{l[2]}, {l[3]}" if l[2] and l[3] else None
        }
        places.append(place)
    
    conn.close()
    return places

def get_places_by_category(category):
    """Función legacy - ahora usa get_places_filtered"""
    return get_places_filtered(category=category)

def validar_respuesta_real(respuesta, lugares_reales):
    """Validar que la respuesta use solo lugares reales de la base de datos.
    También verifica que cualquier nombre entre [[...]] exista en la BD y limpia los marcadores antes de responder.
    """
    if not lugares_reales:
        return (
            'Por ahora no dispongo de información del catálogo de lugares. '
            'Intenta más tarde o pregunta nuevamente cuando el catálogo esté disponible.'
        )

    # Normalizar utilidades
    def _normalize(txt: str) -> str:
        if not isinstance(txt, str):
            txt = str(txt)
        txt = unicodedata.normalize('NFD', txt)
        txt = ''.join(c for c in txt if unicodedata.category(c) != 'Mn')  # quitar acentos
        return txt.lower().strip()

    lugares_norm = {_normalize(l) for l in lugares_reales}

    # Convertir respuesta a minúsculas para algunas detecciones
    respuesta_lower = respuesta.lower()

    problemas_detectados = []

    # Buscar menciones de problemas técnicos (ampliado)
    technical_phrases = [
        'problemas de conexión', 'sin conexión', 'base de datos completa', 'problemas técnicos',
        'base de datos está fallando', 'base de datos fallando', 'mi base de datos está fallando', 'mi base de datos fallando',
        'no tengo acceso a la base de datos', 'no puedo acceder a la base de datos'
    ]
    if any(frase in respuesta_lower for frase in technical_phrases):
        problemas_detectados.append('problemas_tecnicos')

    # Detectar respuestas demasiado genéricas
    generic_markers = ['ideas generales', 'recomendaciones generales', 'de forma general', 'en general puedo']
    if any(g in respuesta_lower for g in generic_markers):
        problemas_detectados.append('generico_sin_datos')

    # Validación estricta de marcadores [[...]]
    marcados = re.findall(r"\[\[(.+?)\]\]", respuesta)
    for m in marcados:
        if _normalize(m) not in lugares_norm:
            problemas_detectados.append(f'lugar_inventado_o_fuera_de_contexto: {m}')

    # Heurística mínima para lugares genéricos comunes que no estén en BD (mantener lógica previa)
    lugares_comunes = ['laguna de paca', 'parque nacional de huayllay', 'distrito de chupaca', 'concepción']
    for lugar_generico in lugares_comunes:
        if lugar_generico in respuesta_lower:
            if all(lugar_generico not in _normalize(lr) for lr in lugares_reales):
                problemas_detectados.append(f'lugar_inventado: {lugar_generico}')

    if problemas_detectados:
        print(f"ALERTA: Respuesta contiene problemas: {problemas_detectados}")
        # Si hay pocos lugares en la base de datos, ser más permisivo
        if len(lugares_reales) < 3:
            print("INFO: Pocos lugares en BD, usando respuesta original con marcadores limpios")
            # Limpiar marcadores y devolver la respuesta original
            respuesta_limpia = re.sub(r"\[\[(.*?)\]\]", r"\1", respuesta)
            return respuesta_limpia
        else:
            return generar_respuesta_solo_datos_reales(lugares_reales, respuesta)

    # Si pasa validaciones, limpiar los marcadores [[...]] antes de devolver
    respuesta_limpia = re.sub(r"\[\[(.*?)\]\]", r"\1", respuesta)
    return respuesta_limpia

def generar_respuesta_solo_datos_reales(lugares_reales, respuesta_original):
    """Generar respuesta usando solo datos reales cuando se detecta información inventada"""
    
    # Crear una respuesta completamente nueva basada solo en datos reales
    respuesta_real = "¡Perfecto! Te puedo recomendar estos lugares específicos que tenemos registrados en Huancayo:\n\n"
    
    # Obtener el contexto completo con detalles
    db_context = get_database_context()
    
    # Extraer información de lugares de forma más robusta
    lugares_info = {}
    
    # Parsear el contexto línea por línea
    for linea in db_context.split('\n'):
        linea = linea.strip()
        if 'LUGAR:' in linea:
            # Extraer nombre del lugar
            partes = linea.split('LUGAR:')
            if len(partes) > 1:
                nombre_lugar = partes[1].split('|')[0].strip()
                if nombre_lugar and nombre_lugar not in lugares_info:
                    lugares_info[nombre_lugar] = {'nombre': nombre_lugar, 'descripcion': '', 'ubicacion': ''}
        
        # Buscar información adicional del lugar actual
        if '|' in linea:
            partes = [p.strip() for p in linea.split('|')]
            for parte in partes:
                if 'DESCRIPCIÓN:' in parte:
                    # Encontrar a qué lugar pertenece esta descripción
                    for nombre in lugares_info:
                        if nombre in linea or any(n in linea for n in lugares_info.keys()):
                            lugares_info[nombre]['descripcion'] = parte.replace('DESCRIPCIÓN:', '').strip()
                            break
                elif 'UBICACIÓN:' in parte:
                    for nombre in lugares_info:
                        if nombre in linea or any(n in linea for n in lugares_info.keys()):
                            lugares_info[nombre]['ubicacion'] = parte.replace('UBICACIÓN:', '').strip()
                            break
    
    # Si no pudimos extraer información detallada, usar solo los nombres
    if not lugares_info:
        respuesta_real = "¡Excelente! Tenemos estos lugares registrados en Huancayo:\n\n"
        for lugar in lugares_reales[:6]:  # Mostrar hasta 6 lugares
            respuesta_real += f"• **{lugar}**\n"
        respuesta_real += f"\nTenemos {len(lugares_reales)} lugares registrados en total."
        respuesta_real += "\n\n¿Sobre cuál te gustaría saber más información?"
        return respuesta_real
    
    # Mostrar lugares con información disponible
    lugares_con_info = [info for info in lugares_info.values() if info['descripcion'] or info['ubicacion']]
    
    if lugares_con_info:
        for lugar in lugares_con_info[:4]:  # Mostrar 4 lugares con detalles
            respuesta_real += f"• **{lugar['nombre']}**"
            if lugar['descripcion']:
                respuesta_real += f" - {lugar['descripcion']}"
            if lugar['ubicacion']:
                respuesta_real += f"\n  📍 {lugar['ubicacion']}"
            respuesta_real += "\n\n"
    else:
        # Mostrar solo nombres si no hay información adicional
        for nombre in list(lugares_info.keys())[:6]:
            respuesta_real += f"• **{nombre}**\n"
    
    respuesta_real += f"Tenemos {len(lugares_reales)} lugares registrados en total."
    respuesta_real += "\n\n¿Sobre cuál te gustaría saber más información específica?"
    
    return respuesta_real

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """Obtener estadísticas del sistema para el dashboard"""
    try:
        # Calcular tiempo de actividad
        uptime = datetime.now() - system_info['start_time'] if system_info['start_time'] else timedelta(0)
        
        # Calcular tiempo promedio de respuesta
        if system_info['response_times']:
            avg_response_time = sum(system_info['response_times']) / len(system_info['response_times'])
            avg_response_time = round(avg_response_time, 2)
        else:
            avg_response_time = 0
        
        # Obtener estadísticas de la base de datos
        db_stats = stats()
        
        # Obtener tamaño del caché
        cache_size = len(response_cache)
        
        return jsonify({
            'system': {
                'uptime_hours': uptime.total_seconds() / 3600,
                'total_requests': system_info['total_requests'],
                'cached_responses': system_info['cached_responses_count'],
                'cache_size': cache_size,
                'avg_response_time': avg_response_time,
                'daily_requests': daily_requests,
                'max_daily_requests': MAX_DAILY_REQUESTS
            },
            'database': {
                'status': db_stats.get('estado', 'error'),
                'total_places': db_stats.get('total_lugares', 0),
                'categories': db_stats.get('categorias', []),
                'last_update': db_stats.get('last_update', None)
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard/activity')
def dashboard_activity():
    """Obtener actividad reciente del sistema"""
    try:
        # Obtener las últimas respuestas del caché (más recientes primero)
        recent_activity = []
        for key in list(response_cache.keys())[-10:]:  # Últimas 10 respuestas
            recent_activity.append({
                'query': key,
                'response': response_cache[key][:100] + '...' if len(response_cache[key]) > 100 else response_cache[key],
                'timestamp': datetime.now().isoformat()
            })
        
        return jsonify({'recent_activity': recent_activity})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard/test-connection', methods=['POST'])
def test_connection():
    """Probar conexión a la base de datos"""
    try:
        conn, db_type = get_db_connection_with_fallback()
        if conn:
            conn.close()
            db_name = "MySQL" if db_type == "mysql" else "SQLite (respaldo)"
            return jsonify({'success': True, 'message': f'Conexión exitosa a {db_name}'})
        else:
            return jsonify({'success': False, 'message': 'No se pudo conectar a ninguna base de datos'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/dashboard/clear-cache', methods=['POST'])
def clear_cache():
    """Limpiar el caché de respuestas y conversación del usuario"""
    try:
        user_id = get_user_id()
        if user_id in conversation_memory:
            del conversation_memory[user_id]
        global response_cache
        response_cache.clear()
        system_info['cached_responses_count'] = 0
        return jsonify({'success': True, 'message': 'Caché y conversación limpiados exitosamente'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


@app.route('/api/places')
def get_places():
    """Obtener lugares filtrados por categoría y búsqueda"""
    try:
        category = request.args.get('category', '')
        search = request.args.get('search', '')
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'places': [], 'error': 'No hay conexión a la base de datos'})
        
        cursor = conn.cursor()
        
        # Primero obtener la estructura real de la tabla
        cursor.execute("DESCRIBE locaciones")
        columnas_info = cursor.fetchall()
        nombres_columnas = [col[0] for col in columnas_info]
        
        # Construir la consulta base con las columnas que existen
        select_columns = []
        if 'nombre' in nombres_columnas:
            select_columns.append('nombre')
        if 'descripcion' in nombres_columnas:
            select_columns.append('descripcion')
        if 'latitud' in nombres_columnas:
            select_columns.append('latitud')
        if 'longitud' in nombres_columnas:
            select_columns.append('longitud')
        # Incluir columna categoria si existe
        if 'categoria' in nombres_columnas:
            select_columns.append('categoria')
        
        if not select_columns:
            return jsonify({'places': [], 'error': 'No se encontraron columnas válidas en la tabla'})
        
        query = f"SELECT {', '.join(select_columns)} FROM locaciones WHERE 1=1"
        params = []
        used_sql_category = False
        
        # Normalización y mapeo de categoría desde el frontend para usarla en SQL si existe columna 'categoria'
        def _norm_cat(s):
            if not s:
                return ''
            s = str(s).strip().lower().replace('-', ' ')
            try:
                import unicodedata
                s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
            except Exception:
                pass
            return s
        
        category_candidates = []
        if category:
            objetivo = _norm_cat(category)
            mapping = {
                'parques': ['parque'],
                'parque': ['parque'],
                'plazas': ['plaza'],
                'plaza': ['plaza'],
                'miradores': ['mirador'],
                'mirador': ['mirador'],
                'centros comerciales': ['centro comercial'],
                'centro comercial': ['centro comercial'],
                'centros-comerciales': ['centro comercial'],
                'patrimonios': ['patrimonio'],
                'patrimonio': ['patrimonio'],
                'estadios': ['estadio'],
                'estadio': ['estadio'],
                'naturaleza': ['naturaleza']
            }
            category_candidates = mapping.get(objetivo, [objetivo])
        
        # Filtrar por categoría usando la columna real si existe, con múltiples candidatos normalizados
        if category_candidates and 'categoria' in nombres_columnas:
            conditions = []
            for cand in category_candidates:
                conditions.append("LOWER(categoria) LIKE LOWER(%s)")
                params.append(f"%{cand}%")
            query += " AND (" + " OR ".join(conditions) + ")"
            used_sql_category = True
        
        # Filtrar por búsqueda si se especifica (solo por nombre y descripción)
        if search:
            search_conditions = []
            if 'nombre' in nombres_columnas:
                search_conditions.append("nombre LIKE %s")
                params.append(f"%{search}%")
            if 'descripcion' in nombres_columnas:
                search_conditions.append("descripcion LIKE %s")
                params.append(f"%{search}%")
            
            if search_conditions:
                query += " AND (" + " OR ".join(search_conditions) + ")"
        
        query += " ORDER BY nombre"
        
        cursor.execute(query, params)
        lugares = cursor.fetchall()
        
        # Helper de normalización local para comparar categorías sin tildes y en minúsculas
        def _norm(s):
            if not s:
                return ''
            s = str(s).strip().lower()
            try:
                import unicodedata
                s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
            except Exception:
                pass
            return s

        # Obtener imágenes para cada lugar y usar la categoría de la BD si existe
        places_with_images = []
        for lugar in lugares:
            # Construir diccionario con datos del lugar
            lugar_data = {}
            for i, columna in enumerate(select_columns):
                if i < len(lugar):
                    lugar_data[columna] = lugar[i]
            
            nombre = lugar_data.get('nombre', '')
            descripcion = lugar_data.get('descripcion', '')
            latitud = lugar_data.get('latitud')
            longitud = lugar_data.get('longitud')
            
            # Usar categoría de la base de datos si está disponible; si no, inferir por nombre
            categoria = lugar_data.get('categoria')
            if not categoria:
                categoria = 'Sin categoría'
                if nombre:
                    nombre_lower = _norm(nombre)
                    if any(palabra in nombre_lower for palabra in ['parque', 'bosque', 'montana', 'laguna', 'cascada', 'rio', 'naturaleza']):
                        categoria = 'Naturaleza'
                    elif any(palabra in nombre_lower for palabra in ['plaza', 'plazuela']):
                        categoria = 'Plazas'
                    elif any(palabra in nombre_lower for palabra in ['mirador', 'vista', 'panoramica']):
                        categoria = 'Miradores'
                    elif any(palabra in nombre_lower for palabra in ['iglesia', 'templo', 'cerro']):
                        categoria = 'Religioso'
                    elif any(palabra in nombre_lower for palabra in ['mercado', 'feria']):
                        categoria = 'Mercados'
                    elif any(palabra in nombre_lower for palabra in ['museo', 'cultural']):
                        categoria = 'Museos'
                    elif any(palabra in nombre_lower for palabra in ['restaurante', 'comida', 'picanteria']):
                        categoria = 'Restaurantes'
                    elif any(palabra in nombre_lower for palabra in ['hotel', 'hostal', 'alojamiento']):
                        categoria = 'Hoteles'
            
            # Filtrar por categoría si aún no se filtró en SQL
            if category and category != 'todos' and not used_sql_category:
                # Mapear valores del frontend a equivalentes de la BD
                category_mapping = {
                    'parques': ['parque', 'naturaleza'],
                    'plazas': ['plaza', 'plazas'],
                    'miradores': ['mirador', 'miradores'],
                    'museos': ['museo', 'museos'],
                    'mercados': ['mercado', 'mercados'],
                    'restaurantes': ['restaurante', 'restaurantes', 'comida'],
                    'hoteles': ['hotel', 'hoteles', 'alojamiento'],
                    'patrimonio': ['patrimonio'],
                    'centro-comercial': ['centro comercial', 'centros comerciales'],
                    'centros-comerciales': ['centro comercial', 'centros comerciales'],
                    'estadios': ['estadio', 'estadios']
                }
                objetivo = _norm(category)
                candidatos = category_mapping.get(objetivo, [objetivo])
                categoria_norm = _norm(categoria)
                if not any(c in categoria_norm for c in candidatos):
                    continue
            
            # Buscar imagen principal del lugar
            imagen_url = None
            if nombre:
                cursor.execute("""
                    SELECT url_imagen, descripcion 
                    FROM locacion_imagenes 
                    WHERE locacion_id = (SELECT id FROM locaciones WHERE nombre = %s LIMIT 1)
                    ORDER BY id LIMIT 1
                """, (nombre,))
                imagen = cursor.fetchone()
                if imagen:
                    imagen_url = imagen[0]
            
            place_data = {
                'nombre': nombre,
                'descripcion': descripcion or '',
                'categoria': categoria,
                'imagen_url': imagen_url,
                'ubicacion': f"{latitud}, {longitud}" if latitud and longitud else None
            }
            places_with_images.append(place_data)
        
        conn.close()
        
        return jsonify({
            'places': places_with_images,
            'total': len(places_with_images)
        })
        
    except Exception as e:
        print(f"Error en get_places: {e}")
        return jsonify({'places': [], 'error': str(e)})

@app.route('/dashboard')
def dashboard():
    """Servir la página del dashboard"""
    return render_template('dashboard.html')

if __name__ == '__main__':
    # Reset de estado al iniciar app (para evitar confusiones después de reinicios)
    context_cache = None
    cache_timestamp = None
    response_cache = {}
    conversation_memory = {}
    system_info = {
        'start_time': None,
        'total_requests': 0,
        'cached_responses_count': 0,
        'avg_response_time': 0,
        'response_times': []
    }
    system_info['start_time'] = datetime.now()
    print("Iniciando chatbot con IA real (Google Gemini)...")
    print("Conectando a MySQL...")
    print("API Key de Gemini configurada")
    app.run(host='0.0.0.0', port=5000, debug=True)