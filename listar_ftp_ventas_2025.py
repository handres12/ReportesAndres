"""
Lista los archivos .xlsx en el FTP "Ventas por items 2025".
Opcional: con --cargar descarga de a uno, extrae ventas y reemplaza TODO el contenido
de Historico_Diario en la BD (no se junta con lo existente).

Uso:
  python listar_ftp_ventas_2025.py              -> solo lista nombres
  python listar_ftp_ventas_2025.py --cargar     -> lista, descarga uno por uno y reemplaza BD
"""
import os
import io
import sys
import ftplib
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

FTP_HOST = os.getenv("FTP_HOST", "129.153.171.10")
FTP_USER = os.getenv("FTP_USER", "integracion")
FTP_PASS = os.getenv("FTP_PASS", "S1mph0ny2024")
CARPETA_OBJETIVO = os.getenv("FTP_CARPETA_VENTAS_2025", "/Ventas por items 2025")

COL_CO = ["CentroOP", "Co", "Centro", "Codigo", "StoreID", "Sede", "Tienda"]
COL_FECHA = ["Fecha", "FechaDocto", "Date", "FechaVenta", "Dia", "Business Date", "BusinessDate"]
COL_VENTA = ["VentaNeta", "Ventas", "ValorTotal", "VlrBruto", "Sales Total", "ValorTotalDescto", "Amount", "Total"]

# Fragmento de nombre de archivo -> código (cuando CentroOP viene vacío o no reconocido)
# Orden: más específico primero (ej. RIONEGRO antes que MEDELLIN para "RIONEGRO MEDELLIN")
FILENAME_A_CODIGO = [
    ("PLAZA HACIENDA", "402"),
    ("PLAZA EL RETIRO", "401"),
    ("PLAZA GRAN ESTACION", "404"),
    ("PLAZA SANTAFE", "405"),
    ("PLAZA CLARO", "F04"),
    ("ACR ", "2"),
    (" ADC ", "3"),
    ("CARTAGENA", "F08"),
    ("RIONEGRO", "305"),
    ("MEDELLIN", "201"),
    ("AEROPUERTO INTERNACIONAL", "304"),
    ("AEROPUERTO ", "301"),
    ("BAZAR 80", "F09"),
    ("HYATT", "F05"),
    ("EXPRES CAFAM", "611"),
    ("EXPRES CALLE 93", "502"),
    ("CASA ANDES", "612"),
    ("EXPRES CHIA", "4"),
    ("MULTIPARQUE", "702"),
    ("PALATINO", "604"),
    ("PEPE SIERRA", "615"),
]

# Cuando CentroOP viene como nombre de sede (ej. "Plaza Hacienda") en vez de código, mapear a código
NOMBRE_A_CODIGO = {
    "hacienda": "402",
    "plaza hacienda": "402",
    "plaza hacienda santa barbara": "402",
    "plaza centro comercial hacienda": "402",
    "plaza centro comercial, hacienda": "402",
    "retiro": "401",
    "plaza retiro": "401",
    "plaza el retiro": "401",
    "plaza centro comercial retiro": "401",
    "gran estacion": "404",
    "gran estación": "404",
    "plaza gran estacion": "404",
    "plaza gran estación": "404",
    "santafe": "405",
    "santa fe": "405",
    "plaza santafe": "405",
    "plaza santa fe": "405",
    "plaza centro comercial santa fe": "405",
    "acr": "2",
    "andres chia": "2",
    "adc": "3",
    "andres dc": "3",
    "cartagena": "F08",
    "medellin": "201",
    "viajero": "304",
    "orleans": "304",
    "andres viajero": "304",
    "aeropuerto internacional": "304",
    "aeropuerto el dorado": "301",
    "aeropuerto": "301",
    "rionegro": "305",
    "bazar": "F09",
    "bazar 80": "F09",
    "hyatt": "F05",
    "plaza claro": "F04",
    "cafam": "611",
    "calle 93": "502",
    "casa andes": "612",
    "expres chia": "4",
    "multiparque": "702",
    "palatino": "604",
    "pepe sierra": "615",
}


