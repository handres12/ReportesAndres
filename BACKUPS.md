# Backups del informe BI

## Archivos

- **`app.py`** — Versión actual para **publicación** (Streamlit Cloud). Incluye:
  - Transacciones correctas (Invoice → Store → StoreID_External = Co)
  - "Ventas al público" en la UI
  - Compatibilidad con Streamlit 1.19 (toggle, dataframe, estilo tablas)
  - Sin bloque de diagnóstico

- **`app_backup_actual.py`** — Copia de seguridad del `app.py` actual (mismo contenido que el de arriba). Úsalo si quieres volver a este estado después de probar cambios.

## Publicación

Para publicar en Streamlit Cloud, el repositorio debe usar **`app.py`** como archivo principal (ya configurado así). No cambies el nombre del archivo principal al publicar.

## Recuperar una versión antigua

Si guardaste una versión anterior en otro archivo (por ejemplo `app_backup_antiguo.py`), puedes:
- Revisarla ahí sin tocar `app.py`.
- Si quisieras usarla como principal: renómbrala a `app.py` y haz antes una copia del actual: `copy app.py app_backup_actual.py`.
