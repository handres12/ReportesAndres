# ESTADO DEL PROYECTO: BI ANDRÉS CARNE DE RES

**Para entrar en contexto rápido (IA o humano):** leer primero **`CONTEXTO_PROYECTO_IA.md`**.

**Última actualización:** 2026-03-15 (pestaña 6 Tendencia, tablas HTML compactas, ETL/app normalización, validación 2025)  
**Objetivo:** Dashboard gerencial en Streamlit (app.py) que cruce ventas operativas (SQL Server/Micros) vs Presupuestos e Históricos (Excel/FTP) usando una base de datos local SQLite (bi_local_data.db).

## 1. REGLAS ESTRICTAS PARA LA IA
1. CERO RESPUESTAS RÁPIDAS O RESÚMENES DE CÓDIGO. Cero "poesía". Respuestas directas y técnicas.
2. Si hay que modificar un archivo, entrega SIEMPRE el código COMPLETO, de la línea 1 a la última. Cero "copia y pega solo esta parte".
3. El código base de `etl_excel.py` no debe bajar de 200 líneas. Debe mantener la extracción robusta y el mapeo manual de sedes y grupos.
4. NUNCA convertir códigos alfanuméricos de Micros (ej. F08) a enteros. Usar siempre `LTRIM(UPPER(TRIM(codigo)), '0')` para los cruces (JOINs).

## 2. DICCIONARIO DE ARCHIVOS (ARQUITECTURA)
* **`.env`**: Variables de entorno (credenciales SQL Server, SQLite, FTP).
* **`app.py`**: DASHBOARD PRINCIPAL (Streamlit). Login Microsoft o usuario/contraseña (CONTEXTO §3). **6 pestañas:** ventas del día, comparativo 2026 vs 2025, presupuesto diario, presupuesto acumulado, transacciones 2026 vs 2025, **Tendencia 2025 vs 2026** (gráfico 2026 índice Enero=100, tabla HTML 2×14). Tablas 1–5 con `_html_tabla_informe()` (HTML compacto sin scroll). `load_ventas_operativas()` normaliza `codigo_sede_crudo` y reagrupa por sede/fecha.
* **`auth.py`**: Login usuario/contraseña (tabla `usuarios`, bcrypt). Se usa cuando no hay [auth] Microsoft.
* **`app_backup_actual.py`**: Copia de seguridad de app.py. Actualizar antes de cambios grandes.
* **`bi_local_data.db`**: Base de datos SQLite principal. Convergen todos los ETLs; se sube a GitHub para la web (Streamlit Cloud).
* **`database.py`**: Conexiones SQLAlchemy: SQL Server principal, NEWACRVentas (secundaria), SQLite local.
* **`models.py`**: Estructura de tablas locales (RawVentas2026, RawInvoice2026, dim_store, hechos_excel_diario, etc.).
* **`init_db.py`**: Crea las tablas vacías en SQLite si no existen.
* **`etl_sql.py`**: Extrae ventas (Detalle) → `raw_ventas_2026`. Normaliza StoreID al cargar (201.0/0201→'201', F04 se mantiene) para coincidir con MAPEO_SEDES.
* **`etl_maestros.py`**: NEWACRVentas → `dim_store`, `dim_item_*`, `raw_invoice_2026`. Invoice: carga incremental; re-trae últimos 2 días para evitar "ayer" con transacciones incompletas.
* **`etl_excel.py`**: Excel en `fuentes_excel`/raíz → presupuesto e histórico → `hechos_excel_diario` (no borra escenario Historico_Diario; ese lo carga el FTP).
* **`ejecutar_etls.py`**: Orden fijo: 1) etl_maestros, 2) etl_sql, 3) etl_excel. Para Programador de tareas (ej. 6:00 y 8:00).
* **`run_pipeline_diario.py`**: Una sola sentencia: ejecuta ETLs → (opcional) FTP 2025 → push a GitHub. Script recomendado para actualizar todo cada día.
* **`cargar_todo.bat`**: Ejecuta `python run_pipeline_diario.py`; doble clic para correr el pipeline sin abrir terminal.
* **`actualizar_8am.bat`**: Para Programador de tareas: ejecuta `run_pipeline_diario.py` sin pause (asume SQL al día a las 8:00). Usado por `programar_actualizacion_8am.ps1`.
* **`programar_actualizacion_8am.ps1`**: Crea una sola tarea diaria **BI_Andres_Actualizacion_8am** a las 08:15. Recomendado cuando las tablas SQL están al día a las 8:00.
* **`programar_tres_actualizaciones.ps1`**: Crea tres tareas diarias: **6:30**, **8:00** y **10:00**. Cada una ejecuta el pipeline completo (local y web actualizados tres veces al día).
* **`listar_ftp_ventas_2025.py`**: Lista/descarga FTP "Ventas por items 2025". Con `--cargar` reemplaza en BD el escenario Historico_Diario (comparativo 2025 día a día, PLAZAS).
* **`etl_ftp_ventas_2025.py`**: Alternativa para cargar histórico 2025 desde FTP.
* **`push_db_to_github.py`**: Hace commit y push de `bi_local_data.db` a GitHub para que la web use datos actualizados. Respeta `PUSH_DB_TO_GITHUB=0` para desactivar.
* **`PIPELINE_DATOS.md`**: Documentación del flujo de datos: fuentes, orden de ETLs, qué no mover, cómo blindar y agregar análisis sin romper lo existente.
* **`ACTUALIZACION_EN_LA_NUBE.md`**: Opciones para que la actualización no dependa del PC (VM en Azure, Functions, GitHub Actions); recomendación y pasos mínimos para una VM.
* **`validador_ventas.py`**: Diagnóstico: confirmar datos de ventas en SQLite.
* **`check_transacciones.py`**: Diagnóstico: por qué no salen transacciones (JOIN Invoice–Store, etc.).
* **`debug_raw_ventas_2026.py`**: Diagnóstico ventas 2026; acepta fecha por argumento (`python debug_raw_ventas_2026.py 2026-03-13`); indica si faltan 201 o F04.
* **`validar_transacciones_2025.py`**: Valida transacciones 2025: Cartagena (F08) y Paraderos FR (F09, F05, F04) sin datos; Rionegro (305) con datos desde abril 2025.

