# Contexto del proyecto — leer primero

**Uso:** Archivo para que la IA (o quien retome el proyecto) entre en contexto rápido.  
**Regla:** En cada cambio relevante al proyecto, actualizar la sección correspondiente y la fecha en «Última actualización» al final.

---

## 1. Qué es este proyecto

- **Dashboard BI en Streamlit** para **Andrés Carne de Res**: informe de ventas con filtros por fecha, restaurante y grupo.
- **Datos:** ventas operativas (SQL Server/Micros) + presupuesto e histórico (Excel) → todo consolidado en **SQLite** (`bi_local_data.db`). La app **solo lee** de SQLite; los ETLs escriben en SQLite desde SQL Server y Excel.
- **Publicado en:** Streamlit Community Cloud → `https://reportesandresbi.streamlit.app` (repo GitHub: `handres12/ReportesAndres`).

---

## 2. Estructura de la app (app.py)

- **Entrada:** Si no hay sesión → pantalla de login (Microsoft **o** usuario/contraseña según configuración). Si hay sesión → informe.
- **Informe:** 6 pestañas:
  1. Ventas al público del día (por sede, con transacciones y ticket).
  2. Comparativo 2026 vs 2025 (Lunes vs Lunes opcional).
  3. Presupuesto diario vs ventas al público.
  4. Presupuesto acumulado vs ventas al público.
  5. Transacciones 2026 vs 2025.
  6. Tendencia 2025 vs 2026 (mes a mes): gráfico 2026 con índice Enero=100 (Vr Neto Ventas POS, Nro Transacciones, Vr Ticket Promedio) y tabla 2×14 en HTML (VR Neto Ventas POS por año/mes en $).
- **Filtros (sidebar):** Rango de fechas (Desde/Hasta), Restaurantes, Grupos, “Ocultar sedes sin venta real”, toggle “Lunes vs Lunes (comparativo 2025)”.
- **Helpers importantes:** `get_engine()`, `load_ventas_operativas()` (ventas + transacciones vía Invoice→Store→StoreID_External=Co; tras leer, normaliza `codigo_sede_crudo` y reagrupa por sede/fecha para evitar duplicados 201 vs 201.0), `load_financiero_excel()`, `load_mapeo_sedes()`, `_dataframe_serializable()`, `_st_dataframe()`, `_sidebar_toggle()`, `_estilo_tabla_informe()`, `_html_tabla_informe()` (tablas HTML compactas sin scroll), `_esc()` y `_cls_var()` (reutilizables para celdas).
- **Tablas del informe:** Pestañas 1–4 y 5 usan tablas HTML compactas (`width: fit-content; max-width: 100%`) generadas con `_html_tabla_informe()` donde aplica; evitan scroll horizontal y espacios grandes. Pestaña 6: gráfico 2026 con tooltip 1 decimal; tabla 2×14 en HTML con valores en $ y punto de miles; títulos "TENDENCIA 2026 - VR NETO VENTAS POS…" y "VR NETO VENTAS POS X AÑO Y MES - (en Millones $) Del: (fecha)".

---

## 3. Autenticación

- **Dos modos:**
  - **Microsoft (Outlook/Entra):** Si en secrets está configurado `[auth]` con `client_id` y `client_secret`, la app muestra solo “Iniciar sesión con Microsoft”. Solo entran cuentas válidas de Azure (ej. solo tu organización). Ver `AUTH_MICROSOFT.md`.
  - **Usuario/contraseña:** Si no hay `[auth]`, la app muestra “Iniciar sesión” y “Registrarse”. Usuarios en tabla `usuarios` en SQLite (módulo `auth.py`, bcrypt).
- **Sidebar:** “Conectado como **nombre**” y botón “Cerrar sesión”.

---

## 4. Archivos clave (qué hace cada uno)

