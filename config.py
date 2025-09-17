import os

# Configuración de la base de datos XAMPP
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',  # Cambia si tienes contraseña
    'database': 'huancayo_db',
    'charset': 'utf8mb4'
}

# Si necesitas cambiar las credenciales, edita estas variables
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'huancayo_db')