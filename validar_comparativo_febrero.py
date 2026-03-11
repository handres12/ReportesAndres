"""
Validación: comparativo ACR y ADC, febrero 2026 (días 1 a 27).
Compara datos de bi_local_data.db contra totales de referencia del archivo 'Suma de Venta Restaurante'.
Venta Neta = VlrBruto - ABS(VlrTotalDesc).
"""
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Totales de referencia del archivo (Suma de Venta Restaurante, feb 1-27)
REFERENCIA_ACR_TOTAL = 2_141_306_106
REFERENCIA_ADC_TOTAL = 4_558_983_618
# Detalle diario referencia: Día -> (ACR, ADC)
REFERENCIA_DIARIO = {
    1: (146_740_493, 144_831_091),
    2: (0, 79_479_649),
    3: (20_779_551, 126_429_728),
    4: (26_568_758, 189_023_858),
    5: (38_933_577, 134_034_590),
    6: (77_746_764, 193_817_651),
    7: (213_703_638, 216_923_646),
    8: (165_284_837, 134_401_392),
    9: (0, 92_169_407),
    10: (24_302_207, 167_210_797),
    11: (20_969_790, 106_052_590),
    12: (40_976_437, 170_338_076),
    13: (66_720_240, 230_961_327),
    14: (311_196_583, 310_981_564),
    15: (195_895_978, 199_325_796),
    16: (0, 96_495_025),
    17: (21_684_662, 112_331_179),
    18: (21_331_466, 121_520_358),
    19: (57_138_367, 132_910_954),
    20: (97_119_092, 207_216_638),
    21: (188_398_699, 202_900_646),
    22: (166_652_503, 130_842_731),
    23: (0, 131_051_275),
    24: (20_453_829, 145_932_337),
    25: (75_646_383, 212_142_798),
    26: (51_435_052, 272_112_350),
    27: (91_627_200, 297_546_165),
}

def main():
    db_url = os.getenv("LOCAL_DB_URL", "sqlite:///./bi_local_data.db")
    engine = create_engine(db_url)

    query = """
    SELECT
        LTRIM(UPPER(TRIM(CAST(StoreID AS TEXT))), '0') AS codigo_sede_crudo,
        CAST(STRFTIME('%d', Fecha) AS INTEGER) AS dia,
        SUM(VlrBruto) AS VlrBruto,
        SUM(VlrTotalDesc) AS VlrTotalDesc
    FROM raw_ventas_2026
    WHERE Fecha >= '2026-02-01' AND Fecha <= '2026-02-27'
      AND (LTRIM(UPPER(TRIM(CAST(StoreID AS TEXT))), '0') = '2' OR LTRIM(UPPER(TRIM(CAST(StoreID AS TEXT))), '0') = '3')
    GROUP BY 1, 2
    ORDER BY dia, codigo_sede_crudo
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
    except Exception as e:
        print(f"Error leyendo BD: {e}")
        return

    if df.empty:
        print("No hay registros en raw_ventas_2026 para feb 2026 (ACR/ADC). Ejecuta etl_sql.py.")
        return

    df["Venta_Neta"] = df["VlrBruto"] - df["VlrTotalDesc"].abs()
    # Pivot: filas = dia, columnas = ACR (2), ADC (3)
    cod_to_sede = {"2": "ACR", "3": "ADC"}
    df["Sede"] = df["codigo_sede_crudo"].map(cod_to_sede)
    pivot = df.pivot_table(index="dia", columns="Sede", values="Venta_Neta", aggfunc="sum").reindex(columns=["ACR", "ADC"])
    pivot = pivot.reindex(range(1, 28)).fillna(0)

    # Tabla comparativa: DÍA | ACR (BD) | ACR (Ref) | Diff ACR | ADC (BD) | ADC (Ref) | Diff ADC
    filas = []
    for d in range(1, 28):
        acr_bd = pivot.loc[d, "ACR"] if d in pivot.index else 0
        adc_bd = pivot.loc[d, "ADC"] if d in pivot.index else 0
        acr_ref, adc_ref = REFERENCIA_DIARIO.get(d, (0, 0))
        filas.append({
            "DIA": d,
            "ACR_BD": round(acr_bd, 0),
            "ACR_Ref": acr_ref,
            "Diff_ACR": round(acr_bd - acr_ref, 0),
            "ADC_BD": round(adc_bd, 0),
            "ADC_Ref": adc_ref,
            "Diff_ADC": round(adc_bd - adc_ref, 0),
        })
    tabla = pd.DataFrame(filas)

    acr_total_bd = tabla["ACR_BD"].sum()
    adc_total_bd = tabla["ADC_BD"].sum()
    diff_acr = acr_total_bd - REFERENCIA_ACR_TOTAL
    diff_adc = adc_total_bd - REFERENCIA_ADC_TOTAL

    # Salida
    print("=" * 80)
    print("VALIDACION COMPARATIVO ACR / ADC - FEBRERO 2026 (DIAS 1-27)")
    print("Venta Neta = VlrBruto - ABS(VlrTotalDesc). Fuente BD: raw_ventas_2026")
    print("=" * 80)
    print()
    print("Tabla diaria (BD vs Referencia):")
    pd.set_option("display.max_rows", 35)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:,.0f}".replace(",", "."))
    print(tabla.to_string(index=False))
    print()
    print("Total general:")
    print(f"  ACR  BD: {acr_total_bd:,.0f}".replace(",", ".") + f"  |  Ref: {REFERENCIA_ACR_TOTAL:,.0f}".replace(",", ".") + f"  |  Diff: {diff_acr:+,.0f}".replace(",", "."))
    print(f"  ADC  BD: {adc_total_bd:,.0f}".replace(",", ".") + f"  |  Ref: {REFERENCIA_ADC_TOTAL:,.0f}".replace(",", ".") + f"  |  Diff: {diff_adc:+,.0f}".replace(",", "."))
    print()
    if abs(diff_acr) < 1 and abs(diff_adc) < 1:
        print("OK Totales coinciden con el archivo de referencia.")
    else:
        print("REVISAR: Hay diferencias vs el archivo de referencia (redondeo o origen de datos).")
    print()
    # Exportar a Excel para revisión
    out = "Validacion_ACR_ADC_Febrero_2026.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        tabla.to_excel(w, sheet_name="Dia_a_dia", index=False)
        pd.DataFrame([
            {"Sede": "ACR", "Total_BD": acr_total_bd, "Total_Ref": REFERENCIA_ACR_TOTAL, "Diff": diff_acr},
            {"Sede": "ADC", "Total_BD": adc_total_bd, "Total_Ref": REFERENCIA_ADC_TOTAL, "Diff": diff_adc},
        ]).to_excel(w, sheet_name="Totales", index=False)
    print(f"Detalle exportado a: {out}")

if __name__ == "__main__":
    main()
