"""
ETL: Extrae archivos Excel de ventas 2025 desde FTP "Ventas por items 2025",
carga directo en hechos_excel_diario (Historico_Diario). Una sola vez; luego no vuelve a FTP.

Uso: python etl_ftp_ventas_2025.py
Configuración: .env (FTP_HOST, FTP_USER, FTP_PASS, LOCAL_DB_URL) o valores por defecto.
"""
import os
import io
import ftplib
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()
from database import engine_local

FTP_HOST = os.getenv("FTP_HOST", "129.153.171.10")
FTP_USER = os.getenv("FTP_USER", "integracion")
FTP_PASS = os.getenv("FTP_PASS", "S1mph0ny2024")
CARPETA_FTP = os.getenv("FTP_CARPETA_VENTAS_2025", "/Ventas por items 2025")

# Nombres posibles para columna de centro/tienda (orden de preferencia)
COL_CO = ["CentroOP", "Co", "Centro", "Codigo", "StoreID", "Sede", "Tienda"]
# Nombres posibles para fecha (los Excel "Ventas por items" usan Business Date)
COL_FECHA = ["Fecha", "FechaDocto", "Date", "FechaVenta", "Dia", "Business Date", "BusinessDate"]
# Nombres posibles para valor de venta (los Excel "Ventas por items" usan Sales Total)
COL_VENTA = ["VentaNeta", "Ventas", "ValorTotal", "VlrBruto", "Sales Total", "ValorTotalDescto", "Amount", "Total"]

# Nombre de archivo -> código cuando Co viene vacío o no reconocido (validar PLAZAS)
FILENAME_A_CODIGO = [
    ("PLAZA HACIENDA", "402"),
    ("PLAZA EL RETIRO", "401"),
    ("PLAZA GRAN ESTACION", "404"),
    ("PLAZA SANTAFE", "405"),
    ("PLAZA CLARO", "F04"),
    ("ACR ", "2"), (" ADC ", "3"), ("CARTAGENA", "F08"), ("RIONEGRO", "305"), ("MEDELLIN", "201"),
    ("AEROPUERTO INTERNACIONAL", "304"), ("AEROPUERTO ", "301"), ("BAZAR 80", "F09"), ("HYATT", "F05"),
    ("EXPRES CAFAM", "611"), ("EXPRES CALLE 93", "502"), ("CASA ANDES", "612"), ("EXPRES CHIA", "4"),
    ("MULTIPARQUE", "702"), ("PALATINO", "604"), ("PEPE SIERRA", "615"),
]
# Cuando Co viene como nombre de sede (ej. Plaza Hacienda) en vez de código
NOMBRE_A_CODIGO = {
    "hacienda": "402", "plaza hacienda": "402", "plaza hacienda santa barbara": "402",
    "plaza centro comercial hacienda": "402", "plaza centro comercial, hacienda": "402",
    "retiro": "401", "plaza retiro": "401", "plaza el retiro": "401", "plaza centro comercial retiro": "401",
    "gran estacion": "404", "gran estación": "404", "plaza gran estacion": "404", "plaza gran estación": "404",
    "santafe": "405", "santa fe": "405", "plaza santafe": "405", "plaza santa fe": "405",
    "plaza centro comercial santa fe": "405",
    "acr": "2", "andres chia": "2", "adc": "3", "andres dc": "3", "cartagena": "F08", "medellin": "201",
    "viajero": "304", "orleans": "304", "andres viajero": "304", "aeropuerto internacional": "304",
    "aeropuerto el dorado": "301", "aeropuerto": "301", "rionegro": "305", "bazar": "F09", "bazar 80": "F09",
    "hyatt": "F05", "plaza claro": "F04", "cafam": "611", "calle 93": "502", "casa andes": "612",
    "expres chia": "4", "multiparque": "702", "palatino": "604", "pepe sierra": "615",
}

CODIGOS_PLAZAS = {"401", "402", "404", "405"}  # Retiro, Hacienda, Gran Estación, Santafe


