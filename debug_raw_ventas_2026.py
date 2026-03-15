"""Consulta raw_ventas_2026 por fecha. Uso: python debug_raw_ventas_2026.py [YYYY-MM-DD]"""
import sqlite3
import pandas as pd
import sys
import os

# Buscar DB en la raíz del proyecto
DB = os.getenv("LOCAL_DB_PATH", "bi_local_data.db")
if not os.path.isfile(DB):
    DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bi_local_data.db")


def mostrar_dia(fecha_str: str) -> None:
    if not os.path.isfile(DB):
        print(f"❌ No se encuentra la base: {DB}")
        return
    conn = sqlite3.connect(DB)
    try:
        q = """
        SELECT StoreID, Fecha, VlrBruto, VlrTotalDesc,
               (VlrBruto - ABS(VlrTotalDesc)) AS VentaNeta
        FROM raw_ventas_2026
        WHERE Fecha = ?
        ORDER BY StoreID
        """
        df = pd.read_sql_query(q, conn, params=[fecha_str])
        print(f"\n--- raw_ventas_2026 para {fecha_str} ---")
        if df.empty:
            print("(sin filas). No hay datos para ese día en la base local.")
            print("Posibles causas: el ETL (etl_sql.py) no ha cargado esa fecha, o en SQL Server (tabla Detalle) no hay registros para ese día.")
        else:
            print(df.to_string(index=False))
            # Sedes conocidas que suelen preguntar: 201 = MEDELLIN, F04 = PLAZA CLARO
            codigos = set(df["StoreID"].astype(str).str.strip().str.upper().str.lstrip("0"))
            if "201" not in codigos:
                print("\n⚠️ No hay filas con StoreID que normalice a '201' (MEDELLIN).")
            if "F04" not in codigos:
                print("⚠️ No hay filas con StoreID que normalice a 'F04' (PLAZA CLARO).")
    finally:
        conn.close()


if __name__ == "__main__":
    fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-03-13"
    mostrar_dia(fecha)

