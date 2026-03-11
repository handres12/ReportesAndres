"""
Carga un CSV suplente con ventas 2025 (p. ej. solo PLAZAS) a hechos_excel_diario.
No borra el resto del histórico: solo reemplaza los centros que vienen en el archivo.

CSV: columnas Co, Fecha, VentaNeta; separador ; o ,. Encoding utf-8 o latin-1.
Ejemplo nombre: historico_2025_suplente.csv o PLAZAS_2025.csv en la raíz o en fuentes_excel.

Uso: python cargar_historico_2025_suplente.py [ruta_opcional.csv]
"""
import os
import sys
import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()
from database import engine_local

COL_CO = ["Co", "CentroOP", "Centro", "StoreID"]
COL_FECHA = ["Fecha", "FechaDocto", "Date"]
COL_VENTA = ["VentaNeta", "Ventas", "ValorTotal", "VlrBruto"]


def _detectar_col(df, candidatos):
    for c in candidatos:
        for col in df.columns:
            if str(col).strip().lower() == c.strip().lower():
                return col
    return None


def _normalizar_columnas(df):
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
    return df


def buscar_archivo():
    nombres = ["historico_2025_suplente.csv", "PLAZAS_2025.csv", "ventas_2025_suplente.csv"]
    carpetas = [os.getcwd(), os.path.join(os.getcwd(), "fuentes_excel")]
    for carpeta in carpetas:
        if not os.path.isdir(carpeta):
            continue
        for n in nombres:
            ruta = os.path.join(carpeta, n)
            if os.path.isfile(ruta):
                return ruta
    return None


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else buscar_archivo()
    if not ruta or not os.path.isfile(ruta):
        print("No se encontró CSV. Pase la ruta: python cargar_historico_2025_suplente.py <archivo.csv>")
        print("O coloque historico_2025_suplente.csv o PLAZAS_2025.csv en la raíz o en fuentes_excel.")
        return

    for sep in [";", ","]:
        try:
            df = pd.read_csv(ruta, sep=sep, encoding="utf-8-sig", low_memory=False)
            break
        except Exception:
            try:
                df = pd.read_csv(ruta, sep=sep, encoding="latin-1", low_memory=False)
                break
            except Exception:
                continue
    else:
        print("No se pudo leer el CSV (pruebe con separador ; o ,).")
        return

    df = _normalizar_columnas(df)
    col_co = _detectar_col(df, COL_CO)
    col_fecha = _detectar_col(df, COL_FECHA)
    col_venta = _detectar_col(df, COL_VENTA)
    if not col_co or not col_fecha or not col_venta:
        print("Faltan columnas. Necesarias: Co (o CentroOP), Fecha, VentaNeta. Encontradas:", list(df.columns)[:10])
        return

    df["StoreID_External"] = df[col_co].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["Fecha"] = pd.to_datetime(df[col_fecha], dayfirst=True, errors="coerce").dt.date
    df["Ventas"] = pd.to_numeric(df[col_venta], errors="coerce").fillna(0)
    df = df.dropna(subset=["Fecha"])
    agrupado = df.groupby(["StoreID_External", "Fecha"], as_index=False)["Ventas"].sum()

    # Agrupacion desde BD
    try:
        lookup = pd.read_sql(text("SELECT store_id, grupo FROM sede_grupo_lookup"), con=engine_local)
        grupos = dict(zip(
            lookup["store_id"].astype(str).str.strip().str.upper().str.lstrip("0"),
            lookup["grupo"]
        ))
    except Exception:
        grupos = {"401": "PLAZAS", "402": "PLAZAS", "404": "PLAZAS", "405": "PLAZAS", "2": "RBB", "3": "RBB"}

    def grupo(c):
        return grupos.get(str(c).strip().upper().lstrip("0"), "OTRO")

    agrupado["Agrupacion"] = agrupado["StoreID_External"].apply(grupo)
    agrupado["Sede_Excel"] = "Suplente_2025"
    agrupado["Escenario"] = "Historico_Diario"
    agrupado["Transacciones"] = 0.0
    agrupado["Ticket_Promedio"] = 0.0

    stores = agrupado["StoreID_External"].unique().tolist()
    with engine_local.connect() as conn:
        for s in stores:
            conn.execute(
                text("DELETE FROM hechos_excel_diario WHERE Escenario = 'Historico_Diario' AND StoreID_External = :sid"),
                {"sid": str(s)}
            )
        conn.commit()

    agrupado[["StoreID_External", "Sede_Excel", "Agrupacion", "Fecha", "Escenario", "Ventas", "Transacciones", "Ticket_Promedio"]].to_sql(
        "hechos_excel_diario", con=engine_local, if_exists="append", index=False
    )
    print("OK Cargados", len(agrupado), "registros (Historico_Diario) para centros:", stores)
    print("Refresque el dashboard (botón Refrescar datos) para ver VENTA 2025.")


if __name__ == "__main__":
    main()