def _co_a_codigo(val):
    """Convierte CentroOP (código o nombre) a código normalizado; valida PLAZAS por nombre."""
    s = str(val).strip().replace(",", " ").replace(".", " ").replace("  ", " ").strip()
    if not s or s.upper() in ("NAN", "NONE"):
        return s
    try:
        f = float(s.replace(",", "."))
        if f == int(f):
            return str(int(f)).lstrip("0") or "0"
    except ValueError:
        pass
    su = s.upper().lstrip("0")
    if su.isdigit() or (len(su) > 1 and su[0] == "F" and su[1:].isdigit()):
        return su if su else s
    low = s.lower()
    for nombre, cod in NOMBRE_A_CODIGO.items():
        if nombre in low or low in nombre:
            return cod
    return s


def _normalizar_nombres(df):
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
    return df


def _detectar_columna(df, candidatos):
    for c in candidatos:
        for col in df.columns:
            if col.strip().lower() == c.strip().lower():
                return col
    return None


def extraer_ventas_desde_excel(bio):
    """Lee un Excel desde BytesIO y devuelve (DataFrame con Co, Fecha, VentaNeta) o (None, columnas_encontradas)."""
    df = pd.read_excel(bio, sheet_name=0)
    df = _normalizar_nombres(df)
    col_co = _detectar_columna(df, COL_CO)
    col_fecha = _detectar_columna(df, COL_FECHA)
    col_venta = _detectar_columna(df, COL_VENTA)
    if not col_co or not col_fecha or not col_venta:
        return None, (col_co, col_fecha, col_venta, df.columns.tolist())
    out = pd.DataFrame()
    out["Co"] = df[col_co].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["Fecha"] = pd.to_datetime(df[col_fecha], dayfirst=True, errors="coerce")
    out["VentaNeta"] = pd.to_numeric(df[col_venta], errors="coerce").fillna(0)
    out = out.dropna(subset=["Fecha"])
    out["Fecha"] = out["Fecha"].dt.date
    return out, (col_co, col_fecha, col_venta, None)


def ejecutar_extraccion_ftp():
    print("Conectando a FTP...")
    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=60)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(False)
    except Exception as e:
        print("Error conexion FTP:", e)
        return None

    try:
        ftp.cwd(CARPETA_FTP)
        archivos = [f for f in ftp.nlst() if f.lower().endswith(".xlsx") and not f.startswith("~$")]
    except Exception as e:
        print("Error listando carpeta FTP:", e)
        ftp.quit()
        return None

    if not archivos:
        print("No hay archivos .xlsx en", CARPETA_FTP)
        ftp.quit()
        return None

    print("Archivos .xlsx encontrados:", len(archivos))
    listado_dfs = []
    for nombre in archivos:
        try:
            bio = io.BytesIO()
            ftp.retrbinary("RETR " + nombre, bio.write)
            bio.seek(0)
            df, cols = extraer_ventas_desde_excel(bio)
            if df is None:
                col_co, col_fecha, col_venta, listado = cols[0], cols[1], cols[2], (cols[3] if len(cols) > 3 else [])
                print("  ", nombre, "-> columnas no detectadas. Esperadas: CentroOP/Co, Fecha, VentaNeta. Encontradas:", listado[:12] if listado else "?")
                continue
            cod_desde_nombre = None
            for frag, cod in FILENAME_A_CODIGO:
                if frag in nombre.upper():
                    cod_desde_nombre = cod
                    break
            if cod_desde_nombre is not None:
                df = df.copy()
                df["Co"] = cod_desde_nombre
                print("  ", nombre, "-> Co por nombre de archivo:", cod_desde_nombre)
            else:
                df = df.copy()
                df["Co"] = df["Co"].apply(_co_a_codigo)
            print("  ", nombre, "-> columnas usadas:", cols[:3], "filas:", len(df))
            listado_dfs.append(df)
        except Exception as e:
            print("  ", nombre, "-> Error:", e)
    ftp.quit()

    if not listado_dfs:
        print("Ningun archivo pudo leerse correctamente.")
        return None
    return pd.concat(listado_dfs, ignore_index=True)


