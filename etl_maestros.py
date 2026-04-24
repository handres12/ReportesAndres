import os
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text, func
from database import engine_sql_server_sec, engine_local, SessionLocalDB
from models import DimStore, DimItemGroup, DimItemFamily, DimMenuItem, RawInvoice2026

# --- Invoice -> raw_invoice_2026 (transacciones en la app, pestaña 6, etc.) ---
#
# Modo por defecto INVOICE_INCREMENTAL_MODE=month (recomendado):
#   - Un mes "cerrado" NO se vuelve a borrar ni a reemplazar: todo BusinessDate estrictamente anterior
#     al día 1 del mes calendario EN CURSO queda congelado en SQLite.
#   - Solo se DELETE + INSERT desde ese día 1 hasta fin de 2026 (mes abierto + días futuros del año).
#   - Así enero/febrero no se pierden ni se "pisan" al avanzar marzo/abril, siempre que el mes
#     haya quedado bien cargado antes de que termine (conviene ETL diario hasta fin de mes).
#
# Modo INVOICE_INCREMENTAL_MODE=rolling (legacy): ventana de INVOICE_RELOAD_DAYS desde la ultima fecha;
#   puede dejar meses viejos con pocos días si nunca entraron en la ventana. No recomendado.
#
# Recarga completa año 2026 (corregir historia o primer carga mala): FULL_RELOAD_INVOICE_2026=1
#   o: python recargar_invoice_2026_full.py
#
INVOICE_RELOAD_DAYS = int(os.getenv("INVOICE_RELOAD_DAYS", "45"))
INICIO_2026 = date(2026, 1, 1)
FULL_RELOAD_INVOICE_2026 = os.getenv("FULL_RELOAD_INVOICE_2026", "").strip().lower() in ("1", "true", "yes")
INVOICE_INCREMENTAL_MODE = os.getenv("INVOICE_INCREMENTAL_MODE", "month").strip().lower()

def extraer_maestros():
    if engine_sql_server_sec is None:
        print("[ERROR] No hay conexión a SQL Server secundario (engine_sql_server_sec=None).")
        print("Causas típicas: falta `pyodbc` en el venv o faltan variables .env de SQL Server.")
        print("Solución: instala el driver y pyodbc, y configura SQL_SERVER_HOST/USER/PASS/DB y SQL_SERVER_DB_SEC en .env.")
        return False
    print("Iniciando extracción desde base de datos secundaria (NEWACRVentas)...\n")
    ok_global = True
    
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
            ok_global = False

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
    else:
        hoy = date.today()
        if INVOICE_INCREMENTAL_MODE == "rolling":
            max_date = max_fecha_inv.date() if hasattr(max_fecha_inv, "date") else max_fecha_inv
            desde = max_date - timedelta(days=INVOICE_RELOAD_DAYS)
            fecha_inicio_inv = max(desde, INICIO_2026).strftime("%Y-%m-%d")
            print(
                f"[rolling] Ultima fecha Invoice en SQLite: {max_date}. "
                f"Borrar y recargar desde {fecha_inicio_inv} (ultimos {INVOICE_RELOAD_DAYS} dias)."
            )
        else:
            inicio_mes_actual = date(hoy.year, hoy.month, 1)
            inicio_borrado = max(inicio_mes_actual, INICIO_2026)
            fecha_inicio_inv = inicio_borrado.strftime("%Y-%m-%d")
            print(
                f"[month] Hoy calendario: {hoy}. Meses cerrados (< {fecha_inicio_inv}) NO se modifican. "
                f"Solo se borra y recarga Invoice con BusinessDate >= {fecha_inicio_inv}."
            )

    try:
        # 2.a) Traer primero desde SQL; solo si esto sale bien se reemplaza el rango local.
        query_invoice = f"""
        SELECT * FROM Invoice 
        WHERE BusinessDate >= '{fecha_inicio_inv}' AND BusinessDate < '2027-01-01'
        """
        df_invoice = pd.read_sql(query_invoice, con=engine_sql_server_sec)
        
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

        # Si ya se pudo leer SQL, ahora sí reemplazamos el rango local de forma segura.
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

            session.execute(text(f"DELETE FROM raw_invoice_2026 WHERE BusinessDate >= '{fecha_inicio_inv}'"))
            session.execute(text(f"DELETE FROM venta_horaria_2026 WHERE BusinessDate >= '{fecha_inicio_inv}'"))
            session.commit()

        # Insertar facturas para transacciones diarias.
        if df_invoice.empty:
            print("OK raw_invoice_2026: sin filas nuevas (ya al día).")
        else:
            df_invoice = df_invoice.dropna(subset=['InvoiceID', 'StoreID'])
            df_invoice = df_invoice.drop_duplicates(subset=['InvoiceID', 'StoreID'])
            df_invoice.to_sql('raw_invoice_2026', con=engine_local, if_exists='append', index=False)
            print(f"OK raw_invoice_2026: {len(df_invoice)} facturas (InvoiceID) cargadas/actualizadas -> transacciones por dia por tienda.")

        # Insertar agregados por hora.
        print("\nActualizando tabla auxiliar venta_horaria_2026...")

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
        ok_global = False

    print("\nProceso finalizado.")
    return ok_global

if __name__ == "__main__":
    extraer_maestros()