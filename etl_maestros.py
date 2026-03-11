import pandas as pd
from sqlalchemy import text, func
from database import engine_sql_server_sec, engine_local, SessionLocalDB
from models import DimStore, DimItemGroup, DimItemFamily, DimMenuItem, RawInvoice2026

def extraer_maestros():
    print("Iniciando extracción desde base de datos secundaria (NEWACRVentas)...\n")
    
    tablas_maestras = {
        'Store': 'dim_store',
        'ItemGroup': 'dim_item_group',
        'ItemFamily': 'dim_item_family',
        'MenuItem': 'dim_menu_item'
    }
    
    # 1. Extraer los catálogos completos (Full Load por seguridad de cambios de nombre)
    for tabla_origen, tabla_destino in tablas_maestras.items():
        print(f"Extrayendo tabla maestra: {tabla_origen} (Carga Completa)...")
        try:
            query = f"SELECT * FROM {tabla_origen}"
            df = pd.read_sql(query, con=engine_sql_server_sec)
            
            if tabla_origen == 'Store':
                df = df.dropna(subset=['StoreID']).drop_duplicates(subset=['StoreID'])
            elif tabla_origen == 'ItemGroup':
                df = df.dropna(subset=['StoreID', 'GroupID']).drop_duplicates(subset=['StoreID', 'GroupID'])
            elif tabla_origen == 'ItemFamily':
                df = df.dropna(subset=['storeID', 'FamilyID']).drop_duplicates(subset=['storeID', 'FamilyID'])
            elif tabla_origen == 'MenuItem':
                df = df.dropna(subset=['storeID', 'MenuItemID']).drop_duplicates(subset=['storeID', 'MenuItemID'])

            with SessionLocalDB() as session:
                session.execute(text(f"DELETE FROM {tabla_destino}"))
                session.commit()
                
            df.to_sql(tabla_destino, con=engine_local, if_exists='append', index=False)
            print(f"  -> OK Cargados {len(df)} registros.")
            
        except Exception as e:
            print(f"  -> Error en {tabla_origen}: {e}")

    # 2. Extraer tabla transaccional Invoice (Carga Incremental)
    print("\nExtrayendo tabla transaccional: Invoice...")
    
    with SessionLocalDB() as session:
        max_fecha_inv = session.query(func.max(RawInvoice2026.BusinessDate)).scalar()
        
        if max_fecha_inv is None:
            print("No se encontraron Invoices previos. Se hará carga inicial desde 2026-01-01.")
            fecha_inicio_inv = '2026-01-01'
        else:
            fecha_inicio_inv = max_fecha_inv.strftime('%Y-%m-%d')
            print(f"Última fecha de Invoice detectada: {fecha_inicio_inv}. Iniciando carga incremental...")
            # Borrar el último día por seguridad
            session.execute(text(f"DELETE FROM raw_invoice_2026 WHERE BusinessDate >= '{fecha_inicio_inv}'"))
            session.commit()

    try:
        query_invoice = f"""
        SELECT * FROM Invoice 
        WHERE BusinessDate >= '{fecha_inicio_inv}' AND BusinessDate < '2027-01-01'
        """
        df_invoice = pd.read_sql(query_invoice, con=engine_sql_server_sec)
        
        if df_invoice.empty:
            print("OK Los Invoices ya estan 100% al dia.")
        else:
            df_invoice = df_invoice.dropna(subset=['InvoiceID', 'StoreID'])
            df_invoice = df_invoice.drop_duplicates(subset=['InvoiceID', 'StoreID'])
            
            df_invoice.to_sql('raw_invoice_2026', con=engine_local, if_exists='append', index=False)
            print(f"OK Se agregaron {len(df_invoice)} Invoices nuevos/actualizados.")
        
    except Exception as e:
        print(f"Error al procesar Invoice: {e}")

    print("\nProceso finalizado.")

if __name__ == "__main__":
    extraer_maestros()