| Archivo | Rol |
|---------|-----|
| **app.py** | Dashboard Streamlit: login/informe, filtros, tablas, estilos. |
| **auth.py** | Registro e inicio de sesión (tabla `usuarios`, bcrypt). Init de tabla si no existe. |
| **database.py** | Motores SQLAlchemy: SQL Server (principal + NEWACRVentas) y SQLite (`engine_local`). |
| **models.py** | Modelos SQLAlchemy para tablas locales (raw_ventas_2026, dim_store, hechos_excel_diario, etc.). |
| **init_db.py** | Crea tablas en SQLite y siembra `sede_grupo_lookup`. |
| **etl_sql.py** | Detalle (base principal) → `raw_ventas_2026`. Normaliza `StoreID` al cargar (201.0/0201→'201', F04 se mantiene) para coincidir con MAPEO_SEDES. |
| **etl_maestros.py** | NEWACRVentas: Store, Invoice, etc. → `dim_store`, `raw_invoice_2026`. |
| **etl_excel.py** | Excel/FTP → presupuesto e histórico → `hechos_excel_diario`, etc. |
| **bi_local_data.db** | SQLite principal. No subir si tiene datos sensibles; en Cloud puede estar vacío o ser copia. |
| **.streamlit/config.toml** | Tema y opciones Streamlit (sin `[theme.sidebar]` en 1.19). |
| **.streamlit/secrets.toml** | Secrets (auth Microsoft, etc.). No commitear; está en `.gitignore`. |
| **requirements.txt** | `streamlit>=1.52.2`, `Authlib>=1.3.2`, `requests`, pandas, sqlalchemy, passlib[bcrypt], etc. |
| **runtime.txt** | `python-3.11.9` (Cloud). |
| **check_transacciones.py** | Script de diagnóstico: por qué no salen transacciones (lee solo SQLite, no modifica la app). |
| **ejecutar_etls.py** | Ejecuta en orden: etl_maestros, etl_sql, etl_excel. Para uso manual o programado (6:00 / 8:00). |
| **run_pipeline_diario.py** | **Una sola sentencia:** ETLs → (opcional) FTP 2025 → push a GitHub. Recomendado para actualizar todo cada día. |
| **cargar_todo.bat** | Ejecuta `python run_pipeline_diario.py`; doble clic para correr el pipeline sin escribir comandos. |
| **ejecutar_etls_6y8.bat** | Lanza `ejecutar_etls.py` (activa venv si existe). Lo usa el Programador de tareas. |
| **programar_tareas_etl.ps1** | Crea en Windows dos tareas: BI_Andres_ETL_6am (6:00) y BI_Andres_ETL_8am (8:00). |
| **push_db_to_github.py** | Tras los ETLs, hace commit y push de bi_local_data.db a GitHub para que la web use datos actualizados. |
| **PIPELINE_DATOS.md** | Flujo de datos, orden de ETLs, qué no mover, cómo blindar. Ver también MEMORIA_PROYECTO.md §5 y §7. |

---

## 5. Datos y reglas críticas

- **Ventas:** `raw_ventas_2026` (StoreID = Co, Fecha, VlrBruto, VlrTotalDesc). Origen: Detalle (base principal).
- **Transacciones:** Invoice (NEWACRVentas) → JOIN con **dim_store**; agrupar por **Store.StoreID_External** (Co) y fecha; COUNT(DISTINCT InvoiceID). **Por qué:** `Invoice.StoreID` es ID interno (ej. 65291); las ventas usan Co (2, 3, F08…). Si agrupas solo por `Invoice.StoreID`, las transacciones no coinciden con las ventas por sede. Siempre usar dim_store para obtener Co = StoreID_External.
- **Código de sede (Co):** Siempre normalizar con `LTRIM(UPPER(TRIM(CAST(... AS TEXT))), '0')`. Nunca convertir códigos alfanuméricos (ej. F08) a entero.
- **Cruces:** Ventas por `dim_store.StoreID`/StoreID_External; financiero/Excel por `StoreID_External` (y mismo normalizado). Mapeo sede/grupo en `sede_grupo_lookup`; si falla o está vacío, se usa `_mapeo_respaldo()` en app.py para que el informe siga mostrando sedes/grupos.

