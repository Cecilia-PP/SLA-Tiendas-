import pandas as pd
import glob
import os

print("🔄 Cruzando 'RESPONSABLE TIENDA / SOCIO ESTRATEGICO' con manejo de excepciones de formato...")

# 1. Cargar Mapa desde ZONA DE SUPERVISION
path_zona = glob.glob("Datos_mensuales/*[Zz]ona*.csv") + glob.glob("*[Zz]ona*.csv")
mapa_supervisores = {}

if path_zona:
    try:
        # Probar lectura con punto y coma y salto de líneas erróneas
        try:
            df_zona = pd.read_csv(path_zona[0], sep=";", encoding="latin1", dtype=str, on_bad_lines="skip")
        except Exception:
            df_zona = pd.read_csv(path_zona[0], sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")

        df_zona.columns = df_zona.columns.str.strip().str.upper()
        
        col_t = [c for c in df_zona.columns if "TIENDA" in c][0]
        
        col_resp_exacta = None
        for c in df_zona.columns:
            if "RESPONSABLE TIENDA / SOCIO ESTRATEGICO" in c or "RESPONSABLE TIENDA" in c or "SOCIO ESTRATEGICO" in c or "SUPERVISOR" in c:
                col_resp_exacta = c
                break
                
        if col_t and col_resp_exacta:
            df_zona[col_t] = df_zona[col_t].astype(str).str.strip().str.lstrip("0")
            mapa_supervisores = df_zona.dropna(subset=[col_t]).drop_duplicates(subset=[col_t]).set_index(col_t)[col_resp_exacta].str.strip().to_dict()
            print(f"  └─ Carga exitosa usando columna: '{col_resp_exacta}' desde {path_zona[0]} ({len(mapa_supervisores)} tiendas asociadas)")
    except Exception as e:
        print(f"⚠️️ Error cargando archivo de supervisión: {e}")

# 2. Cargar BDMVTAL (Pedidos Totales)
archivos_bd = glob.glob("Datos_mensuales/BDMVTAL*.csv") + glob.glob("BDMVTAL*.csv")
list_bd = []

for f in archivos_bd:
    try:
        df_temp = pd.read_csv(f, sep=";", encoding="latin1", dtype=str)
        df_temp.columns = df_temp.columns.str.strip()
        list_bd.append(df_temp)
        print(f"  └─ Cargado pedidos: {f}")
    except Exception as e:
        print(f"⚠️ Error cargando {f}: {e}")

if list_bd:
    df_sla = pd.concat(list_bd, ignore_index=True)
    df_sla.columns = df_sla.columns.str.strip()
    
    # Estandarizar Pedido
    col_ped = [c for c in df_sla.columns if c.lower() in ["nº de pedido", "pedido", "nº pedido", "nro_pedido", "num_pedido"]]
    if col_ped:
        df_sla["Pedido"] = df_sla[col_ped[0]].astype(str).str.strip()
    else:
        df_sla["Pedido"] = df_sla.iloc[:, 0].astype(str).str.strip()

    # Estandarizar Tienda
    col_tien = [c for c in df_sla.columns if any(k in c.lower() for k in ["cod. suc. des", "tienda", "sucursal", "cod_suc_des", "suc_des"])]
    if col_tien:
        df_sla["Tienda"] = df_sla[col_tien[0]].astype(str).str.strip().str.lstrip("0")
    else:
        df_sla["Tienda"] = "Sin Tienda"

    # Estandarizar Almacen
    col_alm = [c for c in df_sla.columns if any(k in c.lower() for k in ["cod. almacen", "almacen", "almacén", "cod_almacen", "cd", "suc_ori"])]
    if col_alm:
        df_sla["Almacen"] = df_sla[col_alm[0]].astype(str).str.strip()
    else:
        df_sla["Almacen"] = "501"

    # Estandarizar Gestion
    col_gest = [c for c in df_sla.columns if any(k in c.lower() for k in ["gestion", "gestión", "zona", "region"])]
    if col_gest:
        df_sla["Gestion"] = df_sla[col_gest[0]].astype(str).str.strip()
    else:
        df_sla["Gestion"] = "General"

    # Mapear Responsable_Tienda / Socio Estratégico
    if mapa_supervisores:
        df_sla["Responsable_Tienda"] = df_sla["Tienda"].map(mapa_supervisores).fillna("Sin Asignar")
    else:
        df_sla["Responsable_Tienda"] = "Sin Asignar"

    # Estandarizar Fecha, Año y Mes
    col_fec = [c for c in df_sla.columns if any(k in c.lower() for k in ["fecha servido", "fecha_servido", "fecha de grabación", "fecha"])]
    if col_fec:
        fec_str = df_sla[col_fec[0]].astype(str).str.strip()
        fec_dt = pd.to_datetime(fec_str, format="%Y%m%d", errors="coerce")
        mask_na = fec_dt.isna()
        if mask_na.any():
            fec_dt[mask_na] = pd.to_datetime(fec_str[mask_na], dayfirst=True, errors="coerce")
            
        df_sla["Fecha_DT"] = fec_dt
        df_sla["Año"] = df_sla["Fecha_DT"].dt.year.fillna(2026).astype(int)
        df_sla["Mes"] = df_sla["Fecha_DT"].dt.month.fillna(0).astype(int)
    else:
        df_sla["Año"] = 2026
        df_sla["Mes"] = 0

    df_sla = df_sla.drop_duplicates(subset=["Pedido"], keep="first")
else:
    df_sla = pd.DataFrame(columns=["Pedido", "Tienda", "Almacen", "Gestion", "Responsable_Tienda", "Año", "Mes"])

# 3. Cargar Maestro
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

# 4. Cargar Rectificaciones
archivos_rect = glob.glob("Datos_mensuales/*[Rr]ectif*.csv") + glob.glob("*[Rr]ectif*.csv")
list_rect = []

for f in archivos_rect:
    try:
        df_t = pd.read_csv(f, sep=";", encoding="latin1", dtype=str)
        df_t.columns = df_t.columns.str.strip()
        list_rect.append(df_t)
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

    col_tien_r = [c for c in df_rect_all.columns if any(k in c.lower() for k in ["tienda", "sucursal", "cod_suc_des"])]
    if col_tien_r:
        df_rect_all["Tienda"] = df_rect_all[col_tien_r[0]].astype(str).str.strip().str.lstrip("0")
        if mapa_supervisores:
            df_rect_all["Responsable_Tienda"] = df_rect_all["Tienda"].map(mapa_supervisores).fillna("Sin Asignar")

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

    # 5. Clasificar cada pedido
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

    if not df_sla.empty:
        df_sla = df_sla.drop(columns=["Casuistica", "Puntos_Obtenidos"], errors="ignore")
        df_sla = df_sla.merge(resumen_ped, on="Pedido", how="left")
        df_sla["Casuistica"] = df_sla["Casuistica"].fillna("Pedido Perfecto")
        df_sla["Puntos_Obtenidos"] = df_sla["Puntos_Obtenidos"].fillna(10.0)
        df_sla.to_parquet("Tablero_SLA_Pedidos.parquet", index=False)
        print("✅ Base Tablero_SLA_Pedidos.parquet actualizada con los datos exactos del Responsable/Socio Estratégico.")

print("🚀 Proceso de mapeo finalizado exitosamente.")
