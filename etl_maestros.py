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

def _upsert_sqlite(table_name: str, df: pd.DataFrame, pk_cols: list[str]) -> int:
    """Inserta/actualiza en SQLite sin borrar filas históricas."""
    if df is None or df.empty:
        return 0

    cols = [str(c) for c in df.columns]
    if not cols:
        return 0

    placeholders = ", ".join([f":{c}" for c in cols])
    updates = [c for c in cols if c not in pk_cols]
    if updates:
        update_sql = ", ".join([f"{c} = excluded.{c}" for c in updates])
        stmt_sql = (
            f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(pk_cols)}) DO UPDATE SET {update_sql}"
        )
    else:
        stmt_sql = (
            f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(pk_cols)}) DO NOTHING"
        )
    stmt = text(stmt_sql)

    rows = []
    for rec in df.to_dict(orient="records"):
        row = {}
        for c in cols:
            v = rec.get(c)
            if pd.isna(v):
                v = None
            elif isinstance(v, pd.Timestamp):
                # sqlite3 no siempre adapta Timestamp de pandas.
                v = v.to_pydatetime()
            row[c] = v
        rows.append(row)

    with SessionLocalDB() as session:
        session.execute(stmt, rows)
        session.commit()
    return len(rows)


def extraer_maestros():
    if engine_sql_server_sec is None:
        print("[ERROR] No hay conexión a SQL Server secundario (engine_sql_server_sec=None).")
        print("Causas típicas: falta `pyodbc` en el venv o faltan variables .env de SQL Server.")
        print("Solución: instala el driver y pyodbc, y configura SQL_SERVER_HOST/USER/PASS/DB y SQL_SERVER_DB_SEC en .env.")
        return False
    print("Iniciando extracción desde base de datos secundaria (NEWACRVentas)...\n")
    ok_global = True
    
    tablas_maestras = {
        'Store': ('dim_store', ['StoreID']),
        'ItemGroup': ('dim_item_group', ['StoreID', 'GroupID']),
        'ItemFamily': ('dim_item_family', ['storeID', 'FamilyID']),
        'MenuItem': ('dim_menu_item', ['storeID', 'MenuItemID'])
    }
    
    # 1. Extraer los catálogos completos (Full Load por seguridad de cambios de nombre)
    for tabla_origen, (tabla_destino, pk_cols) in tablas_maestras.items():
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

            n = _upsert_sqlite(tabla_destino, df, pk_cols)
            print(f"  -> OK Cargados/actualizados {n} registros.")
            
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

        # Crear tabla/índice de horaria para upsert (sin borrar histórico).
        with SessionLocalDB() as session:
            try:
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS venta_horaria_2026 (
                        StoreID VARCHAR(50), BusinessDate DATE, Hora INTEGER,
                        Venta_Hora FLOAT, Transacciones_Hora INTEGER
                    )
                """))
                session.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_venta_horaria_2026
                    ON venta_horaria_2026 (StoreID, BusinessDate, Hora)
                """))
                session.commit()
            except Exception:
                pass

        # Insertar facturas para transacciones diarias.
        if df_invoice.empty:
            print("OK raw_invoice_2026: sin filas nuevas (ya al día).")
        else:
            df_invoice = df_invoice.dropna(subset=['InvoiceID', 'StoreID'])
            df_invoice = df_invoice.drop_duplicates(subset=['InvoiceID', 'StoreID'])
            n_inv = _upsert_sqlite('raw_invoice_2026', df_invoice, ['InvoiceID', 'StoreID'])
            print(f"OK raw_invoice_2026: {n_inv} facturas (InvoiceID) cargadas/actualizadas -> transacciones por dia por tienda.")

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

            stmt_h = text("""
                INSERT INTO venta_horaria_2026 (StoreID, BusinessDate, Hora, Venta_Hora, Transacciones_Hora)
                VALUES (:StoreID, :BusinessDate, :Hora, :Venta_Hora, :Transacciones_Hora)
                ON CONFLICT(StoreID, BusinessDate, Hora) DO UPDATE SET
                    Venta_Hora = excluded.Venta_Hora,
                    Transacciones_Hora = excluded.Transacciones_Hora
            """)
            rows_h = []
            for rec in df_horaria.to_dict(orient="records"):
                rows_h.append({
                    "StoreID": rec["StoreID"],
                    "BusinessDate": rec["BusinessDate"],
                    "Hora": int(rec["Hora"]),
                    "Venta_Hora": float(rec["Venta_Hora"] or 0),
                    "Transacciones_Hora": int(rec["Transacciones_Hora"] or 0),
                })
            with SessionLocalDB() as session:
                session.execute(stmt_h, rows_h)
                session.commit()
            print(f"OK venta_horaria_2026: {len(rows_h)} filas cargadas/actualizadas (tabla auxiliar).")
        
    except Exception as e:
        print(f"Error al procesar Invoice / venta_horaria_2026: {e}")
        ok_global = False

    print("\nProceso finalizado.")
    return ok_global

if __name__ == "__main__":
    extraer_maestros()