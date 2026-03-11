import pandas as pd
from database import engine_sql_server

def ver_columnas():
    print("Conectando a SQL Server para leer la estructura de la tabla 'Detalle'...")
    
    # Traemos solo 1 registro para ver la estructura sin sobrecargar
    query = "SELECT TOP 1 * FROM Detalle"
    
    try:
        df = pd.read_sql(query, con=engine_sql_server)
        print("\n✅ Conexión exitosa. Las columnas disponibles en la tabla 'Detalle' son:\n")
        
        for columna in df.columns:
            print(f"- {columna}")
            
    except Exception as e:
        print(f"❌ Error al consultar la tabla: {e}")

if __name__ == "__main__":
    ver_columnas()