import pandas as pd
import numpy as np
import os
import glob

print("🚀 Procesando BDMVTAL y Rectificaciones...")

ruta_carpeta = os.path.join(".", "Datos_mensuales")

# 0. MAESTRA DE ZONAS
archivos_zona = glob.glob(os.path.join(ruta_carpeta, "*ZONA*.xlsx")) + glob.glob(os.path.join(ruta_carpeta, "*ZONA*.csv"))
df_zona = pd.DataFrame()
if archivos_zona:
    f_zona = archivos_zona[0]
    try:
        if f_zona.endswith(".xlsx"):
            df_z_raw = pd.read_excel(f_zona)
        else:
            df_z_raw = pd.read_csv(f_zona, encoding="latin1", sep=None, engine="python")
        df_z_raw.columns = df_z_raw.columns.astype(str).str.strip()
        col_t = [c for c in df_z_raw.columns if "tiend" in c.lower()][0]
        col_resp = [c for c in df_z_raw.columns if "responsable" in c.lower() or "socio" in c.lower()][0]
        col_gest = [c for c in df_z_raw.columns if "gestion" in c.lower() or "gestión" in c.lower()][0]
        df_zona = df_z_raw[[col_t, col_resp, col_gest]].copy()
        df_zona.columns = ["Tienda", "Responsable_Tienda", "Gestion"]
        df_zona["Tienda"] = df_zona["Tienda"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        df_zona = df_zona.drop_duplicates(subset=["Tienda"])
    except Exception as e:
        print(f"⚠️ Error cargando zonas: {e}")

# 1. DESPACHOS BDMVTAL
archivos_desp = sorted(glob.glob(os.path.join(ruta_carpeta, "*BDMVTAL*.csv"))) + sorted(glob.glob(os.path.join(ruta_carpeta, "*bdmvtal*.csv")))
if not archivos_desp:
    archivos_desp = [f for f in glob.glob(os.path.join(ruta_carpeta, "*.csv")) if "rectif" not in f.lower() and "zona" not in f.lower()]

lista_desp = []
for f in archivos_desp:
    for sep in [";", ",", "\t"]:
        try:
            df_t = pd.read_csv(f, encoding="latin1", sep=sep, low_memory=False)
            if len(df_t.columns) > 1 and any("almac" in c.lower() for c in df_t.columns):
                lista_desp.append(df_t)
                break
        except Exception:
            continue

df_desp = pd.concat(lista_desp, ignore_index=True)
df_desp.columns = df_desp.columns.str.strip()

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

df_desp["Fecha_DT"] = pd.to_datetime(df_desp["Fecha_Carga"].astype(str), format="%Y%m%d", errors="coerce")
df_desp["Año"] = df_desp["Fecha_DT"].dt.year
df_desp["Mes"] = df_desp["Fecha_DT"].dt.month

df_desp_unicos = df_desp.groupby("Pedido", as_index=False).agg(
    Almacen=("Almacen", "first"),
    Tienda=("Tienda", "first"),
    Fecha_Carga=("Fecha_Carga", "first"),
    Año=("Año", "first"),
    Mes=("Mes", "first"),
    Cant_Lineas_Despachadas=("Pedido", "count")
)

# 2. RECTIFICACIONES (EXCLUYENDO ESTADO 'A')
archivos_rect = sorted(glob.glob(os.path.join(ruta_carpeta, "*Rectificacion*.csv"))) + sorted(glob.glob(os.path.join(ruta_carpeta, "*rectificacion*.csv")))
lista_rect = []
for f in archivos_rect:
    for sep in [";", ",", "\t"]:
        try:
            df_r = pd.read_csv(f, encoding="latin1", sep=sep, low_memory=False)
            if len(df_r.columns) > 1 and any("almac" in c.lower() for c in df_r.columns):
                lista_rect.append(df_r)
                break
        except Exception:
            continue

df_rect = pd.concat(lista_rect, ignore_index=True) if lista_rect else pd.DataFrame()

if not df_rect.empty:
    df_rect.columns = df_rect.columns.str.strip()
    col_alm_r = [c for c in df_rect.columns if "almac" in c.lower()][0]
    col_tien_r = [c for c in df_rect.columns if "tiend" in c.lower()][0]

    df_rect = df_rect.rename(columns={col_alm_r: "Almacen", col_tien_r: "Tienda_Original"})
    df_rect["Pedido"] = df_rect["Pedido"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df_rect["Tienda"] = df_rect["Tienda_Original"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

    df_rect["Motivo_Clean"] = df_rect["Motivo"].astype(str).str.strip().str.upper()
    df_rect["Procedencia_Clean"] = df_rect["Procedencia"].astype(str).str.strip().str.upper()
    df_rect["Estado_Clean"] = df_rect["Estado"].astype(str).str.strip().str.upper()
    df_rect["Artículo"] = df_rect["Artículo"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df_rect["Unid_Grabadas"] = pd.to_numeric(df_rect["Unid/Kgs grabados"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
    df_rect["Unid_Abonadas"] = pd.to_numeric(df_rect["Unid/Kgs abonados"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
    df_rect["Monto_Rectif"] = pd.to_numeric(df_rect["Imp.tien.PVP S/IVA mon.BD"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    # EXCLUSIÓN COMPLETA DEL ESTADO 'A'
    df_rect = df_rect[df_rect["Estado_Clean"] != "A"].copy()

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
            return "Sobrante Neto", 0.0, 10.0
        return "Faltante Neto", -6.0, 4.0

    resumen_pedidos_rect = []
    for ped, group in df_rect.groupby("Pedido"):
        casuistica, penalizacion, puntos = clasificar_pedido(group)
        resumen_pedidos_rect.append({
            "Pedido": ped,
            "Casuistica": casuistica,
            "Penalizacion": penalizacion,
            "Puntos_Obtenidos": puntos,
            "Lineas_Rectificadas_Confirmadas": len(group)
        })

    df_pedidos_rect_summary = pd.DataFrame(resumen_pedidos_rect)
else:
    df_pedidos_rect_summary = pd.DataFrame(columns=["Pedido", "Casuistica", "Penalizacion", "Puntos_Obtenidos", "Lineas_Rectificadas_Confirmadas"])

df_sla_pedidos = df_desp_unicos.merge(df_pedidos_rect_summary, on="Pedido", how="left")
df_sla_pedidos["Casuistica"] = df_sla_pedidos["Casuistica"].fillna("Pedido Perfecto")
df_sla_pedidos["Puntos_Obtenidos"] = df_sla_pedidos["Puntos_Obtenidos"].fillna(10.0)
df_sla_pedidos["Lineas_Rectificadas_Confirmadas"] = df_sla_pedidos["Lineas_Rectificadas_Confirmadas"].fillna(0)

if not df_zona.empty:
    df_sla_pedidos = df_sla_pedidos.merge(df_zona, on="Tienda", how="left")
    if not df_rect.empty:
        df_rect = df_rect.merge(df_zona, on="Tienda", how="left")

df_sla_pedidos["Responsable_Tienda"] = df_sla_pedidos.get("Responsable_Tienda", pd.Series(dtype=str)).fillna("Sin Asignar")
df_sla_pedidos["Gestion"] = df_sla_pedidos.get("Gestion", pd.Series(dtype=str)).fillna("Sin Asignar")

df_sla_pedidos.to_parquet("Tablero_SLA_Pedidos.parquet", index=False, compression="snappy")
df_rect.to_parquet("Tablero_Rectificaciones_Detalle.parquet", index=False, compression="snappy")

print("✅ Parquets generados correctamente.")