def _cargar_grupos_desde_bd():
    """Lee sede_grupo_lookup y devuelve dict codigo_limpio -> grupo."""
    try:
        df = pd.read_sql(text("SELECT store_id, grupo FROM sede_grupo_lookup"), con=engine_local)
        return dict(zip(
            df["store_id"].astype(str).str.strip().str.upper().str.lstrip("0"),
            df["grupo"]
        ))
    except Exception:
        return {
            "2": "RBB", "3": "RBB", "F08": "RBB", "201": "RBB",
            "401": "PLAZAS", "402": "PLAZAS", "404": "PLAZAS", "405": "PLAZAS",
            "F09": "PARADERO FR", "F05": "PARADERO FR", "F04": "PARADERO FR",
            "301": "PARADERO", "304": "PARADERO", "305": "PARADERO",
            "611": "EXPRÉS", "502": "EXPRÉS", "612": "EXPRÉS", "4": "EXPRÉS",
            "702": "EXPRÉS", "604": "EXPRÉS", "615": "EXPRÉS",
        }


def consolidar_y_cargar_bd(df):
    """Agrupa por Co y Fecha, asigna grupo, y carga en hechos_excel_diario (Historico_Diario). Valida PLAZAS."""
    if df is None or df.empty:
        return
    df = df.copy()
    df["Co"] = df["Co"].apply(_co_a_codigo)
    agrupado = df.groupby(["Co", "Fecha"], as_index=False).agg({"VentaNeta": "sum"})
    agrupado = agrupado.sort_values(["Co", "Fecha"])

    grupos = _cargar_grupos_desde_bd()
    def grupo(c):
        k = str(c).strip().upper().lstrip("0")
        return grupos.get(k, "OTRO")

    agrupado["StoreID_External"] = agrupado["Co"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    agrupado["Agrupacion"] = agrupado["StoreID_External"].apply(grupo)
    agrupado["Sede_Excel"] = "FTP_Ventas_2025"
    agrupado["Escenario"] = "Historico_Diario"
    agrupado["Ventas"] = agrupado["VentaNeta"]
    agrupado["Transacciones"] = 0.0
    agrupado["Ticket_Promedio"] = 0.0

    cols_bd = ["StoreID_External", "Sede_Excel", "Agrupacion", "Fecha", "Escenario", "Ventas", "Transacciones", "Ticket_Promedio"]
    df_carga = agrupado[cols_bd].copy()

    with engine_local.connect() as conn:
        conn.execute(text("DELETE FROM hechos_excel_diario WHERE Escenario = 'Historico_Diario'"))
        conn.commit()
    df_carga.to_sql("hechos_excel_diario", con=engine_local, if_exists="append", index=False)
    print("BD: cargados", len(df_carga), "registros en hechos_excel_diario (Historico_Diario).")

    # Resumen por Co
    resumen = agrupado.groupby("StoreID_External")["VentaNeta"].agg(["sum", "count"])
    resumen.columns = ["Total_VentaNeta", "Dias"]
    print("\nResumen por centro (Co):")
    print(resumen.to_string())
    # Validación PLAZAS: 401 Retiro, 402 Hacienda, 404 Gran Estación, 405 Santafe
    co_presentes = set(agrupado["StoreID_External"].astype(str).str.strip().str.upper().str.lstrip("0"))
    plazas_ok = CODIGOS_PLAZAS & co_presentes
    plazas_faltan = CODIGOS_PLAZAS - co_presentes
    print("\n--- Validación PLAZAS (comparativo 2025) ---")
    print("  Con dato: 401 Retiro, 402 Hacienda, 404 Gran Estación, 405 Santafe -> presentes:", sorted(plazas_ok) or "ninguno")
    if plazas_faltan:
        print("  Faltan en el archivo FTP (saldrán $0 en pestaña 2):", sorted(plazas_faltan))
    return agrupado


def main():
    print("ETL FTP Ventas 2025 - Extraccion desde", CARPETA_FTP)
    df = ejecutar_extraccion_ftp()
    consolidar_y_cargar_bd(df)
    print("\nListo. Datos 2025 quedaron en la BD; no es necesario volver a conectarse al FTP.")


if __name__ == "__main__":
    main()
