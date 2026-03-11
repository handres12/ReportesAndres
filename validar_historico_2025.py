"""
Valida el archivo Ventas_hist_2025_por dia (CSV) y por qué algunos restaurantes
salen con Venta 2025 = $0 en el dashboard.
- Lee el CSV (Co, Fecha, VentaNeta) y lista qué códigos Co existen.
- Compara con sede_grupo_lookup: si un restaurante está en el mapeo pero no en el CSV,
  ese restaurante mostrará $0 en 2025.
"""
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Códigos que esperamos por grupo (según blueprint)
ESPERADOS = {
    "RBB": ["2", "3", "F08", "201"],
    "PLAZAS": ["401", "402", "404", "405"],
    "PARADERO FR": ["F04", "F05", "F09"],
    "PARADERO": ["301", "304", "305"],
    "EXPRÉS": ["4", "502", "604", "611", "612", "702", "615"],
}

def main():
    # 1) Buscar archivo historico 2025
    nombre = "Ventas_hist_2025_por dia.csv.csv"
    rutas = [os.path.join(os.getcwd(), nombre), os.path.join(os.getcwd(), "fuentes_excel", nombre)]
    ruta = None
    for r in rutas:
        if os.path.isfile(r):
            ruta = r
            break
    if not ruta:
        print("No se encontro archivo:", nombre, "en raiz del proyecto ni en fuentes_excel.")
        return

    print("Leyendo CSV (muestra 2M filas para detectar Co)...")
    try:
        df = pd.read_csv(ruta, sep=";", encoding="utf-8-sig", usecols=[0, 1, 6], low_memory=False, nrows=2_000_000)
        df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
        if "Co" not in df.columns:
            df.columns = ["Co", "Fecha", "VentaNeta"]
    except Exception as e:
        print("Error leyendo CSV:", e)
        return

    df["Co"] = df["Co"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    co_en_csv = sorted(df["Co"].unique())
    print("\n--- CO DIGOS PRESENTES EN EL CSV (historico 2025) ---")
    print(co_en_csv)
    print("\nRango de fechas en muestra:", df["Fecha"].min(), "a", df["Fecha"].max())

    # 2) Qué sedes esperamos vs qué hay
    print("\n--- COMPARATIVO VS MAPEO ESPERADO ---")
    todos_esperados = []
    for grp, codigos in ESPERADOS.items():
        for c in codigos:
            todos_esperados.append((c, grp))
    faltan = []
    for co, grp in todos_esperados:
        if co not in co_en_csv:
            faltan.append((co, grp))
    if faltan:
        print("Restaurantes que NO aparecen en el CSV (por eso salen Venta 2025 = $0 en el informe):")
        for co, grp in faltan:
            print(f"  Co {co} ({grp})")
    else:
        print("Todos los codigos esperados estan en el CSV.")

    # 3) Qué hay en hechos_excel_diario para Historico_Diario
    db_url = os.getenv("LOCAL_DB_URL", "sqlite:///./bi_local_data.db")
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            q = """
            SELECT LTRIM(UPPER(TRIM(CAST(StoreID_External AS TEXT))), '0') AS co,
                   COUNT(*) AS filas, SUM(Ventas) AS total_ventas
            FROM hechos_excel_diario
            WHERE Escenario = 'Historico_Diario'
            GROUP BY 1 ORDER BY 1
            """
            bd = pd.read_sql(text(q), con=conn)
        print("\n--- HECHOS_EXCEL_DIARIO (Historico_Diario) ---")
        print(bd.to_string(index=False))
    except Exception as e:
        print("\nNo se pudo consultar hechos_excel_diario:", e)

    print("\nConclusion: Si PLAZAS (401,402,404,405) u otros no estan en el CSV, no hay dato 2025 para ellos.")
    print("El ETL ya usa separador ; y encoding utf-8-sig para este archivo.")

if __name__ == "__main__":
    main()
