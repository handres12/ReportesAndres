"""
Diagnóstico: por qué no salen transacciones en el informe.
Ejecutar: python check_transacciones.py
No modifica la app; solo lee SQLite y muestra resultados.
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("LOCAL_DB_URL", "sqlite:///bi_local_data.db")
if "sqlite" in db_url and not db_url.replace("sqlite:///", "").startswith("/"):
    base = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base, "bi_local_data.db")
    db_url = f"sqlite:///{db_path}"
engine = create_engine(db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})

def run(q, name):
    try:
        with engine.connect() as conn:
            r = conn.execute(text(q))
            rows = r.fetchall()
        return rows
    except Exception as e:
        print(f"  Error en {name}: {e}")
        return None

print("=== Diagnóstico: transacciones en 0 ===\n")

# 1. ¿Hay Invoice?
r = run("SELECT COUNT(*) FROM raw_invoice_2026", "raw_invoice_2026")
if r is None:
    print("No se pudo leer raw_invoice_2026 (¿existe la tabla?). Ejecuta: python etl_maestros.py")
elif r[0][0] == 0:
    print("raw_invoice_2026 está vacía. Ejecuta: python etl_maestros.py (y revisa que NEWACRVentas tenga datos en Invoice para 2026).")
else:
    print(f"OK raw_invoice_2026: {r[0][0]} filas.")

# 2. ¿Hay dim_store?
r = run("SELECT COUNT(*) FROM dim_store", "dim_store")
if r is None:
    print("No se pudo leer dim_store. Ejecuta: python etl_maestros.py")
elif r[0][0] == 0:
    print("dim_store está vacía. Ejecuta: python etl_maestros.py")
else:
    print(f"OK dim_store: {r[0][0]} filas.")

# 3. ¿El JOIN Invoice–Store devuelve filas?
q_join = """
SELECT 
    LTRIM(UPPER(TRIM(CAST(COALESCE(s.StoreID_External, '') AS TEXT))), '0') AS codigo_sede_crudo,
    DATE(i.BusinessDate) AS Fecha,
    COUNT(DISTINCT i.InvoiceID) AS Cantidad_Transacciones
FROM raw_invoice_2026 i
INNER JOIN dim_store s ON TRIM(CAST(COALESCE(i.StoreID, '') AS TEXT)) = TRIM(CAST(COALESCE(s.StoreID, '') AS TEXT))
WHERE i.InvoiceID IS NOT NULL AND TRIM(CAST(COALESCE(s.StoreID_External, '') AS TEXT)) <> ''
GROUP BY 1, 2
LIMIT 5
"""
r = run(q_join, "JOIN Invoice–Store")
if r is not None:
    if len(r) == 0:
        print("El JOIN entre raw_invoice_2026 y dim_store no devuelve filas.")
        print("  Posibles causas: StoreID en Invoice no coincide con StoreID en Store (revisar tipos/espacios); o StoreID_External está vacío en dim_store.")
        # Muestra muestras de ambos
        r_inv = run("SELECT DISTINCT StoreID FROM raw_invoice_2026 LIMIT 5", "sample Invoice.StoreID")
        r_st = run("SELECT StoreID, StoreID_External FROM dim_store LIMIT 10", "sample dim_store")
        if r_inv:
            print("  Muestra Invoice.StoreID:", [x[0] for x in r_inv])
        if r_st:
            print("  Muestra dim_store (StoreID, StoreID_External):", [(x[0], x[1]) for x in r_st])
    else:
        print("OK El JOIN devuelve transacciones por sede/fecha. Ejemplo:", r[:3])

# 4. ¿Co de ventas coincide con Co de transacciones?
r_ventas_co = run("SELECT DISTINCT LTRIM(UPPER(TRIM(CAST(StoreID AS TEXT))), '0') AS co FROM raw_ventas_2026 LIMIT 20", "ventas Co")
if r_ventas_co:
    cos_ventas = {x[0] for x in r_ventas_co}
    r_trans_co = run("""
        SELECT DISTINCT LTRIM(UPPER(TRIM(CAST(s.StoreID_External AS TEXT))), '0') AS co
        FROM raw_invoice_2026 i
        INNER JOIN dim_store s ON TRIM(CAST(COALESCE(i.StoreID, '') AS TEXT)) = TRIM(CAST(COALESCE(s.StoreID, '') AS TEXT))
        WHERE TRIM(CAST(COALESCE(s.StoreID_External, '') AS TEXT)) <> ''
    """, "transacciones Co")
    if r_trans_co:
        cos_trans = {x[0] for x in r_trans_co}
        comunes = cos_ventas & cos_trans
        if not comunes:
            print("Los códigos de sede (Co) de ventas y de transacciones no coinciden.")
            print("  Co en ventas (raw_ventas_2026):", sorted(cos_ventas)[:15])
            print("  Co en transacciones (StoreID_External):", sorted(cos_trans)[:15])
        else:
            print("OK Hay Co en común entre ventas y transacciones:", sorted(comunes)[:10])

print("\n=== Fin diagnóstico ===")
