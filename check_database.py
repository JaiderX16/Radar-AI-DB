import mysql.connector
from config import DATABASE_CONFIG as DB_CONFIG

def check_database():
    try:
        # Conectar a la base de datos
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        print("=== VERIFICANDO BASE DE DATOS ===\n")
        
        # Verificar qué tablas hay
        cursor.execute('SHOW TABLES')
        tables = cursor.fetchall()
        print('Tablas disponibles:')
        for table in tables:
            table_name = list(table.values())[0]
            print(f'- {table_name}')
        
        print('\n' + '='*50)
        
        # Verificar si existe la tabla locacion_imagenes
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() 
            AND table_name = 'locacion_imagenes'
        """)
        result = cursor.fetchone()
        
        if result['count'] == 0:
            print("❌ La tabla 'locacion_imagenes' NO existe")
            return
        
        print("✅ La tabla 'locacion_imagenes' existe")
        
        # Verificar estructura de la tabla locacion_imagenes
        cursor.execute('DESCRIBE locacion_imagenes')
        columns = cursor.fetchall()
        print('\nEstructura de locacion_imagenes:')
        for col in columns:
            field_name = col['Field']
            field_type = col['Type']
            print(f'- {field_name}: {field_type}')
        
        print('\n' + '='*50)
        
        # Ver algunos registros de ejemplo
        cursor.execute('SELECT * FROM locacion_imagenes LIMIT 5')
        rows = cursor.fetchall()
        print('Ejemplos de registros:')
        for i, row in enumerate(rows):
            print(f'\nRegistro {i+1}:')
            for key, value in row.items():
                print(f'  {key}: {value}')
        
        # Verificar ubicaciones disponibles
        cursor.execute('SELECT DISTINCT ubicacion FROM locacion_imagenes ORDER BY ubicacion')
        ubicaciones = cursor.fetchall()
        print(f'\n=== UBICACIONES DISPONIBLES ({len(ubicaciones)}) ===')
        for ubi in ubicaciones:
            location_name = ubi['ubicacion']
            print(f'- {location_name}')
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_database()