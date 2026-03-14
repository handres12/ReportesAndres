"""
Valida el archivo transacciones_hist (CSV o Excel) para la pestaña Transacciones 2026 vs 2025.
Muestra: ruta, columnas, Co (raw y normalizado), fechas 2025 y si los códigos coinciden con el mapeo de sedes.
Ejecutar en la raíz del proyecto: python validar_transacciones_2025.py
"""
import os
import pandas as pd

# Mismo mapeo que usa la app (código normalizado -> (grupo, sede))
MAPEO_SEDES = {
    '2': ('RBB', 'ACR'), '3': ('RBB', 'ADC'), 'F08': ('RBB', 'CARTAGENA'), '201': ('RBB', 'MEDELLIN'),
    '404': ('PLAZAS', 'GRAN ESTACIÓN'), '402': ('PLAZAS', 'HACIENDA'), '401': ('PLAZAS', 'RETIRO'), '405': ('PLAZAS', 'SANTAFÉ'),
    'F09': ('PARADERO FR', 'BAZAAR'), 'F05': ('PARADERO FR', 'HYATT'), 'F04': ('PARADERO FR', 'PLAZA CLARO'),
    '301': ('PARADERO', 'AEROPUERTO'), '304': ('PARADERO', 'ANDRES VIAJERO'), '305': ('PARADERO', 'RIONEGRO'),
    '611': ('EXPRÉS', 'CAFAM'), '502': ('EXPRÉS', 'CALLE 93'), '612': ('EXPRÉS', 'CASA DE LOS ANDES'),
    '4': ('EXPRÉS', 'EXPRÉS PARADERO'), '702': ('EXPRÉS', 'MULTIPARQUE'), '604': ('EXPRÉS', 'PALATINO'), '615': ('EXPRÉS', 'PEPE SIERRA'),
}

def _norm_cols(cols):
    return [str(c).strip().lstrip("\ufeff") for c in cols]

def _detectar_columna(df, candidatos):
    cols = _norm_cols(df.columns)
    for cand in candidatos:
        cand_low = cand.strip().lower()
        for col in cols:
            if col.strip().lower() == cand_low:
                return col
    return None

