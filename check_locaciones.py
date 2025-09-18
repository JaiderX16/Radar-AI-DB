import mysql.connector
from config import DATABASE_CONFIG as DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor(dictionary=True)

cursor.execute('SELECT * FROM locaciones')
locaciones = cursor.fetchall()
print('Locaciones disponibles:')
for loc in locaciones:
    print(f"ID: {loc['id']} - Nombre: {loc['nombre']} - Descripción: {loc['descripcion']}")

cursor.close()
conn.close()