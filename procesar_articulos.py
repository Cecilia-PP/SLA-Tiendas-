import pandas as pd
import glob
import os

print("🔄 Re-evaluando casuísticas con Criterio 1.2 (>= 12 líneas mixtas)...")

# 1. Cargar Maestro
path_maestro_csv = glob.glob("Datos_mensuales/*[Mm]aestro*.csv") + glob.glob("*[Mm]aestro*.csv")
df_maestro = pd.DataFrame()

if path_maestro_csv:
    try:
        df_maestro = pd.read_csv(path_maestro_csv[0], sep=";", encoding="latin1", dtype=str)
        df_maestro.columns = df_maestro.columns.str.strip()
        
        col_master = [c for c in df_maestro.columns if "bulto master" in c.lower() or "master" in c.lower()]
        if col_master:
            df_maestro["Es_Master"] = df_maestro[col_master[0]].astype(str).str.strip().map({"1": "Sí", "2": "No"}).fillna("No")
        else:
            df_maestro["Es_Master"] = "No"

        cols = list(df_maestro.columns)
        if cols.count("Descripción Familia") > 1:
            idx_sub = [i for i, col in enumerate(cols) if col == "Descripción Familia"]
            if len(idx_sub) > 1:
                cols[idx_sub[1]] = "Descripción Subfamilia"
            df_maestro.columns = cols
    except Exception as e:
        print(f"⚠️ Error cargando Maestro: {e}")

# 2. Cargar Rectificaciones
archivos_rect = glob.glob("Datos_mensuales/*Rectif*.csv") + glob.glob("Datos_mensuales/*rectif*.csv")
list_rect = []

for f in archivos_rect:
    try:
        list_rect.append(pd.read_csv(f, sep=";", encoding="latin1", dtype=str))
    except Exception as e:
        pass

if list_rect:
    df_rect_all = pd.concat(list_rect, ignore_index=True)
    df_rect_all.columns = df_rect_all.columns.str.strip()

    col_art_rect = "Artículo" if "Artículo" in df_rect_all.columns else "SKU"
    col_art_mae = "Artículo" if "Artículo" in df_maestro.columns else ("SKU" if "SKU" in df_maestro.columns else None)

    if not df_maestro.empty and col_art_mae and col_art_rect:
        df_rect_all[col_art_rect] = df_rect_all[col_art_rect].astype(str).str.strip().str.lstrip("0")
        df_maestro[col_art_mae] = df_maestro[col_art_mae].astype(str).str.strip().str.lstrip("0")

        cols_a_traer = [col_art_mae]
        if "Descripción Familia" in df_maestro.columns:
            cols_a_traer.append("Descripción Familia")
        if "Descripción Subfamilia" in df_maestro.columns:
            cols_a_traer.append("Descripción Subfamilia")
        if "Es_Master" in df_maestro.columns:
            cols_a_traer.append("Es_Master")

        df_maestro_clean = df_maestro[cols_a_traer].drop_duplicates(subset=[col_art_mae], keep="first")
        df_rect_all = df_rect_all.merge(df_maestro_clean, left_on=col_art_rect, right_on=col_art_mae, how="left")

        if "Descripción Familia" in df_rect_all.columns:
            df_rect_all["Familia"] = df_rect_all["Descripción Familia"]
        if "Descripción Subfamilia" in df_rect_all.columns:
            df_rect_all["Subfamilia"] = df_rect_all["Descripción Subfamilia"]

    df_rect_all["Familia"] = df_rect_all.get("Familia", pd.Series()).fillna("Sin Familia")
    df_rect_all["Subfamilia"] = df_rect_all.get("Subfamilia", pd.Series()).fillna("Sin Subfamilia")
    df_rect_all["Es_Master"] = df_rect_all.get("Es_Master", pd.Series()).fillna("No")

    col_monto = [c for c in ["Monto_Rectif", "Imp.tien.PVP S/IVA mon.BD", "Monto", "Importe"] if c in df_rect_all.columns]
    if col_monto:
        df_rect_all["Monto_Rectif"] = pd.to_numeric(df_rect_all[col_monto[0]].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    # Desduplicar
    cols_clave_rect = ["Pedido", "Nº Rectificación", col_art_rect, "Motivo"]
    cols_exist = [c for c in cols_clave_rect if c in df_rect_all.columns]
    df_rect_all = df_rect_all.drop_duplicates(subset=cols_exist, keep="first")

    df_rect_all.to_parquet("Tablero_Rectificaciones_Detalle.parquet", index=False)

    # 3. RE-CLASIFICACIÓN STRICTA CON CRITERIO 1.2 (>= 12 LÍNEAS MIXTAS)
    col_motivo = "Motivo_Clean" if "Motivo_Clean" in df_rect_all.columns else "Motivo"
    df_rect_all["Motivo_Norm"] = df_rect_all[col_motivo].astype(str).str.strip().str.upper()

    resumen_ped = df_rect_all.groupby("Pedido").agg(
        Total_Lineas=("Motivo_Norm", "count"),
        Cant_F=("Motivo_Norm", lambda x: (x == "F").sum()),
        Cant_S=("Motivo_Norm", lambda x: (x == "S").sum()),
        Subfams=("Subfamilia", lambda x: len(x.dropna().unique())),
        Tiene_Master_F=("Es_Master", lambda x: ((x == "Sí") & (df_rect_all.loc[x.index, "Motivo_Norm"] == "F")).any())
    ).reset_index()

    def clasificar_pedido(row):
        tot = row["Total_Lineas"]
        f = row["Cant_F"]
        s = row["Cant_S"]
        
        if f > 0 and s > 0:
            if tot >= 12:
                return "Etiquetas Cambiadas", 0.0
            elif row["Subfams"] <= 1:
                return "Sustitución Misma Subfamilia", 7.5
            else:
                return "Sustitución Distinta Subfamilia", 5.5
        elif f > 0:
            if row["Tiene_Master_F"]:
                return "Faltante Neto Master (UXB)", 4.0
            else:
                return "Faltante Neto Fraccionado", 4.0
        elif s > 0:
            return "Sobrante Neto", 10.0
        return "Pedido Perfecto", 10.0

    resumen_ped[["Casuistica", "Puntos_Obtenidos"]] = resumen_ped.apply(clasificar_pedido, axis=1, result_type="expand")

    # Actualizar Tablero_SLA_Pedidos.parquet
    if os.path.exists("Tablero_SLA_Pedidos.parquet"):
        df_sla = pd.read_parquet("Tablero_SLA_Pedidos.parquet")
        df_sla = df_sla.drop(columns=["Casuistica", "Puntos_Obtenidos"], errors="ignore")
        df_sla = df_sla.merge(resumen_ped[["Pedido", "Casuistica", "Puntos_Obtenidos"]], on="Pedido", how="left")
        df_sla["Casuistica"] = df_sla["Casuistica"].fillna("Pedido Perfecto")
        df_sla["Puntos_Obtenidos"] = df_sla["Puntos_Obtenidos"].fillna(10.0)
        df_sla.to_parquet("Tablero_SLA_Pedidos.parquet", index=False)
        print("✅ Tablero_SLA_Pedidos.parquet re-clasificado exitosamente con Criterio 1.2 (>= 12 líneas).")

print("🚀 Procesamiento finalizado.")