---

## 5b. Reglas de intención (no romper)

- **El informe es la fuente de verdad:** etiquetas, columnas y lógica no se cambian “para compatibilidad”. Solo se añaden wrappers (ej. `_st_dataframe`, `_sidebar_toggle`, `_dataframe_serializable`) para que el mismo código funcione en local y en Cloud.
- **No volver a añadir** bloques de “diagnóstico” (expanders con consultas crudas a raw_invoice/raw_ventas para depurar). Esos bloques se quitaron a propósito.
- **Texto en UI:** en todo el informe se usa **“Ventas al público”** (no “Venta” ni “Ventas” suelto). Los títulos de día llevan nombre completo (ej. “MARTES 10 DE MARZO DE 2026”).
- **Antes de cambios grandes:** copiar `app.py` a `app_backup_actual.py` para no perder el estado que funciona.

---

## 5c. Flujo de datos por pestaña (para tocar el informe sin romper)

- **Fuentes base:** `df_op` = ventas operativas (venta + transacciones por sede/fecha); `df_fin` = presupuesto/histórico diarizado; `MAPEO_SEDES` = código → (grupo, sede). Todo se filtra por rango `f_inicio`–`f_fin` y por `s_filtro`/`g_filtro` (restaurantes/grupos del sidebar).
- **Tab 1 (Ventas del día):** datos de `df_op` en el rango; agregar por sede (y grupo); columnas venta, transacciones, ticket. Título con `f_sel` (ej. un solo día).
- **Tab 2 (Comparativo 2026 vs 2025):** `df_op` (2026) y histórico 2025 (`df_h`) con fechas alineadas (Lunes vs Lunes) o mismo día; variación y semáforos.
- **Tab 3 (Ppto diario):** presupuesto diario vs ventas del día en el rango; `df_r` / `df_p` por sede.
- **Tab 4 (Ppto acumulado):** presupuesto acumulado vs ventas acumuladas hasta `f_fin`; `df_r_acum` / `df_p_acum`; título con “MES DE MARZO” (o el mes de f_fin).
- **Tab 5 (Transacciones 2026 vs 2025):** 2026 desde `df_op`; 2025 desde `load_transacciones_hist_2025()` (transacciones_hist*.xlsx). Tabla HTML compacta. Expander cuando hay sedes con $0 en 2026: instrucción para ejecutar `python debug_raw_ventas_2026.py <fecha>`.
- **Tab 6 (Tendencia 2025 vs 2026):** Solo 2026 en gráfico: tres líneas (Vr Neto Ventas POS, Nro Transacciones, Vr Ticket Promedio) con índice Enero=100. Columna Fecha en datetime; normalización de códigos (201.0→201) para evitar $0 en Medellín/Plaza Claro cuando en Detalle sí hay datos. Tabla 2×14 en HTML ($, punto de miles); títulos con "Del: (fecha acumulado)".
- Todas las tablas del informe pasan por `_estilo_tabla_informe()` y `_dataframe_serializable()` (vía `_st_dataframe`) o por `_html_tabla_informe()` (HTML compacto sin scroll). No mostrar un DataFrame sin eso o puede reaparecer LargeUtf8 en Cloud.

---

## 6. Compatibilidad y correcciones ya hechas

- **LargeUtf8:** `_dataframe_serializable()` convierte columnas string a tipo serializable antes de mostrar tablas; `streamlit>=1.36` (ahora 1.42) en requirements.
- **Streamlit Cloud (versión antigua):** `_sidebar_toggle` (toggle vs checkbox), `_st_dataframe` (sin `hide_index` si falla), `_estilo_tabla_informe` con `.map` o `.applymap`, `get_engine()` con ruta por `__file__` y `check_same_thread=False` para SQLite.
- **Altair:** `altair>=4.2.0,<5` en requirements. **Python:** `runtime.txt` con 3.11 para Cloud.

