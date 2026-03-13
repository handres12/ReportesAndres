import pandas as pd
import calendar
from datetime import date
from sqlalchemy import text
from database import engine_local, SessionLocalDB
import os

MESES_MAP = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
}

# 🎯 DICCIONARIO MAESTRO CON TODAS LAS VARIACIONES DE NOMBRES
SEDES_MAP = {
    'ACR': '002', 'ANDRES CHIA': '002', 'ANDRES CARNE DE RES CHIA': '002',
    'ADC': '003', 'ANDRES ADC': '003', 'ANDRES DC BOGOTA': '003', 'ANDRES D.C.': '003',
    'CARTAGENA': 'F08', 'ANDRES CARTAGENA': 'F08',
    'MEDELLIN': '201', 'ANDRES MEDELLIN': '201', 'ANDRÉS MEDELLÍN': '201',
    'GRAN ESTACIÓN': '404', 'PLAZA GRAN ESTACIÓN': '404', 'PLAZA GRAN ESTACION': '404', 'PLAZA G.ESTACION': '404',
    'HACIENDA': '402', 'PLAZA HACIENDA SANTA BARBARA': '402', 'PLAZA HACIENDA': '402',
    'RETIRO': '401', 'PLAZA RETIRO': '401', 'PLAZA CENTRO COMERCIAL RETIRO': '401', 'PLAZA EL RETIRO': '401',
    'SANTAFÉ': '405', 'PLAZA SANTA FE': '405', 'PLAZA CENTRO COMERCIAL SANTA FE': '405', 'SANTAFE': '405', 'PLAZA SANTAFE': '405', 'PLAZA CC. SANTA FÉ': '405',
    'BAZAAR': 'F09', 'BAZAR80': 'F09', 'FRANQUICIA BAZZAR80': 'F09', 'BAZAAR 80': 'F09',
    'HYATT': 'F05', 'HOTEL HYATT': 'F05', 'FRANQUICIA HYATT': 'F05',
    'PLAZA CLARO': 'F04', 'FRANQUICIA PLAZA CLARO': 'F04',
    'AEROPUERTO': '301', 'ANDRES AEROPUERTO': '301', 'AEROPUERTO EL DORADO': '301', 'ANDRES PARADERO AEROPUERTO INTERNACIONAL': '301',
    'ANDRES VIAJERO': '304', 'PLAZA ANDRES VIAJERO': '304', 'ANDRÉS PARADERO VIAJERO': '304', 'VIAJERO': '304', 'ORLEANS': '304',
    'RIONEGRO': '305', 'ANDRES RIONEGRO': '305', 'AEROPUERTO RIO NEGRO': '305', 'AEROPUERTO RIONEGRO': '305', 'ANDRES PARADERO AEROPUERTO RIONEGRO': '305',
    'CAFAM': '611', 'AEX CAFAM': '611', 'CAFAM FLORESTA': '611',
    'CALLE 93': '502', 'AEX CALL E93': '502', 'AEX CALLE 93': '502', 'CONT.CL93': '502',
    'CASA DE LOS ANDES': '612', 'AEX CASA ANDES': '612', 'ANDES': '612',
    'EXPRÉS PARADERO': '004', 'ANDRES PARADERO CHIA': '004', 'ANDRES EXPRÉS': '004', 'EXPRES PARADERO': '004', 'ANDRES EXPRES': '004', 'AEXP': '004', 'AEX LA CALERA PARADERO': '004',
    'MULTIPARQUE': '702', 'AEX MULTIPARQUE': '702', 'AEX MULTIPARQUE PARADERO': '702',
    'PALATINO': '604', 'ANDRES PALATINO': '604',
    'PEPE SIERRA': '615', 'PLAZA PEPE SIERRA': '615', 'AEX PEPE SIERRA': '615'
}

