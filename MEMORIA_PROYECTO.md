# ESTADO DEL PROYECTO: BI ANDRÉS CARNE DE RES

**Para entrar en contexto rápido (IA o humano):** leer primero **`CONTEXTO_PROYECTO_IA.md`**.

**Última actualización:** Marzo 2026  
**Objetivo:** Dashboard gerencial en Streamlit (app.py) que cruce ventas operativas (SQL Server/Micros) vs Presupuestos e Históricos (Excel) usando una base de datos local SQLite (bi_local_data.db).

## 1. REGLAS ESTRICTAS PARA LA IA
1. CERO RESPUESTAS RÁPIDAS O RESÚMENES DE CÓDIGO. Cero "poesía". Respuestas directas y técnicas.
2. Si hay que modificar un archivo, entrega SIEMPRE el código COMPLETO, de la línea 1 a la última. Cero "copia y pega solo esta parte".
3. El código base de `etl_excel.py` no debe bajar de 200 líneas. Debe mantener la extracción robusta y el mapeo manual de sedes y grupos.
4. NUNCA convertir códigos alfanuméricos de Micros (ej. F08) a enteros. Usar siempre `LTRIM(UPPER(TRIM(codigo)), '0')` para los cruces (JOINs).

## 2. DICCIONARIO DE ARCHIVOS (ARQUITECTURA)
* **`.env`**: Variables de entorno (Credenciales SQL Server y SQLite local).
* **`app.py`**: DASHBOARD PRINCIPAL (Streamlit). Cruza y visualiza la data.
* **`bi_local_data.db`**: Base de datos SQLite principal. Convergen todos los ETLs.
* **`database.py`**: Conexiones SQLAlchemy a SQL Server y SQLite.
* **`models.py`**: Estructura de tablas locales (ej. `RawVentas2026`).
* **`init_db.py`**: Crea las tablas vacías en SQLite si no existen.
* **`etl_sql.py`**: Extrae ventas operativas (Micros) a `raw_ventas_2026`.
* **`etl_excel.py`**: Extrae presupuestos/históricos a `hechos_excel_diario`.
* **`etl_maestros.py`**: Puebla `dim_store`.
* **`validador_ventas.py`**: Script de diagnóstico para confirmar datos en SQLite.

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

4. DICCIONARIOS DE MAPEO (CRÍTICO)
El ETL depende de este mapeo manual inyectado en etl_excel.py para evitar el error "SIN GRUPO".

RBB: ACR (002), ADC (003), CARTAGENA (F08), MEDELLIN (201).

PLAZAS: GRAN ESTACIÓN (404), HACIENDA (402), RETIRO (401), SANTAFÉ (405).

PARADERO FR: BAZAAR (F09), HYATT (F05), PLAZA CLARO (F04).

PARADERO: AEROPUERTO (301), ANDRES VIAJERO (304), RIONEGRO (305).

EXPRÉS: CAFAM (611), CALLE 93 (502), CASA DE LOS ANDES (612), EXPRÉS PARADERO (004), MULTIPARQUE (702), PALATINO (604), PEPE SIERRA (615).

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