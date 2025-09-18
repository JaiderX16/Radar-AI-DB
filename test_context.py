import mysql.connector
from config import DATABASE_CONFIG as DB_CONFIG

def test_context():
    """Verificar qué información se envía al contexto"""
    try:
        # Conectar a la base de datos
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Obtener lugares
        cursor.execute("SELECT * FROM locaciones ORDER BY nombre")
        lugares = cursor.fetchall()
        
        # Obtener columnas de locaciones
        cursor.execute("DESCRIBE locaciones")
        columnas_info = cursor.fetchall()
        nombres_columnas = [col[0] for col in columnas_info]
        
        print(f"=== LUGARES ENCONTRADOS: {len(lugares)} ===\n")
        
        # Obtener imágenes con nombres de lugares
        cursor.execute("""
            SELECT l.nombre, li.url_imagen, li.descripcion 
            FROM locacion_imagenes li
            JOIN locaciones l ON li.locacion_id = l.id
            ORDER BY l.nombre
        """)
        imagenes = cursor.fetchall()
        
        print(f"=== IMÁGENES ENCONTRADAS: {len(imagenes)} ===\n")
        
        # Mostrar imágenes por lugar
        imagenes_por_lugar = {}
        for nombre, url_imagen, descripcion in imagenes:
            if nombre not in imagenes_por_lugar:
                imagenes_por_lugar[nombre] = []
            imagenes_por_lugar[nombre].append({
                'url': url_imagen,
                'descripcion': descripcion or 'Imagen del lugar'
            })
        
        # Construir contexto como lo hace la función original
        context = f"BASE DE DATOS HUANCAYO - {len(lugares)} lugares encontrados:\n\n"
        
        # Agregar información de imágenes al contexto
        if imagenes_por_lugar:
            context += f"\nIMÁGENES DISPONIBLES: {len(imagenes)} imágenes asociadas a lugares.\n"
            
            for lugar, imgs in imagenes_por_lugar.items():
                context += f"IMAGENES_{lugar.upper().replace(' ', '_')}: "
                for img in imgs:
                    context += f"[URL: {img['url']}, DESC: {img['descripcion']}] "
                context += "\n"
        
        print("=== CONTEXTO GENERADO ===")
        print(context)
        
        # Mostrar formato de imágenes para Markdown
        print("\n=== FORMATO MARKDOWN PARA IMÁGENES ===")
        for lugar, imgs in imagenes_por_lugar.items():
            print(f"\n{lugar}:")
            for img in imgs:
                markdown_format = f"![{img['descripcion']}]({img['url']})"
                print(f"  {markdown_format}")
        
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_context()