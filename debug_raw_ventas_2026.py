import sqlite3
import pandas as pd


def mostrar_dia(fecha_str: str) -> None:
    conn = sqlite3.connect("bi_local_data.db")
    try:
        q = """
        SELECT StoreID, Fecha, VlrBruto, VlrTotalDesc
        FROM raw_ventas_2026
        WHERE Fecha = ?
        ORDER BY StoreID
        """
        df = pd.read_sql_query(q, conn, params=[fecha_str])
        print(f"Filas en raw_ventas_2026 para {fecha_str}:")
        if df.empty:
            print("(sin filas)")
        else:
            print(df.to_string(index=False))
    finally:
        conn.close()


if __name__ == "__main__":
    # Día clave: 6 de marzo de 2026
    mostrar_dia("2026-03-06")

