import pandas as pd
import numpy as np
import os
import glob

print("🚀 Procesando BDMVTAL (con Tienda Nativa) + Rectificaciones...")

ruta_carpeta = os.path.join(".", "Datos_mensales")

# 1. CARGA DE BDMVTAL (Despachos Totales)
archivos_desp = sorted(glob.glob(os.path.join(ruta_carpeta, "BDMVTAL*.csv")))
lista_desp = []
for f in archivos_desp:
    for sep in [";", ",", "\t"]:
        try:
            df_t = pd.read_csv(f, encoding="latin1", sep=sep, low_memory=False)
            if len(df_t.columns) > 1:
                lista_desp.append(df_t)
                break
        except Exception:
            continue

df_desp = pd.concat(lista_desp, ignore_index=True)
df_desp.columns = df_desp.columns.str.strip()

# Identificar columnas en BDMVTAL (Almacén, Tienda, Fecha de carga, Pedido, Importe)
col_alm_d = [c for c in df_desp.columns if "almac" in c.lower()][0]
col_tien_d = [c for c in df_desp.columns if "tiend" in c.lower()][0]

df_desp = df_desp.rename(columns={
    col_alm_d: "Almacen", 
    col_tien_d: "Tienda_Original",
    "Fecha de carga": "Fecha_Carga", 
    "Pedido": "Pedido_Original", 
    "Importe": "Importe_Pedido"
})