---

## 7. Cómo ejecutar y publicar

- **Local:** `streamlit run app.py`. Requiere `.env` (SQL Server si corres ETLs) y opcionalmente `bi_local_data.db` (o correr ETLs). Si la base está vacía o no hay datos: la app muestra “No hay datos operativos. Ejecuta los ETLs.” y no rompe.
- **Publicar:** Código en GitHub (`handres12/ReportesAndres`), rama `main`, main file `app.py`. En Streamlit Cloud: New app, repo, branch, app path. Secrets en la app si usas Microsoft auth. Ver `PUBLICAR_INFORME_PASO_A_PASO.md` o `PUBLICAR_WEB.md`.
- **Backups:** `app_backup_actual.py` = copia del app actual; `BACKUPS.md` describe uso.

---

## 7b. Actualización automática (ETLs a las 6:00 y 8:00)

**Resumen:** Es automático. Tú solo haces la configuración **una vez (hoy)**. Luego, **todos los días** no tienes que hacer nada: si la PC está encendida a las 6:00 y 8:00, todo corre solo (ETLs + subida a GitHub → la web se actualiza).

| | Qué hacer |
|--|-----------|
| **Hoy (una sola vez)** | 1) Ejecutar `.\programar_tareas_etl.ps1` en PowerShell (crea las tareas de las 6 y 8). 2) Dejar Git listo para push sin contraseña (token o SSH), si quieres que la web se actualice con la base. |
| **Todos los días** | Nada. Las tareas se ejecutan solas a las 6:00 y 8:00. Solo conviene que la PC esté encendida a esas horas (p. ej. no apagarla de noche si quieres que corra). |

- **Objetivo:** Que los datos se actualicen solos mientras el equipo está encendido (p. ej. por la noche), sin abrir la app.
- **Qué se ejecuta:** `ejecutar_etls.py` corre en orden: Maestros (dim_store, Invoice) → Ventas SQL → Excel (presupuesto/histórico).
- **Cómo programar (una vez):** En la carpeta del proyecto, abrir PowerShell y ejecutar:
  ```powershell
  .\programar_tareas_etl.ps1
  ```
  Eso crea dos tareas en el Programador de tareas de Windows: **BI_Andres_ETL_6am** (6:00) y **BI_Andres_ETL_8am** (8:00), todos los días.
- **Requisitos:** La PC debe estar encendida a esas horas; `.env` con credenciales de SQL Server y rutas correctas; `python` en el PATH (o venv activado por el .bat). Para ver/editar tareas: Panel de control → Herramientas administrativas → Programador de tareas.
- **Actualización automática para la web:** Después de cada ejecución (6:00 y 8:00), el mismo .bat lanza `push_db_to_github.py`, que hace commit y push de `bi_local_data.db` al repo. Así Streamlit Cloud recibe el archivo actualizado en el próximo deploy y la web muestra los mismos datos que local. Para que el push funcione sin intervención: Git en el PATH, remote `origin` apuntando a GitHub, y **permisos de push** (Personal Access Token en HTTPS o SSH). Si no quieres subir la base a GitHub, pon `PUSH_DB_TO_GITHUB=0` en el entorno o en un .env que el .bat cargue. **Importante:** Si el repo es público, la base quedará visible; valora usar repo privado o no subir la DB.

---

## 8. Documentación adicional

- **MEMORIA_PROYECTO.md** — Reglas para la IA, diccionario de archivos, mapeos, protocolo de blindaje.
- **DOCUMENTACION.md** — Tablas, bases, proceso ventas/transacciones/ticket, ETL, modelos.
- **AUTH_MICROSOFT.md** — Configurar login con Microsoft (Outlook/Entra). **CONFIGURAR_TENANT_OUTLOOK.md** — Tenant y correo Outlook. **PASO_A_PASO_LOGIN_MICROSOFT.md** — Pasos local; **PASO_A_PASO_LOGIN_WEB.md** — Pasos web (flujo Authlib, URI raíz en Azure).
- **PUBLICAR_INFORME_PASO_A_PASO.md** / **PUBLICAR_WEB.md** — Pasos para publicar en la web.

