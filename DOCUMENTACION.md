# Documentación · Proyecto BI Streamlit (Andrés Carne de Res)

Relación de tablas, bases de datos y proceso de datos para ventas, transacciones y ticket promedio.

---

## 1. Bases de datos

| Conexión | Uso | Variable / Motor |
|----------|-----|------------------|
| **SQL Server principal** | Integracion-GrupoIGA-Micros (ventas Detalle) | `SQL_SERVER_DB`, `engine_sql_server` |
| **SQL Server secundaria** | NEWACRVentas (maestros + Invoice) | `SQL_SERVER_DB_SEC` (default: NEWACRVentas), `engine_sql_server_sec` |
| **SQLite local** | Datos consolidados para la app | `LOCAL_DB_URL` (default: `bi_local_data.db`), `engine_local` |

La app solo lee de la base **local** (SQLite). Los ETL escriben en SQLite a partir de las dos bases SQL Server.

---

## 2. Relación de tablas (origen → destino)

### 2.1 Base principal (Integracion-GrupoIGA-Micros)

| Tabla origen | Campos clave | Tabla destino (SQLite) | Script ETL |
|--------------|--------------|-------------------------|------------|
| **Detalle** | `Co`, `FechaDocto`, `VlrBruto`, `VlrTotalDesc` | `raw_ventas_2026` | `etl_sql.py` |

- **Co** en Detalle = código de sede (equivalente al “Co” del negocio).
- Se consolida por `(StoreID, Fecha)` antes de cargar; en destino: `StoreID` = Co, `Fecha`, `VlrBruto`, `VlrTotalDesc`.

### 2.2 Base secundaria (NEWACRVentas)

| Tabla origen | Campos clave | Tabla destino (SQLite) | Script ETL |
|--------------|--------------|-------------------------|------------|
| **Store** | `StoreID`, `StoreID_External`, `Store_Name`, … | `dim_store` | `etl_maestros.py` |
| **Invoice** | `InvoiceID`, `StoreID`, `BusinessDate`, … | `raw_invoice_2026` | `etl_maestros.py` |
| **ItemGroup** | `StoreID`, `GroupID`, … | `dim_item_group` | `etl_maestros.py` |
| **ItemFamily** | `storeID`, `FamilyID`, … | `dim_item_family` | `etl_maestros.py` |
| **MenuItem** | `storeID`, `MenuItemID`, … | `dim_menu_item` | `etl_maestros.py` |

**Relación clave para transacciones y nombre del restaurante:**

- **Invoice.StoreID** se relaciona con la tabla **Store**:
  - Por **Store.StoreID** (ID interno), o  
  - Por **Store.StoreID_External** (cuando en Invoice ya viene el código externo).
- **Store.StoreID_External** = **Co** del restaurante (mismo concepto que `Co` en Detalle).
- **Store.Store_Name** = nombre del restaurante.

Esquema:

```
Invoice (NEWACRVentas)          Store (NEWACRVentas)
├── InvoiceID                   ├── StoreID          (interno)
├── StoreID  ──────────────────►├── StoreID_External (Co)
├── BusinessDate                 └── Store_Name
└── ...
```

Para que ventas y transacciones coincidan por sede, el **Co** usado en ventas (Detalle → `raw_ventas_2026.StoreID`) debe corresponder al mismo valor que **Store.StoreID_External** usado al agrupar Invoice.

### 2.3 Tablas solo en SQLite (maestros / configuración)

| Tabla | Descripción |
|-------|-------------|
| **sede_grupo_lookup** | Mapeo `store_id` → `sede`, `grupo` (agrupaciones en la app). |
| **raw_presupuesto_excel** | Presupuesto por sede (Excel). |
| **hechos_excel_diario** | Histórico diarizado (Excel/FTP): `StoreID_External`, `Sede_Excel`, `Agrupacion`, `Fecha`, `Escenario`, `Ventas`, `Transacciones`, `Ticket_Promedio`. |

---

## 3. Normalización del código de sede (Co)

En toda la app se usa un **código normalizado** para comparar sedes entre tablas:

- **codigo_sede_crudo** = `LTRIM(UPPER(TRIM(CAST(StoreID AS TEXT))), '0')`

Así se evitan diferencias por ceros a la izquierda o mayúsculas/minúsculas entre:

- `raw_ventas_2026.StoreID` (Co de Detalle)
- `dim_store.StoreID_External` (Co)
- `dim_store.StoreID` (interno, por si Invoice viene por ahí)

---

## 4. Proceso: venta diaria, transacciones y ticket promedio

### 4.1 Origen de los datos en la app

