import pandas as pd
import os
from sqlalchemy import create_engine, text

def validar_ventas_diarias():
    print("Iniciando validador de datos crudos (SQLite: raw_ventas_2026)...")
    db_url = os.getenv("LOCAL_DB_URL", "sqlite:///./bi_local_data.db")
    engine = create_engine(db_url)
    
    # Extraemos el código exacto, mes, día y valores consolidados
    query = """
    SELECT 
        TRIM(CAST(StoreID AS TEXT)) AS Sede_Cruda_En_BD,
        STRFTIME('%Y-%m', Fecha) AS Mes,
        STRFTIME('%Y-%m-%d', Fecha) AS Dia,
        SUM(VlrBruto) AS Suma_Bruto,
        SUM(VlrTotalDesc) AS Suma_Descuentos,
        SUM(VlrBruto) - ABS(SUM(VlrTotalDesc)) AS Venta_Neta_Calculada
    FROM raw_ventas_2026
    WHERE Fecha >= '2026-01-01' AND Fecha <= '2026-03-08'
    GROUP BY 
        TRIM(CAST(StoreID AS TEXT)),
        STRFTIME('%Y-%m', Fecha),
        STRFTIME('%Y-%m-%d', Fecha)
    ORDER BY 
        Sede_Cruda_En_BD, 
        Dia
    """
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
            
        if df.empty:
            print("❌ La consulta no arrojó resultados. La tabla raw_ventas_2026 está vacía o las fechas consultadas no existen.")
            return

        print(f"✅ Se encontraron {len(df)} registros. Generando validación...")
        
        # 1. Exportar el detalle exacto por DÍA a Excel
        archivo_salida = "Validacion_Ventas_Ene_Mar_2026.xlsx"
        df.to_excel(archivo_salida, index=False)
        
        # 2. Imprimir resumen en consola agrupado por MES
        print("\n--- RESUMEN DE VENTAS NETAS POR SEDE Y MES ---")
        resumen_mes = df.groupby(['Sede_Cruda_En_BD', 'Mes'])['Venta_Neta_Calculada'].sum().reset_index()
        
        # Formato moneda para facilitar lectura en consola
        resumen_mes['Venta_Neta_Calculada'] = resumen_mes['Venta_Neta_Calculada'].apply(lambda x: f"${x:,.0f}".replace(",", "."))
        print(resumen_mes.to_string(index=False))
        
        print(f"\n✅ Detalle diario exportado con éxito a: {archivo_salida}")
        print("⚠️ REVISA LA COLUMNA 'Sede_Cruda_En_BD'. Dependiendo de si trae ceros a la izquierda o no (ej. '002' vs '2'), ajustaremos el JOIN en app.py.")
        
    except Exception as e:
        print(f"❌ Error al consultar la base de datos: {e}")

if __name__ == "__main__":
    validar_ventas_diarias()