## 3. ARQUITECTURA DE DATOS Y RELACIONES (DIAGRAMA)
Las bases de datos se dividen en dos orígenes que convergen en SQLite. El cruce principal SIEMPRE debe hacerse a través de `dim_store`, conectando el `StoreID` (interno de Micros) con el `StoreID_External` (código de negocio).

```mermaid
erDiagram
    DIM_STORE {
        string StoreID PK "ID Interno Micros (ej. '2')"
        string StoreID_External "Código Negocio (ej. '002', 'F08')"
        string Store_Name "Nombre Sede (ej. 'ACR')"
    }
    
    RAW_VENTAS_2026 {
        string StoreID PK, FK "Cruza con dim_store.StoreID"
        date Fecha PK
        float VlrBruto
        float VlrTotalDesc
    }
    
    RAW_INVOICE_2026 {
        string InvoiceID PK
        string StoreID FK "Cruza con dim_store.StoreID"
        date BusinessDate
        int Cantidad_Transacciones
    }
    
    HECHOS_EXCEL_DIARIO {
        int id PK
        string StoreID_External FK "Cruza con dim_store.StoreID_External (usar LTRIM '0')"
        string Sede_Excel "Nombre original en Excel"
        string Agrupacion "Grupo forzado: RBB, PLAZAS, etc."
        date Fecha
        string Escenario "Presupuesto_Diarizado, Historico_Diario, etc."
        float Ventas
        float Transacciones
    }

    DIM_STORE ||--o{ RAW_VENTAS_2026 : "Filtra Ventas (Por StoreID)"
    DIM_STORE ||--o{ RAW_INVOICE_2026 : "Filtra Transacciones (Por StoreID)"
    DIM_STORE ||--o{ HECHOS_EXCEL_DIARIO : "Cruza Ppto/Hist (Por StoreID_External)"

    Rutas Críticas de Cruce (JOINs):

Operación (Micros): raw_ventas_2026.StoreID = dim_store.StoreID

Finanzas (Excel): hechos_excel_diario.StoreID_External = dim_store.StoreID_External

Regla de Limpieza: Para cruzar hechos_excel_diario con dim_store, SIEMPRE aplicar: LTRIM(UPPER(TRIM(CAST(columna AS TEXT))), '0') para evitar discrepancias entre "002" y "2", o fallos con letras como "F08".

**Pestaña 5 – Transacciones 2026 vs 2025:** 2026 desde `df_op`, 2025 desde `transacciones_hist*.xlsx` vía `load_transacciones_hist_2025()`. Tabla HTML compacta; expander con instrucción `debug_raw_ventas_2026.py <fecha>` si hay $0 en 2026. **Pestaña 6 – Tendencia 2025 vs 2026:** Gráfico solo 2026 (índice Enero=100); tabla 2×14 HTML; normalización de códigos y Fecha en app para evitar $0 en Medellín/Plaza Claro. No modificar la lógica de pestañas 5–6 al agregar otros análisis.

4. DICCIONARIOS DE MAPEO (CRÍTICO)
El ETL depende de este mapeo manual inyectado en etl_excel.py para evitar el error "SIN GRUPO".

RBB: ACR (002), ADC (003), CARTAGENA (F08), MEDELLIN (201).

PLAZAS: GRAN ESTACIÓN (404), HACIENDA (402), RETIRO (401), SANTAFÉ (405).

PARADERO FR: BAZAAR (F09), HYATT (F05), PLAZA CLARO (F04).

PARADERO: AEROPUERTO (301), ANDRES VIAJERO (304), RIONEGRO (305).

EXPRÉS: CAFAM (611), CALLE 93 (502), CASA DE LOS ANDES (612), EXPRÉS PARADERO (004), MULTIPARQUE (702), PALATINO (604), PEPE SIERRA (615).

## 5. PIPELINE Y ACTUALIZACIÓN DIARIA

**Una sola sentencia para cargar todo a pasos (cada día):**
```bash
python run_pipeline_diario.py
```
O doble clic en **`cargar_todo.bat`**.

**Asunción:** Las tablas SQL (Detalle, NEWACRVentas) están al día a las **8:00**. Por tanto conviene **una ejecución diaria después de las 8:00** (ej. 8:15). **Orden interno del pipeline:** (1) ETLs (`ejecutar_etls.py`: maestros → ventas SQL → Excel), (2) opcional FTP 2025 (`listar_ftp_ventas_2025.py --cargar`), (3) subida a GitHub (`push_db_to_github.py`). Prerrequisitos: SQL Server con datos; archivos Excel en `fuentes_excel`/raíz sin mover. Detalle completo y diagramas en **`PIPELINE_DATOS.md`**. **Programar una vez:** `.\programar_actualizacion_8am.ps1` crea la tarea BI_Andres_Actualizacion_8am a las 08:15 (ejecuta `actualizar_8am.bat` → `run_pipeline_diario.py`).

## 6. PROTOCOLO DE BLINDAJE (QUÉ HACER SI HAY CEROS)
1. **¿Venta Diaria en $0?** - Corre `python validador_ventas.py`. 
   - Si sale vacía, el problema es el `etl_sql.py` (conexión SQL Server principal).
2. **¿Transacciones en $0?**
   - Corre `python etl_maestros.py`. 
   - Verifica que diga "Se agregaron Invoices". Si dice 0, revisa la base `NEWACRVentas`.
3. **¿Aparecen Sedes con nombre "Sede (XXX)"?**
   - Significa que la sede no está en el `MAPEO_SEDES` de `app.py`. 
   - Copia el código XXX y agrégalo al diccionario en el archivo `app.py`.
4. **¿Los datos no coinciden con Excel?**
   - Verifica la fecha en el Sidebar. 
   - Asegúrate de que el toggle "Alinear Lunes vs Lunes" esté en la posición correcta.
5. **¿Transacciones o ticket de "ayer" salen en 0 o muy raros (solo una sede)?**
   - Las ventas vienen de Detalle (SQL); las transacciones de Invoice (NEWACRVentas). Si "ayer" se cargó incompleto en NEWACRVentas, el ETL ya re-trae los últimos 2 días de Invoice. Vuelve a ejecutar `python run_pipeline_diario.py` (o `python etl_maestros.py`). Si sigue mal, revisar en NEWACRVentas que ese día tenga todos los Invoice cargados.

## 7. CONTINUIDAD DEL PROYECTO (BLINDAJE AL AGREGAR ANÁLISIS)

**Cómo se blinda la información hoy para que cada cambio no genere modificaciones:**

1. **Lo que no se toca:** Rutas y nombres de los Excel en `fuentes_excel`/raíz. Nombres de tablas y columnas que usa la app. Orden de los ETLs (maestros → ventas SQL → Excel). Lógica y fuentes de datos de las pestañas 1–6 (ventas del día, comparativo 2026 vs 2025, presupuesto diario, presupuesto acumulado, transacciones 2026 vs 2025, tendencia 2025 vs 2026).
2. **Regla al agregar análisis:** (A) **Nuevas pestañas** que solo **leen** las tablas ya existentes, sin modificar consultas ni código de las pestañas 1–5. (B) Si hace falta datos nuevos: **tablas nuevas** + **ETL nuevo** que las llene; en la app solo se agrega una pestaña que lee esas tablas. Así cada cambio queda individualizado y no rompe lo construido.
3. **Documento de referencia:** **`PIPELINE_DATOS.md`** describe el flujo completo, qué hace cada ETL, qué no mover y cómo blindar. Antes de cambios grandes en `app.py`, copiar a `app_backup_actual.py`.