---

## Última actualización

- **Fecha:** 2026-03-15  
- **Cambios recientes:** Login Microsoft local + web (OAuth Authlib en Cloud). Backup app_backup_actual.py. Docs PASO_A_PASO_LOGIN_*.md. — FAQ “Preguntas frecuentes al retomar” (transacciones en 0, datos operativos, sedes XXX). Script `check_transacciones.py` para depurar transacciones sin tocar la app. **Actualización automática:** `ejecutar_etls.py`, `ejecutar_etls_6y8.bat` y `programar_tareas_etl.ps1` para ETLs a las 6:00 y 8:00 (sección 7b).

- 2026-03-15: Pestaña 6 Tendencia 2025 vs 2026 (gráfico índice Enero=100, tabla HTML 2×14). Pestañas 1–5 tablas HTML compactas. ETL y app: normalización StoreID/codigo_sede_crudo. debug_raw_ventas_2026.py (argumento fecha), validar_transacciones_2025.py (Cartagena/Paraderos FR/Rionegro).

**Al hacer cambios relevantes:** editar la sección que corresponda arriba y añadir una línea aquí, por ejemplo:  
`- YYYY-MM-DD: [descripción breve del cambio].`


---

### Preguntas frecuentes al retomar

- **¿Por qué no salen las transacciones (o salen en 0)?**  
  1) Las transacciones vienen de **Invoice (NEWACRVentas)** unido a **dim_store**; se agrupan por **Store.StoreID_External** (Co) y fecha. Si la query agrupa solo por `Invoice.StoreID` (ID interno), no coinciden con las ventas por sede → revisar que en `load_ventas_operativas()` el CTE TransaccionesDiarias haga JOIN con dim_store y use `StoreID_External` normalizado como `codigo_sede_crudo`.  
  2) Ejecutar **`python etl_maestros.py`** para cargar Invoice y Store en SQLite; sin eso no hay transacciones.  
  3) Verificar que en NEWACRVentas existan datos en Invoice y Store y que el JOIN Invoice–Store por StoreID (o el que use el ETL) devuelva filas.  
  4) Si las ventas sí salen pero las transacciones no: suele ser que el Co de ventas (raw_ventas_2026.StoreID) no coincide con el Co que sale del JOIN (Store.StoreID_External). Revisar normalización (LTRIM '0', mismo formato).  
  5) **Para depurar sin tocar la app:** ejecutar `python check_transacciones.py` en la raíz del proyecto. Ese script lee solo SQLite e indica si faltan Invoice/dim_store, si el JOIN devuelve filas y si los Co de ventas y transacciones coinciden.

- **¿Por qué “No hay datos operativos”?**  
  La base SQLite está vacía o `load_ventas_operativas()` no devuelve filas. Ejecutar los ETLs (etl_maestros, etl_sql, etl_excel según corresponda) y asegurar que `raw_ventas_2026` tenga datos.

- **¿Sedes con nombre “Sede (XXX)” o códigos raros?**  
  Esa sede no está en el mapeo. Añadir el código XXX a `sede_grupo_lookup` (vía init_db/seed o manual) o al diccionario de respaldo en `app.py` (`_mapeo_respaldo()`).

---

**Comprobar que estás al mismo nivel de madurez:** si tras leer este archivo (y opcionalmente DOCUMENTACION.md / MEMORIA_PROYECTO.md) entiendes por qué las transacciones van por dim_store→StoreID_External, por qué no se toca la lógica del informe para “arreglar” Cloud, qué hace cada pestaña con df_op/df_fin/f_inicio/f_fin, y qué no volver a introducir (diagnóstico, cambiar “Ventas al público”), estás en contexto suficiente para seguir desarrollando sin perder la lógica del proyecto.
