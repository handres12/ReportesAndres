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
import altair as alt

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
    # Recuadro más alto = menos barra para bajar; ancho mínimo en GRUPO/RESTAURANTE para que no se corte el texto
    opts = {k: v for k, v in kwargs.items() if k not in ("height", "column_config")}
    if "height" in kwargs:
        opts["height"] = kwargs["height"]
    elif "height" not in opts:
        opts["height"] = 560  # más filas visibles, menos desplazamiento
    if "column_config" not in kwargs and df is not None:
        try:
            cols = getattr(df, "data", df).columns if hasattr(getattr(df, "data", df), "columns") else getattr(df, "columns", [])
            # Ancho mínimo para GRUPO y RESTAURANTE para que no se corte (PARADERO FR, AEROPUERTO, ANDRES VIAJERO, etc.)
            min_ancho_texto = 140
            opts["column_config"] = {c: st.column_config.Column(width=min_ancho_texto) for c in cols if c in ("GRUPO", "RESTAURANTE")}
        except Exception:
            pass
    try:
        # Si use_container_width=True, no forzar width para que la tabla use todo el ancho y no haya scroll horizontal
        width_arg = None if opts.get("use_container_width") else "content"
        st.dataframe(df, width=width_arg, hide_index=hide_index, **opts)
    except (TypeError, AttributeError):
        opts_plain = {k: v for k, v in opts.items() if k in ("height", "use_container_width")}
        st.dataframe(df, width="stretch", hide_index=hide_index, **opts_plain)

