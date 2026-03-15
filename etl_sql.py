import pandas as pd
from sqlalchemy import text
from database import engine_sql_server, engine_local, SessionLocalDB
from models import RawVentas2026


def extraer_datos_sql():
    print("[OK] Iniciando extraccion de VENTAS (Base Principal - Tabla: Detalle)...")
    
    # Consulta optimizada para la tabla Detalle
    query_ventas = """
    SELECT 
        LTRIM(RTRIM(CAST(Co AS VARCHAR(50)))) AS StoreID, 
        CAST(FechaDocto AS DATE) AS Fecha, 
        CAST(VlrBruto AS FLOAT) AS VlrBruto, 
        CAST(VlrTotalDesc AS FLOAT) AS VlrTotalDesc
    FROM Detalle
    WHERE FechaDocto >= '2026-01-01' AND FechaDocto < '2027-01-01'
    """
    
    try:
        print("--> Ejecutando consulta en SQL Server...")
        df_ventas = pd.read_sql(query_ventas, con=engine_sql_server)
        print(f"OK Se extrajeron {len(df_ventas)} registros de items.")
        
        # Limpieza de nulos y estandarización de StoreID (igual que en app.py / MAPEO_SEDES)
        df_ventas = df_ventas.dropna(subset=['StoreID', 'Fecha'])
        df_ventas['StoreID'] = df_ventas['StoreID'].astype(str).str.strip().str.upper()
        # Normalizar: quitar ceros a la izquierda; si es numérico (ej. 201.0) dejar solo dígitos sin .0
        def _norm_store_id(s):
            s = str(s).strip().upper().lstrip('0') or '0'
            try:
                return str(int(float(s)))  # 201.0 -> 201, 0201 -> 201
            except (ValueError, TypeError):
                return s  # F04, F08, etc. se quedan igual
        df_ventas['StoreID'] = df_ventas['StoreID'].apply(_norm_store_id)
        # Si Detalle trae nombre de sede en vez de código, mapear a código (Medellín, Plaza Claro, Cafam)
        ALIAS_A_CODIGO = {
            "MEDELLIN": "201", "MEDELLÍN": "201",
            "PLAZA CLARO": "F04", "PLAZACLARO": "F04",
            "CAFAM": "611",
        }
        def _a_codigo(x):
            k = str(x).strip().upper().replace("  ", " ")
            # Quitar tildes para que "MEDELLÍN" y "MEDELLIN" coincidan
            for old, new in [("Í", "I"), ("É", "E"), ("Á", "A"), ("Ó", "O"), ("Ú", "U"), ("Ñ", "N")]:
                k = k.replace(old, new)
            return ALIAS_A_CODIGO.get(k, x)
        df_ventas['StoreID'] = df_ventas['StoreID'].apply(_a_codigo)
        
        # Forzado numérico para evitar errores de concatenación
        df_ventas['VlrBruto'] = pd.to_numeric(df_ventas['VlrBruto'], errors='coerce').fillna(0.0)
        df_ventas['VlrTotalDesc'] = pd.to_numeric(df_ventas['VlrTotalDesc'], errors='coerce').fillna(0.0)
        
        # Consolidación matemática por Sede y Fecha (Flash Diario)
        print("Consolidando ventas diarias...")
        df_diario = df_ventas.groupby(['StoreID', 'Fecha'], as_index=False).agg({
            'VlrBruto': 'sum',
            'VlrTotalDesc': 'sum'
        })
        
        # Limpieza de la tabla local antes de la carga
        with SessionLocalDB() as session:
            session.execute(text("DELETE FROM raw_ventas_2026"))
            session.commit()
            
        # Carga a SQLite
        df_diario.to_sql('raw_ventas_2026', con=engine_local, if_exists='append', index=False)
        print(f"OK Ventas cargadas en SQLite ({len(df_diario)} registros diarios).")
        
    except Exception as e:
        print(f"Error critico en ETL de Ventas: {e}")

    print("\nProceso de ventas finalizado.")

if __name__ == "__main__":
    extraer_datos_sql()