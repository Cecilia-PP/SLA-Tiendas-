import pandas as pd
import glob
import os

print("🔄 Corrigiendo la condición de 'Faltante UxB' para evitar falsos positivos en pedidos masivos...")

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

archivos_rect = glob.glob("Datos_mensuales/*Rectif*.csv") + glob.glob("Datos_mensuales/*rectif*.csv") + glob.glob("*Rectif*.csv")
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

    col_unid = None
    for c in ["Unid/Kgs grabados", "Unid_Grabadas", "Unidades Grabadas", "Unid/Kgs abonados"]:
        if c in df_rect_all.columns:
            col_unid = c
            break

    if col_unid:
        df_rect_all["Unidades_Num"] = pd.to_numeric(df_rect_all[col_unid].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    else:
        df_rect_all["Unidades_Num"] = 1.0

    col_monto = [c for c in ["Monto_Rectif", "Imp.tien.PVP S/IVA mon.BD", "Monto", "Importe"] if c in df_rect_all.columns]
    if col_monto:
        df_rect_all["Monto_Rectif"] = pd.to_numeric(df_rect_all[col_monto[0]].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    cols_clave_rect = ["Pedido", "Nº Rectificación", col_art_rect, "Motivo"]
    cols_exist = [c for c in cols_clave_rect if c in df_rect_all.columns]
    df_rect_all = df_rect_all.drop_duplicates(subset=cols_exist, keep="first")

    df_rect_all.to_parquet("Tablero_Rectificaciones_Detalle.parquet", index=False)

    col_motivo = "Motivo_Clean" if "Motivo_Clean" in df_rect_all.columns else "Motivo"
    df_rect_all["Motivo_Norm"] = df_rect_all[col_motivo].astype(str).str.strip().str.upper()

    pedidos_clasif = []

    for ped, group in df_rect_all.groupby("Pedido"):
        tot_lineas = len(group)
        f_group = group[group["Motivo_Norm"] == "F"]
        s_group = group[group["Motivo_Norm"] == "S"]
        
        cant_f = len(f_group)
        cant_s = len(s_group)
        
        if cant_f > 0 and cant_s > 0:
            if tot_lineas >= 12:
                cas, pts = "Etiquetas Cambiadas", 0.0
            elif cant_f == cant_s:
                subfams_f = set(f_group["Subfamilia"].dropna().unique())
                subfams_s = set(s_group["Subfamilia"].dropna().unique())
                fams_f = set(f_group["Familia"].dropna().unique())
                fams_s = set(s_group["Familia"].dropna().unique())
                
                coincide_subfam = len(subfams_f.intersection(subfams_s)) > 0
                coincide_fam = len(fams_f.intersection(fams_s)) > 0
                
                unid_coincidencia_principal = False
                if not f_group.empty and not s_group.empty:
                    max_f_fam = f_group.sort_values(by="Unidades_Num", ascending=False).iloc[0]["Familia"]
                    max_s_fam = s_group.sort_values(by="Unidades_Num", ascending=False).iloc[0]["Familia"]
                    if max_f_fam == max_s_fam and max_f_fam != "Sin Familia":
                        unid_coincidencia_principal = True

                if coincide_subfam or coincide_fam or unid_coincidencia_principal:
                    cas, pts = "Sustitución Misma Subfamilia", 7.5
                else:
                    cas, pts = "Sustitución Distinta Subfamilia", 5.5
            else:
                cas, pts = "Falta/Sobra", 4.5
        elif cant_f > 0:
            # REGLA AJUSTADA: Requiere que al menos el 50% de las líneas faltantes sean Master
            # o que sea una falta exclusiva de Master
            cant_master_f = (f_group["Es_Master"] == "Sí").sum()
            
            if cant_master_f > 0 and (cant_master_f / cant_f) >= 0.5:
                cas, pts = "Faltante UxB", 4.0
            else:
                cas, pts = "Faltante Neto", 4.0
        elif cant_s > 0:
            cas, pts = "Sobrante Neto", 10.0
        else:
            cas, pts = "Pedido Perfecto", 10.0
            
        pedidos_clasif.append({"Pedido": ped, "Casuistica": cas, "Puntos_Obtenidos": pts})

    resumen_ped = pd.DataFrame(pedidos_clasif)

    if os.path.exists("Tablero_SLA_Pedidos.parquet"):
        df_sla = pd.read_parquet("Tablero_SLA_Pedidos.parquet")
        df_sla = df_sla.drop(columns=["Casuistica", "Puntos_Obtenidos"], errors="ignore")
        df_sla = df_sla.merge(resumen_ped, on="Pedido", how="left")
        df_sla["Casuistica"] = df_sla["Casuistica"].fillna("Pedido Perfecto")
        df_sla["Puntos_Obtenidos"] = df_sla["Puntos_Obtenidos"].fillna(10.0)
        df_sla.to_parquet("Tablero_SLA_Pedidos.parquet", index=False)
        print("✅ Tablero_SLA_Pedidos.parquet re-evaluado con el umbral ajustado para 'Faltante UxB'.")

print("🚀 Procesamiento finalizado con éxito.")