def _parse_transaction_date(serie):
    """
    Parsea Transaction_Date conservando la hora. Acepta datetime, string ISO o formato
    tipo "3/09/2025 3:52:47 p. m." (12h con a. m. / p. m.). Devuelve serie datetime.
    """
    if serie.empty:
        return serie
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    s = serie.astype(str).str.strip()
    # Normalizar español a formato que entiende pandas: " p. m." -> " PM", " a. m." -> " AM"
    s = s.str.replace(r"\s+p\.\s*m\.", " PM", case=False, regex=True)
    s = s.str.replace(r"\s+a\.\s*m\.", " AM", case=False, regex=True)
    result = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    # Intentar primero formato día/mes/año con 12h (ej. "3/09/2025 3:52:47 p. m.")
    for fmt in (
        "%d/%m/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
    ):
        try:
            parsed = pd.to_datetime(s, format=fmt, errors="coerce")
            mask = parsed.notna()
            result = result.where(~mask, parsed)
        except Exception:
            continue
    # Rellenar lo que siga sin parsear
    still_na = result.isna()
    if still_na.any():
        result = result.where(~still_na, pd.to_datetime(serie, errors="coerce"))
    return result

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

  /* Tablas: ancho de celda al contenido (sin espacio en blanco extra); recuadro más alto = menos scroll */
  .dataframe thead tr th {
    background: #3d4554 !important;
    color: #fff !important; font-weight: 700 !important;
    padding: 6px 10px !important; font-size: 1.0625rem !important;
    border: 1px solid #2f3644 !important;
    white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important;
  }
  .dataframe tbody tr:hover { background: var(--acr-cream-dark) !important; }
  .dataframe tbody tr:nth-child(even) { background: #faf9f7 !important; }
  .dataframe tbody td {
    font-size: 1.0625rem !important; color: var(--text-primary) !important;
    padding: 6px 10px !important; border: 1px solid #e0e2e6 !important;
    white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important;
  }
  /* Celdas al ancho del contenido; ancho mínimo para que el texto no se corte (PARADERO, AEROPUERTO, etc.) */
  .dataframe table { table-layout: auto !important; width: auto !important; }
  .dataframe th, .dataframe td { box-sizing: border-box !important; min-width: min-content !important; overflow: visible !important; }
  /* Recuadro más alto hacia abajo para ver más filas sin bajar la barra; scroll horizontal si hace falta para no cortar texto */
  div[data-testid="stDataFrame"] > div { max-height: 75vh !important; min-height: 420px !important; overflow-x: auto !important; overflow-y: auto !important; }
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
    # Ventas: Co = raw_ventas_2026.StoreID (Detalle.Co). Normalización igual que ETL para coincidir con MAPEO_SEDES.
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
            # Unificar códigos con MAPEO_SEDES: 201.0 / 0201 -> 201; nombres de sede -> código (Medellín, Plaza Claro, Cafam)
            def _norm_codigo(c):
                c = str(c).strip().upper().lstrip('0') or '0'
                try:
                    c = str(int(float(c)))
                except (ValueError, TypeError):
                    pass
                ALIAS_A_CODIGO = {"MEDELLIN": "201", "MEDELLÍN": "201", "PLAZA CLARO": "F04", "PLAZACLARO": "F04", "CAFAM": "611"}
                k = c.replace("  ", " ")
                for old, new in [("Í", "I"), ("É", "E"), ("Á", "A"), ("Ó", "O"), ("Ú", "U"), ("Ñ", "N")]:
                    k = k.replace(old, new)
                return ALIAS_A_CODIGO.get(k, c)
            df['codigo_sede_crudo'] = df['codigo_sede_crudo'].astype(str).str.strip().apply(_norm_codigo)
            # Reagrupar por si había 201 y 201.0 (o nombre y código) como grupos distintos
            agg_cols = {'VlrBruto': 'sum', 'VlrTotalDesc': 'sum', 'Cantidad_Transacciones': 'sum', 'Store_Name': 'first'}
            agg_cols = {k: v for k, v in agg_cols.items() if k in df.columns}
            if agg_cols:
                df = df.groupby(['codigo_sede_crudo', 'Fecha'], as_index=False).agg(agg_cols)
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=120)
def load_ventas_horarias_2026(_cache_version=5):
    """
    Ventas y transacciones por hora (solo 2026) desde tabla local venta_horaria_2026.
    Esa tabla se llena en el ETL extrayendo la Hora en Python desde Transaction_Date (como en Excel).
    Solo se usa para el gráfico de la pestaña 7.
    """
    engine = get_engine()
    # Asegurar que la tabla exista (la crea el ETL; si no se ha corrido, la creamos vacía para no fallar)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS venta_horaria_2026 (
                    StoreID VARCHAR(50), BusinessDate DATE, Hora INTEGER,
                    Venta_Hora FLOAT, Transacciones_Hora INTEGER
                )
            """))
            conn.commit()
    except Exception:
        pass

    norm_co = "LTRIM(UPPER(TRIM(CAST(%s AS TEXT))), '0')"
    query = f"""
    SELECT
        {norm_co % 's.StoreID_External'} AS codigo_sede_crudo,
        vh.BusinessDate AS Fecha,
        vh.Hora AS Hora,
        vh.Venta_Hora AS Venta_Hora,
        vh.Transacciones_Hora AS Transacciones_Hora
    FROM venta_horaria_2026 vh
    INNER JOIN dim_store s
        ON TRIM(CAST(COALESCE(vh.StoreID, '') AS TEXT)) = TRIM(CAST(COALESCE(s.StoreID, '') AS TEXT))
    WHERE DATE(vh.BusinessDate) >= '2026-01-01'
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
    except Exception as e:
        if not _en_streamlit_cloud():
            st.error(f"Error al leer ventas horarias (venta_horaria_2026): {e}")
        return pd.DataFrame(columns=["codigo_sede_crudo", "Fecha", "Hora", "Venta_Hora", "Transacciones_Hora", "Sede_Nom", "Grupo"])

    if df.empty:
        return df

    df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
    df["Hora"] = pd.to_numeric(df["Hora"], errors="coerce").fillna(0).astype(int)

    def _norm_codigo(c):
        c = str(c).strip().upper().lstrip("0") or "0"
        try:
            c = str(int(float(c)))
        except (ValueError, TypeError):
            pass
        ALIAS_A_CODIGO = {
            "MEDELLIN": "201", "MEDELLÍN": "201",
            "PLAZA CLARO": "F04", "PLAZACLARO": "F04",
            "CAFAM": "611",
        }
        k = c.replace("  ", " ")
        for old, new in [("Í", "I"), ("É", "E"), ("Á", "A"), ("Ó", "O"), ("Ú", "U"), ("Ñ", "N")]:
            k = k.replace(old, new)
        return ALIAS_A_CODIGO.get(k, c)

    df["codigo_sede_crudo"] = df["codigo_sede_crudo"].astype(str).str.strip().apply(_norm_codigo)
    MAPEO_SEDES = load_mapeo_sedes()
    df["Sede_Nom"] = df["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[1])
    df["Grupo"] = df["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[0])
    return df


def load_ventas_horarias_2026_raw():
    """
    Lee venta_horaria_2026 sin JOIN con dim_store.
    Sirve para diagnóstico cuando el JOIN devuelve 0 filas (p. ej. StoreID no coincide).
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(
                text("SELECT StoreID, BusinessDate AS Fecha, Hora, Venta_Hora, Transacciones_Hora FROM venta_horaria_2026 WHERE DATE(BusinessDate) >= '2026-01-01'"),
                con=conn,
            )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
    df["Hora"] = pd.to_numeric(df["Hora"], errors="coerce").fillna(0).astype(int)
    return df


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
    col_co = _detectar_columna(df, ["Co", "CentroOP", "Centro", "Codigo", "StoreID_External", "StoreID", "Sede", "Tienda"])
    col_mes = _detectar_columna(df, ["Mes", "Month", "MES"])
    col_2025 = None
    for c in df.columns:
        if str(c).strip() == "2025":
            col_2025 = c
            break
    col_fecha = _detectar_columna(df, ["Fecha", "FechaDocto", "Date", "FechaVenta", "Dia", "Business Date", "BusinessDate"])
    col_tx = _detectar_columna(df, [
        "Transacciones", "Cantidad_Transacciones", "Cantidad", "CantTransacciones",
        "Num Transacciones", "NumeroTransacciones", "Tickets", "Invoices", "Sales Count", "SalesCount"
    ])

    # Formato A: Co, Mes, columna 2025 (transacciones mensuales por año) -> diarizar
    MESES_NUM = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    if col_co and col_mes and col_2025 is not None:
        codigo_norm = (
            df[col_co].astype(str).str.strip().str.upper().str.replace(r"\.0$", "", regex=True).str.lstrip("0")
        )
        df["_co"] = codigo_norm
        df["_mes_str"] = df[col_mes].astype(str).str.strip().str.lower()
        df["_tx"] = pd.to_numeric(df[col_2025], errors="coerce").fillna(0)
        df = df[(df["_co"] != "") & (~df["_co"].str.upper().str.contains("NAN", na=True))]
        filas = []
        for _, row in df.iterrows():
            mes_num = MESES_NUM.get(row["_mes_str"])
            if mes_num is None:
                continue
            _, dias_mes = calendar.monthrange(2025, mes_num)
            tx_dia = row["_tx"] / dias_mes if dias_mes else 0
            for dia in range(1, dias_mes + 1):
                filas.append({
                    "codigo_sede_crudo": row["_co"],
                    "Fecha": date(2025, mes_num, dia),
                    "Transacciones": tx_dia,
                })
        if filas:
            out = pd.DataFrame(filas)
            agg = out.groupby(["codigo_sede_crudo", "Fecha"], as_index=False)["Transacciones"].sum()
            agg["codigo_sede_crudo"] = agg["codigo_sede_crudo"].astype(str).str.strip()
            return agg
    # Formato B: Co, Fecha, Transacciones (datos diarios)
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
    out = out[out["codigo_sede_crudo"].astype(str).str.strip() != ""]
    out = out[~out["codigo_sede_crudo"].astype(str).str.upper().str.contains("NAN", na=True)]
    out = out[out["Fecha"].apply(lambda d: getattr(d, "year", None) == 2025)]
    if out.empty:
        return pd.DataFrame()
    agg = out.groupby(["codigo_sede_crudo", "Fecha"], as_index=False)["Transacciones"].sum()
    return agg


@st.cache_data(ttl=600)
def load_pestana_6_excel():
    """
    Carga venta 2024 y 2025.xlsx (o pestaña 6.xlsx) a nivel de fila (por establecimiento y mes).
    Columnas: Co (opcional), Mes/#Mes, Venta 2024 (F), Venta 2025 (I), Transacciónes 2024/2025.
    Añade Sede_Nom y Grupo desde Co + MAPEO_SEDES para que el informe pueda filtrar por Restaurantes/Grupos.
    Devuelve DataFrame con _mes, _r24, _tx24, _r25, _tx25, Sede_Nom, Grupo. Si no hay Co, Sede_Nom/Grupo son NaN (se usan todas las filas).
    """
    def _norm_cols(cols):
        return [str(c).strip().lstrip("\ufeff") for c in cols]

    def _detectar_col(df, candidatos):
        cols = _norm_cols(df.columns)
        for cand in candidatos:
            cand_low = cand.strip().lower()
            for col in cols:
                if cand_low in col.strip().lower():
                    return col
        return None

    def _a_num(serie):
        if serie is None or serie.empty:
            return pd.Series(dtype=float)
        # Si Excel devolvió números, usarlos tal cual (evitar borrar el punto decimal)
        num = pd.to_numeric(serie, errors="coerce")
        as_str = serie.astype(str)
        cleaned = as_str.str.replace(r"\.", "", regex=True).str.replace(",", ".", regex=False)
        parsed = pd.to_numeric(cleaned, errors="coerce")
        return num.where(num.notna(), parsed).fillna(0)

    base = os.path.dirname(os.path.abspath(__file__))
    posibles = [base, os.path.join(base, "fuentes_excel"), os.getcwd()]
    ruta = None
    ruta_pestana6 = None
    for carpeta in posibles:
        if not os.path.isdir(carpeta):
            continue
        for f in os.listdir(carpeta):
            f_low = f.lower()
            if not f_low.endswith(".xlsx"):
                continue
            if "venta 2024" in f_low and "2025" in f_low:
                ruta = os.path.join(carpeta, f)
                break
            if ("pestaña 6" in f_low or "pestana 6" in f_low) and ruta_pestana6 is None:
                ruta_pestana6 = os.path.join(carpeta, f)
        if ruta:
            break
    if not ruta and ruta_pestana6:
        ruta = ruta_pestana6
    if not ruta or not os.path.isfile(ruta):
        return pd.DataFrame()

    try:
        df = pd.read_excel(ruta, sheet_name=0)
    except Exception:
        return pd.DataFrame()

    df.columns = _norm_cols(df.columns)
    col_mes_num = _detectar_col(df, ["#Mes", "NumMes", "MesNum", "Nro Mes"])
    col_mes_nom = _detectar_col(df, ["Mes", "Month"])
    col_co = _detectar_col(df, ["Co", "Código", "Codigo", "StoreID", "Punto de venta"])
    col_r24 = _detectar_col(df, ["Venta 2024", "Restaurante 2024", "Ventas 2024"])
    col_tx24 = _detectar_col(df, ["Transacciónes 2024", "Transacciones 2024", "Transacciones2024"])
    col_r25 = _detectar_col(df, ["Venta 2025", "Restaurante 2025", "Ventas 2025"])
    col_tx25 = _detectar_col(df, ["Transacciónes 2025", "Transacciones 2025", "Transacciones2025"])

    if not col_r24 or not col_tx24 or not col_r25 or not col_tx25:
        return pd.DataFrame()

    mes_col = col_mes_num if col_mes_num is not None else col_mes_nom
    if mes_col is None:
        return pd.DataFrame()

    MESES_NOM = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                 "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    df["_mes"] = df[mes_col].apply(lambda x: MESES_NOM.get(str(x).strip().lower(), None) if pd.notna(x) else None)
    if df["_mes"].isna().all():
        df["_mes"] = pd.to_numeric(df[mes_col], errors="coerce").astype("Int64")
    df = df.dropna(subset=["_mes"])
    df["_mes"] = df["_mes"].astype(int)
    df["_r24"] = _a_num(df[col_r24])
    df["_tx24"] = _a_num(df[col_tx24])
    df["_r25"] = _a_num(df[col_r25])
    df["_tx25"] = _a_num(df[col_tx25])

    # Mapear Co (o Punto de venta) a Sede_Nom y Grupo para poder filtrar como en el resto del informe
    def _norm_co(c):
        if pd.isna(c): return ""
        c = str(c).strip().upper().lstrip("0") or "0"
        try:
            c = str(int(float(c)))
        except (ValueError, TypeError):
            pass
        return c

    try:
        MAPEO = load_mapeo_sedes()
        sede_to_code = {str(s).strip().upper().replace("Í", "I").replace("É", "E"): k for k, (g, s) in MAPEO.items() if s}
    except Exception:
        MAPEO = {}
        sede_to_code = {}

    if col_co is not None:
        es_nombre = "punto de venta" in str(col_co).lower() or "punto de venta" in str(col_co)
        if es_nombre:
            def _nombre_a_codigo(v):
                if pd.isna(v): return ""
                n = str(v).strip().upper().replace("Í", "I").replace("É", "E").replace("Á", "A").replace("Ó", "O").replace("Ú", "U").replace("Ñ", "N")
                return sede_to_code.get(n, _norm_co(v))
            df["_codigo"] = df[col_co].map(_nombre_a_codigo)
        else:
            df["_codigo"] = df[col_co].map(_norm_co)
        df["Sede_Nom"] = df["_codigo"].map(lambda c: MAPEO.get(c, ("OTRO", None))[1] if c else None)
        df["Grupo"] = df["_codigo"].map(lambda c: MAPEO.get(c, (None, "OTRO"))[0] if c else None)
    else:
        df["_codigo"] = ""
        df["Sede_Nom"] = pd.NA
        df["Grupo"] = pd.NA

    return df[["_mes", "_r24", "_tx24", "_r25", "_tx25", "Sede_Nom", "Grupo"]].copy()


# --- FORMATOS ---
def f_moneda(v): return f"${v:,.0f}".replace(",", ".") if pd.notna(v) else "$0"
def f_entero(v): return f"{v:,.0f}".replace(",", ".") if pd.notna(v) else "0"

def _fmt_millones_pesos(n):
    """Formato valor en millones: $ 14.164 (punto como separador de miles)."""
    if n is None or (isinstance(n, str) and n == "—"): return "—"
    try: return f"$ {int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError): return "—"

def _fmt_unidades(n):
    """Formato cantidad/unidades: 33.060 (punto como separador de miles, sin $)."""
    if n is None or (isinstance(n, str) and n == "—"): return "—"
    try: return f"{int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError): return "—"

def _fmt_miles_pesos(v):
    """Formato valor en miles de $: 113857 -> $ 113,9 (miles)."""
    if v is None or (isinstance(v, str) and v == "—"): return "—"
    try:
        x = float(v) / 1000
        return f"$ {x:,.1f}".replace(",", ".")
    except (TypeError, ValueError): return "—"

def _fmt_miles_unidades(n):
    """Formato cantidad en miles: 20416 -> 20,4 (miles)."""
    if n is None or (isinstance(n, str) and n == "—"): return "—"
    try:
        x = float(n) / 1000
        return f"{x:,.1f}".replace(",", ".")
    except (TypeError, ValueError): return "—"

def _esc(s):
    """Escapa HTML en cadenas para tablas."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _cls_var(var_str):
    """Estilo para celda VARIACIÓN (verde/rojo)."""
    if var_str is None or var_str == "—": return ""
    if "▲" in str(var_str) or "+" in str(var_str): return "background-color:#e6f4e6;color:#1a5f1a;font-weight:600;"
    if "▼" in str(var_str) or ("-" in str(var_str) and "%" in str(var_str)): return "background-color:#fde8e8;color:#a01c28;font-weight:600;"
    return ""

def _html_tabla_informe(headers, row_tuples, col_var_index=None):
    """Genera tabla HTML compacta (fit-content, sin scroll). row_tuples: list of (tr_class, [v1, v2, ...], var_style_for_last).
       tr_class: '' | ' total-gral' | ' total-grupo'. col_var_index: índice 0-based de col VARIACIÓN (para estilo), o None."""
    css = (
        "<style>.tbl-informe { width: fit-content; max-width: 100%; table-layout: auto; border-collapse: collapse; font-size: 0.9rem; }"
        ".tbl-informe th, .tbl-informe td { border: 1px solid #ddd; padding: 4px 10px; white-space: nowrap; text-align: left; }"
        ".tbl-informe th { background: #f0f2f6; font-weight: 600; }"
        ".tbl-informe td:nth-child(3), .tbl-informe td:nth-child(4) { text-align: right; }"
        ".tbl-informe td:nth-child(5) { text-align: center; }"
        ".tbl-informe tr.total-gral td { background-color: #E8A317; color: #1a1510; font-weight: bold; }"
        ".tbl-informe tr.total-grupo td { background-color: #3d4554; color: #fff; font-weight: bold; }</style>"
    )
    html = css + "<table class='tbl-informe'><thead><tr>"
    html += "".join(f"<th>{_esc(h)}</th>" for h in headers) + "</tr></thead><tbody>"
    for tr_cls, cells, var_style in row_tuples:
        html += f"<tr class='{tr_cls}'>"
        for i, v in enumerate(cells):
            style = (" style='" + var_style + "'" if var_style and col_var_index is not None and i == col_var_index else "")
            html += f"<td{style}>{_esc(v)}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

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
    _refresh = st.session_state.get("_refresh", 0)
    f_inicio = st.sidebar.date_input("Desde", u_f, key=f"f_desde_{_refresh}")
    f_fin = st.sidebar.date_input("Hasta", u_f, key=f"f_hasta_{_refresh}")
    if f_fin < f_inicio:
        f_fin = f_inicio
        st.sidebar.caption("Hasta no puede ser anterior a Desde. Se usó la misma fecha.")

    f_sel = f_inicio  # para títulos y acumulado "hasta" usamos f_fin donde aplique

    sedes_map = sorted(list(set([v[1] for v in MAPEO_SEDES.values()])))
    s_filtro = st.sidebar.multiselect("Restaurantes", options=sedes_map, default=sedes_map, key=f"p_sedes_{_refresh}")
    grupos_map = sorted(list(set([v[0] for v in MAPEO_SEDES.values()])))
    g_filtro = st.sidebar.multiselect("Grupos", options=grupos_map, default=grupos_map, key=f"p_grupos_{_refresh}")
    
    st.sidebar.markdown("---")
    if st.sidebar.button(
        "🔄 Refrescar datos",
        help="Vuelve al reporte por defecto: última fecha con datos, todos los restaurantes y grupos (y recarga cachés).",
    ):
        # Resetear filtros y fechas: _refresh hace que los widgets (fechas, restaurantes, grupos) se recreen con valores por defecto
        st.session_state["_refresh"] = st.session_state.get("_refresh", 0) + 1
        # Pestaña 7: volver a última fecha con datos
        st.session_state["p7_fecha"] = u_f
        try:
            load_ventas_operativas.clear()
            load_financiero_excel.clear()
            load_transacciones_hist_2025.clear()
            load_pestana_6_excel.clear()
            load_ventas_horarias_2026.clear()
        except Exception:
            pass
        st.rerun()
    # Flag global para el comparativo 2025 (se controla visualmente en la pestaña 2)
    alinear = st.session_state.get("p2_lunes_vs_lunes", True)
    f_inicio_25 = (f_inicio - timedelta(days=364)) if alinear else f_inicio.replace(year=2025)
    f_fin_25 = (f_fin - timedelta(days=364)) if alinear else f_fin.replace(year=2025)
    # La opción \"Ppto acumulado: mismo rango\" ahora vive dentro de la pestaña 4 (no en el sidebar).

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

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "1. Ventas al público del día",
        "2. Comparativo 2026 vs 2025",
        "3. Presupuesto diario vs ventas al público",
        "4. Presupuesto acumulado vs ventas al público",
        "5. Transacciones 2026 vs 2025",
        "6. Tendencia 2025 vs 2026 (mes a mes)",
        "7. Venta diaria comparativa",
    ])

    with tab1:
        st.markdown(f'<p class="section-title">{titulo_fecha}</p>', unsafe_allow_html=True)
        # Aviso: hasta qué fecha hay datos (las ventas vienen de SQL Server → ETL → SQLite)
        fecha_max = df_op['Fecha'].max()
        if hasattr(fecha_max, 'date'):
            fecha_max = fecha_max.date()
        st.caption(f"Datos de ventas disponibles **hasta el {fecha_max.strftime('%d/%m/%Y')}**. Si el día que buscas es más reciente, la base principal (SQL Server, tabla Detalle) aún no tiene esa fecha cargada; cuando esté disponible, ejecuta de nuevo los ETLs (**ejecutar_etls.py**).")
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
                headers1 = ['GRUPO', 'RESTAURANTE', 'VENTAS AL PÚBLICO', 'TRANSACCIONES', 'TICKET PROMEDIO']
                row_tuples = []
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
                    tr_cls = " total-gral" if f['RESTAURANTE'] == 'Total' else (" total-grupo" if f['es_total'] else "")
                    row_tuples.append((tr_cls, [f['Grupo'], rest_label, f_moneda(f['venta']), f_entero(tr), f_moneda(ticket)], ""))
                st.markdown(_html_tabla_informe(headers1, row_tuples, col_var_index=None), unsafe_allow_html=True)

    with tab2:
        st.markdown(f'<p class="section-title">Comparativo {titulo_fecha}</p>', unsafe_allow_html=True)
        # Esta opción aplica solo a este informe: alinear el comparativo 2026 vs 2025 por día de la semana
        st.toggle(
            "Lunes vs Lunes (comparativo 2025)",
            value=st.session_state.get("p2_lunes_vs_lunes", True),
            key="p2_lunes_vs_lunes",
            help="Si está activo, compara el mismo día de la semana: lunes con lunes, domingo con domingo (ajusta las fechas 2025).",
        )
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
                headers2 = ['GRUPO', 'RESTAURANTE', 'VENTA DIARIA 2025', 'VENTA DIARIA 2026', 'VARIACIÓN']
                row_tuples = []
                for f in filas2:
                    rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                    var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                    tr_cls = " total-gral" if f['RESTAURANTE'] == 'Total' else (" total-grupo" if f['es_total'] else "")
                    row_tuples.append((tr_cls, [f['Grupo'], rest_label, f_moneda(f['v25']), f_moneda(f['v26']), var_str], _cls_var(var_str)))
                st.markdown(_html_tabla_informe(headers2, row_tuples, col_var_index=4), unsafe_allow_html=True)
                # Ayuda cuando hay sedes con $0 en 2026 (ej. Medellín, Plaza Claro el 13/mar)
                sedes_sin_venta_26 = [f["RESTAURANTE"] for f in filas2 if not f["es_total"] and f["v26"] == 0]
                if sedes_sin_venta_26:
                    fecha_diagnostico = (f_inicio or f_fin or date(2026, 3, 13)).strftime("%Y-%m-%d")
                    with st.expander("¿Por qué algunas sedes muestran $0 en Venta diaria 2026?"):
                        st.markdown(
                            f"**Sedes con $0 el día seleccionado:** {', '.join(sedes_sin_venta_26)}.  \n\n"
                            "Los datos 2026 vienen de la **base local** (tabla `raw_ventas_2026`), cargada por el ETL desde **SQL Server (tabla Detalle)**. "
                            "Si no hay registros para ese día/sede en Detalle, aquí aparece $0.  \n\n"
                            f"**Para revisar en tu PC:** ejecuta en la carpeta del proyecto:  \n"
                            f"`python debug_raw_ventas_2026.py {fecha_diagnostico}`  \n"
                            "Verás qué sedes (StoreID) tienen datos ese día. "
                            "Si MEDELLIN (201) o PLAZA CLARO (F04) no aparecen, el origen está en SQL Server o el ETL no ha cargado esa fecha."
                        )

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
            headers3 = ['GRUPO', 'RESTAURANTE', 'PRESUPUESTO DIARIO 2026', 'VENTAS AL PÚBLICO 2026', 'VARIACIÓN']
            row_tuples = []
            for f in filas3:
                rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                tr_cls = " total-gral" if f['RESTAURANTE'] == 'Total' else (" total-grupo" if f['es_total'] else "")
                row_tuples.append((tr_cls, [f['Grupo'], rest_label, f_moneda(f['ppto']), f_moneda(f['venta']), var_str], _cls_var(var_str)))
            st.markdown(_html_tabla_informe(headers3, row_tuples, col_var_index=4), unsafe_allow_html=True)
            st.caption("Si un restaurante muestra **$0 en ventas**, puede que no haya datos de venta para esa fecha en la base operativa (ejecuta el ETL y pulsa «Refrescar datos» en el menú).")
        else:
            st.info("Sin datos para presupuesto o ventas al público del día.")

    with tab4:
        st.markdown(f'<p class="section-title">Ppto acumulado vs ventas al público acumuladas — MES DE {MESES_ES[f_fin.month].upper() if f_fin else ""}</p>', unsafe_allow_html=True)
        # Esta opción solo aplica a este informe: mismo rango 1-X vs 1-X o presupuesto total mes vs ventas acum. 1-X
        ppto_acum_mismo_rango = st.toggle(
            "Ppto acumulado: mismo rango (1-X vs 1-X)",
            value=True,
            key="p4_ppto_acum_mismo_rango",
            help="Si está activo: presupuesto acumulado 1-X vs ventas acumuladas 1-X. Si está apagado: presupuesto total del mes vs ventas acumuladas 1-X.",
        )
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
                col_ppto = "PRESUP. ACUM. 1-" + str(f_fin.day) if ppto_acum_mismo_rango else "PRESUP. MES " + MESES_ES[f_fin.month].upper()
                headers4 = ['GRUPO', 'RESTAURANTE', col_ppto, 'VENTAS AL PÚBLICO ACUM.', 'VARIACIÓN']
                row_tuples = []
                for f in filas4:
                    rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                    var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                    ppto_val = f['ppto_acum'] if ppto_acum_mismo_rango else f['ppto_mes']
                    tr_cls = " total-gral" if f['RESTAURANTE'] == 'Total' else (" total-grupo" if f['es_total'] else "")
                    row_tuples.append((tr_cls, [f['Grupo'], rest_label, f_moneda(ppto_val), f_moneda(f['venta_acum']), var_str], _cls_var(var_str)))
                st.markdown(_html_tabla_informe(headers4, row_tuples, col_var_index=4), unsafe_allow_html=True)
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
            # Tabla HTML compacta: ancho justo al contenido, sin scroll ni espacios grandes
            css_t5 = (
                "<style>.tbl-tx5 { width: fit-content; max-width: 100%; table-layout: auto; border-collapse: collapse; "
                "font-size: 0.9rem; }.tbl-tx5 th, .tbl-tx5 td { border: 1px solid #ddd; padding: 4px 10px; white-space: nowrap; "
                "text-align: left; }.tbl-tx5 th { background: #f0f2f6; font-weight: 600; }.tbl-tx5 td:nth-child(3), "
                ".tbl-tx5 td:nth-child(4) { text-align: right; }.tbl-tx5 td:nth-child(5) { text-align: center; }"
                ".tbl-tx5 tr.total-gral td { background-color: #E8A317; color: #1a1510; font-weight: bold; }"
                ".tbl-tx5 tr.total-grupo td { background-color: #3d4554; color: #fff; font-weight: bold; }</style>"
            )
            tbl5 = css_t5 + "<table class='tbl-tx5'><thead><tr><th>GRUPO</th><th>RESTAURANTE</th><th>TRANSACCIONES 2026</th><th>TRANSACCIONES 2025</th><th>VARIACIÓN</th></tr></thead><tbody>"
            for f in filas5:
                rest_label = ("▪ " + f['RESTAURANTE']) if f['es_total'] and f['RESTAURANTE'] != 'Total' else f['RESTAURANTE']
                var_str = "—" if f['var'] is None else (f"{f['var']:+.0%} ▲" if f['var'] >= 0 else f"{f['var']:+.0%} ▼")
                tr_cls = " total-gral" if f['RESTAURANTE'] == 'Total' else (" total-grupo" if f['es_total'] else "")
                var_style = _cls_var(var_str)
                tbl5 += f"<tr class='{tr_cls}'><td>{_esc(f['Grupo'])}</td><td>{_esc(rest_label)}</td><td>{_esc(f_entero(f['tr26']))}</td><td>{_esc(f_entero(f['tr25']))}</td><td style='{var_style}'>{_esc(var_str)}</td></tr>"
            tbl5 += "</tbody></table>"
            st.markdown(tbl5, unsafe_allow_html=True)
            st.caption("Transacciones 2026 desde la base operativa. Transacciones 2025 desde el archivo transacciones_hist (solo año 2025) en la raíz o en fuentes_excel.")
        else:
            st.info("No hay datos de transacciones para el rango seleccionado. 2026: base operativa. 2025: archivo transacciones_hist.csv o transacciones_hist.xlsx con columnas Co, Fecha y Transacciones (solo año 2025).")

    with tab6:
        # Tendencia 2025 vs 2026 mes a mes: gráfico % crecimiento y tablas VR NETO x año/mes y YTD
        tipo_tienda_label = "(* TODOS *)" if (set(s_filtro) == set(sedes_map) and set(g_filtro) == set(grupos_map)) else "(filtro aplicado)"
        rango_fecha_6 = f"Del: {f_inicio.strftime('%d/%m/%Y')} Al: {f_fin.strftime('%d/%m/%Y')}" if f_inicio and f_fin else ""
        # Agregados 2026 por mes (desde df_op, hasta f_fin)
        df_op_6 = df_op.copy()
        df_op_6["Fecha"] = pd.to_datetime(df_op_6["Fecha"])
        df_op_6["Venta_Real"] = df_op_6["VlrBruto"] - df_op_6["VlrTotalDesc"].abs()
        if not df_op_6.empty:
            df_op_6["Sede_Nom"] = df_op_6["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[1])
            df_op_6["Grupo"] = df_op_6["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[0])
            df_op_6 = df_op_6[df_op_6["Sede_Nom"].isin(s_filtro) & df_op_6["Grupo"].isin(g_filtro)]
        mask_26 = (df_op_6["Fecha"].dt.year == 2026) & (df_op_6["Fecha"] <= pd.Timestamp(f_fin)) if f_fin else (df_op_6["Fecha"].dt.year == 2026)
        _df26 = df_op_6.loc[mask_26].copy()
        if not _df26.empty:
            _df26["Mes"] = _df26["Fecha"].dt.month
            if "Cantidad_Transacciones" in _df26.columns:
                mes_26 = _df26.groupby("Mes").agg(Venta_Real=("Venta_Real", "sum"), Transacciones=("Cantidad_Transacciones", "sum")).reset_index()
            else:
                mes_26 = _df26.groupby("Mes").agg(Venta_Real=("Venta_Real", "sum")).reset_index()
                mes_26["Transacciones"] = 0
            mes_26["Ticket"] = mes_26["Venta_Real"] / mes_26["Transacciones"].replace(0, float("nan"))
        else:
            mes_26 = pd.DataFrame(columns=["Mes", "Venta_Real", "Transacciones", "Ticket"])
        # Agregados 2025 por mes (desde df_fin Historico)
        df_fin_25 = df_fin[(pd.to_datetime(df_fin["Fecha"]).dt.year == 2025) & (df_fin["Escenario"].str.contains("Historico", na=False))].copy()
        if not df_fin_25.empty:
            df_fin_25["Fecha"] = pd.to_datetime(df_fin_25["Fecha"])
            df_fin_25["Sede_Nom"] = df_fin_25["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[1])
            df_fin_25["Grupo"] = df_fin_25["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[0])
            df_fin_25 = df_fin_25[df_fin_25["Sede_Nom"].isin(s_filtro) & df_fin_25["Grupo"].isin(g_filtro)]
        if not df_fin_25.empty:
            df_fin_25["Mes"] = df_fin_25["Fecha"].dt.month
            mes_25 = df_fin_25.groupby("Mes").agg(Ventas=("Ventas", "sum"), Transacciones=("Transacciones", "sum")).reset_index()
            mes_25["Ticket"] = mes_25["Ventas"] / mes_25["Transacciones"].replace(0, float("nan"))
        else:
            mes_25 = pd.DataFrame(columns=["Mes", "Ventas", "Transacciones", "Ticket"])
        # Gráfico solo 2026: Vr Neto Ventas POS, Transacciones y Ticket promedio (índice Enero=100 para que las líneas se crucen)
        st.markdown(f"**TENDENCIA 2026 - VR NETO VENTAS POS, NRO TRANSACCIONES Y VR TICKET PROMEDIO   Del: {f_fin.strftime('%d/%m/%Y') if f_fin else '—'}.**")
        if not mes_26.empty:
            mes_26_s = mes_26.sort_values("Mes").reset_index(drop=True)
            v0 = mes_26_s.loc[mes_26_s["Mes"] == mes_26_s["Mes"].min(), "Venta_Real"].sum()
            t0 = mes_26_s.loc[mes_26_s["Mes"] == mes_26_s["Mes"].min(), "Transacciones"].sum()
            tk0 = mes_26_s.loc[mes_26_s["Mes"] == mes_26_s["Mes"].min(), "Ticket"].mean()
            rows_chart = []
            for _, r in mes_26_s.iterrows():
                m, mn = int(r["Mes"]), MESES_ES[int(r["Mes"])]
                v, t, tk = r["Venta_Real"], r["Transacciones"], r["Ticket"] if pd.notna(r["Ticket"]) else 0
                idx_v = (100 * v / v0) if v0 and v0 != 0 else 100
                idx_t = (100 * t / t0) if t0 and t0 != 0 else 100
                idx_tk = (100 * tk / tk0) if tk0 and pd.notna(tk0) and tk0 != 0 else 100
                rows_chart.append({"Mes": m, "Mes_nombre": mn, "Vr Neto Ventas POS 2026": idx_v, "Nro Transacciones 2026": idx_t, "Vr Ticket Promedio 2026": idx_tk})
            df_chart_26 = pd.DataFrame(rows_chart)
            df_chart = df_chart_26.melt(id_vars=["Mes", "Mes_nombre"], value_vars=["Vr Neto Ventas POS 2026", "Nro Transacciones 2026", "Vr Ticket Promedio 2026"], var_name="Metrica", value_name="Índice")
            # Tooltip con etiquetas claras y valor con 1 decimal (Enero=100)
            ch = alt.Chart(df_chart).mark_line(point=True, strokeWidth=2.5).encode(
                x=alt.X("Mes_nombre:N", sort=[MESES_ES[i] for i in sorted(df_chart_26["Mes"].unique())], title="Mes"),
                y=alt.Y("Índice:Q", title="Índice (Enero=100)"),
                color=alt.Color("Metrica:N", legend=alt.Legend(title=""), scale=alt.Scale(
                    domain=["Vr Neto Ventas POS 2026", "Nro Transacciones 2026", "Vr Ticket Promedio 2026"],
                    range=["#0d47a1", "#e65100", "#00695c"],
                )),
                tooltip=[
                    alt.Tooltip("Mes_nombre:N", title="Mes"),
                    alt.Tooltip("Metrica:N", title="Métrica"),
                    alt.Tooltip("Índice:Q", title="Índice (Enero=100)", format=".1f"),
                ],
            ).properties(width=700, height=350)
            st.altair_chart(ch, use_container_width=True)
        else:
            st.info("No hay datos 2026 por mes para mostrar la tendencia.")
        # Datos 2024 y 2025 desde Excel (venta 2024 y 2025.xlsx): filtrar por Restaurantes/Grupos y agregar por mes
        df_excel_6 = load_pestana_6_excel()
        excel_6_cargado = not df_excel_6.empty
        if not df_excel_6.empty and "Sede_Nom" in df_excel_6.columns and df_excel_6["Sede_Nom"].notna().any():
            df_excel_6 = df_excel_6[df_excel_6["Sede_Nom"].isin(s_filtro) & df_excel_6["Grupo"].isin(g_filtro)]
        if not df_excel_6.empty:
            agg_24_25 = df_excel_6.groupby("_mes", as_index=False).agg(
                {"_r24": "sum", "_tx24": "sum", "_r25": "sum", "_tx25": "sum"}
            )
            ventas_24 = {int(r["_mes"]): float(r["_r24"]) for _, r in agg_24_25.iterrows()}
            transacciones_24 = {int(r["_mes"]): float(r["_tx24"]) for _, r in agg_24_25.iterrows()}
            ticket_24 = {int(r["_mes"]): (float(r["_r24"]) / float(r["_tx24"]) if r["_tx24"] and r["_tx24"] > 0 else None) for _, r in agg_24_25.iterrows()}
            ventas_25_excel = {int(r["_mes"]): float(r["_r25"]) for _, r in agg_24_25.iterrows()}
            transacciones_25_excel = {int(r["_mes"]): float(r["_tx25"]) for _, r in agg_24_25.iterrows()}
            ticket_25_excel = {int(r["_mes"]): (float(r["_r25"]) / float(r["_tx25"]) if r["_tx25"] and r["_tx25"] > 0 else None) for _, r in agg_24_25.iterrows()}
        else:
            ventas_24 = {}
            transacciones_24 = {}
            ticket_24 = {}
            ventas_25_excel = {}
            transacciones_25_excel = {}
            ticket_25_excel = {}

        cols_mes = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        headers = ["Año"] + cols_mes + ["Totales"]
        # Variación 2026 vs 2025 (solo comparamos 26 vs 25): texto y estilo semáforo por celda
        def _fila_variacion_26_25(v25_d, v26_d):
            celdas_texto = []
            estilos = []
            for i in range(1, 13):
                v25 = v25_d.get(i) if i in v25_d else None
                v26 = v26_d.get(i) if i in v26_d else None
                v25_n = (v25 or 0) if v25 is not None else 0
                v26_n = (v26 or 0) if v26 is not None else 0
                if v25_n == 0 or v26 is None:
                    celdas_texto.append("—")
                    estilos.append("")
                else:
                    var = (v26_n - v25_n) / float(v25_n)
                    txt = f"{var:+.1%} ▲" if var >= 0 else f"{var:+.1%} ▼"
                    txt = txt.replace(".", ",")  # decimal con coma
                    celdas_texto.append(txt)
                    estilos.append(_cls_var(txt))
            # Total: variación (suma 26 - suma 25) / suma 25
            s25 = sum((v or 0) for v in v25_d.values())
            s26 = sum((v or 0) for v in v26_d.values())
            if s25 == 0:
                celdas_texto.append("—")
                estilos.append("")
            else:
                var_tot = (s26 - s25) / float(s25)
                txt = f"{var_tot:+.1%} ▲" if var_tot >= 0 else f"{var_tot:+.1%} ▼"
                txt = txt.replace(".", ",")
                celdas_texto.append(txt)
                estilos.append(_cls_var(txt))
            return celdas_texto, estilos

        tbl_css = (
            "<style>.tbl-ventas-mes { width: 100%; max-width: 100%; table-layout: fixed; border-collapse: collapse; "
            "font-size: 0.9rem; }.tbl-ventas-mes th, .tbl-ventas-mes td { border: 1px solid #ddd; padding: 6px 8px; "
            "text-align: right; overflow: hidden; text-overflow: ellipsis; }.tbl-ventas-mes th { background: #f0f2f6; "
            "text-align: center; font-weight: 600; }.tbl-ventas-mes td:first-child { text-align: center; font-weight: 500; }</style>"
        )
        # Ventas por año (2024/2025 desde Excel filtrado; 2025 fallback desde df_fin; 2026 desde mes_26)
        ventas_26 = {int(r["Mes"]): r["Venta_Real"] for _, r in mes_26.iterrows()}
        ventas_25 = {int(r["Mes"]): r["Ventas"] for _, r in mes_25.iterrows()}
        if ventas_25_excel:
            ventas_25 = ventas_25_excel
        transacciones_26 = {int(r["Mes"]): r["Transacciones"] for _, r in mes_26.iterrows()}
        transacciones_25 = transacciones_25_excel if transacciones_25_excel else ({} if not mes_25.empty else {})
        if not transacciones_25 and not mes_25.empty:
            transacciones_25 = {int(r["Mes"]): r["Transacciones"] for _, r in mes_25.iterrows()}
        ticket_26 = {int(r["Mes"]): r["Ticket"] for _, r in mes_26.iterrows() if pd.notna(r.get("Ticket"))}
        ticket_25 = ticket_25_excel if ticket_25_excel else {}
        if not ticket_25 and not mes_25.empty:
            ticket_25 = {int(r["Mes"]): r["Ticket"] for _, r in mes_25.iterrows() if pd.notna(r.get("Ticket"))}

        # Tabla 1: VR NETO VENTAS POS X AÑO Y MES (3×15) — valor ÷ 1000, formato $ 17.343.321
        def _fmt_ventas_miles(n):
            """Formato ventas (valor ya ÷1000): $ 17.343.321 (punto miles, enteros)."""
            if n is None or (isinstance(n, str) and n == "—"): return "—"
            try:
                x = int(round(float(n)))
                return f"$ {x:,}".replace(",", ".")
            except (TypeError, ValueError): return "—"

        def _filas_ventas_miles(ventas_d):
            vals = {c: round(ventas_d.get(i, 0) / 1000, 0) for i, c in enumerate(cols_mes, 1)}
            tot = int(sum(vals[c] for c in cols_mes))  # total = suma de los 12 meses mostrados
            return [_fmt_ventas_miles(vals[c]) for c in cols_mes] + [_fmt_ventas_miles(tot)]

        filas_ventas = []
        if ventas_24:
            filas_ventas.append(("2024", _filas_ventas_miles(ventas_24)))
        filas_ventas.append(("2025", _filas_ventas_miles(ventas_25)))
        filas_ventas.append(("2026", _filas_ventas_miles(ventas_26)))
        st.markdown(f"**VR NETO VENTAS POS X AÑO Y MES** - (valor ÷ 1000, en miles $)  Del: {f_fin.strftime('%d/%m/%Y') if f_fin else '—'}.**")
        tbl_html = tbl_css + "<table class='tbl-ventas-mes'><thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>"
        for año, celdas in filas_ventas:
            tbl_html += f"<tr><td>{año}</td>" + "".join(f"<td>{v}</td>" for v in celdas) + "</tr>"
        # Fila 4: Variación 2026 vs 2025 (semáforo)
        var_ventas_txt, var_ventas_style = _fila_variacion_26_25(ventas_25, ventas_26)
        tbl_html += "<tr><td>Var. 26/25</td>"
        for j, (v, style) in enumerate(zip(var_ventas_txt, var_ventas_style)):
            tbl_html += f"<td style='{style}'>{v}</td>" if style else f"<td>{v}</td>"
        tbl_html += "</tr></tbody></table>"
        st.markdown(tbl_html, unsafe_allow_html=True)

        # Tabla 2: TICKET PROMEDIO POR MES (3×15) — presentar el dato tal cual (sin ÷1000)
        def _fmt_pesos_entero(v):
            if v is None or (isinstance(v, str) and v == "—"): return "—"
            try: return f"$ {int(round(float(v))):,}".replace(",", ".")
            except (TypeError, ValueError): return "—"

        def _filas_ticket(ticket_d, ventas_d, tx_d):
            celdas = []
            for i in range(1, 13):
                v = ticket_d.get(i) if ticket_d.get(i) and pd.notna(ticket_d.get(i)) else None
                celdas.append(_fmt_pesos_entero(v) if v is not None else "—")
            sum_v = sum(ventas_d.values()) if ventas_d else 0
            sum_t = sum(tx_d.values()) if tx_d else 0
            ytd = (sum_v / sum_t) if sum_t and sum_t > 0 else None
            celdas.append(_fmt_pesos_entero(ytd) if ytd is not None else "—")
            return celdas

        filas_ticket = []
        if ticket_24 or ventas_24 or transacciones_24:
            filas_ticket.append(("2024", _filas_ticket(ticket_24, ventas_24, transacciones_24)))
        filas_ticket.append(("2025", _filas_ticket(ticket_25, ventas_25, transacciones_25)))
        filas_ticket.append(("2026", _filas_ticket(ticket_26, ventas_26, transacciones_26)))
        st.markdown(f"**TICKET PROMEDIO POR MES** ($)  Del: {f_fin.strftime('%d/%m/%Y') if f_fin else '—'}.**")
        tbl_ticket = tbl_css + "<table class='tbl-ventas-mes'><thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>"
        for año, celdas in filas_ticket:
            tbl_ticket += f"<tr><td>{año}</td>" + "".join(f"<td>{v}</td>" for v in celdas) + "</tr>"
        var_ticket_txt, var_ticket_style = _fila_variacion_26_25(ticket_25, ticket_26)
        tbl_ticket += "<tr><td>Var. 26/25</td>"
        for j, (v, style) in enumerate(zip(var_ticket_txt, var_ticket_style)):
            tbl_ticket += f"<td style='{style}'>{v}</td>" if style else f"<td>{v}</td>"
        tbl_ticket += "</tr></tbody></table>"
        st.markdown(tbl_ticket, unsafe_allow_html=True)

        # Tabla 3: TRANSACCIONES POR MES (3×15) — mismo criterio: datos del Excel filtrados, suma por mes, total = suma de los 12 meses
        def _filas_transacciones(tx_d):
            vals = {c: tx_d.get(i, 0) for i, c in enumerate(cols_mes, 1)}
            tot = int(sum(vals[c] for c in cols_mes))  # total = suma de los 12 meses mostrados (como ventas y ticket)
            return [_fmt_unidades(vals[c]) for c in cols_mes] + [_fmt_unidades(tot)]

        filas_tx = []
        if transacciones_24:
            filas_tx.append(("2024", _filas_transacciones(transacciones_24)))
        filas_tx.append(("2025", _filas_transacciones(transacciones_25)))
        filas_tx.append(("2026", _filas_transacciones(transacciones_26)))
        st.markdown(f"**TRANSACCIONES POR MES** (suma por mes)  Del: {f_fin.strftime('%d/%m/%Y') if f_fin else '—'}.**")
        tbl_tx = tbl_css + "<table class='tbl-ventas-mes'><thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>"
        for año, celdas in filas_tx:
            tbl_tx += f"<tr><td>{año}</td>" + "".join(f"<td>{v}</td>" for v in celdas) + "</tr>"
        var_tx_txt, var_tx_style = _fila_variacion_26_25(transacciones_25, transacciones_26)
        tbl_tx += "<tr><td>Var. 26/25</td>"
        for j, (v, style) in enumerate(zip(var_tx_txt, var_tx_style)):
            tbl_tx += f"<td style='{style}'>{v}</td>" if style else f"<td>{v}</td>"
        tbl_tx += "</tr></tbody></table>"
        st.markdown(tbl_tx, unsafe_allow_html=True)
        if excel_6_cargado:
            st.caption("Datos 2024 y 2025 desde **venta 2024 y 2025.xlsx** (o pestaña 6.xlsx); se aplican los mismos filtros de Restaurantes y Grupos. Ventas = valor ÷ 1000 (en miles $); ticket promedio = dato tal cual ($); transacciones = suma por mes. 2026 desde base operativa.")
        else:
            st.caption("Para incluir 2024 y 2025: añade **venta 2024 y 2025.xlsx** (o pestaña 6.xlsx) en la raíz o fuentes_excel. Columnas: Co o Punto de venta (para filtrar), Mes/#Mes, Venta 2024 (F), Venta 2025 (I), Transacciónes 2024/2025.")

    with tab7:
        st.markdown("<p class='section-title'>Venta diaria comparativa</p>", unsafe_allow_html=True)
        _fmax = df_op["Fecha"].max()
        if hasattr(_fmax, "date"):
            _fmax = _fmax.date()
        _fmin = df_op["Fecha"].min()
        if hasattr(_fmin, "date"):
            _fmin = _fmin.date()
        fecha_default = f_fin or f_inicio or _fmax
        if fecha_default is None:
            fecha_default = _fmax
        if hasattr(fecha_default, "date"):
            fecha_default = fecha_default.date()
        if "p7_fecha" not in st.session_state:
            st.session_state["p7_fecha"] = min(fecha_default, _fmax)
        fecha_sel = st.session_state["p7_fecha"]

        modo_comp = st.radio(
            "Comparar contra:",
            options=["Día anterior", "4 semanas anteriores"],
            horizontal=True,
            key="p7_modo",
        )
        # Navegación día anterior / siguiente
        col_prev, col_fecha, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ Día anterior", key="p7_prev"):
                st.session_state["p7_fecha"] = max(_fmin, fecha_sel - timedelta(days=1))
                st.rerun()
        with col_next:
            if st.button("Día siguiente ▶", key="p7_next"):
                st.session_state["p7_fecha"] = min(_fmax, fecha_sel + timedelta(days=1))
                st.rerun()
        with col_fecha:
            st.markdown(
                f"<div style='text-align:center; font-weight:600; font-size:1.05rem; color:#212529;'>"
                f"{DIAS_SEMANA[fecha_sel.weekday()]} {fecha_sel.day} de {MESES_ES[fecha_sel.month]} de {fecha_sel.year}</div>",
                unsafe_allow_html=True,
            )

        if modo_comp == "Día anterior":
            fecha_ref = fecha_sel - timedelta(days=7)
            etiqueta_ref = "mismo día semana anterior"
        else:
            fecha_ref = fecha_sel - timedelta(days=28)
            etiqueta_ref = "4 semanas anteriores"
        texto_actual = f"{DIAS_SEMANA[fecha_sel.weekday()]} {fecha_sel.day} de {MESES_ES[fecha_sel.month]} de {fecha_sel.year}"
        texto_ref = f"{DIAS_SEMANA[fecha_ref.weekday()]} {fecha_ref.day} de {MESES_ES[fecha_ref.month]} de {fecha_ref.year}"
        st.markdown(
            f"<div style='background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; "
            "padding: 12px 16px; margin: 8px 0 16px 0; border-left: 4px solid #2e86ab;'>"
            f"<span style='color:#495057;font-size:0.95rem;'>Comparando: <strong>{texto_actual}</strong> vs <strong>{texto_ref}</strong> "
            f"<span style='color:#6c757d;'>({etiqueta_ref})</span></span></div>",
            unsafe_allow_html=True,
        )

        def _resumen_p7(fecha):
            df_base = df_op[df_op["Fecha"] == fecha].copy()
            if df_base.empty:
                return 0.0, 0.0, 0.0
            if "Sede_Nom" not in df_base.columns or "Grupo" not in df_base.columns:
                df_base["Sede_Nom"] = df_base["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[1])
                df_base["Grupo"] = df_base["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[0])
            df_base = df_base[df_base["Sede_Nom"].isin(s_filtro) & df_base["Grupo"].isin(g_filtro)]
            if df_base.empty:
                return 0.0, 0.0, 0.0
            df_base = df_base.copy()
            df_base["Venta_Real"] = df_base["VlrBruto"] - df_base["VlrTotalDesc"].abs()
            v = float(df_base["Venta_Real"].sum())
            # Si la suma de Cantidad_Transacciones es 0 pero hay filas, usar el conteo de filas como aproximación,
            # para evitar tickets promedio en 0 cuando sí hubo movimiento.
            if "Cantidad_Transacciones" in df_base.columns:
                t_raw = float(df_base["Cantidad_Transacciones"].sum())
            else:
                t_raw = float(len(df_base))
            if t_raw <= 0 and len(df_base) > 0:
                t_raw = float(len(df_base))
            tk = (v / t_raw) if t_raw > 0 else 0.0
            return v, t_raw, tk

        v_act, tr_act, tk_act = _resumen_p7(fecha_sel)
        v_ref, tr_ref, tk_ref = _resumen_p7(fecha_ref)

        # Diagnóstico rápido: qué datos se están usando para cada día (por si hay filtros activos)
        with st.expander("Ver detalle de sedes y transacciones usadas en el comparativo"):
            df_act = df_op[df_op["Fecha"] == fecha_sel].copy()
            df_ref = df_op[df_op["Fecha"] == fecha_ref].copy()
            for df_det, titulo in [(df_act, f"Día seleccionado ({fecha_sel})"), (df_ref, f"Día de referencia ({fecha_ref})")]:
                if df_det.empty:
                    st.caption(f"{titulo}: sin filas en df_op (no hay ventas cargadas para esa fecha con los filtros actuales).")
                else:
                    if "Sede_Nom" not in df_det.columns or "Grupo" not in df_det.columns:
                        df_det["Sede_Nom"] = df_det["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[1])
                        df_det["Grupo"] = df_det["codigo_sede_crudo"].apply(lambda x: MAPEO_SEDES.get(x, ("OTRO", "OTRO"))[0])
                    df_det = df_det[df_det["Sede_Nom"].isin(s_filtro) & df_det["Grupo"].isin(g_filtro)]
                    df_det["Venta_Real"] = df_det["VlrBruto"] - df_det["VlrTotalDesc"].abs()
                    cols = ["Fecha", "codigo_sede_crudo", "Sede_Nom", "Grupo", "Venta_Real"]
                    if "Cantidad_Transacciones" in df_det.columns:
                        cols.append("Cantidad_Transacciones")
                    st.caption(f"{titulo}: {len(df_det)} filas después de filtros de Restaurantes y Grupos.")
                    st.dataframe(df_det[cols], use_container_width=True, hide_index=True)

        def _var_pct(act, ref):
            return None if ref == 0 else (act / ref) - 1.0

        var_v = _var_pct(v_act, v_ref)
        var_tr = _var_pct(tr_act, tr_ref)
        var_tk = _var_pct(tk_act, tk_ref)

        def _var_str(var):
            if var is None:
                return "—"
            return f"{var:+.1%}".replace(".", ",") + (" ▲" if var >= 0 else " ▼")

        lbl_actual = f"{DIAS_SEMANA[fecha_sel.weekday()][:3]} {fecha_sel.day}/{fecha_sel.month}"
        lbl_ref = f"{DIAS_SEMANA[fecha_ref.weekday()][:3]} {fecha_ref.day}/{fecha_ref.month}"

        # Resumen ejecutivo: conclusión en una mirada + impacto en pesos (lo que un CEO quiere ver primero)
        _delta_ventas = v_act - v_ref
        _sube_baja = "por encima" if (var_v or 0) >= 0 else "por debajo"
        _conclusion = f"Hoy ({lbl_actual}) estás <strong>{_sube_baja}</strong> del día de referencia ({lbl_ref}) en ventas."
        if var_v is not None and var_tr is not None and var_tk is not None:
            _todas = [var_v, var_tr, var_tk]
            _positivas = sum(1 for x in _todas if x is not None and x >= 0)
            if _positivas == 3:
                _conclusion = f"<strong>{lbl_actual}</strong> ganó en las 3 métricas vs {lbl_ref}."
            elif _positivas == 0:
                _conclusion = f"<strong>{lbl_ref}</strong> ganó en las 3 métricas. Hoy ({lbl_actual}) está por debajo en ventas, transacciones y ticket."
            else:
                _conclusion = f"Resultado mixto: {_positivas} métrica(s) arriba y {3 - _positivas} abajo vs {lbl_ref}."
        _color_v = "#0d8050" if (var_v or 0) >= 0 else "#c53030"
        _color_tr = "#0d8050" if (var_tr or 0) >= 0 else "#c53030"
        _color_tk = "#0d8050" if (var_tk or 0) >= 0 else "#c53030"
        _txt_v = _var_str(var_v)
        _txt_tr = _var_str(var_tr)
        _txt_tk = _var_str(var_tk)
        st.markdown(
            "<div style='background: #fff; border-radius: 12px; padding: 16px 20px; margin: 0 0 16px 0; "
            "border: 1px solid #e9ecef; box-shadow: 0 2px 8px rgba(0,0,0,0.06);'>"
            "<p style='margin: 0 0 12px 0; font-size: 1rem; color: #212529;'>"
            "📌 <strong>En una mirada:</strong> "
            + _conclusion + "</p>"
            + ("<p style='margin: 0 0 8px 0; font-size: 0.9rem; color: #495057;'>Diferencia en ventas: <strong style='color:" + (_color_v if _delta_ventas >= 0 else "#c53030") + "'>" + f_moneda(abs(_delta_ventas)) + (" más" if _delta_ventas >= 0 else " menos") + "</strong> vs referencia.</p>" if _delta_ventas != 0 else "")
            + "<div style='display: flex; gap: 24px; flex-wrap: wrap; margin-top: 12px;'>"
            + f"<span style='font-size: 1.1rem;'><strong>Ventas</strong> <span style='color:{_color_v}; font-weight: 700;'>{_txt_v}</span></span>"
            + f"<span style='font-size: 1.1rem;'><strong>Transacciones</strong> <span style='color:{_color_tr}; font-weight: 700;'>{_txt_tr}</span></span>"
            + f"<span style='font-size: 1.1rem;'><strong>Ticket prom.</strong> <span style='color:{_color_tk}; font-weight: 700;'>{_txt_tk}</span></span>"
            + "</div></div>",
            unsafe_allow_html=True,
        )

        # Gráfico de variación % (respuesta directa: ¿cómo salimos vs referencia?)
        _pct_v = (var_v * 100) if var_v is not None else 0
        _pct_tr = (var_tr * 100) if var_tr is not None else 0
        _pct_tk = (var_tk * 100) if var_tk is not None else 0
        df_var = pd.DataFrame([
            {"Metrica": "Ventas", "Variacion_pct": _pct_v},
            {"Metrica": "Transacciones", "Variacion_pct": _pct_tr},
            {"Metrica": "Ticket promedio", "Variacion_pct": _pct_tk},
        ])
        _ymax = max(15, abs(_pct_v), abs(_pct_tr), abs(_pct_tk)) * 1.2
        ch_var = (
            alt.Chart(df_var)
            .mark_bar(size=40)
            .encode(
                x=alt.X("Metrica:N", title="", sort=None),
                y=alt.Y("Variacion_pct:Q", title="Variación % vs día de referencia", scale=alt.Scale(domain=[-_ymax, _ymax]), axis=alt.Axis(format="+.1f")),
                color=alt.condition(
                    alt.datum.Variacion_pct >= 0,
                    alt.value("#0d8050"),
                    alt.value("#c53030"),
                ),
                tooltip=[alt.Tooltip("Metrica:N"), alt.Tooltip("Variacion_pct:Q", format="+.1f", title="Variación %")],
            )
            .properties(height=220, title="Variación vs día de referencia")
            .configure_axis(gridColor="#e9ecef")
        )
        st.altair_chart(ch_var, use_container_width=True)
        st.markdown("---")
        st.markdown("**Comparativo en nivel** (proporción dentro de cada métrica):")
        # Una sola gráfica con los 6 datos: normalizado por métrica (el mayor = 100) para que se vea proporcionado
        def _norm(act, ref):
            m = max(act, ref) if (act or ref) else 1
            return (act / m * 100) if act else 0, (ref / m * 100) if ref else 0

        v_na, v_nr = _norm(v_act, v_ref)
        tr_na, tr_nr = _norm(tr_act, tr_ref)
        tk_na, tk_nr = _norm(tk_act, tk_ref)

        # Tarjetas de resumen por día
        card_css = (
            "<style>.p7-card { background: #fff; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); "
            "padding: 16px 20px; border: 1px solid #e9ecef; } "
            ".p7-card h4 { margin: 0 0 12px 0; font-size: 0.95rem; color: #2e86ab; } "
            ".p7-card p { margin: 4px 0; font-size: 0.85rem; color: #495057; } "
            ".p7-card strong { color: #212529; }</style>"
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                card_css
                + f"<div class='p7-card'><h4>📅 {lbl_actual}</h4>"
                + f"<p>Ventas: <strong>{f_moneda(v_act)}</strong></p>"
                + f"<p>Transacciones: <strong>{f_entero(tr_act)}</strong></p>"
                + f"<p>Ticket prom.: <strong>{f_moneda(tk_act)}</strong></p></div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                card_css
                + f"<div class='p7-card'><h4>📅 {lbl_ref}</h4>"
                + f"<p>Ventas: <strong>{f_moneda(v_ref)}</strong></p>"
                + f"<p>Transacciones: <strong>{f_entero(tr_ref)}</strong></p>"
                + f"<p>Ticket prom.: <strong>{f_moneda(tk_ref)}</strong></p></div>",
                unsafe_allow_html=True,
            )
        st.markdown("<br>", unsafe_allow_html=True)

        df_chart = pd.DataFrame([
            {"Etiqueta": f"Ventas · {lbl_actual}", "Día": lbl_actual, "Valor_norm": v_na, "Valor_real": v_act, "Métrica": "Ventas"},
            {"Etiqueta": f"Ventas · {lbl_ref}", "Día": lbl_ref, "Valor_norm": v_nr, "Valor_real": v_ref, "Métrica": "Ventas"},
            {"Etiqueta": f"Transacciones · {lbl_actual}", "Día": lbl_actual, "Valor_norm": tr_na, "Valor_real": tr_act, "Métrica": "Transacciones"},
            {"Etiqueta": f"Transacciones · {lbl_ref}", "Día": lbl_ref, "Valor_norm": tr_nr, "Valor_real": tr_ref, "Métrica": "Transacciones"},
            {"Etiqueta": f"Ticket prom. · {lbl_actual}", "Día": lbl_actual, "Valor_norm": tk_na, "Valor_real": tk_act, "Métrica": "Ticket prom."},
            {"Etiqueta": f"Ticket prom. · {lbl_ref}", "Día": lbl_ref, "Valor_norm": tk_nr, "Valor_real": tk_ref, "Métrica": "Ticket prom."},
        ])
        ch_bars = (
            alt.Chart(df_chart)
            .mark_bar(size=32)
            .encode(
                x=alt.X("Etiqueta:N", sort=None, title="", axis=alt.Axis(labelAngle=-25, labelFontSize=11)),
                y=alt.Y("Valor_norm:Q", title="Proporción (máx del par = 100%)", scale=alt.Scale(domain=[0, 105]), axis=alt.Axis(gridColor="#e9ecef", tickCount=6)),
                color=alt.Color("Día:N", legend=alt.Legend(title="Día", orient="top"), scale=alt.Scale(range=["#2e86ab", "#e94f37"])),
                tooltip=[
                    alt.Tooltip("Etiqueta:N", title=""),
                    alt.Tooltip("Valor_norm:Q", title="Proporción", format=",.0f"),
                    alt.Tooltip("Valor_real:Q", title="Valor", format=",.0f"),
                ],
            )
            .properties(height=340, title=alt.TitleParams("Comparativo: Ventas, Transacciones y Ticket promedio", fontSize=16, fontWeight=600))
            .configure_view(strokeWidth=0)
            .configure_axis(domainColor="#dee2e6", labelColor="#495057", titleFontSize=12)
        )
        st.altair_chart(ch_bars, use_container_width=True)

        # Tabla comparativa (estilo card)
        tbl_comp_css = (
            "<style>"
            ".wrap-tbl-comp { background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); padding: 0; overflow: hidden; margin: 16px 0; border: 1px solid #e9ecef; }"
            ".tbl-comp-dia { width: 100%; max-width: 100%; table-layout: auto; border-collapse: collapse; font-size: 0.95rem; }"
            ".tbl-comp-dia th, .tbl-comp-dia td { padding: 12px 16px; white-space: nowrap; text-align: right; border-bottom: 1px solid #e9ecef; }"
            ".tbl-comp-dia th { background: linear-gradient(180deg, #2e86ab 0%, #257a9e 100%); color: #fff; font-weight: 600; text-align: center; font-size: 0.9rem; }"
            ".tbl-comp-dia td:first-child { text-align: left; font-weight: 600; color: #495057; }"
            ".tbl-comp-dia tbody tr:hover { background: #f8f9fa; }"
            ".tbl-comp-dia tbody tr:last-child td { border-bottom: none; }"
            "</style>"
        )
        html_comp = (
            tbl_comp_css
            + "<div class='wrap-tbl-comp'><table class='tbl-comp-dia'><thead><tr>"
            + f"<th>Métrica</th><th>{_esc(lbl_actual)}</th><th>{_esc(lbl_ref)}</th><th>Variación</th>"
            + "</tr></thead><tbody>"
        )
        for label, val_act, val_ref, var in [
            ("Ventas", f_moneda(v_act), f_moneda(v_ref), var_v),
            ("Transacciones", f_entero(tr_act), f_entero(tr_ref), var_tr),
            ("Ticket promedio", f_moneda(tk_act), f_moneda(tk_ref), var_tk),
        ]:
            var_txt = _var_str(var)
            var_style = _cls_var(var_txt)
            html_comp += f"<tr><td>{_esc(label)}</td><td>{_esc(val_act)}</td><td>{_esc(val_ref)}</td><td style='{var_style}'>{_esc(var_txt)}</td></tr>"
        html_comp += "</tbody></table></div>"
        st.markdown(html_comp, unsafe_allow_html=True)

        st.caption(
            "Fuente: ventas al público (raw_ventas_2026 + transacciones). "
            "Se respetan los filtros de Restaurantes y Grupos del panel izquierdo."
        )

if __name__ == "__main__":
    main()
