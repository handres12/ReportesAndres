import os
import urllib
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# ---------------------------------------------------------
# 1. CONFIGURACIÓN BD ORIGEN PRINCIPAL (Integracion-GrupoIGA-Micros)
# ---------------------------------------------------------
SQL_SERVER_HOST = os.getenv("SQL_SERVER_HOST")
SQL_SERVER_USER = os.getenv("SQL_SERVER_USER")
SQL_SERVER_PASS = os.getenv("SQL_SERVER_PASS")
SQL_SERVER_DB = os.getenv("SQL_SERVER_DB")

params_prin = urllib.parse.quote_plus(
    f"DRIVER={{SQL Server}};"
    f"SERVER={SQL_SERVER_HOST};"
    f"DATABASE={SQL_SERVER_DB};"
    f"UID={SQL_SERVER_USER};"
    f"PWD={SQL_SERVER_PASS}"
)
SQL_SERVER_URL = f"mssql+pyodbc:///?odbc_connect={params_prin}"

try:
    engine_sql_server = create_engine(SQL_SERVER_URL, echo=False)
except Exception as e:
    print(f"Error engine principal: {e}")

# ---------------------------------------------------------
# 2. CONFIGURACIÓN BD ORIGEN SECUNDARIA (NEWACRVentas)
# ---------------------------------------------------------
# Tomamos el nombre de la variable de entorno, si no existe usamos por defecto NEWACRVentas
SQL_SERVER_DB_SEC = os.getenv("SQL_SERVER_DB_SEC", "NEWACRVentas")

params_sec = urllib.parse.quote_plus(
    f"DRIVER={{SQL Server}};"
    f"SERVER={SQL_SERVER_HOST};"
    f"DATABASE={SQL_SERVER_DB_SEC};"
    f"UID={SQL_SERVER_USER};"
    f"PWD={SQL_SERVER_PASS}"
)
SQL_SERVER_SEC_URL = f"mssql+pyodbc:///?odbc_connect={params_sec}"

try:
    # Este es el nuevo motor para conectarnos a las tablas maestras
    engine_sql_server_sec = create_engine(SQL_SERVER_SEC_URL, echo=False)
except Exception as e:
    print(f"Error engine secundario: {e}")

# ---------------------------------------------------------
# 3. CONFIGURACIÓN BASE DE DATOS DESTINO (LOCAL)
# ---------------------------------------------------------
LOCAL_DB_URL = os.getenv("LOCAL_DB_URL", "sqlite:///./bi_local_data.db")

engine_local = create_engine(
    LOCAL_DB_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in LOCAL_DB_URL else {},
    echo=False
)

SessionLocalDB = sessionmaker(autocommit=False, autoflush=False, bind=engine_local)
BaseLocal = declarative_base()

def get_local_db():
    db = SessionLocalDB()
    try:
        yield db
    finally:
        db.close()