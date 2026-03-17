import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text, func
from database import engine_sql_server_sec, engine_local, SessionLocalDB
from models import DimStore, DimItemGroup, DimItemFamily, DimMenuItem, RawInvoice2026

# Re-traer siempre los últimos N días de Invoice para que "ayer" no quede incompleto
INVOICE_RELOAD_DAYS = 2
INICIO_2026 = date(2026, 1, 1)

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
            # Re-traer últimos N días para que "ayer" no quede con transacciones incompletas
            max_date = max_fecha_inv.date() if hasattr(max_fecha_inv, 'date') else max_fecha_inv
            desde = max_date - timedelta(days=INVOICE_RELOAD_DAYS)
            fecha_inicio_inv = max(desde, INICIO_2026).strftime('%Y-%m-%d')
            print(f"Última fecha de Invoice: {max_date}. Re-cargando desde {fecha_inicio_inv} (últimos {INVOICE_RELOAD_DAYS} días)...")
            session.execute(text(f"DELETE FROM raw_invoice_2026 WHERE BusinessDate >= '{fecha_inicio_inv}'"))
            session.commit()

    try:
        # 2.a) Traer detalle de Invoice (como antes) a raw_invoice_2026
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
            print(f"OK Se agregaron {len(df_invoice)} Invoices nuevos/actualizados en raw_invoice_2026.")

        # 2.b) Tabla venta por hora. La hora se calcula EN SQL con DATEPART (no depende del driver).
        print("\nCalculando venta horaria (Invoice → venta_horaria_2026)...")
        query_invoice_hora = f"""
        SELECT
            StoreID,
            CAST(BusinessDate AS DATE) AS BusinessDate,
            DATEPART(HOUR, Transaction_Date) AS Hora,
            CheckSubTotal
        FROM Invoice
        WHERE BusinessDate >= '{fecha_inicio_inv}' AND BusinessDate < '2027-01-01'
          AND InvoiceID IS NOT NULL
        ORDER BY StoreID, BusinessDate, Transaction_Date
        """
        df_inv = pd.read_sql(query_invoice_hora, con=engine_sql_server_sec)
        # Crear tabla siempre (así la app no falla si no se ha corrido el ETL o no hay datos)
        with SessionLocalDB() as session:
            try:
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS venta_horaria_2026 (
                        StoreID VARCHAR(50), BusinessDate DATE, Hora INTEGER,
                        Venta_Hora FLOAT, Transacciones_Hora INTEGER
                    )
                """))
                session.commit()
            except Exception:
                pass
            session.execute(text(f"DELETE FROM venta_horaria_2026 WHERE BusinessDate >= '{fecha_inicio_inv}'"))
            session.commit()

        if df_inv.empty:
            print("No hay filas Invoice para generar venta_horaria_2026 (tabla creada vacía).")
        else:
            df_inv["Hora"] = pd.to_numeric(df_inv["Hora"], errors="coerce").fillna(0).astype(int)
            df_inv["BusinessDate"] = pd.to_datetime(df_inv["BusinessDate"]).dt.date
            df_inv["CheckSubTotal"] = pd.to_numeric(df_inv["CheckSubTotal"], errors="coerce").fillna(0)

            if (df_inv["Hora"] == 0).all() and len(df_inv) > 0:
                print("  AVISO: DATEPART(HOUR,...) devolvio solo 0. En SQL Server Transaction_Date puede ser tipo DATE (sin hora).")

            df_horaria = df_inv.groupby(["StoreID", "BusinessDate", "Hora"], as_index=False).agg(
                Venta_Hora=("CheckSubTotal", "sum"),
                Transacciones_Hora=("CheckSubTotal", "count"),
            )

            df_horaria.to_sql("venta_horaria_2026", con=engine_local, if_exists="append", index=False)
            _horas_unicas = sorted(df_horaria["Hora"].unique().tolist())
            print(f"OK Cargadas/actualizadas {len(df_horaria)} filas en venta_horaria_2026. Horas presentes: {_horas_unicas[:24]}{'…' if len(_horas_unicas) > 24 else ''}")
        
    except Exception as e:
        print(f"Error al procesar Invoice / venta_horaria_2026: {e}")

    print("\nProceso finalizado.")

if __name__ == "__main__":
    extraer_maestros()