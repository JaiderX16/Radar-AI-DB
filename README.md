# 🚀 Sistema de Consultas Inteligentes a Base de Datos con IA

Un proyecto completo que permite hacer consultas en lenguaje natural a bases de datos utilizando modelos de IA avanzados como Google Gemini.

## 📋 Características

- ✅ **Consultas en lenguaje natural** - Pregunta a tu base de datos como si hablaras con una persona
- 🎯 **Soporte para múltiples modelos de IA** - OpenAI, Anthropic, Google, xAI
- 🗄️ **Compatibilidad con múltiples bases de datos** - PostgreSQL, MySQL, SQLite, Snowflake
- 📊 **Ejemplos prácticos** - Base de datos de e-commerce incluida
- ⚙️ **Configuración flexible** - Variables de entorno y parámetros personalizables
- 🔍 **Análisis de esquemas** - Descubre la estructura de tu base de datos

## 🚀 Instalación Rápida

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Configurar variables de entorno (opcional)
El proyecto ya viene configurado con valores predeterminados, pero puedes personalizarlo:
```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

### 3. Ejecutar la aplicación
```bash
python app_gemini.py
```

### 4. Acceder a la aplicación
Abre tu navegador y visita: http://127.0.0.1:5000

## ⚙️ Configuración

### Variables de entorno necesarias

Edita el archivo `.env` con tus configuraciones:

```env
# Base de datos
DATABASE_URL=sqlite:///data/sample.db
# O para PostgreSQL:
# DATABASE_URL=postgresql://usuario:contraseña@localhost:5432/mi_db

# Modelo de IA
AI_MODEL=openai:gpt-4o

# Claves de API (obtén tus propias claves)
OPENAI_API_KEY=tu_clave_aqui
ANTHROPIC_API_KEY=tu_clave_aqui
GOOGLE_API_KEY=tu_clave_aqui
```

### Modelos de IA disponibles

| Proveedor | Modelo | Costo | Velocidad | Recomendado |
|-----------|--------|-------|-----------|-------------|
| OpenAI | gpt-4o | Alto | Rápido | ✅ |
| OpenAI | gpt-4o-mini | Medio | Muy rápido | ✅ |
| Anthropic | claude-3-5-sonnet | Medio | Rápido | ✅ |
| Anthropic | claude-3-5-haiku | Bajo | Muy rápido | ✅ |
| Google | gemini-pro | Medio | Rápido | ✅ |

## 🎯 Uso Básico

### 1. Usar la base de datos de ejemplo

```python
from src.database_query import DatabaseQuerySystem

# Crear instancia con base de datos de ejemplo
system = DatabaseQuerySystem(
    db_url="sqlite:///data/sample.db",
    model="openai:gpt-4o"
)

# Hacer consultas
resultado = system.ask_question("¿Cuántos usuarios están registrados?")
print(resultado)  # "8 usuarios registrados"

resultado = system.ask_question("¿Cuál es el producto más vendido?")
print(resultado)  # "iPhone 15 con 15 unidades vendidas"
```

### 2. Usar con tu propia base de datos

```python
from src.database_query import DatabaseQuerySystem

# PostgreSQL
system = DatabaseQuerySystem(
    db_url="postgresql://user:pass@localhost:5432/mydb",
    model="anthropic:claude-3-5-sonnet",
    context="Base de datos de mi empresa con información de..."
)

# MySQL
system = DatabaseQuerySystem(
    db_url="mysql://user:pass@localhost:3306/mydb",
    model="google:gemini-pro"
)
```

### 3. Consultas avanzadas

```python
# Múltiples consultas
preguntas = [
    "¿Cuántos pedidos se realizaron este mes?",
    "¿Cuál es el ingreso total?",
    "¿Qué productos tienen bajo stock?"
]

resultados = system.run_batch_queries(preguntas)

# Obtener información del esquema
schema = system.get_schema_info()
print(schema)
```

## 📊 Ejemplos de Consultas

### Base de datos de e-commerce incluida

La base de datos de ejemplo incluye:
- **8 usuarios** con información básica
- **5 categorías** de productos
- **15 productos** con precios y stock
- **50 pedidos** con fechas variadas
- **Items de pedidos** generados automáticamente

### Consultas de ejemplo que puedes hacer:

```python
# Análisis de usuarios
"¿Cuántos usuarios se registraron en los últimos 30 días?"
"¿Quién es el usuario que más ha gastado?"

# Análisis de productos
"¿Cuáles son los 5 productos más caros?"
"¿Qué productos tienen menos de 20 unidades en stock?"

# Análisis de ventas
"¿Cuál fue el día con más ventas?"
"¿Cuánto dinero se ha generado en total?"
"¿Cuál es la categoría más popular?"

# Análisis temporal
"¿Cómo han sido las ventas por mes?"
"¿En qué día de la semana se hacen más pedidos?"
```

## 🔧 Configuración Avanzada

### Cambiar modelo de IA dinámicamente

```python
from config.ai_models import AIModelConfig

# Ver modelos disponibles
AIModelConfig.print_available_models()

# Usar modelo específico
system = DatabaseQuerySystem(
    db_url="sqlite:///data/sample.db",
    model="anthropic:claude-3-5-sonnet"
)
```

### Personalizar contexto

```python
contexto = """
Mi base de datos es de una tienda de música.
Tablas principales:
- albums: id, titulo, artista_id, fecha_lanzamiento, precio
- artistas: id, nombre, genero
- ventas: id, album_id, fecha, cantidad
"""

system = DatabaseQuerySystem(
    db_url="sqlite:///data/musica.db",
    context=contexto
)
```

## 🐛 Solución de Problemas

### Error: "No se puede conectar a la base de datos"
- Verifica que la URL de conexión sea correcta
- Asegúrate de que el servidor de base de datos esté ejecutándose
- Para PostgreSQL/MySQL, verifica credenciales y permisos

### Error: "Clave de API no válida"
- Obtén una clave válida del proveedor correspondiente
- Verifica que la clave esté correctamente configurada en `.env`
- Asegúrate de tener saldo disponible en tu cuenta

### Error: "Modelo no encontrado"
- Verifica que el modelo esté en la lista de disponibles
- Usa el formato correcto: `proveedor:modelo`
- Ejecuta `python config/ai_models.py` para ver modelos disponibles

## 📁 Estructura del Proyecto

```
IA + DB/
├── src/
│   └── database_query.py      # Sistema principal de consultas
├── config/
│   └── ai_models.py          # Configuración de modelos de IA
├── examples/
│   └── create_sample_db.py   # Script para crear base de datos de ejemplo
├── data/
│   └── sample.db            # Base de datos de ejemplo (se crea al ejecutar)
├── requirements.txt          # Dependencias del proyecto
├── .env.example             # Ejemplo de configuración
└── README.md               # Este archivo
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver el archivo `LICENSE` para más detalles.

## 🔗 Recursos Adicionales

- [Documentación oficial de ToolFront](https://docs.toolfront.ai)
- [Repositorio GitHub de ToolFront](https://github.com/kruskal-labs/toolfront)
- [API de OpenAI](https://platform.openai.com/docs)
- [API de Anthropic](https://docs.anthropic.com/)
- [API de Google Gemini](https://ai.google.dev/)

## 🆘 Soporte

Si tienes problemas o preguntas:
1. Revisa la sección de solución de problemas
2. Verifica que todas las dependencias estén instaladas
3. Asegúrate de tener las claves de API configuradas
4. Prueba con la base de datos de ejemplo primero

¡Disfruta consultando tu base de datos con inteligencia artificial! 🎉