- **Ventas del día:** `raw_ventas_2026` (origen: Detalle, base principal).  
  Por (sede, fecha): `Venta_Real = VlrBruto - VlrTotalDesc`.

- **Transacciones del día:** tabla **Invoice** (NEWACRVentas):
  1. Se toma **InvoiceID** y **StoreID**, **BusinessDate**.
  2. Se une **Invoice** con **Store** por `Invoice.StoreID` = `Store.StoreID` o `Store.StoreID_External`.
  3. Se usa **Store.StoreID_External** normalizado como **Co**.
  4. Se agrupa por (Co, fecha) y se calcula **Transacciones** = `COUNT(DISTINCT InvoiceID)`.

- **Ticket promedio:** para cada (sede, día):  
  **Ticket promedio = Venta del día / Transacciones**  
  usando la **misma venta** que se muestra en cada campo (no otra fuente).

### 4.2 Consulta en la app (`load_ventas_operativas`)

1. **VentasDiarias (CTE):**  
   `raw_ventas_2026` agregado por `(codigo_sede_crudo, Fecha)` con `SUM(VlrBruto)`, `SUM(VlrTotalDesc)`.

2. **TransaccionesDiarias (CTE):**  
   `raw_invoice_2026` unido a `dim_store` (por `StoreID` o `StoreID_External`), luego agrupado por `(codigo_sede_crudo, Fecha)` con `COUNT(DISTINCT InvoiceID)`.

3. **Resultado:**  
   `VentasDiarias` con `LEFT JOIN TransaccionesDiarias` y `LEFT JOIN dim_store` para el nombre.  
   Cada fila tiene: sede, fecha, venta (VlrBruto, VlrTotalDesc), cantidad de transacciones.

4. **En la pestaña “Venta diaria del día”:**  
   Se agrega por sede (y opcionalmente por grupo) sumando **Venta_Real** y **Cantidad_Transacciones** del mismo dataset; **TICKET PROMEDIO** = venta agregada / transacciones agregadas.

---

## 5. Flujo ETL resumido

| Orden sugerido | Script | Qué hace |
|----------------|--------|----------|
| 1 | `etl_maestros.py` | Carga desde NEWACRVentas: Store, Invoice (incremental), ItemGroup, ItemFamily, MenuItem → `dim_*`, `raw_invoice_2026`. |
| 2 | `etl_sql.py` | Carga desde base principal: Detalle → consolidado por (Co, Fecha) → `raw_ventas_2026`. |
| 3 | `etl_excel.py` (u otros) | Carga presupuesto e histórico desde Excel/FTP → `raw_presupuesto_excel`, `hechos_excel_diario`. |

Para que transacciones y ticket no salgan en 0:

1. Ejecutar `etl_maestros.py` (Invoice y Store en SQLite).
2. Asegurar que el **Co** en Detalle coincida con **Store.StoreID_External** (o que el JOIN por `StoreID`/`StoreID_External` en la consulta encuentre coincidencias).

---

## 6. Modelos principales (SQLite)

- **raw_ventas_2026:** `StoreID`, `Fecha`, `VlrBruto`, `VlrTotalDesc`
- **raw_invoice_2026:** `InvoiceID`, `StoreID`, `BusinessDate`, …
- **dim_store:** `StoreID`, `StoreID_External`, `Store_Name`, …
- **sede_grupo_lookup:** `store_id`, `sede`, `grupo`
- **hechos_excel_diario:** `StoreID_External`, `Sede_Excel`, `Agrupacion`, `Fecha`, `Escenario`, `Ventas`, `Transacciones`, `Ticket_Promedio`

Definiciones completas en `models.py`.

---

## 7. Publicar el reporte en la web (link sin dominio)

Hay dos formas de obtener un enlace público:

- **Opción A – Desde tu PC (link temporal):** usar **ngrok** (o similar) para exponer el Streamlit que corre en tu máquina. Cualquiera con el link puede entrar mientras la app esté abierta y tu PC encendida. No necesitas dominio ni GitHub. Ver `PUBLICAR_WEB.md`.
- **Opción B – En la nube (link fijo 24/7):** subir el código a **GitHub** y desplegar en **Streamlit Community Cloud** (share.streamlit.io). Te dan una URL tipo `https://tu-app.streamlit.app`. La app en la nube no tendrá tu SQLite local; hay que incluir los datos en el repo o usar una base en la nube. Ver `PUBLICAR_WEB.md`.

---

*Documentación generada para el proyecto BI Streamlit. Actualizar este archivo cuando cambien orígenes, tablas o reglas de negocio.*
