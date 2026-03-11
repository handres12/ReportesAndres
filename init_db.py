from database import engine_local, BaseLocal
from sqlalchemy import text
# Importamos models para que SQLAlchemy reconozca las clases antes de crear las tablas
import models

# Diccionario maestro: store_id (código normalizado sin ceros a la izquierda) -> (sede_nombre, grupo)
SEED_SEDE_GRUPO = [
    ("2", "ACR", "RBB"), ("3", "ADC", "RBB"), ("F08", "CARTAGENA", "RBB"), ("201", "MEDELLIN", "RBB"),
    ("404", "GRAN ESTACIÓN", "PLAZAS"), ("402", "HACIENDA", "PLAZAS"), ("401", "RETIRO", "PLAZAS"), ("405", "SANTAFÉ", "PLAZAS"),
    ("F09", "BAZAAR", "PARADERO FR"), ("F05", "HYATT", "PARADERO FR"), ("F04", "PLAZA CLARO", "PARADERO FR"),
    ("301", "AEROPUERTO", "PARADERO"), ("304", "ANDRES VIAJERO", "PARADERO"), ("305", "RIONEGRO", "PARADERO"),
    ("611", "CAFAM", "EXPRÉS"), ("502", "CALLE 93", "EXPRÉS"), ("612", "CASA DE LOS ANDES", "EXPRÉS"),
    ("4", "EXPRÉS PARADERO", "EXPRÉS"), ("702", "MULTIPARQUE", "EXPRÉS"), ("604", "PALATINO", "EXPRÉS"), ("615", "PEPE SIERRA", "EXPRÉS"),
]

def seed_sede_grupo_lookup():
    """Pobla sede_grupo_lookup si está vacía. store_id = código normalizado (LTRIM '0')."""
    with engine_local.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM sede_grupo_lookup")).scalar()
        if r and r > 0:
            return
        for store_id, sede, grupo in SEED_SEDE_GRUPO:
            conn.execute(text(
                "INSERT OR REPLACE INTO sede_grupo_lookup (store_id, sede, grupo) VALUES (:sid, :sede, :grupo)"
            ), {"sid": store_id, "sede": sede, "grupo": grupo})
        conn.commit()
    print("OK sede_grupo_lookup sembrada con mapeo maestro.")

def inicializar_base_datos():
    print("Iniciando conexion con la base de datos local...")
    BaseLocal.metadata.create_all(bind=engine_local)
    print("OK Tablas creadas.")
    seed_sede_grupo_lookup()

if __name__ == "__main__":
    inicializar_base_datos()