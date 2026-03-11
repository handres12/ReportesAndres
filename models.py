from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean
from database import BaseLocal

class RawVentas2026(BaseLocal):
    __tablename__ = "raw_ventas_2026"
    StoreID = Column(String(50), primary_key=True, index=True)
    Fecha = Column(Date, primary_key=True, index=True)
    VlrBruto = Column(Float, default=0.0)
    VlrTotalDesc = Column(Float, default=0.0)

class SedeGrupoLookup(BaseLocal):
    __tablename__ = "sede_grupo_lookup"
    store_id = Column(String(50), primary_key=True, index=True)
    sede = Column(String(100), nullable=False)
    grupo = Column(String(100), nullable=False)

class RawPresupuestoExcel(BaseLocal):
    __tablename__ = "raw_presupuesto_excel"
    sede = Column(String(100), primary_key=True, index=True)
    venta_2025 = Column(Float, default=0.0)
    transacciones_2025 = Column(Integer, default=0)
    ticket_2025 = Column(Float, default=0.0)
    ppto_ventas_restaurante_2026 = Column(Float, default=0.0)

class DimStore(BaseLocal):
    __tablename__ = "dim_store"
    StoreID = Column(String(50), primary_key=True, index=True)
    CompanyID = Column(String(50))
    StoreID_External = Column(String(50))
    Store_Name = Column(String(150))
    StorePOS_Version = Column(String(50))
    Tips_use = Column(String(50))

class DimItemGroup(BaseLocal):
    __tablename__ = "dim_item_group"
    StoreID = Column(String(50), primary_key=True)
    GroupID = Column(String(50), primary_key=True)
    Group_Name = Column(String(150))
    Bodega = Column(String(50))

class DimItemFamily(BaseLocal):
    __tablename__ = "dim_item_family"
    storeID = Column(String(50), primary_key=True)
    GroupID = Column(String(50))
    FamilyID = Column(String(50), primary_key=True)
    Family_Name = Column(String(150))
    Bodega = Column(String(50))

class DimMenuItem(BaseLocal):
    __tablename__ = "dim_menu_item"
    storeID = Column(String(50), primary_key=True)
    MenuItemID = Column(String(50), primary_key=True)
    GroupID = Column(String(50))
    FamilyID = Column(String(50))
    MenuItemClassID = Column(String(50))
    MenuItemID_External = Column(String(50))
    MenuItem_Name = Column(String(150))

class RawInvoice2026(BaseLocal):
    __tablename__ = "raw_invoice_2026"
    InvoiceID = Column(String(50), primary_key=True)
    StoreID = Column(String(50), primary_key=True)
    LocID = Column(String(50))
    StockRoomNumber = Column(String(50))
    OrderTypeID = Column(String(50))
    TenderMediaID = Column(String(50))
    WorkStationID = Column(String(50))
    Transaction_Date = Column(DateTime)
    BusinessDate = Column(Date, index=True) 
    Check_Number = Column(String(50))
    Check_InvoiceNumber = Column(String(50))
    Check_InvoiceType = Column(String(50))
    CheckSubTotal = Column(Float, default=0.0)
    CheckDiscountTotal = Column(Float, default=0.0)
    CheckServiceTotal = Column(Float, default=0.0)
    CheckTaxTotal = Column(Float, default=0.0)
    CheckTipTotal = Column(Float, default=0.0)
    CheckPayment = Column(Float, default=0.0)
    CheckAmountDue = Column(Float, default=0.0)
    CheckStatus = Column(String(50))
    CustomerID = Column(String(50))
    CheckServiceOther = Column(Float, default=0.0)
    ServiceTipo = Column(String(50))

class HechosExcelDiario(BaseLocal):
    __tablename__ = "hechos_excel_diario"
    id = Column(Integer, primary_key=True, autoincrement=True)
    StoreID_External = Column(String(50), index=True) 
    Sede_Excel = Column(String(100)) 
    Agrupacion = Column(String(100)) # 🎯 NUEVO: Guardaremos RBB, PLAZAS, etc.
    Fecha = Column(Date, index=True) 
    Escenario = Column(String(50), index=True) 
    Ventas = Column(Float, default=0.0)
    Transacciones = Column(Float, default=0.0)
    Ticket_Promedio = Column(Float, default=0.0)