def main():
    base = os.getcwd()
    posibles_carpetas = [base, os.path.join(base, "fuentes_excel"), os.path.dirname(base)]
    ruta_archivo = None
    for carpeta in posibles_carpetas:
        if not os.path.exists(carpeta):
            continue
        for f in os.listdir(carpeta):
            f_low = f.lower()
            if f_low.startswith("transacciones_hist") and (f_low.endswith(".xlsx") or f_low.endswith(".xls") or f_low.endswith(".csv")):
                ruta_archivo = os.path.join(carpeta, f)
                break
        if ruta_archivo:
            break

    if not ruta_archivo:
        print("No se encontró archivo transacciones_hist (.csv o .xlsx) en raíz, fuentes_excel ni carpeta padre.")
        print("Para que la WEB muestre transacciones 2025, el archivo debe estar en el repositorio (raíz o fuentes_excel).")
        return

    print("Archivo encontrado:", ruta_archivo)
    print()

    try:
        if ruta_archivo.lower().endswith(".csv"):
            df = pd.read_csv(ruta_archivo, sep=";", encoding="utf-8-sig", low_memory=False)
            if df.empty and os.path.getsize(ruta_archivo) > 0:
                df = pd.read_csv(ruta_archivo, sep=",", encoding="utf-8-sig", low_memory=False)
        else:
            df = pd.read_excel(ruta_archivo, sheet_name=0)
    except Exception as e:
        print("Error leyendo archivo:", e)
        return

    df.columns = _norm_cols(df.columns)
    col_co = _detectar_columna(df, ["Co", "CentroOP", "Centro", "Codigo", "StoreID_External", "StoreID", "Sede", "Tienda"])
    col_mes = _detectar_columna(df, ["Mes", "Month", "MES"])
    col_2025 = next((c for c in df.columns if str(c).strip() == "2025"), None)
    col_fecha = _detectar_columna(df, ["Fecha", "FechaDocto", "Date", "FechaVenta", "Dia", "Business Date", "BusinessDate"])
    col_tx = _detectar_columna(df, [
        "Transacciones", "Cantidad_Transacciones", "Cantidad", "Sales Count", "SalesCount",
        "Num Transacciones", "NumeroTransacciones", "Tickets", "Invoices"
    ])

    # Formato mensual: Co, Mes, columna 2025
    if col_co and col_mes and col_2025 is not None:
        print("Formato detectado: Co + Mes + columna 2025 (transacciones mensuales). La app diarizará por día.")
        print("Columnas usadas: Co =", col_co, "| Mes =", col_mes, "| 2025 =", col_2025)
        print()
        codigo_norm = (
            df[col_co].astype(str).str.strip().str.upper().str.replace(r"\.0$", "", regex=True).str.lstrip("0")
        )
        df["_co_raw"] = df[col_co].astype(str).str.strip()
        df["_co_norm"] = codigo_norm
        df["_mes_str"] = df[col_mes].astype(str).str.strip().str.lower()
        df["_tx"] = pd.to_numeric(df[col_2025], errors="coerce").fillna(0)
        df = df[(df["_co_norm"] != "") & (~df["_co_norm"].astype(str).str.upper().str.contains("NAN", na=True))]
        co_unique = df[["_co_raw", "_co_norm"]].drop_duplicates().sort_values("_co_norm")
        print("--- Co en el archivo (raw -> normalizado = código para match) ---")
        for _, r in co_unique.iterrows():
            raw, norm = r["_co_raw"], r["_co_norm"]
            if not norm or str(norm).upper() == "NAN":
                continue
            sede = MAPEO_SEDES.get(str(norm), ("?", "?"))[1]
            ok = "OK" if str(norm) in MAPEO_SEDES else "NO EN MAPEO"
            print(f"  {raw!r:>10} -> {norm!r:>6}  ({sede})  {ok}")
        print("--- Transacciones 2025 por mes (se diarizan en la app) ---")
        print(df.groupby("_co_norm")["_tx"].sum().to_string())
        no_mapeo = [c for c in co_unique["_co_norm"].astype(str).unique() if c and c not in MAPEO_SEDES]
        if no_mapeo:
            print("\nCódigos NO en mapeo (saldrán 0):", no_mapeo)
        print("\nPara la WEB: sube el archivo al repo (raíz o fuentes_excel) y haz push.")
        return

    if not col_co or not col_fecha or not col_tx:
        print("No se detectó formato Co+Fecha+Transacciones ni Co+Mes+2025. Columnas:", list(df.columns)[:15])
        return

    print("Formato detectado: Co + Fecha + Transacciones (datos diarios).")
    print("Columnas usadas: Co =", col_co, "| Fecha =", col_fecha, "| Transacciones =", col_tx)
    print()
    raw_co = df[col_co].astype(str).str.strip()
    codigo_norm = (
        df[col_co].astype(str).str.strip().str.upper().str.replace(r"\.0$", "", regex=True).str.lstrip("0")
    )
    fechas = pd.to_datetime(df[col_fecha], dayfirst=True, errors="coerce")
    df["_fecha"] = fechas.dt.date
    df["_co_raw"] = raw_co
    df["_co_norm"] = codigo_norm
    df["_tx"] = pd.to_numeric(df[col_tx], errors="coerce").fillna(0)
    df_2025 = df[df["_fecha"].notna() & df["_fecha"].apply(lambda d: getattr(d, "year", None) == 2025)]
    df_2025 = df_2025[df_2025["_co_norm"].astype(str).str.strip() != ""]
    df_2025 = df_2025[~df_2025["_co_norm"].astype(str).str.upper().str.contains("NAN", na=True)]
    print("--- Co (raw -> normalizado) ---")
    co_unique = df_2025[["_co_raw", "_co_norm"]].drop_duplicates().sort_values("_co_norm")
    for _, r in co_unique.iterrows():
        raw, norm = r["_co_raw"], r["_co_norm"]
        if not norm or str(norm).upper() == "NAN":
            continue
        sede = MAPEO_SEDES.get(str(norm), ("?", "?"))[1]
        ok = "OK" if str(norm) in MAPEO_SEDES else "NO EN MAPEO"
        print(f"  {raw!r:>10} -> {norm!r:>6}  ({sede})  {ok}")
    print("\nRango 2025:", df_2025["_fecha"].min(), "a", df_2025["_fecha"].max(), "| Filas:", len(df_2025))
    no_mapeo = [c for c in co_unique["_co_norm"].astype(str).unique() if c and c not in MAPEO_SEDES]
    if no_mapeo:
        print("Códigos NO en mapeo:", no_mapeo)
    print("\nPara la WEB: sube el archivo al repo y haz push.")

if __name__ == "__main__":
    main()
