import pandas as pd
from database import engine_sql_server_sec

def explorar_tablas_secundarias():
    tablas = ['Store', 'Invoice', 'MenuItem', 'ItemFamily', 'ItemGroup']
    
    print("Conectando a NEWACRVentas para leer la estructura de los maestros...\n")
    
    for tabla in tablas:
        print(f"--- Explorando tabla: {tabla} ---")
        query = f"SELECT TOP 1 * FROM {tabla}"
        try:
            df = pd.read_sql(query, con=engine_sql_server_sec)
            print("Columnas encontradas:")
            for col in df.columns:
                print(f"  - {col}")
            print("\n")
        except Exception as e:
            print(f"❌ Error al consultar la tabla {tabla}: {e}\n")

if __name__ == "__main__":
    explorar_tablas_secundarias()