df_desp["Pedido"] = df_desp["Pedido_Original"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
df_desp["Tienda"] = df_desp["Tienda_Original"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
df_desp["Almacen"] = df_desp["Almacen"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
df_desp["Importe_Pedido"] = pd.to_numeric(df_desp["Importe_Pedido"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

# Fechas
df_desp["Fecha_DT"] = pd.to_datetime(df_desp["Fecha_Carga"].astype(str), format="%Y%m%d", errors="coerce")
df_desp["Año"] = df_desp["Fecha_DT"].dt.year
df_desp["Mes"] = df_desp["Fecha_DT"].dt.month
df_desp["N° Semana"] = df_desp["Fecha_DT"].dt.isocalendar().week
df_desp["Día"] = df_desp["Fecha_DT"].dt.day

# Unificar Pedidos Únicos de BDMVTAL
df_desp_unicos = df_desp.groupby("Pedido", as_index=False).agg(
    Almacen=("Almacen", "first"),
    Tienda=("Tienda", "first"),
    Fecha_Carga=("Fecha_Carga", "first"),
    Fecha_DT=("Fecha_DT", "first"),
    Año=("Año", "first"),
    Mes=("Mes", "first"),
    Semana=("N° Semana", "first"),
    Dia=("Día", "first"),
    Importe_Pedido=("Importe_Pedido", "sum")
)

# 2. CARGA DE RECTIFICACIONES
archivos_rect = sorted(glob.glob(os.path.join(ruta_carpeta, "*Rectificaciones*.csv")))
lista_rect = []
for f in archivos_rect:
    for sep in [";", ",", "\t"]:
        try:
            df_r = pd.read_csv(f, encoding="latin1", sep=sep, low_memory=False)
            if len(df_r.columns) > 1:
                lista_rect.append(df_r)
                break
        except Exception:
            continue

df_rect = pd.concat(lista_rect, ignore_index=True)
df_rect.columns = df_rect.columns.str.strip()

col_alm_r = [c for c in df_rect.columns if "almac" in c.lower()][0]
col_tien_r = [c for c in df_rect.columns if "tiend" in c.lower()][0]

df_rect = df_rect.rename(columns={col_alm_r: "Almacen", col_tien_r: "Tienda_Original"})
df_rect["Pedido"] = df_rect["Pedido"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
df_rect["Tienda"] = df_rect["Tienda_Original"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

df_rect["Motivo_Clean"] = df_rect["Motivo"].astype(str).str.strip().str.upper()
df_rect["Procedencia_Clean"] = df_rect["Procedencia"].astype(str).str.strip().str.upper()
df_rect["Artículo"] = df_rect["Artículo"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
df_rect["Unid_Grabadas"] = pd.to_numeric(df_rect["Unid/Kgs grabados"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
df_rect["Unid_Abonadas"] = pd.to_numeric(df_rect["Unid/Kgs abonados"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
df_rect["Monto_Rectif"] = pd.to_numeric(df_rect["Imp.tien.PVP S/IVA mon.BD"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

# 3. CLASIFICACIÓN DE CASUÍSTICAS POR PEDIDO
def clasificar_pedido(df_ped):
    cant_lineas = len(df_ped)
    motivos = set(df_ped["Motivo_Clean"].unique())
    procedencias = set(df_ped["Procedencia_Clean"].unique())
    
    tiene_f = "F" in motivos
    tiene_s = "S" in motivos
    
    if "T" in procedencias and cant_lineas > 10 and tiene_f and tiene_s:
        return "Etiquetas Cambiadas", -10.0, 0.0
    
    if tiene_f and tiene_s:
        skus = df_ped["Artículo"].tolist()
        prefijos = set([s[:3] for s in skus if len(s) >= 3])
        if len(prefijos) == 1:
            return "Sustitución Misma Subfamilia", -2.5, 7.5
        else:
            return "Sustitución Distinta Subfamilia", -4.5, 5.5
            
    if tiene_f and not tiene_s:
        return "Faltante Neto", -6.0, 4.0
        
    if tiene_s and not tiene_f:
        return "Sobrante Neto", -1.0, 9.0
        
    return "Faltante Neto", -6.0, 4.0

resumen_pedidos_rect = []
for ped, group in df_rect.groupby("Pedido"):
    casuistica, penalizacion, puntos = clasificar_pedido(group)
    cant_lineas = len(group)
    monto_total = group["Monto_Rectif"].sum()
    unid_grab = group["Unid_Grabadas"].sum()
    unid_abon = group["Unid_Abonadas"].sum()
    
    resumen_pedidos_rect.append({
        "Pedido": ped,
        "Casuistica": casuistica,
        "Penalizacion": penalizacion,
        "Puntos_Obtenidos": puntos,
        "Lineas_Rectificadas": cant_lineas,
        "Monto_Rectificacion": monto_total,
        "Unid_Grabadas": unid_grab,
        "Unid_Abonadas": unid_abon
    })

df_pedidos_rect_summary = pd.DataFrame(resumen_pedidos_rect)

# 4. CRUCE DESPACHOS BDMVTAL + CASUÍSTICAS RECTIFICACIONES
df_sla_pedidos = df_desp_unicos.merge(df_pedidos_rect_summary, on="Pedido", how="left")

# Pedidos de BDMVTAL sin rectificación = Pedido Perfecto
df_sla_pedidos["Casuistica"] = df_sla_pedidos["Casuistica"].fillna("Pedido Perfecto")
df_sla_pedidos["Penalizacion"] = df_sla_pedidos["Penalizacion"].fillna(0.0)
df_sla_pedidos["Puntos_Obtenidos"] = df_sla_pedidos["Puntos_Obtenidos"].fillna(10.0)
df_sla_pedidos["Lineas_Rectificadas"] = df_sla_pedidos["Lineas_Rectificadas"].fillna(0)
df_sla_pedidos["Monto_Rectificacion"] = df_sla_pedidos["Monto_Rectificacion"].fillna(0.0)
df_sla_pedidos["Unid_Grabadas"] = df_sla_pedidos["Unid_Grabadas"].fillna(0)
df_sla_pedidos["Unid_Abonadas"] = df_sla_pedidos["Unid_Abonadas"].fillna(0)

# Exportar Parquets
df_sla_pedidos.to_parquet("Tablero_SLA_Pedidos.parquet", index=False, compression="snappy")
df_rect.to_parquet("Tablero_Rectificaciones_Detalle.parquet", index=False, compression="snappy")

print("="*60)
print(f"✅ ¡Parquet generado con éxito!")
print(f"📌 Total Pedidos Únicos en BDMVTAL : {len(df_sla_pedidos):,}")
print(f"📌 Tiendas Únicas en BDMVTAL       : {df_sla_pedidos['Tienda'].nunique():,}")
print(f"📌 Pedidos con Rectificación       : {len(df_pedidos_rect_summary):,}")
print(f"📌 Pedidos Perfectos (10/10)       : {len(df_sla_pedidos[df_sla_pedidos['Casuistica'] == 'Pedido Perfecto']):,}")
print("="*60)
