# Dashboard BI - Andrés Carne de Res (redeploy 2025-03)
import streamlit as st
import pandas as pd
import os
import base64
import traceback
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from datetime import date, timedelta
import calendar

# auth se importa solo cuando hace falta (login en local), para no fallar en la nube
auth = None

# Cargar variables de entorno
load_dotenv()

def _en_streamlit_cloud():
    """True si la app corre en Streamlit Cloud (no en tu PC)."""
    return "/mount/src" in os.path.abspath(__file__)

# Flujo OAuth con Authlib para la nube (evita bug de st.login + oauth2callback en Cloud)
def _oauth_cloud_get_config():
    """En la nube: devuelve dict con client_id, client_secret, server_metadata_url, redirect_uri_root (URL raíz para callback)."""
    if not _en_streamlit_cloud():
        return None
    try:
        sec = getattr(st, "secrets", None)
        if not sec:
            return None
        a = sec.get("auth") or {}
        cid = a.get("client_id") or (a.get("microsoft") or {}).get("client_id")
        csec = a.get("client_secret") or (a.get("microsoft") or {}).get("client_secret")
        meta = a.get("server_metadata_url") or (a.get("microsoft") or {}).get("server_metadata_url")
        ru = (a.get("redirect_uri") or "").strip()
        if not (cid and csec and meta and ru):
            return None
        # redirect_uri_root = URL raíz (sin /oauth2callback) para que Microsoft redirija ahí
        root = ru.replace("/oauth2callback", "").rstrip("/") + "/"
        return {"client_id": cid, "client_secret": csec, "server_metadata_url": meta, "redirect_uri_root": root}
    except Exception:
        return None

def _oauth_cloud_handle_callback():
    """Si hay ?code= en la URL (vuelta de Microsoft), intercambia por token y guarda usuario. Devuelve True si hizo login."""
    cfg = _oauth_cloud_get_config()
    if not cfg or "code" not in st.query_params:
        return False
    if "_oauth_error" in st.session_state:
        del st.session_state["_oauth_error"]
    try:
        import requests
        from authlib.integrations.requests_client import OAuth2Session
        meta = requests.get(cfg["server_metadata_url"], timeout=10).json()
        token_endpoint = meta.get("token_endpoint")
        userinfo_endpoint = meta.get("userinfo_endpoint")
        if not token_endpoint:
            st.session_state["_oauth_error"] = "No token_endpoint en metadata"
            return False
        state = st.query_params.get("state")
        client = OAuth2Session(
            cfg["client_id"], cfg["client_secret"],
            redirect_uri=cfg["redirect_uri_root"],
            scope="openid profile email",
            state=state,
        )
        q = st.query_params
        # La URL de callback debe coincidir exactamente con la registrada en Azure (con o sin barra final)
        base = cfg["redirect_uri_root"].rstrip("/")
        auth_response = base + "?" + "&".join(f"{k}={v}" for k, v in q.items())
        token = client.fetch_token(token_endpoint, authorization_response=auth_response)
        user_info = {}
        if userinfo_endpoint:
            resp = client.get(userinfo_endpoint)
            if resp.status_code == 200:
                user_info = resp.json()
        st.session_state["_oauth_user"] = {
            "name": user_info.get("name") or user_info.get("preferred_username") or "",
            "email": user_info.get("email") or user_info.get("preferred_username") or "",
        }
        if "_oauth_error" in st.session_state:
            del st.session_state["_oauth_error"]
        st.rerun()
        return True
    except Exception as e:
        err = str(e)
        if "invalid_grant" in err or "AADSTS70008" in err or "expired" in err.lower():
            st.session_state["_oauth_error"] = "El código de autorización expiró o ya se usó. Haz clic de nuevo en «Iniciar sesión con Microsoft» (el código solo vale unos minutos)."
        else:
            st.session_state["_oauth_error"] = err
        return False

def _oauth_cloud_auth_url():
    """URL a la que enviar al usuario para iniciar sesión con Microsoft (solo en la nube)."""
    cfg = _oauth_cloud_get_config()
    if not cfg:
        return None
    try:
        import requests
        from authlib.integrations.requests_client import OAuth2Session
        meta = requests.get(cfg["server_metadata_url"], timeout=10).json()
        auth_endpoint = meta.get("authorization_endpoint")
        if not auth_endpoint:
            return None
        client = OAuth2Session(
            cfg["client_id"], cfg["client_secret"],
            redirect_uri=cfg["redirect_uri_root"],
            scope="openid profile email",
        )
        url, _ = client.create_authorization_url(auth_endpoint, prompt="select_account")
        return url
    except Exception:
        return None

def _en_streamlit_cloud():
    """True si la app corre en Streamlit Cloud (no en tu PC)."""
    return "/mount/src" in os.path.abspath(__file__)

# Compatibilidad: en Streamlit 1.19 (Cloud) toggle existe pero falla al llamarlo; en versiones nuevas funciona
def _sidebar_toggle(label, value=True):
    try:
        return st.sidebar.toggle(label, value=value)
    except Exception:
        return st.sidebar.checkbox(label, value=value)

def _st_dataframe(df, hide_index=False, **kwargs):
    # width="stretch" reemplaza use_container_width=True (deprecado 2025)
    opts = {k: v for k, v in kwargs.items() if k != "use_container_width"}
    try:
        st.dataframe(df, width="stretch", hide_index=hide_index, **opts)
    except (TypeError, AttributeError):
        st.dataframe(df, width="stretch", hide_index=hide_index)

