"""
Prueba mínima para Streamlit Cloud.
Si en la web ves "OK - La nube responde", el fallo está en app.py o en las dependencias.
Si sigue el error, el fallo está en la configuración o cuenta de Cloud.
"""
import streamlit as st

st.set_page_config(page_title="Prueba", layout="wide")
st.write("## OK - La nube responde")
st.caption("Si ves esto, Streamlit Cloud funciona. El error viene de app.py o de requirements. Cambia Main file de vuelta a app.py y revisamos.")