def _co_a_codigo(val):
    """Convierte CentroOP (código o nombre) a código normalizado (402, 401, etc.)."""
    s = str(val).strip().replace(",", " ").replace(".", " ").replace("  ", " ").strip()
    if not s or s.upper() in ("NAN", "NONE"):
        return s
    # Si es número (ej. 402.0), devolver entero sin ceros a la izquierda
    try:
        f = float(s.replace(",", "."))
        if f == int(f):
            return str(int(f)).lstrip("0") or "0"
    except ValueError:
        pass
    # Si ya es solo dígitos o F+dígitos
    su = s.upper().lstrip("0")
    if su.isdigit() or (len(su) > 1 and su[0] == "F" and su[1:].isdigit()):
        return su if su else s
    # Buscar por nombre (ej. Plaza Hacienda -> 402)
    low = s.lower()
    for nombre, cod in NOMBRE_A_CODIGO.items():
        if nombre in low or low in nombre:
            return cod
    return s


def _normalizar_nombres(df):
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
    return df


def _detectar_col(df, candidatos):
    for c in candidatos:
        for col in df.columns:
            if col.strip().lower() == c.strip().lower():
                return col
    return None


def listar_archivos_ftp():
    """Conecta al FTP, lista .xlsx en la carpeta y devuelve (lista_nombres, ftp o None)."""
    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=60)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(False)
        ftp.cwd(CARPETA_OBJETIVO)
        todos = ftp.nlst()
        archivos = [f for f in todos if f.lower().endswith(".xlsx") and not f.startswith("~$")]
        archivos.sort()
        return archivos, ftp
    except Exception as e:
        print("Error de conexion FTP:", e)
        return [], None


def extraer_ventas_desde_excel(bio):
    df = pd.read_excel(bio, sheet_name=0)
    df = _normalizar_nombres(df)
    col_co = _detectar_col(df, COL_CO)
    col_fecha = _detectar_col(df, COL_FECHA)
    col_venta = _detectar_col(df, COL_VENTA)
    if not col_co or not col_fecha or not col_venta:
        return None, df.columns.tolist()
    out = pd.DataFrame()
    out["Co"] = df[col_co].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["Fecha"] = pd.to_datetime(df[col_fecha], dayfirst=True, errors="coerce").dt.date
    out["VentaNeta"] = pd.to_numeric(df[col_venta], errors="coerce").fillna(0)
    out = out.dropna(subset=["Fecha"])
    return out, None


