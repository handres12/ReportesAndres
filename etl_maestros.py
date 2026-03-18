import os
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text, func
from database import engine_sql_server_sec, engine_local, SessionLocalDB
from models import DimStore, DimItemGroup, DimItemFamily, DimMenuItem, RawInvoice2026

# Re-traer siempre los últimos N días de Invoice para que no queden días con transacciones incompletas.
# Si un día (ej. 11-mar) solo tiene una tienda en raw_invoice_2026, es porque ese día no se ha
# vuelto a traer desde que se cargó; aumentar este valor hace que se rellenen más días cada vez que corre el ETL.
INVOICE_RELOAD_DAYS = int(os.getenv("INVOICE_RELOAD_DAYS", "45"))
INICIO_2026 = date(2026, 1, 1)
# Recarga completa 2026 (útil una vez para repoblar todos los días): ejecutar con env FULL_RELOAD_INVOICE_2026=1
FULL_RELOAD_INVOICE_2026 = os.getenv("FULL_RELOAD_INVOICE_2026", "").strip().lower() in ("1", "true", "yes")

def extraer_maestros():
    if engine_sql_server_sec is None:
        print("[ERROR] No hay conexión a SQL Server secundario (engine_sql_server_sec=None).")
        print("Causas típicas: falta `pyodbc` en el venv o faltan variables .env de SQL Server.")
        print("Solución: instala el driver y pyodbc, y configura SQL_SERVER_HOST/USER/PASS/DB y SQL_SERVER_DB_SEC en .env.")
        return
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

    # 2. Transacciones: facturas (InvoiceID) de Invoice desde 2026-01-01, por día por tienda -> raw_invoice_2026
    print("\nExtrayendo Invoice (facturas por día por tienda, desde 2026-01-01)...")
    
    with SessionLocalDB() as session:
        max_fecha_inv = session.query(func.max(RawInvoice2026.BusinessDate)).scalar()
        
        if max_fecha_inv is None or FULL_RELOAD_INVOICE_2026:
            if FULL_RELOAD_INVOICE_2026:
                print("FULL_RELOAD_INVOICE_2026=1: recarga completa de Invoice 2026 desde 2026-01-01.")
            else:
                print("No se encontraron Invoices previos. Se hará carga inicial desde 2026-01-01.")
            fecha_inicio_inv = '2026-01-01'
            if max_fecha_inv is not None:
                session.execute(text("DELETE FROM raw_invoice_2026 WHERE BusinessDate >= '2026-01-01'"))
                session.commit()
        else:
            # Re-traer últimos N días para que no queden días con transacciones incompletas
            max_date = max_fecha_inv.date() if hasattr(max_fecha_inv, 'date') else max_fecha_inv
            desde = max_date - timedelta(days=INVOICE_RELOAD_DAYS)
            fecha_inicio_inv = max(desde, INICIO_2026).strftime('%Y-%m-%d')
            print(f"Última fecha de Invoice: {max_date}. Re-cargando desde {fecha_inicio_inv} (últimos {INVOICE_RELOAD_DAYS} días)...")
            session.execute(text(f"DELETE FROM raw_invoice_2026 WHERE BusinessDate >= '{fecha_inicio_inv}'"))
            session.commit()

    try:
        # 2.a) Traer facturas (InvoiceID) de Invoice -> raw_invoice_2026. La app agrega COUNT(InvoiceID) por día y tienda.
        query_invoice = f"""
        SELECT * FROM Invoice 
        WHERE BusinessDate >= '{fecha_inicio_inv}' AND BusinessDate < '2027-01-01'
        """
        df_invoice = pd.read_sql(query_invoice, con=engine_sql_server_sec)
        
        if df_invoice.empty:
            print("OK raw_invoice_2026: sin filas nuevas (ya al día).")
        else:
            df_invoice = df_invoice.dropna(subset=['InvoiceID', 'StoreID'])
            df_invoice = df_invoice.drop_duplicates(subset=['InvoiceID', 'StoreID'])
            df_invoice.to_sql('raw_invoice_2026', con=engine_local, if_exists='append', index=False)
            print(f"OK raw_invoice_2026: {len(df_invoice)} facturas (InvoiceID) cargadas/actualizadas -> transacciones por dia por tienda.")

        # 2.b) Opcional: tabla auxiliar venta_horaria_2026 (solo si la app usa ventas/transacciones por hora).
        print("\nActualizando tabla auxiliar venta_horaria_2026...")
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
            print(f"OK venta_horaria_2026: {len(df_horaria)} filas (tabla auxiliar).")
        
    except Exception as e:
        print(f"Error al procesar Invoice / venta_horaria_2026: {e}")

    print("\nProceso finalizado.")

if __name__ == "__main__":
    extraer_maestros()