"""
Cliente de base de datos con integración de Google Gemini
Implementación alternativa a ToolFront usando SQLAlchemy y Google Generative AI
"""

import os
import sqlite3
from typing import Optional, List, Dict, Any
import google.generativeai as genai
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

class DatabaseClient:
    """Cliente de base de datos con capacidades de IA"""
    
    def __init__(self, 
                 db_url: Optional[str] = None,
                 google_api_key: Optional[str] = None):
        """
        Inicializar el cliente de base de datos
        
        Args:
            db_url: URL de conexión a la base de datos
            google_api_key: Clave de API de Google Gemini
        """
        self.db_url = db_url or os.getenv('DATABASE_URL', 'sqlite:///data/sample.db')
        self.google_api_key = google_api_key or os.getenv('GOOGLE_API_KEY')
        
        if not self.google_api_key:
            raise ValueError("Debes proporcionar google_api_key o definir GOOGLE_API_KEY en .env")
        
        # Configurar Google Gemini
        genai.configure(api_key=self.google_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        
        # Configurar conexión a base de datos
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
    def get_schema_info(self) -> str:
        """Obtener información del esquema de la base de datos"""
        inspector = inspect(self.engine)
        
        schema_info = []
        schema_info.append("=== Esquema de la Base de Datos ===")
        
        tables = inspector.get_table_names()
        for table in tables:
            schema_info.append(f"\nTabla: {table}")
            columns = inspector.get_columns(table)
            for col in columns:
                schema_info.append(f"  - {col['name']}: {col['type']}")
        
        return "\n".join(schema_info)
    
    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Ejecutar una consulta SQL y devolver resultados"""
        try:
            with self.Session() as session:
                result = session.execute(text(sql))
                if result.returns_rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in result.fetchall()]
                else:
                    session.commit()
                    return [{"message": f"Consulta ejecutada exitosamente. Filas afectadas: {result.rowcount}"}]
        except Exception as e:
            return [{"error": str(e)}]
    
    def ask_question(self, question: str, context: Optional[str] = None) -> str:
        """
        Convertir una pregunta en lenguaje natural a SQL y ejecutarla
        
        Args:
            question: Pregunta en lenguaje natural
            context: Contexto adicional sobre la base de datos
            
        Returns:
            Respuesta en lenguaje natural
        """
        
        # Obtener contexto de la base de datos
        db_context = self.get_schema_info()
        
        # Crear prompt para Gemini
        prompt = f"""
        Eres un experto en SQL y bases de datos. Tienes acceso a la siguiente base de datos:

        {db_context}

        Contexto adicional: {context or 'Base de datos de e-commerce con usuarios, productos, pedidos y categorías.'}

        Pregunta del usuario: {question}

        Por favor:
        1. Genera una consulta SQL apropiada para responder esta pregunta
        2. Ejecuta la consulta (asumo que tienes acceso a los datos)
        3. Proporciona una respuesta clara y concisa en español

        Responde SOLO con la respuesta final en lenguaje natural. No incluyas la consulta SQL.
        """
        
        try:
            response = self.model.generate_content(prompt)
            
            # Extraer SQL de la respuesta (implementación básica)
            sql_start = response.text.find('```sql')
            sql_end = response.text.find('```', sql_start + 6) if sql_start != -1 else -1
            
            if sql_start != -1 and sql_end != -1:
                sql_query = response.text[sql_start + 6:sql_end].strip()
                
                # Ejecutar la consulta
                results = self.execute_query(sql_query)
                
                if results and 'error' not in results[0]:
                    # Crear respuesta basada en resultados
                    if len(results) == 1 and isinstance(results[0], dict):
                        # Resultado único
                        return str(list(results[0].values())[0])
                    elif len(results) > 1:
                        # Múltiples resultados
                        return f"Encontré {len(results)} resultados."
                    else:
                        return "No se encontraron resultados."
                else:
                    return response.text
            else:
                return response.text
                
        except Exception as e:
            return f"Error al procesar la pregunta: {str(e)}"
    
    def get_sample_queries(self) -> List[str]:
        """Obtener ejemplos de consultas útiles"""
        return [
            "¿Cuántos usuarios están registrados?",
            "¿Cuál es el producto más caro?",
            "¿Cuántos pedidos se han realizado?",
            "¿Qué categoría tiene más productos?",
            "¿Cuál es el ingreso total de todos los pedidos?",
            "¿Qué productos tienen menos de 10 unidades en stock?",
            "¿Cuál es el usuario que más ha gastado?",
            "¿Cuántos pedidos se hicieron este mes?"
        ]
    
    def test_connection(self) -> bool:
        """Probar la conexión a la base de datos"""
        try:
            with self.Session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            print(f"Error de conexión: {e}")
            return False

class SimpleDatabaseQuery:
    """Versión simplificada para SQLite directo"""
    
    def __init__(self, db_path: str = "data/sample.db", context: str = ""):
        self.db_path = db_path
        self.context = context
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        
        if not self.google_api_key:
            raise ValueError("Debes definir GOOGLE_API_KEY en .env")
        
        genai.configure(api_key=self.google_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
    
    def get_schema(self) -> str:
        """Obtener información del esquema de la base de datos"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Obtener todas las tablas
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                
                schema_info = []
                for table in tables:
                    table_name = table[0]
                    if table_name != 'sqlite_sequence':  # Ignorar tabla del sistema
                        cursor.execute(f"PRAGMA table_info({table_name})")
                        columns = cursor.fetchall()
                        
                        column_info = []
                        for col in columns:
                            column_name = col[1]
                            column_type = col[2]
                            is_null = "NULL" if col[3] == 0 else "NOT NULL"
                            column_info.append(f"{column_name} {column_type} {is_null}")
                        
                        schema_info.append(f"Tabla {table_name}:\n" + 
                                         "  " + ", ".join(column_info))
                
                return "\n\n".join(schema_info)
                
        except Exception as e:
            return f"Error al obtener esquema: {str(e)}"
    
    def get_table_info(self) -> str:
        """Alias para get_schema"""
        return self.get_schema()

    def ask_question(self, question: str) -> str:
        """Hacer una pregunta en lenguaje natural"""
        
        # Obtener información de la base de datos
        db_info = self.get_table_info()
        
        prompt = f"""
        Tienes acceso a esta base de datos SQLite:

        {db_info}

        La base de datos contiene información de e-commerce con usuarios, productos, pedidos y categorías.

        Pregunta: {question}

        Por favor, proporciona una respuesta clara y concisa en español basándote en los datos disponibles.
        Si necesitas ejecutar una consulta SQL, proporciona la respuesta directamente.
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

    def ask(self, question: str) -> str:
        """Convertir pregunta en lenguaje natural a SQL y ejecutar"""
        try:
            # Obtener esquema de la base de datos
            schema = self.get_schema()
            
            # Crear prompt para Google Gemini
            prompt = f"""
            Eres un experto en SQL. Convierte la siguiente pregunta en una consulta SQL válida.
            
            Pregunta: {question}
            
            Esquema de la base de datos:
            {schema}
            
            Instrucciones:
            1. Genera solo la consulta SQL, sin explicaciones
            2. Usa nombres de tabla y columnas exactamente como aparecen en el esquema
            3. La consulta debe ser válida para SQLite
            4. Si la pregunta requiere agregaciones, usa funciones como COUNT, SUM, MAX, etc.
            5. Si no puedes generar una consulta, retorna "SELECT 'No puedo generar una consulta para esta pregunta' as error"
            
            Consulta SQL:"""
            
            # Generar consulta SQL con Google Gemini
            response = self.model.generate_content(prompt)
            sql_query = response.text.strip()
            
            # Eliminar marcadores de código si los hay
            sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
            
            # Limpiar la consulta SQL
            if sql_query.startswith('```sql'):
                sql_query = sql_query[6:]
            if sql_query.endswith('```'):
                sql_query = sql_query[:-3]
            sql_query = sql_query.strip()
            
            # Ejecutar la consulta
            results = self._execute_query(sql_query)
            
            # Formatear resultados
            if results and 'error' in results[0]:
                return f"Error: {results[0]['error']}"
            elif results:
                return self._format_results(results)
            else:
                return "No se encontraron resultados"
                
        except Exception as e:
            return f"Error al procesar la pregunta: {str(e)}"

    def _execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """Ejecutar una consulta SQL y retornar resultados"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(sql)
                
                # Si es una consulta SELECT, retornar resultados
                if sql.strip().upper().startswith('SELECT'):
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]
                else:
                    # Para INSERT, UPDATE, DELETE
                    conn.commit()
                    return [{"message": f"{cursor.rowcount} filas afectadas"}]
                    
        except Exception as e:
            return [{"error": str(e)}]

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """Formatear los resultados de manera legible"""
        if not results:
            return "No se encontraron resultados"
        
        if len(results) == 1:
            # Un solo resultado
            result = results[0]
            if len(result) == 1:
                # Un solo valor
                return str(list(result.values())[0])
            else:
                # Múltiples columnas
                return ", ".join([f"{k}: {v}" for k, v in result.items()])
        else:
            # Múltiples resultados
            formatted = []
            for i, result in enumerate(results[:5]):  # Limitar a 5 resultados
                formatted.append(", ".join([f"{k}: {v}" for k, v in result.items()]))
            
            output = "\n".join(formatted)
            if len(results) > 5:
                output += f"\n... y {len(results) - 5} resultados más"
            
            return output