def _dataframe_serializable(df):
    """Evita LargeUtf8 en frontend: solo columnas texto a tipo serializable. No cambia valores ni aspecto."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in out.columns:
        try:
            if pd.api.types.is_string_dtype(out[c]) or getattr(out[c].dtype, "name", "") == "object":
                out[c] = out[c].apply(lambda x: "" if pd.isna(x) else str(x))
        except Exception:
            pass
    return out

# Configuración de página
st.set_page_config(page_title="Ventas al Público - Andrés Carne de Res", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# --- Estilo: tipografía clara, paleta profesional, sin tocar tablas ni valores ---
BRAND_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Source+Sans+3:wght@400;600;700&display=swap');
  :root {
    --acr-red: #C41E3A;
    --acr-red-dark: #9E1830;
    --acr-gold: #B8860B;
    --acr-green: #1a6b1a;
    --acr-cream: #FFFBF5;
    --acr-cream-dark: #F5EDE4;
    --acr-brown: #1a1510;
    --acr-white: #FFFFFF;
    --text-primary: #1a1a1a;
    --text-secondary: #4a4a4a;
    --bg-sidebar: #f0f2f6;
    --border-sidebar: #C41E3A;
    --font-head: 'Plus Jakarta Sans', sans-serif;
    --font-body: 'Source Sans 3', sans-serif;
  }
  .stApp {
    background: linear-gradient(180deg, #FFFCF8 0%, var(--acr-cream) 12%, var(--acr-cream) 100%);
    font-family: var(--font-body);
    font-size: 1.0625rem;
    -webkit-font-smoothing: antialiased;
  }
  header[data-testid="stHeader"] {
    background: linear-gradient(90deg, var(--acr-red) 0%, var(--acr-red-dark) 100%);
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  }
  .main .block-container { padding-top: 1.75rem; padding-bottom: 2rem; max-width: 100%; }

  /* SIDEBAR */
  [data-testid="stSidebar"] {
    background: var(--bg-sidebar) !important;
    border-right: 4px solid var(--border-sidebar) !important;
  }
  [data-testid="stSidebar"] [data-testid="stMarkdown"] { color: var(--text-primary) !important; font-family: var(--font-head) !important; font-size: 1.05rem !important; font-weight: 700 !important; }
  [data-testid="stSidebar"] label { color: var(--text-primary) !important; font-size: 1rem !important; font-weight: 600 !important; }
  [data-testid="stSidebar"] .stRadio label { color: var(--text-primary) !important; font-size: 1rem !important; font-weight: 600 !important; }
  [data-testid="stSidebar"] .stSelectbox label, [data-testid="stSidebar"] .stMultiSelect label { color: var(--text-primary) !important; font-size: 1rem !important; }
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: var(--text-secondary) !important; font-size: 0.95rem !important; }
  [data-testid="stSidebar"] .stCaptionContainer { color: var(--text-secondary) !important; font-size: 0.9rem !important; }
  [data-testid="stSidebar"] .stRadio > div { gap: 0.6rem; }
  [data-testid="stSidebar"] section [data-testid="stVerticalBlock"] > div { padding: 0.25rem 0; }
  [data-testid="stSidebar"] div[data-testid="stMarkdown"] p { font-size: 1rem !important; color: var(--text-primary) !important; font-weight: 600 !important; }
  [data-testid="stSidebar"] button { font-size: 1rem !important; font-weight: 600 !important; }
  [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label { font-size: 1.05rem !important; }

  /* Cabecera del informe */
  .brand-header { display: flex; align-items: center; gap: 16px; margin-bottom: 0.25rem; }
  .brand-logo { width: 96px; height: 96px; border-radius: 14px; object-fit: contain; background: #fff; padding: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
  .brand-title { font-family: var(--font-head); font-size: 2rem; font-weight: 800; color: var(--acr-brown); letter-spacing: -0.02em; line-height: 1.25; }
  .brand-subtitle { font-family: var(--font-body); color: var(--text-secondary); font-size: 1.05rem; margin-bottom: 1.5rem; font-weight: 500; letter-spacing: 0.01em; }

  /* KPI / Metric cards: estilo tipo tarjetas ejecutivas */
  .kpi-card {
    background: var(--acr-white);
    border-radius: 10px;
    padding: 1.1rem 1.25rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    border-left: 4px solid var(--acr-red);
    margin-bottom: 0.5rem;
  }
  .kpi-card.gold { border-left-color: var(--acr-gold); }
  .kpi-card.green { border-left-color: var(--acr-green); }
  .kpi-label { font-size: 1rem; color: var(--text-secondary); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
  .kpi-value { font-size: 1.65rem; font-weight: 800; color: var(--acr-brown); }
  .kpi-delta { font-size: 1rem; margin-top: 4px; font-weight: 600; }
  .kpi-delta.up { color: var(--acr-green); }
  .kpi-delta.down { color: var(--acr-red); }

  /* Tarjetas de métricas: altura fija igual, sin recorte de valores */
  div[data-testid="stMetric"] {
    background: linear-gradient(145deg, #ffffff 0%, #f2f4f8 100%);
    border-radius: 16px;
    padding: 1.4rem 1.5rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
    border: 1px solid rgba(0,0,0,0.06);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    overflow: visible !important;
    min-width: 12rem;
    height: 8rem !important;
    min-height: 8rem !important;
    box-sizing: border-box;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
  }
  div[data-testid="stHorizontalBlock"] > div:has(div[data-testid="stMetric"]) {
    display: flex !important;
  }
  div[data-testid="stHorizontalBlock"] > div:has(div[data-testid="stMetric"]) > div {
    flex: 1;
    min-height: 8rem !important;
    height: 8rem !important;
  }
  div[data-testid="stMetric"]:hover {
    box-shadow: 0 8px 28px rgba(0,0,0,0.08), 0 2px 6px rgba(0,0,0,0.04);
    transform: translateY(-2px);
  }
  div[data-testid="stMetric"] label {
    font-family: var(--font-head) !important;
    font-size: 0.8rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: #5f6368 !important;
  }
  div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: var(--font-head) !important;
    font-size: 1.6rem !important;
    font-weight: 800 !important;
    color: var(--acr-brown) !important;
    letter-spacing: -0.03em;
    line-height: 1.25;
    overflow: visible !important;
    text-overflow: clip !important;
    white-space: nowrap !important;
    word-break: keep-all !important;
  }
  div[data-testid="stMetric"] [data-testid="stMetricValue"] span {
    overflow: visible !important;
    text-overflow: clip !important;
  }
  div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-family: var(--font-body) !important;
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    margin-top: 0.5rem !important;
    padding: 0.28rem 0.6rem !important;
    border-radius: 8px !important;
    display: inline-block !important;
  }
  /* Primera tarjeta: estilo destacado, misma altura fija */
  div[data-testid="stHorizontalBlock"] > div:first-child div[data-testid="stMetric"]:first-of-type {
    background: linear-gradient(145deg, #3d4554 0%, #2a303c 100%) !important;
    border: none !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.15), 0 2px 8px rgba(0,0,0,0.08);
    height: 8rem !important;
    min-height: 8rem !important;
  }
  div[data-testid="stHorizontalBlock"] > div:first-child div[data-testid="stMetric"]:first-of-type:hover {
    box-shadow: 0 12px 32px rgba(0,0,0,0.18), 0 4px 12px rgba(0,0,0,0.08);
  }
  div[data-testid="stHorizontalBlock"] > div:first-child div[data-testid="stMetric"]:first-of-type label {
    color: #b8bcc8 !important;
  }
  div[data-testid="stHorizontalBlock"] > div:first-child div[data-testid="stMetric"]:first-of-type [data-testid="stMetricValue"] {
    font-family: var(--font-head) !important;
    color: #ffffff !important;
  }
  div[data-testid="stHorizontalBlock"] > div:first-child div[data-testid="stMetric"]:first-of-type [data-testid="stMetricDelta"] {
    color: #e0e4ea !important;
  }
  /* Segunda tarjeta: contorno oscuro, valor y % en la misma línea, % sin recuadro */
  div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stMetric"] {
    background: linear-gradient(145deg, #fafbfc 0%, #f0f2f6 100%) !important;
    border: 2px solid #3d4554 !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08), 0 0 0 1px rgba(61,69,84,0.15) !important;
    height: 8rem !important;
    min-height: 8rem !important;
  }
  div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stMetric"]:hover {
    box-shadow: 0 8px 28px rgba(0,0,0,0.1), 0 0 0 1px rgba(61,69,84,0.2) !important;
  }
  /* Segunda tarjeta: valor y % en la misma fila (grid), % sin recuadro */
  div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stMetric"] {
    display: grid !important;
    grid-template-columns: 1fr auto !important;
    grid-template-rows: auto 1fr !important;
    align-content: center !important;
  }
  div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stMetric"] label {
    grid-column: 1 / -1 !important;
  }
  div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    grid-column: 1 !important;
    grid-row: 2 !important;
    align-self: baseline !important;
    margin-bottom: 0 !important;
  }
  div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    grid-column: 2 !important;
    grid-row: 2 !important;
    align-self: baseline !important;
    margin-top: 0 !important;
    margin-left: 0.5rem !important;
    padding: 0 !important;
    border-radius: 0 !important;
    background: none !important;
    border: none !important;
    box-shadow: none !important;
  }

  /* Tablas: estilo reporte (cabecera gris, bordes, agrupación) */
  .dataframe thead tr th {
    background: #3d4554 !important;
    color: #fff !important; font-weight: 700 !important;
    padding: 12px 14px !important; font-size: 1rem !important;
    border: 1px solid #2f3644 !important;
  }
  .dataframe tbody tr:hover { background: var(--acr-cream-dark) !important; }
  .dataframe tbody tr:nth-child(even) { background: #faf9f7 !important; }
  .dataframe tbody td {
    font-size: 1rem !important; color: var(--text-primary) !important;
    padding: 10px 14px !important; border: 1px solid #e0e2e6 !important;
  }
  div[data-testid="stHorizontalBlock"] { align-items: stretch !important; }
  div[data-testid="stHorizontalBlock"] > div { align-items: stretch !important; min-width: 0; overflow: visible !important; }
  div[data-testid="stHorizontalBlock"] > div:has(div[data-testid="stMetric"]) { flex: 1 1 auto !important; min-width: 14rem !important; }
  div[data-testid="stHorizontalBlock"] > div:has(div[data-testid="stMetric"]) > div { height: 100% !important; min-height: 7.5rem !important; }

  /* Títulos de sección (solo tipografía; no afecta tablas) */
  .section-title {
    font-family: var(--font-head) !important;
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--acr-brown);
    letter-spacing: -0.01em;
    margin: 1.5rem 0 0.85rem 0;
    line-height: 1.3;
  }
  hr { border: none; border-top: 1px solid #e2ddd6; opacity: 0.9; margin: 1rem 0; }

  /* Menú de pestañas: diseño actual y claro */
  .stTabs [data-baseweb="tab-list"] {
    gap: 0;
    background: #f2f4f6;
    border-radius: 12px;
    padding: 6px;
    margin-bottom: 1rem;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .stTabs [data-baseweb="tab"] {
    font-family: var(--font-head) !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 0.65rem 1.1rem !important;
    border-radius: 8px !important;
    color: var(--text-secondary) !important;
    transition: background 0.2s ease, color 0.2s ease;
  }
  .stTabs [data-baseweb="tab"]:hover {
    background: rgba(255,255,255,0.7) !important;
    color: var(--acr-brown) !important;
  }
  .stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: var(--acr-white) !important;
    color: var(--acr-red) !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
  }
  .stTabs [data-baseweb="tab-highlight"] {
    background: var(--acr-red) !important;
    border-radius: 8px;
    height: 3px !important;
  }
</style>
"""

# Orden fijo de grupos (alineado al reporte Excel)
ORDEN_GRUPOS = ['RBB', 'PLAZAS', 'PARADERO FR', 'PARADERO', 'EXPRÉS', 'OTROS']

# Orden fijo de sedes dentro de cada grupo (usado en todas las pestañas)
ORDEN_SEDES = [
    # RBB
    "ACR", "ADC", "CARTAGENA", "MEDELLIN",
    # PLAZAS
    "GRAN ESTACIÓN", "HACIENDA", "RETIRO", "SANTAFÉ",
    # PARADERO FR
    "BAZAAR", "HYATT", "PLAZA CLARO",
    # PARADERO
    "AEROPUERTO", "ANDRES VIAJERO", "RIONEGRO",
    # EXPRÉS
    "CAFAM", "CALLE 93", "CASA DE LOS ANDES", "EXPRÉS PARADERO",
    "MULTIPARQUE", "PALATINO", "PEPE SIERRA",
]
ORDEN_SEDES_MAP = {nombre: idx for idx, nombre in enumerate(ORDEN_SEDES)}

