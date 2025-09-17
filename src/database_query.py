#!/usr/bin/env python3
"""
Sistema de consultas inteligentes a base de datos usando IA
Este módulo permite hacer consultas en lenguaje natural a bases de datos
utilizando Google Gemini AI.
"""

import os
import sys
from typing import Optional, Dict, Any, List
from pathlib import Path

# Agregar el directorio padre al path para importaciones
sys.path.append(str(Path(__file__).parent.parent))

try:
    from src.database_client import SimpleDatabaseQuery
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Error al importar dependencias: {e}")
    print("Por favor instala las dependencias: py -m pip install -r requirements.txt")
    sys.exit(1)

# Cargar variables de entorno
load_dotenv()

class DatabaseQuerySystem:
    """
    Sistema principal para consultas inteligentes a base de datos
    """
    
    def __init__(self, 
                 db_url: Optional[str] = None,
                 model: str = "gemini-pro",
                 context: Optional[str] = None):
        """
        Inicializar el sistema de consultas
        
        Args:
            db_url: URL de conexión a la base de datos
            model: Modelo de IA a usar
            context: Contexto adicional sobre la base de datos
        """
        self.db_url = db_url or os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError(
                "Debes proporcionar db_url o definir DATABASE_URL en .env"
            )
        
        self.model = model
        self.context = context or self._get_default_context()
        self.db = None
        
    def _get_default_context(self) -> str:
        """Obtener contexto por defecto para la base de datos"""
        return """
        Esta es una base de datos de e-commerce con las siguientes tablas:
        
        1. users: id (INTEGER PRIMARY KEY), name (TEXT), email (TEXT), created_at (TIMESTAMP)
        2. categories: id (INTEGER PRIMARY KEY), name (TEXT), description (TEXT)
        3. products: id (INTEGER PRIMARY KEY), name (TEXT), price (REAL), stock (INTEGER), category_id (INTEGER), created_at (TIMESTAMP)
        4. orders: id (INTEGER PRIMARY KEY), user_id (INTEGER), order_date (TIMESTAMP), total (REAL), status (TEXT)
        5. order_items: id (INTEGER PRIMARY KEY), order_id (INTEGER), product_id (INTEGER), quantity (INTEGER), unit_price (REAL)
        
        Las relaciones son:
        - users.id -> orders.user_id
        - categories.id -> products.category_id  
        - orders.id -> order_items.order_id
        - products.id -> order_items.product_id
        """
    
    def connect(self) -> bool:
        """Conectar a la base de datos"""
        try:
            # Extraer la ruta del archivo para SQLite
            if self.db_url.startswith('sqlite:///'):
                db_path = self.db_url.replace('sqlite:///', '')
            else:
                db_path = self.db_url
                
            self.db = SimpleDatabaseQuery(db_path, self.context)
            print(f"✅ Conectado exitosamente a la base de datos")
            return True
        except Exception as e:
            print(f"❌ Error al conectar: {e}")
            return False
    
    def ask_question(self, question: str, verbose: bool = True) -> Optional[str]:
        """
        Hacer una pregunta en lenguaje natural a la base de datos
        
        Args:
            question: Pregunta en lenguaje natural
            verbose: Mostrar información adicional
            
        Returns:
            Respuesta de la base de datos
        """
        if not self.db:
            if not self.connect():
                return None
        
        try:
            if verbose:
                print(f"🤔 Pregunta: {question}")
                print(f"🤖 Usando modelo: {self.model}")
            
            # Realizar la consulta
            answer = self.db.ask(question)
            
            if verbose:
                print(f"✅ Respuesta: {answer}")
            
            return answer
            
        except Exception as e:
            error_msg = f"Error al procesar la pregunta: {e}"
            print(f"❌ {error_msg}")
            return None
    
    def get_schema_info(self) -> Optional[str]:
        """Obtener información del esquema de la base de datos"""
        if not self.db:
            if not self.connect():
                return None
        
        try:
            schema_info = self.db.ask("Muestra todas las tablas y sus columnas")
            return schema_info
        except Exception as e:
            print(f"Error al obtener esquema: {e}")
            return None
    
    def run_batch_queries(self, questions: List[str]) -> Dict[str, Any]:
        """Ejecutar múltiples consultas"""
        results = {}
        
        for i, question in enumerate(questions, 1):
            print(f"\n📊 Consulta {i}/{len(questions)}")
            answer = self.ask_question(question)
            results[question] = answer
        
        return results

def main():
    """Función principal de ejemplo"""
    print("🚀 Sistema de Consultas Inteligentes a Base de Datos")
    print("=" * 50)
    
    # Configuración de ejemplo
    config = {
        'db_url': os.getenv('DATABASE_URL', 'sqlite:///data/sample.db'),
        'model': os.getenv('AI_MODEL', 'openai:gpt-4o'),
        'context': """
        Base de datos de e-commerce con las siguientes tablas:
        - users: información de usuarios registrados
        - products: catálogo de productos con precios y stock
        - orders: pedidos realizados por los usuarios
        - order_items: detalles de cada pedido
        """
    }
    
    # Crear instancia del sistema
    try:
        query_system = DatabaseQuerySystem(**config)
        
        # Ejemplos de consultas
        sample_queries = [
            "¿Cuántos usuarios están registrados?",
            "¿Cuál es el producto más vendido?",
            "¿Cuál es el ingreso total de todos los pedidos?",
            "¿Cuántos pedidos se realizaron este mes?",
            "¿Cuáles son los productos con menos de 10 unidades en stock?"
        ]
        
        print("Ejecutando consultas de ejemplo...")
        results = query_system.run_batch_queries(sample_queries)
        
        print("\n📋 Resumen de resultados:")
        print("-" * 30)
        for question, answer in results.items():
            print(f"Q: {question}")
            print(f"A: {answer}")
            print("-" * 30)
            
    except Exception as e:
        print(f"Error en la ejecución principal: {e}")

if __name__ == "__main__":
    main()