def main():
    cargar = "--cargar" in sys.argv or "-c" in sys.argv

    print("Iniciando en:", CARPETA_OBJETIVO)
    archivos, ftp = listar_archivos_ftp()

    if not archivos:
        print("No se encontraron archivos .xlsx en esa carpeta.")
        if ftp:
            ftp.quit()
        return

    print("\n--- Archivos .xlsx en la carpeta ---")
    for i, nombre in enumerate(archivos, 1):
        print(f"  {i}. {nombre}")
    print(f"\nTotal: {len(archivos)} archivos.\n")

    if not cargar:
        if ftp:
            ftp.quit()
        print("Para descargar uno por uno y reemplazar todo el historico 2025 en la BD, ejecute:")
        print("  python listar_ftp_ventas_2025.py --cargar")
        return

    # Descargar de a uno, extraer, acumular; luego reemplazar todo en BD
    from database import engine_local

    codigos_ok = {"2", "3", "4", "201", "301", "304", "305", "401", "402", "404", "405", "502", "604", "611", "612", "615", "702", "F04", "F05", "F08", "F09"}
    listado_dfs = []
    for nombre in archivos:
        try:
            bio = io.BytesIO()
            ftp.retrbinary("RETR " + nombre, bio.write)
            bio.seek(0)
            df, cols_err = extraer_ventas_desde_excel(bio)
            if df is None:
                print("  ", nombre, "-> columnas no detectadas. Encontradas:", (cols_err or [])[:10])
                continue
            cod_desde_nombre = None
            for frag, cod in FILENAME_A_CODIGO:
                if frag in nombre.upper():
                    cod_desde_nombre = cod
                    break
            if cod_desde_nombre is not None:
                df["Co"] = cod_desde_nombre
                print("  ", nombre, "-> Co por nombre de archivo:", cod_desde_nombre)
            else:
                df["Co"] = df["Co"].apply(_co_a_codigo)
            print("  ", nombre, "-> filas:", len(df), "| Co unicos:", df["Co"].nunique())
            listado_dfs.append(df)
        except Exception as e:
            print("  ", nombre, "-> Error:", e)
    ftp.quit()

    if not listado_dfs:
        print("Ningun archivo pudo leerse. No se modifica la BD.")
        return

    # Un solo DataFrame con todo; normalizar Co (nombre -> codigo, ej. Plaza Hacienda -> 402)
    combinado = pd.concat(listado_dfs, ignore_index=True)
    combinado["Co"] = combinado["Co"].apply(_co_a_codigo)
    agrupado = combinado.groupby(["Co", "Fecha"], as_index=False)["VentaNeta"].sum()
    agrupado = agrupado.sort_values(["Co", "Fecha"])

    # Agrupacion desde BD
    try:
        lookup = pd.read_sql(text("SELECT store_id, grupo FROM sede_grupo_lookup"), con=engine_local)
        grupos = dict(zip(
            lookup["store_id"].astype(str).str.strip().str.upper().str.lstrip("0"),
            lookup["grupo"]
        ))
    except Exception:
        grupos = {"2": "RBB", "3": "RBB", "401": "PLAZAS", "402": "PLAZAS", "404": "PLAZAS", "405": "PLAZAS"}

    def grupo(c):
        return grupos.get(str(c).strip().upper().lstrip("0"), "OTRO")

    agrupado["StoreID_External"] = agrupado["Co"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    agrupado["Agrupacion"] = agrupado["StoreID_External"].apply(grupo)
    agrupado["Sede_Excel"] = "FTP_Ventas_2025"
    agrupado["Escenario"] = "Historico_Diario"
    agrupado["Ventas"] = agrupado["VentaNeta"]
    agrupado["Transacciones"] = 0.0
    agrupado["Ticket_Promedio"] = 0.0
    df_carga = agrupado[["StoreID_External", "Sede_Excel", "Agrupacion", "Fecha", "Escenario", "Ventas", "Transacciones", "Ticket_Promedio"]]

    # Reemplazar TODO el contenido de Historico_Diario (no juntar con lo existente)
    with engine_local.connect() as conn:
        conn.execute(text("DELETE FROM hechos_excel_diario WHERE Escenario = 'Historico_Diario'"))
        conn.commit()
    df_carga.to_sql("hechos_excel_diario", con=engine_local, if_exists="append", index=False)

    print("\nOK Historico_Diario reemplazado por completo. Registros cargados:", len(df_carga))
    print("Centros (Co) con dato:", sorted(agrupado["StoreID_External"].unique().tolist()))
    # Validación PLAZAS (pestaña 2 comparativo 2025)
    CODIGOS_PLAZAS = {"401", "402", "404", "405"}
    co_presentes = set(agrupado["StoreID_External"].astype(str).str.strip().str.upper().str.lstrip("0"))
    plazas_ok = CODIGOS_PLAZAS & co_presentes
    plazas_faltan = CODIGOS_PLAZAS - co_presentes
    print("--- Validación PLAZAS (401 Retiro, 402 Hacienda, 404 Gran Estación, 405 Santafe) ---")
    print("  Presentes con dato:", sorted(plazas_ok) if plazas_ok else "ninguno")
    if plazas_faltan:
        print("  Faltan (saldrán $0 en pestaña 2):", sorted(plazas_faltan))


if __name__ == "__main__":
    main()