# Meses en español para toda la interfaz
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}
# Días de la semana (lunes=0, domingo=6, según date.weekday())
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

@st.cache_resource
def get_engine():
    db_url = os.getenv("LOCAL_DB_URL")
    if not db_url:
        # En la nube (Streamlit Cloud) la app corre desde la raíz del repo; DB junto a app.py
        base = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base, "bi_local_data.db")
        db_url = f"sqlite:///{db_path}"
    kwargs = {}
    if "sqlite" in db_url:
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(db_url, **kwargs)

@st.cache_data
def load_mapeo_sedes():
    """Carga mapeo código normalizado -> (grupo, sede) desde sede_grupo_lookup."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT store_id, sede, grupo FROM sede_grupo_lookup"), con=conn)
        if df.empty:
            return _mapeo_respaldo()
        return dict(zip(
            df["store_id"].astype(str).str.strip().str.upper().str.lstrip("0"),
            list(zip(df["grupo"], df["sede"]))
        ))
    except Exception:
        return _mapeo_respaldo()

def _mapeo_respaldo():
    return {
    '2': ('RBB', 'ACR'), '3': ('RBB', 'ADC'), 'F08': ('RBB', 'CARTAGENA'), '201': ('RBB', 'MEDELLIN'),
    '404': ('PLAZAS', 'GRAN ESTACIÓN'), '402': ('PLAZAS', 'HACIENDA'), '401': ('PLAZAS', 'RETIRO'), '405': ('PLAZAS', 'SANTAFÉ'),
    'F09': ('PARADERO FR', 'BAZAAR'), 'F05': ('PARADERO FR', 'HYATT'), 'F04': ('PARADERO FR', 'PLAZA CLARO'),
    '301': ('PARADERO', 'AEROPUERTO'), '304': ('PARADERO', 'ANDRES VIAJERO'), '305': ('PARADERO', 'RIONEGRO'),
    '611': ('EXPRÉS', 'CAFAM'), '502': ('EXPRÉS', 'CALLE 93'), '612': ('EXPRÉS', 'CASA DE LOS ANDES'), 
    '4': ('EXPRÉS', 'EXPRÉS PARADERO'), '702': ('EXPRÉS', 'MULTIPARQUE'), '604': ('EXPRÉS', 'PALATINO'), '615': ('EXPRÉS', 'PEPE SIERRA')
}

@st.cache_data(ttl=120)
def load_ventas_operativas():
    """
    Ventas y transacciones por sede/día.
    - Ventas: raw_ventas_2026 (Detalle); StoreID = Co.
    - Transacciones: tabla Invoice (NEWACRventas) → Invoice.StoreID se relaciona con Store
      para obtener Store.StoreID_External (Co) y nombre; se agrupa por (Co, día) y se cuenta
      COUNT(DISTINCT InvoiceID). Ticket promedio = venta del día / transacciones (misma venta
      que se muestra en cada campo).
    """
    engine = get_engine()
    # Ventas: Co = raw_ventas_2026.StoreID (Detalle.Co). Transacciones: Invoice.StoreID es ID interno;
    # hay que unir Invoice -> Store por StoreID y usar Store.StoreID_External (Co) para que coincida con ventas.
    norm_co = "LTRIM(UPPER(TRIM(CAST(%s AS TEXT))), '0')"
    query = f"""
    WITH VentasDiarias AS (
        SELECT 
            {norm_co % 'StoreID'} AS codigo_sede_crudo,
            DATE(Fecha) AS Fecha,
            SUM(VlrBruto) AS VlrBruto,
            SUM(VlrTotalDesc) AS VlrTotalDesc
        FROM raw_ventas_2026
        GROUP BY 1, 2
    ),
    -- Invoice.StoreID = ID interno; Store.StoreID_External = Co (mismo que Detalle.Co)
    TransaccionesDiarias AS (
        SELECT 
            {norm_co % 's.StoreID_External'} AS codigo_sede_crudo,
            DATE(i.BusinessDate) AS Fecha,
            COUNT(DISTINCT i.InvoiceID) AS Cantidad_Transacciones
        FROM raw_invoice_2026 i
        INNER JOIN dim_store s ON TRIM(CAST(COALESCE(i.StoreID, '') AS TEXT)) = TRIM(CAST(COALESCE(s.StoreID, '') AS TEXT))
        WHERE i.InvoiceID IS NOT NULL AND TRIM(CAST(COALESCE(s.StoreID_External, '') AS TEXT)) <> ''
        GROUP BY 1, 2
    )
    SELECT 
        COALESCE(s_main.Store_Name, 'DESCONOCIDA') AS Store_Name,
        v.Fecha, v.codigo_sede_crudo, COALESCE(v.VlrBruto, 0) AS VlrBruto,
        COALESCE(v.VlrTotalDesc, 0) AS VlrTotalDesc, COALESCE(t.Cantidad_Transacciones, 0) AS Cantidad_Transacciones
    FROM VentasDiarias v
    LEFT JOIN dim_store s_main ON v.codigo_sede_crudo = {norm_co % "COALESCE(s_main.StoreID_External, s_main.StoreID)"}
    LEFT JOIN TransaccionesDiarias t ON v.codigo_sede_crudo = t.codigo_sede_crudo AND v.Fecha = t.Fecha
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
        if not df.empty:
            df['Fecha'] = pd.to_datetime(df['Fecha']).dt.date
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def load_financiero_excel():
    """Presupuesto, histórico diarizado e Historico_Diario (2025). TTL 2 min para ver datos recién cargados (FTP/ETL)."""
    engine = get_engine()
    query = """
    SELECT 
        LTRIM(UPPER(TRIM(CAST(h.StoreID_External AS TEXT))), '0') AS codigo_sede_crudo,
        COALESCE(s.Store_Name, h.Sede_Excel) AS Store_Name,
        h.Agrupacion, h.Fecha, h.Escenario, h.Ventas, h.Transacciones
    FROM hechos_excel_diario h
    LEFT JOIN dim_store s ON LTRIM(UPPER(TRIM(CAST(h.StoreID_External AS TEXT))), '0') = LTRIM(UPPER(TRIM(CAST(s.StoreID_External AS TEXT))), '0')
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
        if not df.empty:
            df['Fecha'] = pd.to_datetime(df['Fecha']).dt.date
            # Normalizar codigo para que coincida con MAPEO_SEDES (evita que sedes como Andrés Viajero queden en 0 en acumulado)
            df['codigo_sede_crudo'] = df['codigo_sede_crudo'].astype(str).str.strip().str.upper().str.lstrip('0')
        return df
    except Exception as e:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def load_transacciones_hist_2025():
    """
    Transacciones históricas (solo año 2025) desde el archivo local
    transacciones_hist*.xlsx (en raíz o en fuentes_excel).
    Devuelve DataFrame con columnas: codigo_sede_crudo, Fecha, Transacciones.
    """
    # Buscar archivo en raíz, fuentes_excel y carpeta padre (a veces está junto al proyecto)
    base = os.getcwd()
    posibles_carpetas = [base, os.path.join(base, "fuentes_excel"), os.path.dirname(base)]
    ruta_archivo = None
    for carpeta in posibles_carpetas:
        if not os.path.exists(carpeta):
            continue
        for f in os.listdir(carpeta):
            f_low = f.lower()
            if f_low.startswith("transacciones_hist") and (f_low.endswith(".xlsx") or f_low.endswith(".xls") or f_low.endswith(".csv")):
                ruta_archivo = os.path.join(carpeta, f)
                break
        if ruta_archivo:
            break
    if not ruta_archivo:
        return pd.DataFrame()

    def _norm_cols(cols):
        return [str(c).strip().lstrip("\ufeff") for c in cols]

    def _detectar_columna(df, candidatos):
        cols = _norm_cols(df.columns)
        for cand in candidatos:
            cand_low = cand.strip().lower()
            for col in cols:
                if col.strip().lower() == cand_low:
                    return col
        return None

    try:
        if ruta_archivo.lower().endswith(".csv"):
            df = pd.read_csv(ruta_archivo, sep=";", encoding="utf-8-sig", low_memory=False)
            if df.empty and os.path.getsize(ruta_archivo) > 0:
                df = pd.read_csv(ruta_archivo, sep=",", encoding="utf-8-sig", low_memory=False)
        else:
            df = pd.read_excel(ruta_archivo, sheet_name=0)
    except Exception:
        return pd.DataFrame()

    df.columns = _norm_cols(df.columns)
    col_co = _detectar_columna(df, ["Co", "CentroOP", "Centro", "Codigo", "StoreID_External", "StoreID", "Sede", "Tienda", "CentroOP"])
    col_fecha = _detectar_columna(df, ["Fecha", "FechaDocto", "Date", "FechaVenta", "Dia", "Business Date", "BusinessDate"])
    col_tx = _detectar_columna(df, [
        "Transacciones", "Cantidad_Transacciones", "Cantidad", "CantTransacciones",
        "Num Transacciones", "NumeroTransacciones", "Tickets", "Invoices", "Sales Count", "SalesCount"
    ])
    if not col_co or not col_fecha or not col_tx:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["codigo_sede_crudo"] = (
        df[col_co]
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
        .str.lstrip("0")
    )
    fechas = pd.to_datetime(df[col_fecha], dayfirst=True, errors="coerce")
    out["Fecha"] = fechas.dt.date
    out["Transacciones"] = pd.to_numeric(df[col_tx], errors="coerce").fillna(0)
    out = out.dropna(subset=["Fecha"])
    # Quitar filas con código vacío o nan
    out = out[out["codigo_sede_crudo"].astype(str).str.strip() != ""]
    out = out[~out["codigo_sede_crudo"].astype(str).str.upper().str.contains("NAN", na=True)]
    out = out[out["Fecha"].apply(lambda d: getattr(d, "year", None) == 2025)]
    if out.empty:
        return pd.DataFrame()
    agg = out.groupby(["codigo_sede_crudo", "Fecha"], as_index=False)["Transacciones"].sum()
    return agg

# --- FORMATOS ---
def f_moneda(v): return f"${v:,.0f}".replace(",", ".") if pd.notna(v) else "$0"
def f_entero(v): return f"{v:,.0f}".replace(",", ".") if pd.notna(v) else "0"

def _estilo_tabla_informe(df_show, col_var="VARIACIÓN"):
    """Aplica estilo tipo reporte: filas de total por grupo (gris oscuro), Total general (amarillo), semáforos en col_var."""
    df_show = _dataframe_serializable(df_show)
    def _estilo_fila(row):
        rest = str(row.get("RESTAURANTE", ""))
        if rest == "Total":
            return ["background-color: #E8A317; color: #1a1510; font-weight: bold"] * len(row)
        if rest.startswith("Total ") or rest.startswith("▪ Total "):
            return ["background-color: #3d4554; color: #fff; font-weight: bold"] * len(row)
        return [""] * len(row)

    def _estilo_var(val):
        if pd.isna(val): return ""
        s = str(val)
        if "▲" in s or ("+" in s and "%" in s):
            return "background-color: #e6f4e6; color: #1a5f1a; font-weight: 600;"
        if "▼" in s or ("-" in s and "%" in s):
            return "background-color: #fde8e8; color: #a01c28; font-weight: 600;"
        return ""

    sty = df_show.style.apply(_estilo_fila, axis=1)
    if col_var and col_var in df_show.columns:
        # pandas 2.2+ usa .map; versiones anteriores .applymap
        if hasattr(sty, "map"):
            sty = sty.map(_estilo_var, subset=[col_var])
        else:
            sty = sty.applymap(_estilo_var, subset=[col_var])
    return sty
def f_delta(actual, anterior):
    if pd.isna(anterior) or anterior == 0: return 0
    return (actual / anterior) - 1

def _auth_microsoft_configured():
    """True si está configurado el login con Microsoft (Outlook/Entra) en secrets."""
    if st.session_state.get("_skip_microsoft_auth"):
        return False
    try:
        if not hasattr(st, "user") or not hasattr(st, "login"):
            return False
        sec = getattr(st, "secrets", None)
        if sec is None or not hasattr(sec, "get"):
            return False
        a = sec.get("auth") or {}
        # Todo en [auth] (proveedor por defecto)
        if a.get("client_id") and a.get("client_secret"):
            return True
        # Formato nombrado [auth.microsoft]
        m = (a.get("microsoft") or {}) if isinstance(a, dict) else {}
        return bool(m.get("client_id") and m.get("client_secret"))
    except Exception:
        return False

def _auth_provider_name():
    """Si usas [auth.microsoft], devuelve 'microsoft'; si todo en [auth], None."""
    try:
        sec = getattr(st, "secrets", None)
        if not sec: return None
        a = sec.get("auth") or {}
        if a.get("client_id") and a.get("client_secret"):
            return None
        m = (a.get("microsoft") or {}) if isinstance(a, dict) else {}
        if m.get("client_id") and m.get("client_secret"):
            return "microsoft"
        return None
    except Exception:
        return None

def _pagina_login_microsoft():
    """Pantalla de login solo con Microsoft (cuando [auth] está configurado). En la nube usa flujo Authlib (sin oauth2callback)."""
    # En la nube: si volvemos de Microsoft con ?code=, intercambiar por token y redirigir
    if _oauth_cloud_get_config() and _oauth_cloud_handle_callback():
        return

    st.markdown(BRAND_CSS, unsafe_allow_html=True)
    st.markdown("## Acceso al informe de ventas")
    st.markdown("Inicia sesión con tu **cuenta de Outlook / Microsoft 365** (correo corporativo).")

    # En la nube: usar enlace a URL de Authlib (evita bug de st.login + oauth2callback)
    auth_url_cloud = _oauth_cloud_auth_url() if _oauth_cloud_get_config() else None
    if auth_url_cloud:
        if st.session_state.get("_oauth_error"):
            st.error(st.session_state["_oauth_error"])
            if "redirect_uri" in st.session_state.get("_oauth_error", ""):
                st.caption("Revisa que en Azure esté exactamente: https://reportesandresbi.streamlit.app/ (con barra final).")
        st.markdown("Haz clic en el botón para ir a Microsoft y autorizar el acceso. **No esperes mucho** después de autorizar: vuelve a la pestaña en seguida.")
        st.link_button("Iniciar sesión con Microsoft", url=auth_url_cloud, type="primary")
        cfg = _oauth_cloud_get_config()
        if cfg:
            st.caption("En la nube se usa un flujo alternativo. En Azure debe estar la URI: " + cfg.get("redirect_uri_root", ""))
    else:
        # Local: st.login()
        with st.expander("¿No funciona el login? Ver diagnóstico"):
            has_user = hasattr(st, "user")
            has_login = hasattr(st, "login")
            sec = getattr(st, "secrets", None)
            auth = (sec.get("auth") or {}) if sec else {}
            ms = (auth.get("microsoft") or {}) if isinstance(auth, dict) else {}
            has_cid = bool(auth.get("client_id") or ms.get("client_id"))
            has_csec = bool(auth.get("client_secret") or ms.get("client_secret"))
            ru = (auth.get("redirect_uri") or "")
            redirect_ok = ru.rstrip("/").endswith("oauth2callback") or "/oauth2callback" in ru
            st.caption("st.user: " + ("sí" if has_user else "no") + " · st.login: " + ("sí" if has_login else "no"))
            st.caption("client_id en secrets: " + ("sí" if has_cid else "no") + " · client_secret: " + ("sí" if has_csec else "no"))
            st.caption("redirect_uri termina en oauth2callback: " + ("sí" if redirect_ok else "no — debe ser .../oauth2callback"))
            if not redirect_ok and ru:
                st.code(ru, language=None)
            provider = _auth_provider_name()
            st.caption("Proveedor: " + (provider or "por defecto [auth]"))

        def _do_login():
            if _auth_provider_name() == "microsoft":
                st.login("microsoft")
            else:
                st.login()

        try:
            if st.button("Iniciar sesión con Microsoft", type="primary", on_click=_do_login):
                pass
        except Exception as e:
            st.warning("En este entorno el login con Microsoft no está disponible. Usa usuario y contraseña.")
            st.code(str(e), language=None)
            if st.button("Ir a inicio de sesión con usuario"):
                st.session_state["_skip_microsoft_auth"] = True
                st.rerun()

def _pagina_login_registro():
    """Login/registro con usuario y contraseña (cuando no hay auth Microsoft)."""
    global auth
    if auth is None:
        try:
            import auth as _auth
            auth = _auth
        except Exception:
            st.markdown(BRAND_CSS, unsafe_allow_html=True)
            st.error("Módulo de autenticación no disponible en este entorno. Contacte al administrador.")
            return
    st.markdown(BRAND_CSS, unsafe_allow_html=True)
    st.markdown("## Acceso al informe de ventas")
    try:
        engine = get_engine()
        auth.init_auth_table(engine)
    except Exception as e:
        st.error("No se pudo conectar a la base de datos.")
        st.code(str(e))
        return
    tab1, tab2 = st.tabs(["Iniciar sesión", "Registrarse"])

    with tab1:
        with st.form("login_form"):
            u = st.text_input("Usuario", key="login_user")
            p = st.text_input("Contraseña", type="password", key="login_pass")
            if st.form_submit_button("Entrar"):
                if auth.verify(engine, u, p):
                    st.session_state["user"] = u
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

    with tab2:
        with st.form("register_form"):
            ru = st.text_input("Usuario", key="reg_user")
            rp = st.text_input("Contraseña", type="password", key="reg_pass")
            rp2 = st.text_input("Repetir contraseña", type="password", key="reg_pass2")
            if st.form_submit_button("Registrarse"):
                if not ru or not rp:
                    st.error("Usuario y contraseña son obligatorios.")
                elif rp != rp2:
                    st.error("Las contraseñas no coinciden.")
                elif auth.register(engine, ru, rp):
                    st.success("Cuenta creada. Inicia sesión en la pestaña «Iniciar sesión».")
                else:
                    st.error("El usuario ya existe o no se pudo crear la cuenta.")

def _usuario_actual():
    """Nombre a mostrar: Microsoft (st.user), OAuth nube (_oauth_user) o usuario de registro."""
    if _en_streamlit_cloud() and st.session_state.get("_oauth_user"):
        u = st.session_state["_oauth_user"]
        return u.get("name") or u.get("email") or "Usuario"
    try:
        if _auth_microsoft_configured() and getattr(st.user, "is_logged_in", False):
            return getattr(st.user, "name", None) or getattr(st.user, "email", None) or "Usuario"
    except Exception:
        pass
    return st.session_state.get("user")

def _esta_logueado():
    """True si hay sesión (Microsoft, OAuth nube _oauth_user, o usuario/contraseña)."""
    if st.session_state.get("_oauth_user"):
        return True
    try:
        if st.session_state.get("user"):
            return True
        if _auth_microsoft_configured() and getattr(st.user, "is_logged_in", False):
            return True
    except Exception:
        pass
    return False

def main():
    try:
        _main_impl()
    except Exception as e:
        st.error("Error al cargar la aplicación. Copie el mensaje y compártalo con soporte.")
        st.code(traceback.format_exc(), language="text")
        st.caption("Si esto aparece en la nube, el informe local funciona pero el entorno web falla por lo anterior.")

def _main_impl():
    # Exigir login: en local siempre; en la web solo si [auth] Microsoft está configurado (acceso por correo).
    requiere_login = (not _en_streamlit_cloud()) or _auth_microsoft_configured()
    if requiere_login:
        try:
            if not _esta_logueado():
                if _auth_microsoft_configured():
                    _pagina_login_microsoft()
                else:
                    _pagina_login_registro()
                return
        except Exception:
            _pagina_login_registro()
            return

    st.markdown(BRAND_CSS, unsafe_allow_html=True)
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo-andres.png")
    if os.path.isfile(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        logo_src = f"data:image/png;base64,{logo_b64}"
    else:
        logo_src = "https://seeklogo.com/images/A/andres-carne-de-res-logo-256225F950-seeklogo.com.png"
    header_html = f"""
    <div class="brand-header">
      <img src="{logo_src}" alt="Andrés Carne de Res" class="brand-logo" />
      <div>
        <div class="brand-title">Ventas al Público · Andrés Carne de Res</div>
        <div class="brand-subtitle">Seguimiento diario y acumulado · Presupuesto, histórico y transacciones</div>
      </div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

    # En la nube puede no haber base de datos; si falla, mostrar mensaje y no romper (evitar 400)
    try:
        MAPEO_SEDES = load_mapeo_sedes()
        df_op = load_ventas_operativas()
        df_fin = load_financiero_excel()
    except Exception as e:
        if _en_streamlit_cloud():
            st.info("Informe disponible en la versión local. En la nube no hay base de datos configurada.")
            st.caption("Para ver datos aquí, sube bi_local_data.db o configura una fuente en la nube.")
            return
        raise
    
    if df_op.empty:
        st.error("No hay datos operativos. Ejecuta los ETLs.")
        return

    # --- SIDEBAR: usuario (solo si hay sesión) y filtros ---
    if _esta_logueado():
        st.sidebar.caption(f"Conectado como **{_usuario_actual() or '—'}**")
        if st.sidebar.button("Cerrar sesión"):
            try:
                if _auth_microsoft_configured() and getattr(st.user, "is_logged_in", False):
                    st.logout()
            except Exception:
                pass
            if st.session_state.get("user"):
                del st.session_state["user"]
            if st.session_state.get("_oauth_user"):
                del st.session_state["_oauth_user"]
            st.rerun()
        st.sidebar.markdown("---")
    st.sidebar.header("Filtros")
    u_f = df_op['Fecha'].max()
    if not isinstance(u_f, date):
        u_f = u_f.date() if hasattr(u_f, 'date') else date.today()

    st.sidebar.subheader("Rango de fechas")
    f_inicio = st.sidebar.date_input("Desde", u_f, key="f_desde")
    f_fin = st.sidebar.date_input("Hasta", u_f, key="f_hasta")
    if f_fin < f_inicio:
        f_fin = f_inicio
        st.sidebar.caption("Hasta no puede ser anterior a Desde. Se usó la misma fecha.")

    f_sel = f_inicio  # para títulos y acumulado "hasta" usamos f_fin donde aplique

    sedes_map = sorted(list(set([v[1] for v in MAPEO_SEDES.values()])))
    s_filtro = st.sidebar.multiselect("Restaurantes", options=sedes_map, default=sedes_map)
    grupos_map = sorted(list(set([v[0] for v in MAPEO_SEDES.values()])))
    g_filtro = st.sidebar.multiselect("Grupos", options=grupos_map, default=grupos_map)
    ocultar_sin_venta = st.sidebar.checkbox("Ocultar sedes sin venta real", value=True)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Refrescar datos", help="Tras ejecutar el ETL, pulsa aquí para cargar ventas y presupuesto de nuevo (evita caché)."):
        try:
            load_ventas_operativas.clear()
            load_financiero_excel.clear()
            load_transacciones_hist_2025.clear()
        except Exception:
            pass
        st.rerun()
    alinear = _sidebar_toggle("Lunes vs Lunes (comparativo 2025)", value=True)
    f_inicio_25 = (f_inicio - timedelta(days=364)) if alinear else f_inicio.replace(year=2025)
    f_fin_25 = (f_fin - timedelta(days=364)) if alinear else f_fin.replace(year=2025)
    # Pestaña 4: true = mismo rango (1-X ppto vs 1-X ventas); false = presupuesto total mes vs ventas acum 1-X
    ppto_acum_mismo_rango = _sidebar_toggle("Ppto acumulado: mismo rango (1-X vs 1-X)", value=True)
    if f_inicio and f_fin:
        if f_inicio == f_fin:
            d1 = f"{DIAS_SEMANA[f_inicio.weekday()]} {f_inicio.day} de {MESES_ES[f_inicio.month]} de {f_inicio.year}"
            d2 = f"{DIAS_SEMANA[f_inicio_25.weekday()]} {f_inicio_25.day} de {MESES_ES[f_inicio_25.month]} de {f_inicio_25.year}"
        else:
            d1 = f"{DIAS_SEMANA[f_inicio.weekday()]} {f_inicio.day} al {DIAS_SEMANA[f_fin.weekday()]} {f_fin.day} de {MESES_ES[f_inicio.month]} de {f_inicio.year}"
            d2 = f"{DIAS_SEMANA[f_inicio_25.weekday()]} {f_inicio_25.day} al {DIAS_SEMANA[f_fin_25.weekday()]} {f_fin_25.day} de {MESES_ES[f_inicio_25.month]} de {f_inicio_25.year}"
        st.sidebar.caption(f"Comparando: **{d1}** / **{d2}**")

    # Datos en el rango [f_inicio, f_fin] (se agregan por sede en las tablas)
    df_r = df_op[(df_op['Fecha'] >= f_inicio) & (df_op['Fecha'] <= f_fin)].copy()
    # Siempre crear la columna Venta_Real (aunque el DataFrame esté vacío) para evitar KeyError en la nube
    df_r['Venta_Real'] = df_r['VlrBruto'] - df_r['VlrTotalDesc'].abs()
    if not df_r.empty:
        df_r['Sede_Nom'] = df_r['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[1])
        df_r['Grupo'] = df_r['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[0])
        df_r = df_r[df_r['Sede_Nom'].isin(s_filtro) & df_r['Grupo'].isin(g_filtro)]

    # Comparativo 2025: datos del Excel descargado del FTP (Historico_Diario), cargado con listar_ftp_ventas_2025.py --cargar
    df_h_raw = df_fin[(df_fin['Fecha'] >= f_inicio_25) & (df_fin['Fecha'] <= f_fin_25) & (df_fin['Escenario'].str.contains('Historico', na=False))].copy()
    if not df_h_raw.empty:
        df_h_raw['Sede_Nom'] = df_h_raw['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[1])
        df_h_raw['Grupo'] = df_h_raw['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[0])
        df_h_raw = df_h_raw[df_h_raw['Sede_Nom'].isin(s_filtro) & df_h_raw['Grupo'].isin(g_filtro)]
        df_h = df_h_raw.groupby('codigo_sede_crudo', as_index=False).agg({
            'Ventas': 'sum', 'Transacciones': 'sum', 'Sede_Nom': 'first', 'Grupo': 'first'
        })
    else:
        df_h = pd.DataFrame(columns=['codigo_sede_crudo', 'Ventas', 'Transacciones', 'Sede_Nom', 'Grupo'])

    # Presupuesto diario: solo pestaña 3 usa PP 2026 x día (Presupuesto_Diario_2026) si existe; si no, Presupuesto_Diarizado
    df_p_raw_pp_dia = df_fin[(df_fin['Fecha'] >= f_inicio) & (df_fin['Fecha'] <= f_fin) & (df_fin['Escenario'] == 'Presupuesto_Diario_2026')].copy()
    df_p_raw_ppto_diar = df_fin[(df_fin['Fecha'] >= f_inicio) & (df_fin['Fecha'] <= f_fin) & (df_fin['Escenario'] == 'Presupuesto_Diarizado')].copy()
    df_p_raw = df_p_raw_pp_dia if not df_p_raw_pp_dia.empty else df_p_raw_ppto_diar
    if not df_p_raw.empty:
        df_p_raw = df_p_raw.copy()
        df_p_raw['Sede_Nom'] = df_p_raw['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[1])
        df_p_raw['Grupo'] = df_p_raw['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[0])
        df_p_raw = df_p_raw[df_p_raw['Sede_Nom'].isin(s_filtro) & df_p_raw['Grupo'].isin(g_filtro)]
        df_p = df_p_raw.groupby('codigo_sede_crudo', as_index=False).agg({'Ventas': 'sum', 'Sede_Nom': 'first', 'Grupo': 'first'})
    else:
        df_p = pd.DataFrame(columns=['codigo_sede_crudo', 'Ventas', 'Sede_Nom', 'Grupo'])

    # Transacciones 2026 vs 2025 (pestaña 5): 2026 desde df_op (Cantidad_Transacciones), 2025 desde transacciones_hist (solo año 2025)
    df_tx_25_raw = load_transacciones_hist_2025()
    if not df_tx_25_raw.empty and f_inicio_25 and f_fin_25:
        mask_t25 = (df_tx_25_raw['Fecha'] >= f_inicio_25) & (df_tx_25_raw['Fecha'] <= f_fin_25)
        tx_25_agg = df_tx_25_raw[mask_t25].groupby('codigo_sede_crudo', as_index=False)['Transacciones'].sum()
        tx_25_agg['Sede_Nom'] = tx_25_agg['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[1])
        tx_25_agg['Grupo'] = tx_25_agg['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[0])
        tx_25_agg = tx_25_agg[tx_25_agg['Sede_Nom'].isin(s_filtro) & tx_25_agg['Grupo'].isin(g_filtro)]
        df_tx_25 = tx_25_agg
    else:
        df_tx_25 = pd.DataFrame(columns=['codigo_sede_crudo', 'Transacciones', 'Sede_Nom', 'Grupo'])
    if not df_r.empty and 'Cantidad_Transacciones' in df_r.columns:
        df_tx_26 = df_r.groupby('codigo_sede_crudo', as_index=False).agg({
            'Cantidad_Transacciones': 'sum', 'Sede_Nom': 'first', 'Grupo': 'first'
        }).rename(columns={'Cantidad_Transacciones': 'Transacciones'})
    else:
        df_tx_26 = pd.DataFrame(columns=['codigo_sede_crudo', 'Transacciones', 'Sede_Nom', 'Grupo'])

    # Acumulado mes (1 al día f_fin) para informe 4
    if f_fin:
        y, m = f_fin.year, f_fin.month
        inicio_mes = date(y, m, 1)
        mask_acum = (df_op['Fecha'] >= inicio_mes) & (df_op['Fecha'] <= f_fin)
        df_op_acum = df_op[mask_acum].copy()
        if not df_op_acum.empty:
            df_op_acum['Venta_Real'] = df_op_acum['VlrBruto'] - df_op_acum['VlrTotalDesc'].abs()
            df_op_acum['Sede_Nom'] = df_op_acum['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[1])
            df_op_acum['Grupo'] = df_op_acum['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[0])
            df_op_acum = df_op_acum[df_op_acum['Sede_Nom'].isin(s_filtro) & df_op_acum['Grupo'].isin(g_filtro)]
            df_r_acum = df_op_acum.groupby('codigo_sede_crudo', as_index=False).agg({'Venta_Real': 'sum', 'Sede_Nom': 'first', 'Grupo': 'first'})
        else:
            df_r_acum = pd.DataFrame(columns=['codigo_sede_crudo', 'Venta_Real', 'Sede_Nom', 'Grupo'])
        _, last_d = calendar.monthrange(y, m)
        fin_mes = date(y, m, last_d)
        # Acumulado usa el mismo archivo que el diario (PP 2026 X Día) si existe; si no, Presupuesto_Diarizado
        mask_ppto_mes_pp = (df_fin['Fecha'] >= inicio_mes) & (df_fin['Fecha'] <= fin_mes) & (df_fin['Escenario'] == 'Presupuesto_Diario_2026')
        mask_ppto_acum_pp = (df_fin['Fecha'] >= inicio_mes) & (df_fin['Fecha'] <= f_fin) & (df_fin['Escenario'] == 'Presupuesto_Diario_2026')
        mask_ppto_mes_old = (df_fin['Fecha'] >= inicio_mes) & (df_fin['Fecha'] <= fin_mes) & (df_fin['Escenario'] == 'Presupuesto_Diarizado')
        mask_ppto_acum_old = (df_fin['Fecha'] >= inicio_mes) & (df_fin['Fecha'] <= f_fin) & (df_fin['Escenario'] == 'Presupuesto_Diarizado')
        use_pp_diario = not df_fin[mask_ppto_acum_pp].empty
        mask_ppto_mes = mask_ppto_mes_pp if use_pp_diario else mask_ppto_mes_old
        mask_ppto_acum = mask_ppto_acum_pp if use_pp_diario else mask_ppto_acum_old
        df_p_mes = df_fin[mask_ppto_mes].copy()
        df_p_acum_r = df_fin[mask_ppto_acum].copy()
        if not df_p_mes.empty:
            df_p_mes['Sede_Nom'] = df_p_mes['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[1])
            df_p_mes['Grupo'] = df_p_mes['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[0])
            df_p_mes = df_p_mes[df_p_mes['Sede_Nom'].isin(s_filtro) & df_p_mes['Grupo'].isin(g_filtro)]
        if not df_p_acum_r.empty:
            df_p_acum_r['Sede_Nom'] = df_p_acum_r['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[1])
            df_p_acum_r['Grupo'] = df_p_acum_r['codigo_sede_crudo'].apply(lambda x: MAPEO_SEDES.get(x, ('OTRO', 'OTRO'))[0])
            df_p_acum_r = df_p_acum_r[df_p_acum_r['Sede_Nom'].isin(s_filtro) & df_p_acum_r['Grupo'].isin(g_filtro)]
            df_p_acum = df_p_acum_r.groupby('codigo_sede_crudo', as_index=False).agg({'Ventas': 'sum', 'Sede_Nom': 'first', 'Grupo': 'first'})
        else:
            df_p_acum = pd.DataFrame(columns=['codigo_sede_crudo', 'Ventas', 'Sede_Nom', 'Grupo'])
        ppto_mes_por_sede = df_p_mes.groupby('codigo_sede_crudo')['Ventas'].sum() if not df_p_mes.empty else pd.Series(dtype=float)
    else:
        df_r_acum = pd.DataFrame()
        df_p_acum = pd.DataFrame()
        ppto_mes_por_sede = pd.Series(dtype=float)

    def _filas_por_grupo(df_sedes, col_venta='Venta_Real', col_ppto=None):
        """Construye lista de filas: por grupo, sedes + Total grupo; luego Total general."""
        filas = []
        for grp in ORDEN_GRUPOS:
            dg = df_sedes[df_sedes['Grupo'] == grp]
            if dg.empty:
                continue
            # Ordenar sedes según ORDEN_SEDES; si no está mapeada, va al final en orden alfabético
            orden = dg['Sede_Nom'].map(ORDEN_SEDES_MAP).fillna(len(ORDEN_SEDES)).astype(int)
            for _, r in dg.assign(_orden=orden).sort_values(['_orden', 'Sede_Nom']).iterrows():
                v = r[col_venta] if col_venta in r else 0
                p = r[col_ppto] if col_ppto and col_ppto in r else 0
                filas.append({'Grupo': grp, 'RESTAURANTE': r['Sede_Nom'], 'venta': v, 'ppto': p, 'es_total': False})
            v_grp = dg[col_venta].sum() if col_venta in dg.columns else 0
            p_grp = dg[col_ppto].sum() if col_ppto and col_ppto in dg.columns else 0
            filas.append({'Grupo': grp, 'RESTAURANTE': f"Total {grp}", 'venta': v_grp, 'ppto': p_grp, 'es_total': True})
        if filas:
            tot_v = sum(f['venta'] for f in filas if f['es_total'])
            tot_p = sum(f['ppto'] for f in filas if f['es_total'])
            filas.append({'Grupo': '', 'RESTAURANTE': 'Total', 'venta': tot_v, 'ppto': tot_p, 'es_total': True})
        return filas

    if f_inicio and f_fin:
        titulo_fecha = (f"{DIAS_SEMANA[f_inicio.weekday()].upper()} {f_inicio.day} DE {MESES_ES[f_inicio.month].upper()} DE {f_inicio.year}" if f_inicio == f_fin
            else f"{DIAS_SEMANA[f_inicio.weekday()].upper()} {f_inicio.day} AL {DIAS_SEMANA[f_fin.weekday()].upper()} {f_fin.day} DE {MESES_ES[f_inicio.month].upper()} DE {f_inicio.year}")
    else:
        titulo_fecha = ""

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1. Ventas al público del día",
        "2. Comparativo 2026 vs 2025",
        "3. Presupuesto diario vs ventas al público",
        "4. Presupuesto acumulado vs ventas al público",
        "5. Transacciones 2026 vs 2025",
    ])

    with tab1:
        st.markdown(f'<p class="section-title">{titulo_fecha}</p>', unsafe_allow_html=True)
        if df_r.empty:
            st.info("No hay ventas al público para el día seleccionado.")
        else:
            agg_dict = {'Venta_Real': 'sum', 'Sede_Nom': 'first', 'Grupo': 'first'}
            if 'Cantidad_Transacciones' in df_r.columns:
                agg_dict['Cantidad_Transacciones'] = 'sum'
            df1 = df_r.groupby("codigo_sede_crudo", as_index=False).agg(agg_dict)
            if 'Cantidad_Transacciones' not in df1.columns:
                df1['Cantidad_Transacciones'] = 0
            filas1 = _filas_por_grupo(df1, col_venta='Venta_Real', col_ppto=None)
            if filas1:
                total_venta = filas1[-1]['venta']
                col_met, col_tab = st.columns([2, 4])
                with col_met:
                    st.metric("Ventas al público", f_moneda(total_venta))
                with col_tab:
                    pass
                rows_show = []
                for f in filas1:
                    if not f['es_total']:
                        mask = df1['Sede_Nom'] == f['RESTAURANTE']
                        tr = float(df1.loc[mask, 'Cantidad_Transacciones'].sum()) if mask.any() else 0
                    elif f['RESTAURANTE'] == 'Total':
                        tr = float(df1['Cantidad_Transacciones'].sum())
                    else:
                        tr = float(df1.loc[df1['Grupo'] == f['Grupo'], 'Cantidad_Transacciones'].sum())
                    ticket = (f['venta'] / tr) if tr and tr > 0 else 0
                    rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                    rows_show.append({
                        'GRUPO': f['Grupo'],
                        'RESTAURANTE': rest_label,
                        'VENTAS AL PÚBLICO': f_moneda(f['venta']),
                        'TRANSACCIONES': f_entero(tr),
                        'TICKET PROMEDIO': f_moneda(ticket),
                    })
                df_show1 = pd.DataFrame(rows_show)
                _st_dataframe(_estilo_tabla_informe(df_show1, col_var=None), hide_index=True)

    with tab2:
        st.markdown(f'<p class="section-title">Comparativo {titulo_fecha}</p>', unsafe_allow_html=True)
        if df_r.empty:
            st.info("No hay ventas al público 2026 para el día seleccionado.")
        else:
            codigos_r = set(df_r['codigo_sede_crudo'])
            codigos_h = set(df_h['codigo_sede_crudo']) if not df_h.empty else set()
            codigos = codigos_r | codigos_h
            filas2 = []
            for grp in ORDEN_GRUPOS:
                codigos_ordenados = sorted(
                    codigos,
                    key=lambda c: ORDEN_SEDES_MAP.get(
                        MAPEO_SEDES.get(c, ('OTRO', f'Sede {c}'))[1],
                        len(ORDEN_SEDES),
                    ),
                )
                for c in codigos_ordenados:
                    g, n = MAPEO_SEDES.get(c, ('OTRO', f'Sede {c}'))
                    if g != grp or n not in s_filtro or g not in g_filtro:
                        continue
                    v26 = df_r[df_r['codigo_sede_crudo'] == c]['Venta_Real'].sum()
                    v25 = df_h[df_h['codigo_sede_crudo'] == c]['Ventas'].sum() if not df_h.empty and 'Ventas' in df_h.columns else 0
                    var = (v26 / v25 - 1) if v25 and v25 > 0 else None
                    filas2.append({'Grupo': grp, 'RESTAURANTE': n, 'v26': v26, 'v25': v25, 'var': var, 'es_total': False})
                dg = [f for f in filas2 if f['Grupo'] == grp and not f['es_total']]
                if dg:
                    s26 = sum(x['v26'] for x in dg)
                    s25 = sum(x['v25'] for x in dg)
                    var_grp = (s26 / s25 - 1) if s25 and s25 > 0 else None
                    filas2.append({'Grupo': grp, 'RESTAURANTE': f"Total {grp}", 'v26': s26, 'v25': s25, 'var': var_grp, 'es_total': True})
            if filas2:
                tot26 = sum(f['v26'] for f in filas2 if f['es_total'])
                tot25 = sum(f['v25'] for f in filas2 if f['es_total'])
                var_total = (tot26 / tot25 - 1) if tot25 and tot25 > 0 else None
                filas2.append({'Grupo': '', 'RESTAURANTE': 'Total', 'v26': tot26, 'v25': tot25, 'var': var_total, 'es_total': True})
                col_met, _ = st.columns([2, 4])
                with col_met:
                    st.metric("Var. vs año anterior", f"{var_total:+.0%}" if var_total is not None else "—")
                rows_show = []
                for f in filas2:
                    rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                    var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                    rows_show.append({'GRUPO': f['Grupo'], 'RESTAURANTE': rest_label, 'VENTA DIARIA 2026': f_moneda(f['v26']), 'VENTA DIARIA 2025': f_moneda(f['v25']), 'VARIACIÓN': var_str})
                df_show2 = pd.DataFrame(rows_show)
                _st_dataframe(_estilo_tabla_informe(df_show2), hide_index=True)

    with tab3:
        st.markdown(f'<p class="section-title">Presupuesto diario vs ventas al público — {titulo_fecha}</p>', unsafe_allow_html=True)
        codigos = set(df_r['codigo_sede_crudo']).union(set(df_p['codigo_sede_crudo']) if not df_p.empty else set())
        filas3 = []
        for grp in ORDEN_GRUPOS:
            # Ordenar códigos según el nombre de sede y ORDEN_SEDES
            codigos_ordenados = sorted(
                codigos,
                key=lambda c: ORDEN_SEDES_MAP.get(
                    MAPEO_SEDES.get(c, ('OTRO', f'Sede {c}'))[1],
                    len(ORDEN_SEDES),
                ),
            )
            for c in codigos_ordenados:
                g, n = MAPEO_SEDES.get(c, ('OTRO', f'Sede {c}'))
                if g != grp or n not in s_filtro or g not in g_filtro:
                    continue
                v = df_r[df_r['codigo_sede_crudo'] == c]['Venta_Real'].sum()
                p = df_p[df_p['codigo_sede_crudo'] == c]['Ventas'].sum() if 'Ventas' in df_p.columns else 0
                var = (v / p - 1) if p and p > 0 else None
                filas3.append({'Grupo': grp, 'RESTAURANTE': n, 'venta': v, 'ppto': p, 'var': var, 'es_total': False})
            dg = [f for f in filas3 if f['Grupo'] == grp and not f['es_total']]
            if dg:
                sv = sum(x['venta'] for x in dg)
                sp = sum(x['ppto'] for x in dg)
                var_grp = (sv / sp - 1) if sp and sp > 0 else None
                filas3.append({'Grupo': grp, 'RESTAURANTE': f"Total {grp}", 'venta': sv, 'ppto': sp, 'var': var_grp, 'es_total': True})
        if filas3:
            tot_v = sum(f['venta'] for f in filas3 if f['es_total'])
            tot_p = sum(f['ppto'] for f in filas3 if f['es_total'])
            var_tot = (tot_v / tot_p - 1) if tot_p and tot_p > 0 else None
            filas3.append({'Grupo': '', 'RESTAURANTE': 'Total', 'venta': tot_v, 'ppto': tot_p, 'var': var_tot, 'es_total': True})

            # KPIs horizontales: Presupuesto día + Venta día con % dentro de la tarjeta de venta
            c1, c2, _ = st.columns([2, 2, 4])
            with c1:
                st.metric("Presupuesto día", f_moneda(tot_p))
            with c2:
                st.metric(
                    "Ventas al público día",
                    f_moneda(tot_v),
                    delta=f"{var_tot:+.0%}" if var_tot is not None else "—",
                )
            rows_show = []
            for f in filas3:
                rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                rows_show.append({'GRUPO': f['Grupo'], 'RESTAURANTE': rest_label, 'PRESUPUESTO DIARIO 2026': f_moneda(f['ppto']), 'VENTAS AL PÚBLICO 2026': f_moneda(f['venta']), 'VARIACIÓN': var_str})
            df_show3 = pd.DataFrame(rows_show)
            _st_dataframe(_estilo_tabla_informe(df_show3), hide_index=True)
            st.caption("Si un restaurante muestra **$0 en ventas**, puede que no haya datos de venta para esa fecha en la base operativa (ejecuta el ETL y pulsa «Refrescar datos» en el menú).")
        else:
            st.info("Sin datos para presupuesto o ventas al público del día.")

    with tab4:
        st.markdown(f'<p class="section-title">Ppto acumulado vs ventas al público acumuladas — MES DE {MESES_ES[f_fin.month].upper() if f_fin else ""}</p>', unsafe_allow_html=True)
        if df_r_acum.empty or not f_fin:
            st.info("Sin datos acumulados para el mes.")
        else:
            codigos = set(df_r_acum['codigo_sede_crudo']).union(set(df_p_acum['codigo_sede_crudo']) if not df_p_acum.empty else set())
            filas4 = []
            for grp in ORDEN_GRUPOS:
                codigos_ordenados = sorted(
                    codigos,
                    key=lambda c: ORDEN_SEDES_MAP.get(
                        MAPEO_SEDES.get(c, ('OTRO', f'Sede {c}'))[1],
                        len(ORDEN_SEDES),
                    ),
                )
                for c in codigos_ordenados:
                    g, n = MAPEO_SEDES.get(c, ('OTRO', f'Sede {c}'))
                    if g != grp or n not in s_filtro or g not in g_filtro:
                        continue
                    vacum = df_r_acum[df_r_acum['codigo_sede_crudo'] == c]['Venta_Real'].sum()
                    pacum = df_p_acum[df_p_acum['codigo_sede_crudo'] == c]['Ventas'].sum() if not df_p_acum.empty and 'Ventas' in df_p_acum.columns else 0
                    pmes = ppto_mes_por_sede.get(c, 0) if hasattr(ppto_mes_por_sede, 'get') else (ppto_mes_por_sede[c] if c in ppto_mes_por_sede.index else 0)
                    if ppto_acum_mismo_rango:
                        var = (vacum / pacum - 1) if pacum and pacum > 0 else None
                    else:
                        var = (vacum / pmes - 1) if pmes and pmes > 0 else None
                    filas4.append({'Grupo': grp, 'RESTAURANTE': n, 'venta_acum': vacum, 'ppto_acum': pacum, 'ppto_mes': pmes, 'var': var, 'es_total': False})
                dg = [f for f in filas4 if f['Grupo'] == grp and not f['es_total']]
                if dg:
                    va = sum(x['venta_acum'] for x in dg)
                    pa = sum(x['ppto_acum'] for x in dg)
                    pm = sum(x['ppto_mes'] for x in dg)
                    var_grp = (va / pa - 1) if ppto_acum_mismo_rango and pa and pa > 0 else ((va / pm - 1) if not ppto_acum_mismo_rango and pm and pm > 0 else None)
                    filas4.append({'Grupo': grp, 'RESTAURANTE': f"Total {grp}", 'venta_acum': va, 'ppto_acum': pa, 'ppto_mes': pm, 'var': var_grp, 'es_total': True})
            if filas4:
                tot_va = sum(f['venta_acum'] for f in filas4 if f['es_total'])
                tot_pa = sum(f['ppto_acum'] for f in filas4 if f['es_total'])
                tot_pmes = sum(f['ppto_mes'] for f in filas4 if f['es_total'])
                ppto_mes_gral = df_p_mes['Ventas'].sum() if not df_p_mes.empty and 'Ventas' in df_p_mes.columns else 0
                if ppto_acum_mismo_rango:
                    var_tot = (tot_va / tot_pa - 1) if tot_pa and tot_pa > 0 else None
                else:
                    var_tot = (tot_va / ppto_mes_gral - 1) if ppto_mes_gral and ppto_mes_gral > 0 else None
                filas4.append({'Grupo': '', 'RESTAURANTE': 'Total', 'venta_acum': tot_va, 'ppto_acum': tot_pa, 'ppto_mes': ppto_mes_gral, 'var': var_tot, 'es_total': True})
                c1, c2, _ = st.columns([2, 2, 4])
                with c1:
                    if ppto_acum_mismo_rango:
                        st.metric("Presupuesto acum. 1-" + str(f_fin.day), f_moneda(tot_pa))
                    else:
                        st.metric("Presupuesto mes " + MESES_ES[f_fin.month], f_moneda(ppto_mes_gral))
                with c2:
                    st.metric(
                        "Ventas al público acum. 1-" + str(f_fin.day),
                        f_moneda(tot_va),
                        delta=f"{var_tot:+.0%}" if var_tot is not None else "—",
                    )
                rows_show = []
                col_ppto = "PRESUP. ACUM. 1-" + str(f_fin.day) if ppto_acum_mismo_rango else "PRESUP. MES " + MESES_ES[f_fin.month].upper()
                for f in filas4:
                    rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                    var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                    ppto_val = f['ppto_acum'] if ppto_acum_mismo_rango else f['ppto_mes']
                    rows_show.append({'GRUPO': f['Grupo'], 'RESTAURANTE': rest_label, col_ppto: f_moneda(ppto_val), 'VENTAS AL PÚBLICO ACUM.': f_moneda(f['venta_acum']), 'VARIACIÓN': var_str})
                df_show4 = pd.DataFrame(rows_show)
                _st_dataframe(_estilo_tabla_informe(df_show4), hide_index=True)
                if ppto_acum_mismo_rango:
                    st.caption("Comparando mismo rango: presupuesto acumulado 1-" + str(f_fin.day) + " vs ventas acumuladas 1-" + str(f_fin.day) + ".")
                else:
                    st.caption("Comparando: presupuesto total del mes vs ventas acumuladas 1-" + str(f_fin.day) + ".")
            else:
                st.info("Sin datos acumulados.")

    with tab5:
        st.markdown(f'<p class="section-title">Transacciones 2026 vs 2025 — {titulo_fecha}</p>', unsafe_allow_html=True)
        codigos_tx_r = set(df_tx_26['codigo_sede_crudo']) if not df_tx_26.empty else set()
        codigos_tx_h = set(df_tx_25['codigo_sede_crudo']) if not df_tx_25.empty else set()
        codigos_tx = codigos_tx_r | codigos_tx_h
        filas5 = []
        for grp in ORDEN_GRUPOS:
            for c in codigos_tx:
                g, n = MAPEO_SEDES.get(c, ('OTRO', f'Sede {c}'))
                if g != grp or n not in s_filtro or g not in g_filtro:
                    continue
                tr26 = df_tx_26[df_tx_26['codigo_sede_crudo'] == c]['Transacciones'].sum() if not df_tx_26.empty else 0
                tr25 = df_tx_25[df_tx_25['codigo_sede_crudo'] == c]['Transacciones'].sum() if not df_tx_25.empty else 0
                var = (tr26 / tr25 - 1) if tr25 and tr25 > 0 else None
                filas5.append({'Grupo': grp, 'RESTAURANTE': n, 'tr26': tr26, 'tr25': tr25, 'var': var, 'es_total': False})
            dg = [f for f in filas5 if f['Grupo'] == grp and not f['es_total']]
            if dg:
                s26 = sum(x['tr26'] for x in dg)
                s25 = sum(x['tr25'] for x in dg)
                var_grp = (s26 / s25 - 1) if s25 and s25 > 0 else None
                filas5.append({'Grupo': grp, 'RESTAURANTE': f"Total {grp}", 'tr26': s26, 'tr25': s25, 'var': var_grp, 'es_total': True})
        if filas5:
            tot26 = sum(f['tr26'] for f in filas5 if f['es_total'])
            tot25 = sum(f['tr25'] for f in filas5 if f['es_total'])
            var_total = (tot26 / tot25 - 1) if tot25 and tot25 > 0 else None
            filas5.append({'Grupo': '', 'RESTAURANTE': 'Total', 'tr26': tot26, 'tr25': tot25, 'var': var_total, 'es_total': True})
            col_met, _ = st.columns([2, 4])
            with col_met:
                st.metric("Var. transacciones vs 2025", f"{var_total:+.0%}" if var_total is not None else "—")
            rows_show = []
            for f in filas5:
                rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                rows_show.append({
                    'GRUPO': f['Grupo'], 'RESTAURANTE': rest_label,
                    'TRANSACCIONES 2026': f_entero(f['tr26']), 'TRANSACCIONES 2025': f_entero(f['tr25']), 'VARIACIÓN': var_str
                })
            df_show5 = pd.DataFrame(rows_show)
            _st_dataframe(_estilo_tabla_informe(df_show5), hide_index=True)
            st.caption("Transacciones 2026 desde la base operativa. Transacciones 2025 desde el archivo transacciones_hist (solo año 2025) en la raíz o en fuentes_excel.")
        else:
            st.info("No hay datos de transacciones para el rango seleccionado. 2026: base operativa. 2025: archivo transacciones_hist.csv o transacciones_hist.xlsx con columnas Co, Fecha y Transacciones (solo año 2025).")

if __name__ == "__main__":
    main()