def obtener_rutas():
    carpetas_a_buscar = [os.path.join(os.getcwd(), "fuentes_excel"), os.getcwd()]
    todos_los_archivos = []
    
    for carpeta in carpetas_a_buscar:
        if os.path.exists(carpeta):
            for f in os.listdir(carpeta):
                if os.path.isfile(os.path.join(carpeta, f)) and not f.startswith('~$') and ('.csv' in f.lower() or '.xlsx' in f.lower()):
                    todos_los_archivos.append((carpeta, f))
                    
    r_ventas = r_trans = r_presup = r_2025 = None
    
    for carpeta, f in todos_los_archivos:
        f_low = f.lower()
        ruta = os.path.join(carpeta, f)
        
        if "presupuesto" in f_low and not r_presup: r_presup = ruta
        elif "transacciones" in f_low and not r_trans: r_trans = ruta
        elif ("2025" in f_low or "dia" in f_low) and not r_2025: r_2025 = ruta
        elif "ventas" in f_low and "2025" not in f_low and "dia" not in f_low and not r_ventas: r_ventas = ruta
            
    return r_ventas, r_trans, r_presup, r_2025


def obtener_ruta_pp_2026_dia():
    """Busca 'PP 2026 x día' (presupuesto 2026 por día) en raíz y fuentes_excel."""
    carpetas = [os.getcwd(), os.path.join(os.getcwd(), "fuentes_excel")]
    for carpeta in carpetas:
        if not os.path.exists(carpeta):
            continue
        for f in os.listdir(carpeta):
            if f.startswith("~$") or not (f.lower().endswith(".xlsx") or f.lower().endswith(".xls")):
                continue
            f_low = f.lower()
            if "pp" in f_low and "2026" in f_low and ("dia" in f_low or "día" in f_low):
                return os.path.join(carpeta, f)
    return None


