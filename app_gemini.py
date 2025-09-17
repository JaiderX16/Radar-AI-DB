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
    """Formatea la respuesta con mejor presentación visual"""
    if not text:
        return text
    
    # Reemplazar asteriscos por negritas HTML
    import re
    
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
            formatted_lines.append(f'<li>{content}</li>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            
            # Aplicar negritas a texto entre asteriscos dobles
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            
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

def get_database_context():
    """Obtener TODA la información real de la base de datos MySQL con caché"""
    global context_cache, cache_timestamp
    
    # Verificar si el caché es válido
    import time
    if context_cache and cache_timestamp and (time.time() - cache_timestamp) < CACHE_DURATION:
        return context_cache
    
    try:
        conn = get_db_connection()
        if not conn:
            # Devolver contexto predeterminado cuando no hay conexión MySQL
            context_cache = "HUANCAYO: Sin conexión a MySQL."
            cache_timestamp = time.time()
            return context_cache
            
        cursor = conn.cursor()
        
        # Obtener TODOS los datos de todas las columnas
        cursor.execute("SELECT * FROM locaciones ORDER BY nombre")
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
                
                # Procesar cada columna
                for i, valor in enumerate(lugar):
                    if valor is not None:  # Solo incluir datos no nulos
                        nombre_columna = nombres_columnas[i]
                        
                        if nombre_columna == 'nombre':
                            info_lugar.append(f"LUGAR: {valor}")
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
                        else:
                            # Cualquier otra columna
                            info_lugar.append(f"{nombre_columna.upper()}: {valor}")
                
                # Unir toda la información del lugar
                if info_lugar:
                    context += " | ".join(info_lugar) + "\n"
        else:
            context += "No hay datos disponibles en la base de datos."
        
        # Agregar información de las imágenes si existen
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM locacion_imagenes")
                total_imagenes = cursor.fetchone()[0]
                if total_imagenes > 0:
                    context += f"\nIMÁGENES DISPONIBLES: {total_imagenes} imágenes asociadas a lugares."
                conn.close()
        except:
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

@app.route('/api/chat', methods=['POST'])
def chat():
    global daily_requests
    start_time = datetime.now()
    user_message = request.json.get('message', '')
    stream_mode = request.json.get('stream', False)
    
    # Obtener ID del usuario
    user_id = get_user_id()
    
    # Verificar límite diario
    if daily_requests >= MAX_DAILY_REQUESTS:
        response_time = (datetime.now() - start_time).total_seconds()
        system_info['total_requests'] += 1
        system_info['response_times'].append(response_time)
        return jsonify({'response': '⚠️ Hemos alcanzado el límite diario de consultas. Por favor, intenta nuevamente mañana o prueba con preguntas similares que ya hayan sido respondidas.'})
    
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
                yield f"data: {json.dumps({'chunk': '', 'done': True})}\n\n"
            return Response(generate_simple(), mimetype='text/event-stream')
        else:
            return jsonify({'response': simple_response})
    
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
        
        if stream_mode:
            # Devolver respuesta en caché en modo streaming
            def generate_cached():
                chunks = cached_response.split()
                for chunk in chunks:
                    json_data = json.dumps({'chunk': chunk + ' ', 'done': False})
                    yield f"data: {json_data}\n\n"
                yield f"data: {json.dumps({'chunk': '', 'done': True})}\n\n"
            return Response(generate_cached(), mimetype='text/event-stream')
        else:
            return jsonify({'response': cached_response})
    
    # Obtener contexto real de la base de datos y conversación
    db_context = get_database_context()
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
    
    # Si no hay datos reales disponibles, no invocar al modelo y responder seguro
    if not lugares_reales:
        safe_msg = (
            'Ahora mismo no dispongo de información del catálogo de lugares para responder con datos reales. '
            'Por favor, intenta más tarde o vuelve a consultar cuando el catálogo esté disponible.'
        )
        add_to_conversation(user_id, user_message, True)
        add_to_conversation(user_id, safe_msg, False)
        if stream_mode:
            def generate_no_data():
                for chunk in safe_msg.split():
                    json_data = json.dumps({'chunk': chunk + ' ', 'done': False})
                    yield f"data: {json_data}\n\n"
                yield f"data: {json.dumps({'chunk': '', 'done': True})}\n\n"
            return Response(generate_no_data(), mimetype='text/event-stream')
        else:
            return jsonify({'response': safe_msg})

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

INSTRUCCIONES DE FORMATO:
- Usa **negritas** para resaltar lugares importantes y categorías
- Organiza la información en párrafos separados (presiona ENTER dos veces)
- Usa listas con viñetas (*) para enumerar opciones o lugares
- Incluye saltos de línea reales entre secciones (no escribas \\n)
- Mantén un tono conversacional y amigable
- NO uses \\n ni caracteres de escape, usa saltos de línea reales
- IMPORTANTE: Cada nombre de lugar que menciones DEBE ir exactamente entre [[ y ]], por ejemplo: [[Cerrito de la Libertad]]. SOLO puedes encerrar entre [[ ]] nombres de lugares que existan en el contexto.
- Si el usuario pregunta por un lugar que no aparece en el contexto, responde claramente que NO hay información al respecto y no inventes nada.

RESPONDE ÚNICAMENTE BASÁNDOTE EN LOS DATOS REALES DEL CONTEXTO. IMPORTANTE: NO MENCIONES PROBLEMAS TÉCNICOS NI DE CONEXIÓN."""

    try:
        daily_requests += 1
        
        if stream_mode:
            # Modo streaming con mejor manejo de tiempos
            def generate():
                try:
                    response_stream = model.generate_content(prompt, stream=True)
                    chunk_count = 0
                    max_chunks = 150  # Aumentar límite para respuestas más largas
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
                    
                    cache_response(user_message, respuesta_validada)
                    add_to_conversation(user_id, user_message, True)
                    add_to_conversation(user_id, respuesta_validada, False)
                    
                    yield f"data: {json.dumps({'chunk': '', 'done': True})}\n\n"
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
            
            cache_response(user_message, respuesta_validada)
            
            # Guardar en memoria conversacional
            add_to_conversation(user_id, user_message, True)
            add_to_conversation(user_id, respuesta_validada, False)
            
            return jsonify({'response': respuesta_validada})
    except Exception as e:
        error_msg = f'Error al procesar la consulta: {str(e)}'
        if "quota" in str(e).lower() or "429" in str(e):
            error_msg = '⚠️ Límite de consultas alcanzado. Intenta con preguntas similares a las anteriores.'
        return jsonify({'response': error_msg})

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
    
    # Extraer información detallada de cada lugar
    lineas = db_context.split('\n')
    lugares_detallados = []
    
    for linea in lineas:
        if 'LUGAR:' in linea and '|' in linea:
            partes = linea.split('|')
            if len(partes) >= 3:
                nombre = partes[0].replace('LUGAR:', '').strip()
                ubicacion = partes[1].strip()
                descripcion = partes[2].strip()
                lugares_detallados.append({
                    'nombre': nombre,
                    'ubicacion': ubicacion,
                    'descripcion': descripcion
                })
    
    # Mostrar lugares con detalles
    for lugar in lugares_detallados[:4]:  # Mostrar 4 lugares con detalles
        respuesta_real += f"**{lugar['nombre']}** - {lugar['descripcion']}\n"
        respuesta_real += f"📍 Ubicación: {lugar['ubicacion']}\n\n"
    
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