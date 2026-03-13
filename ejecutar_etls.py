"""
Script único para ejecutar todos los ETLs en orden.
Pensado para ser llamado por el Programador de tareas de Windows a las 6:00 y 8:00.
Orden: Maestros (dim_store, Invoice) -> Ventas SQL -> Excel (presupuesto/histórico).
"""
import os
import sys
from datetime import datetime

# Fijar directorio de trabajo al del script (donde está .env y fuentes_excel)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Zona horaria para los logs (Colombia)
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Bogota")
except Exception:
    TZ = None


def _ahora():
    if TZ:
        return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    print("=" * 60)
    print(f" INICIO EJECUCION ETLs - {_ahora()}")
    print("=" * 60)

    # 1. Maestros (dim_store, dim_item_*, raw_invoice_2026)
    try:
        from etl_maestros import extraer_maestros
        extraer_maestros()
        print("[OK] ETL Maestros finalizado.\n")
    except Exception as e:
        print(f"[ERROR] ETL Maestros: {e}\n")

    # 2. Ventas desde SQL Server (raw_ventas_2026)
    try:
        from etl_sql import extraer_datos_sql
        extraer_datos_sql()
        print("[OK] ETL SQL (Ventas) finalizado.\n")
    except Exception as e:
        print(f"[ERROR] ETL SQL: {e}\n")

    # 3. Excel (presupuesto, histórico, hechos_excel_diario)
    try:
        from etl_excel import ejecutar_etl
        ejecutar_etl()
        print("[OK] ETL Excel finalizado.\n")
    except Exception as e:
        print(f"[ERROR] ETL Excel: {e}\n")

    print("=" * 60)
    print(f" FIN EJECUCION ETLs - {_ahora()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