def procesar_presupuesto_diario_2026(ruta_archivo):
    """
    Lee Excel PP 2026 x día: columnas FECHA, Co, CASA, DIA, PPTO DIARIO.
    Co se cruza con StoreID_External. Retorna filas para hechos_excel_diario (Escenario Presupuesto_Diario_2026).
    """
    if not ruta_archivo or not os.path.isfile(ruta_archivo):
        return pd.DataFrame()
    try:
        df = pd.read_excel(ruta_archivo, header=0)
    except Exception as e:
        print(f"[X] Error leyendo PP 2026 x día {ruta_archivo}: {e}")
        return pd.DataFrame()
    df.columns = [str(c).strip() for c in df.columns]
    col_ppto = None
    for c in df.columns:
        if "ppto" in c.lower() and "diario" in c.lower():
            col_ppto = c
            break
    if col_ppto is None or "Co" not in df.columns or "FECHA" not in df.columns:
        print("[!] PP 2026 x día: se esperan columnas FECHA, Co y PPTO DIARIO. Encontradas:", list(df.columns))
        return pd.DataFrame()
    df["Fecha"] = pd.to_datetime(df["FECHA"], errors="coerce").dt.date
    df = df.dropna(subset=["Fecha"])
    df["StoreID_External"] = df["Co"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["Ventas"] = pd.to_numeric(df[col_ppto], errors="coerce").fillna(0)
    df["Sede_Excel"] = df["CASA"].astype(str).str.strip() if "CASA" in df.columns else df["StoreID_External"]
    df["Escenario"] = "Presupuesto_Diario_2026"
    df["Transacciones"] = 0
    df["Ticket_Promedio"] = 0
    out = df[["StoreID_External", "Sede_Excel", "Fecha", "Escenario", "Ventas", "Transacciones", "Ticket_Promedio"]].copy()
    return out

def leer_archivo_robusto(ruta, header_val=0, sep_val=','):
    if not ruta: return pd.DataFrame()
    try:
        if str(ruta).endswith('.xlsx'):
            return pd.read_excel(ruta, header=header_val)
        else:
            try:
                return pd.read_csv(ruta, header=header_val, sep=sep_val, encoding='utf-8', low_memory=False)
            except UnicodeDecodeError:
                return pd.read_csv(ruta, header=header_val, sep=sep_val, encoding='latin-1', low_memory=False)
    except Exception as e:
        print(f"[X] Error leyendo {ruta}: {e}")
        return pd.DataFrame()

def procesar_presupuesto(ruta_archivo):
    if not ruta_archivo: return pd.DataFrame()
    df_raw = leer_archivo_robusto(ruta_archivo, header_val=None)
    if df_raw.empty: return df_raw
    
    df_data = df_raw.iloc[2:].copy()
    df_clean = pd.DataFrame({
        'Punto de venta': df_data.iloc[:, 1],
        'Mes': df_data.iloc[:, 2],
        'Anio': 2026,
        'Ventas': pd.to_numeric(df_data.iloc[:, 9], errors='coerce').fillna(0),
        'Transacciones': pd.to_numeric(df_data.iloc[:, 7], errors='coerce').fillna(0)
    })
    return df_clean.dropna(subset=['Punto de venta', 'Mes'])

def procesar_historico_mensual(ruta_archivo, nombre_valor):
    if not ruta_archivo: return pd.DataFrame()
    df = leer_archivo_robusto(ruta_archivo, header_val=1)
    if df.empty: return df
    
    df = df.dropna(subset=['Punto de venta', 'Mes'])
    df = df[~df['Punto de venta'].str.contains('Total', case=False, na=False)]
    
    df_melt = df.melt(id_vars=['Punto de venta', 'Mes'], var_name='Anio', value_name='Valor')
    df_melt['Anio'] = pd.to_numeric(df_melt['Anio'], errors='coerce')
    df_melt['Valor'] = pd.to_numeric(df_melt['Valor'], errors='coerce').fillna(0)
    df_melt = df_melt.dropna(subset=['Anio'])
    df_melt = df_melt[df_melt['Anio'] != 2025]
    return df_melt.rename(columns={'Valor': nombre_valor})

def procesar_diario_2025(ruta_archivo):
    if not ruta_archivo: return pd.DataFrame()
    # CSV historico 2025: separador ; y puede tener BOM en cabecera (Co -> ﻿Co)
    try:
        df = pd.read_csv(ruta_archivo, sep=';', encoding='utf-8-sig', header=0, low_memory=False)
    except Exception as e:
        df = leer_archivo_robusto(ruta_archivo, header_val=0, sep_val=';')
    if df.empty: return df
    # Normalizar nombres de columnas (quitar BOM u otros caracteres)
    df.columns = [str(c).strip().lstrip('\ufeff') for c in df.columns]
    if 'Co' not in df.columns or 'Fecha' not in df.columns or 'VentaNeta' not in df.columns:
        print("  Advertencia: CSV 2025 debe tener columnas Co, Fecha, VentaNeta. Encontradas:", list(df.columns)[:5])
        return pd.DataFrame()
    df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce').dt.date
    df = df.dropna(subset=['Fecha'])
    df['StoreID_External'] = df['Co'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    df['VentaNeta'] = pd.to_numeric(df['VentaNeta'], errors='coerce').fillna(0)
    
    df_agrupado = df.groupby(['StoreID_External', 'Fecha'], as_index=False).agg({'VentaNeta': 'sum'})
    df_agrupado['Sede_Excel'] = 'Cargado_Desde_Micros_2025'
    df_agrupado['Escenario'] = 'Historico_Diario'
    df_agrupado['Transacciones'] = 0 
    df_agrupado['Ticket_Promedio'] = 0
    return df_agrupado.rename(columns={'VentaNeta': 'Ventas'})

def diarizar_mensual(df_mensual, escenario):
    if df_mensual.empty: return pd.DataFrame()
    filas_diarias = []
    for _, row in df_mensual.iterrows():
        sede_excel = str(row['Punto de venta']).strip().upper()
        mes_str = str(row['Mes']).strip().lower()
        anio = int(row['Anio'])
        
        ventas_mes = row.get('Ventas', 0.0)
        transacciones_mes = row.get('Transacciones', 0.0)
        mes_num = MESES_MAP.get(mes_str)
        store_id_ext = SEDES_MAP.get(sede_excel, 'SIN_MAPEO')
        
        if not mes_num or store_id_ext == 'SIN_MAPEO': continue
            
        _, dias_en_mes = calendar.monthrange(anio, mes_num)
        ventas_dia = ventas_mes / dias_en_mes
        transacciones_dia = transacciones_mes / dias_en_mes
        ticket_dia = ventas_dia / transacciones_dia if transacciones_dia > 0 else 0
        
        for dia in range(1, dias_en_mes + 1):
            filas_diarias.append({
                'StoreID_External': store_id_ext,
                'Sede_Excel': row['Punto de venta'],
                'Fecha': date(anio, mes_num, dia),
                'Escenario': escenario,
                'Ventas': ventas_dia,
                'Transacciones': transacciones_dia,
                'Ticket_Promedio': ticket_dia
            })
    return pd.DataFrame(filas_diarias)

def ejecutar_etl():
    print("[OK] Iniciando extraccion robusta de Excel...\n")
    ruta_v_mensual, ruta_t_mensual, ruta_presup, ruta_2025 = obtener_rutas()
    
    if not all([ruta_v_mensual, ruta_t_mensual, ruta_presup]):
        print("[X] Faltan archivos por detectar (ventas mensual, transacciones, presupuesto).")
        return
    if not ruta_2025:
        print("[!] No se encontro archivo 2025 por dia; se conservara Historico_Diario ya cargado en BD (ej. desde FTP).")

    df_pres_mensual = procesar_presupuesto(ruta_presup)
    df_pres_diarizado = diarizar_mensual(df_pres_mensual, 'Presupuesto_Diarizado')

    df_v_mensual = procesar_historico_mensual(ruta_v_mensual, 'Ventas')
    df_t_mensual = procesar_historico_mensual(ruta_t_mensual, 'Transacciones')
    
    if not df_v_mensual.empty and not df_t_mensual.empty:
        df_hist_mensual = pd.merge(df_v_mensual, df_t_mensual, on=['Punto de venta', 'Mes', 'Anio'], how='outer').fillna(0)
    else:
        df_hist_mensual = pd.DataFrame()
        
    df_hist_diarizado = diarizar_mensual(df_hist_mensual, 'Historico_Diarizado')
    df_2025_exacto = procesar_diario_2025(ruta_2025) if ruta_2025 else pd.DataFrame()
    ruta_pp_2026_dia = obtener_ruta_pp_2026_dia()
    df_pp_2026_dia = procesar_presupuesto_diario_2026(ruta_pp_2026_dia) if ruta_pp_2026_dia else pd.DataFrame()
    if not df_pp_2026_dia.empty:
        print(f"[OK] Presupuesto diario 2026 (PP x día): {len(df_pp_2026_dia)} registros.")
    partes = [df_hist_diarizado, df_pres_diarizado, df_2025_exacto, df_pp_2026_dia]
    df_final = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    if df_final.empty:
        return

    # 🎯 MAPEO DE GRUPOS DESDE sede_grupo_lookup (fuente única)
    try:
        df_lookup = pd.read_sql(text("SELECT store_id, grupo FROM sede_grupo_lookup"), con=engine_local)
        GRUPOS_DESDE_BD = dict(zip(df_lookup["store_id"].astype(str).str.strip().str.upper().str.lstrip("0"), df_lookup["grupo"]))
    except Exception as e:
        print(f"[!] No se pudo cargar sede_grupo_lookup: {e}. Usando mapeo de respaldo.")
        GRUPOS_DESDE_BD = {
            '2': 'RBB', '3': 'RBB', 'F08': 'RBB', '201': 'RBB',
            '404': 'PLAZAS', '402': 'PLAZAS', '401': 'PLAZAS', '405': 'PLAZAS',
            'F09': 'PARADERO FR', 'F05': 'PARADERO FR', 'F04': 'PARADERO FR',
            '301': 'PARADERO', '304': 'PARADERO', '305': 'PARADERO',
            '611': 'EXPRÉS', '502': 'EXPRÉS', '612': 'EXPRÉS', '4': 'EXPRÉS', '004': 'EXPRÉS',
            '702': 'EXPRÉS', '604': 'EXPRÉS', '615': 'EXPRÉS'
        }

    def asignar_grupo_final(row):
        codigo = str(row['StoreID_External']).strip().upper().lstrip('0')
        return GRUPOS_DESDE_BD.get(codigo, 'OTRO')

    df_final['Agrupacion'] = df_final.apply(asignar_grupo_final, axis=1)

    # Solo reemplazar los escenarios que estamos cargando; preservar Historico_Diario si vino del FTP
    escenarios_a_borrar = ['Presupuesto_Diarizado', 'Historico_Diarizado', 'Presupuesto_Diario_2026']
    if not df_2025_exacto.empty:
        escenarios_a_borrar.append('Historico_Diario')
    placeholders = ", ".join([f"'{e}'" for e in escenarios_a_borrar])
    with engine_local.connect() as conn:
        conn.execute(text(f"DELETE FROM hechos_excel_diario WHERE Escenario IN ({placeholders})"))
        conn.commit()

    print(f"[OK] Guardando {len(df_final)} registros unificados...")
    df_final.to_sql('hechos_excel_diario', con=engine_local, if_exists='append', index=False)
    print("[OK] Consolidado con exito!")

if __name__ == "__main__":
    ejecutar_etl()