import pandas as pd
import os
from sqlalchemy import create_engine, text

def ejecutar_auditoria():
    print("🔍 INICIANDO AUDITORÍA DE INTEGRIDAD - BI ANDRÉS...")
    db_url = os.getenv("LOCAL_DB_URL", "sqlite:///./bi_local_data.db")
    engine = create_engine(db_url)
    
    queries = {
        "Ventas sin Sede": """
            SELECT DISTINCT v.StoreID 
            FROM raw_ventas_2026 v
            LEFT JOIN dim_store s ON LTRIM(UPPER(TRIM(v.StoreID)), '0') = LTRIM(UPPER(TRIM(s.StoreID_External)), '0')
            WHERE s.StoreID_External IS NULL
        """,
        "Invoices sin Sede": """
            SELECT DISTINCT i.StoreID 
            FROM raw_invoice_2026 i
            LEFT JOIN dim_store s ON TRIM(i.StoreID) = TRIM(s.StoreID)
            WHERE s.StoreID IS NULL
        """,
        "Sedes en Excel sin Mapeo": """
            SELECT DISTINCT StoreID_External 
            FROM hechos_excel_diario 
            WHERE StoreID_External NOT IN (SELECT StoreID_External FROM dim_store)
        """
    }
    
    errores_encontrados = 0
    
    with engine.connect() as conn:
        for nombre, sql in queries.items():
            res = pd.read_sql(text(sql), con=conn)
            if not res.empty:
                print(f"❌ ERROR: {nombre} detectados!")
                print(res)
                errores_encontrados += 1
            else:
                print(f"✅ {nombre}: OK")
                
    if errores_encontrados == 0:
        print("\n💎 BLINDAJE TOTAL: Los datos están perfectamente cruzados.")
    else:
        print(f"\n⚠️ ATENCIÓN: Se encontraron {errores_encontrados} inconsistencias que causarán ceros en el Dashboard.")

if __name__ == "__main__":
    ejecutar_auditoria()