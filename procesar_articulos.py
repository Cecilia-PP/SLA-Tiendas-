# -*- coding: utf-8 -*-
import pandas as pd
import glob
import os

# ==============================================================================
# CONFIGURACIÓN DE RUTAS ABSOLUTAS Y DIRECTORIO DE TRABAJO
# ==============================================================================
DIR_BASE = r"C:\Users\cpe021ar\Documents\Python\Tablero_Satifacción_de_Tienda"
DIR_DATOS = os.path.join(DIR_BASE, "Datos_mensuales")

os.chdir(DIR_BASE)

PATH_PARQUET_RECT = os.path.join(DIR_BASE, "Tablero_Rectificaciones_Detalle.parquet")
PATH_PARQUET_SLA = os.path.join(DIR_BASE, "Tablero_SLA_Pedidos.parquet")
PATH_PARQUET_ANUL = os.path.join(DIR_BASE, "Tablero_Anulaciones_Detalle.parquet")

print("==================================================================")
print("🚀 EJECUTANDO ETL CON FALTANTE UXB Y FORMATO NO ENTREGADO (> 10 LÍNEAS)")
print(f"📂 DIRECTORIO BASE: {DIR_BASE}")
print("==================================================================")

def normalizar_pedido(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.lstrip("0")

# 1. MAPEO DE ZONA / SUPERVISIÓN
path_zona = glob.glob(os.path.join(DIR_DATOS, "*[Zz]ona*.csv")) + glob.glob(os.path.join(DIR_BASE, "*[Zz]ona*.csv"))
mapa_supervisores = {}
mapa_gestion = {}

if path_zona:
    print(f"📌 Cargando Zona de Supervisión: {path_zona[0]}")
    try:
        df_zona = pd.read_csv(path_zona[0], sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
        df_zona.columns = df_zona.columns.str.strip().str.upper()
        
        col_t = [c for c in df_zona.columns if "TIENDA" in c or "SUCURSAL" in c][0]
        col_resp = [c for c in df_zona.columns if any(k in c for k in ["RESPONSABLE", "SUPERVISOR", "SOCIO"])][0]
        col_gest = [c for c in df_zona.columns if "GESTION" in c or "GESTIÓN" in c]
        
        df_zona[col_t] = df_zona[col_t].apply(normalizar_pedido)
        df_zona_clean = df_zona.dropna(subset=[col_t]).drop_duplicates(subset=[col_t])
        
        mapa_supervisores = df_zona_clean.set_index(col_t)[col_resp].str.strip().to_dict()
        if col_gest:
            mapa_gestion = df_zona_clean.set_index(col_t)[col_gest[0]].str.strip().to_dict()
    except Exception as e:
        print(f"    ⚠️ Warning cargando Zona: {e}")

# 2. MAPEO DEDUPLICADO DE ÁREA DE SALIDA (PEDIDO + TIENDA Y PEDIDO SOLO)
mapa_area_pedido_tienda = {}
mapa_area_salida_solo = {}

archivos_area = glob.glob(os.path.join(DIR_DATOS, "*[Aa]rea*[Ss]alida*.csv")) + glob.glob(os.path.join(DIR_BASE, "*[Aa]rea*[Ss]alida*.csv"))

if archivos_area:
    list_area = []
    for f in archivos_area:
        print(f"📌 Cargando maestro de Área de Salida: {f}")
        try:
            df_a = pd.read_csv(f, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
            df_a.columns = df_a.columns.str.strip().str.upper()
            
            col_p = [c for c in df_a.columns if any(k in c for k in ["PEDIDO", "Nº DE PEDIDO", "Nº PEDIDO", "NRO_PEDIDO"])][0]
            col_v = [c for c in df_a.columns if any(k in c for k in ["AREA", "ÁREA", "SALIDA", "DESCRIPCION", "SECTOR"])][0]
            col_t_a = [c for c in df_a.columns if any(k in c for k in ["TIENDA", "SUCURSAL", "COD_SUC_DES", "DESTINO"])]
            
            if col_t_a:
                df_sub = df_a[[col_p, col_t_a[0], col_v]].copy()
                df_sub.columns = ["Pedido_Raw", "Tienda_Raw", "Area_Raw"]
            else:
                df_sub = df_a[[col_p, col_v]].copy()
                df_sub["Tienda_Raw"] = ""
                df_sub = df_sub[["Pedido_Raw", "Tienda_Raw", "Area_Raw"]]

            list_area.append(df_sub)
        except Exception as e:
            print(f"    ⚠️ Error leyendo {f}: {e}")

    if list_area:
        df_area_concat = pd.concat(list_area, ignore_index=True)
        df_area_concat["Pedido_Clean"] = df_area_concat["Pedido_Raw"].apply(normalizar_pedido)
        df_area_concat["Tienda_Clean"] = df_area_concat["Tienda_Raw"].apply(normalizar_pedido)
        df_area_concat["Area_Clean"] = df_area_concat["Area_Raw"].astype(str).str.strip()
        
        df_area_valida = df_area_concat[
            (df_area_concat["Pedido_Clean"] != "") & 
            (~df_area_concat["Area_Clean"].isin(["", "nan", "None", "0"]))
        ]

        # Nivel 1: Pedido + Tienda
        df_pt_valido = df_area_valida[df_area_valida["Tienda_Clean"] != ""].drop_duplicates(subset=["Pedido_Clean", "Tienda_Clean"], keep="first")
        mapa_area_pedido_tienda = df_pt_valido.set_index(["Pedido_Clean", "Tienda_Clean"])["Area_Clean"].to_dict()

        # Nivel 2: Pedido solo (Respaldo)
        df_p_valido = df_area_valida.drop_duplicates(subset=["Pedido_Clean"], keep="first")
        mapa_area_salida_solo = df_p_valido.set_index("Pedido_Clean")["Area_Clean"].to_dict()

        print(f"    ✓ Diccionario de consulta construido con {len(mapa_area_pedido_tienda):,} claves únicas (Pedido + Tienda).")

# 3. CARGAR BDMVTAL (MAESTRO DE PEDIDOS)
archivos_bd = glob.glob(os.path.join(DIR_DATOS, "BDMVTAL*.csv")) + glob.glob(os.path.join(DIR_BASE, "BDMVTAL*.csv"))
list_bd = []

for f in archivos_bd:
    try:
        df_temp = pd.read_csv(f, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
        df_temp.columns = df_temp.columns.str.strip()
        list_bd.append(df_temp)
    except Exception as e:
        print(f"    ⚠️ Error cargando {f}: {e}")

df_sla = pd.DataFrame()
if list_bd:
    df_sla = pd.concat(list_bd, ignore_index=True)
    
    col_ped = [c for c in df_sla.columns if c.lower() in ["nº de pedido", "pedido", "nº pedido", "nro_pedido", "num_pedido"]][0]
    df_sla["Pedido"] = df_sla[col_ped].apply(normalizar_pedido)

    col_tien = [c for c in df_sla.columns if any(k in c.lower() for k in ["cod. suc. des", "tienda", "sucursal", "cod_suc_des"])][0]
    df_sla["Tienda"] = df_sla[col_tien].apply(normalizar_pedido)

    col_alm = [c for c in df_sla.columns if any(k in c.lower() for k in ["cod. almacen", "almacen", "almacén", "cd"])][0]
    df_sla["Almacen"] = df_sla[col_alm].astype(str).str.strip()

    df_sla["Gestion"] = df_sla["Tienda"].map(mapa_gestion).fillna("Sin Clasificar").replace(["", "nan", "None"], "Sin Clasificar")
    df_sla["Responsable_Tienda"] = df_sla["Tienda"].map(mapa_supervisores).fillna("Sin Asignar").replace(["", "nan", "None"], "Sin Asignar")
    
    # Asignación Áreas: Nivel 1 (Pedido + Tienda) -> Nivel 2 (Pedido Solo)
    df_sla["Area_Salida"] = df_sla.set_index(["Pedido", "Tienda"]).index.map(mapa_area_pedido_tienda)
    df_sla["Area_Salida"] = df_sla["Area_Salida"].fillna(df_sla["Pedido"].map(mapa_area_salida_solo)).fillna("Sin Clasificar").replace(["", "nan", "None"], "Sin Clasificar")

    # Excepción Opción A: Anular Área 13 para Almacén 514 en SLA
    mask_alm514_area13_sla = (df_sla["Almacen"] == "514") & (df_sla["Area_Salida"] == "13")
    df_sla.loc[mask_alm514_area13_sla, "Area_Salida"] = "Sin Clasificar"

    col_fec = [c for c in df_sla.columns if any(k in c.lower() for k in ["fecha servido", "fecha_servido", "fecha de grabación", "fecha"])][0]
    fec_str = df_sla[col_fec].astype(str).str.strip()
    fec_dt = pd.to_datetime(fec_str, format="%Y%m%d", errors="coerce")
    mask_na = fec_dt.isna()
    if mask_na.any():
        fec_dt[mask_na] = pd.to_datetime(fec_str[mask_na], dayfirst=True, errors="coerce")
        
    df_sla["Fecha_DT"] = fec_dt
    df_sla["Año"] = df_sla["Fecha_DT"].dt.year.fillna(2026).astype(int)
    df_sla["Mes"] = df_sla["Fecha_DT"].dt.month.fillna(0).astype(int)

    df_sla = df_sla.drop_duplicates(subset=["Pedido"], keep="first")

# 4. CARGAR MAESTRO DE PRODUCTOS
path_maestro = glob.glob(os.path.join(DIR_DATOS, "*[Mm]aestro*.csv")) + glob.glob(os.path.join(DIR_BASE, "*[Mm]aestro*.csv"))
df_maestro = pd.DataFrame()
if path_maestro:
    try:
        df_maestro = pd.read_csv(path_maestro[0], sep=";", encoding="latin1", dtype=str, on_bad_lines="skip")
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
        print(f"    ⚠️ Error Maestro: {e}")

# 4.1. CARGAR MAESTRO DE EMPAQUE (UxB 503.csv)
archivos_uxb = glob.glob(os.path.join(DIR_DATOS, "*[Uu][Xx][Bb]*.csv")) + glob.glob(os.path.join(DIR_BASE, "*[Uu][Xx][Bb]*.csv"))
mapa_uxb = {}

if archivos_uxb:
    try:
        print(f"📌 Cargando maestro de formatos de empaque: {archivos_uxb[0]}")
        df_uxb = pd.read_csv(archivos_uxb[0], sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
        df_uxb.columns = df_uxb.columns.str.strip()
        
        col_art_uxb = [c for c in df_uxb.columns if any(k in c.lower() for k in ["art", "sku", "cod"])][0]
        df_uxb["SKU_Clean"] = df_uxb[col_art_uxb].astype(str).str.strip().str.lstrip("0")
        
        for c in ["BxF", "UxB", "UxM"]:
            if c in df_uxb.columns:
                df_uxb[c] = pd.to_numeric(df_uxb[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
                
        # Consolidar por SKU seleccionando el valor máximo de UxM
        df_uxb_grouped = df_uxb.groupby("SKU_Clean").agg({
            "UxB": "max",
            "UxM": "max",
            "BxF": "max"
        }).reset_index()
        
        mapa_uxb = df_uxb_grouped.set_index("SKU_Clean")[["BxF", "UxB", "UxM"]].to_dict(orient="index")
        print(f"    ✓ Maestro UxB/UxM consolidado exitosamente con {len(mapa_uxb):,} artículos únicos.")
    except Exception as e:
        print(f"    ⚠️ Warning cargando maestro UxB: {e}")

# 5. CARGAR Y FILTRAR RECTIFICACIONES
archivos_rect = glob.glob(os.path.join(DIR_DATOS, "*[Rr]ectif*.csv")) + glob.glob(os.path.join(DIR_BASE, "*[Rr]ectif*.csv"))
list_rect = []

for f in archivos_rect:
    try:
        df_t = pd.read_csv(f, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
        df_t.columns = df_t.columns.str.strip()
        list_rect.append(df_t)
    except Exception as e:
        print(f"    ⚠️ Error cargando {f}: {e}")

if list_rect:
    df_rect_all = pd.concat(list_rect, ignore_index=True)

    # 🚫 PURGA ESTRICTA: ELIMINAR RECTIFICACIONES AUTOMÁTICAS ('A', 'AUTO', 'AUTOMATICA')
    cols_check = [c for c in df_rect_all.columns if any(k in c.lower() for k in ["estado", "procedencia", "origen", "tipo"])]
    mask_auto = pd.Series(False, index=df_rect_all.index)
    for col in cols_check:
        mask_auto = mask_auto | df_rect_all[col].astype(str).str.strip().str.upper().isin(["A", "AUTO", "AUTOMATICA", "AUTOMÁTICA"])

    cant_auto = mask_auto.sum()
    df_rect_all = df_rect_all[~mask_auto].copy()
    print(f"    🚫 Purga realizada: {cant_auto:,} rectificaciones automáticas fueron eliminadas de la base de datos.")

    col_ped_r = [c for c in df_rect_all.columns if c.lower() in ["nº de pedido", "pedido", "nº pedido", "nro_pedido", "num_pedido"]][0]
    df_rect_all["Pedido"] = df_rect_all[col_ped_r].apply(normalizar_pedido)

    col_tien_r = [c for c in df_rect_all.columns if any(k in c.lower() for k in ["tienda", "sucursal", "cod_suc_des"])][0]
    df_rect_all["Tienda"] = df_rect_all[col_tien_r].apply(normalizar_pedido)

    # ⚡ ASIGNACIÓN ÁREA NIVEL 1: (PEDIDO + TIENDA) -> NIVEL 2: (PEDIDO SOLO)
    df_rect_all["Area_Salida"] = df_rect_all.set_index(["Pedido", "Tienda"]).index.map(mapa_area_pedido_tienda)
    df_rect_all["Area_Salida"] = df_rect_all["Area_Salida"].fillna(df_rect_all["Pedido"].map(mapa_area_salida_solo)).fillna("Sin Clasificar").replace(["", "nan", "None"], "Sin Clasificar")

    col_art_rect = "Artículo" if "Artículo" in df_rect_all.columns else "SKU"
    col_art_mae = "Artículo" if "Artículo" in df_maestro.columns else ("SKU" if "SKU" in df_maestro.columns else None)

    if not df_maestro.empty and col_art_mae and col_art_rect:
        df_rect_all[col_art_rect] = df_rect_all[col_art_rect].apply(normalizar_pedido)
        df_maestro[col_art_mae] = df_maestro[col_art_mae].apply(normalizar_pedido)

        cols_a_traer = [col_art_mae]
        if "Descripción Familia" in df_maestro.columns: cols_a_traer.append("Descripción Familia")
        if "Descripción Subfamilia" in df_maestro.columns: cols_a_traer.append("Descripción Subfamilia")
        if "Es_Master" in df_maestro.columns: cols_a_traer.append("Es_Master")

        df_maestro_clean = df_maestro[cols_a_traer].drop_duplicates(subset=[col_art_mae], keep="first")
        df_rect_all = df_rect_all.merge(df_maestro_clean, left_on=col_art_rect, right_on=col_art_mae, how="left")

        if "Descripción Familia" in df_rect_all.columns: df_rect_all["Familia"] = df_rect_all["Descripción Familia"]
        if "Descripción Subfamilia" in df_rect_all.columns: df_rect_all["Subfamilia"] = df_rect_all["Descripción Subfamilia"]

    df_rect_all["Familia"] = df_rect_all.get("Familia", pd.Series()).fillna("Sin Familia")
    df_rect_all["Subfamilia"] = df_rect_all.get("Subfamilia", pd.Series()).fillna("Sin Subfamilia")
    df_rect_all["Es_Master"] = df_rect_all.get("Es_Master", pd.Series()).fillna("No")

    col_alm_r = [c for c in df_rect_all.columns if any(k in c.lower() for k in ["cod. almacen", "almacen", "almacén", "cd"])][0]
    df_rect_all["Almacen"] = df_rect_all[col_alm_r].astype(str).str.strip()

    df_rect_all["Responsable_Tienda"] = df_rect_all["Tienda"].map(mapa_supervisores).fillna("Sin Asignar").replace(["", "nan", "None"], "Sin Clasificar")
    df_rect_all["Gestion"] = df_rect_all["Tienda"].map(mapa_gestion).fillna("Sin Clasificar").replace(["", "nan", "None"], "Sin Clasificar")

    col_unid = [c for c in ["Unid/Kgs grabados", "Unid_Grabadas", "Unidades Grabadas", "Unid/Kgs abonados"] if c in df_rect_all.columns]
    df_rect_all["Unidades_Num"] = pd.to_numeric(df_rect_all[col_unid[0]].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0) if col_unid else 1.0

    col_monto = [c for c in ["Monto_Rectif", "Imp.tien.PVP S/IVA mon.BD", "Monto", "Importe"] if c in df_rect_all.columns]
    if col_monto:
        df_rect_all["Monto_Rectif"] = pd.to_numeric(df_rect_all[col_monto[0]].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    # DEDUPLICAR LÍNEAS
    cols_clave_rect = ["Pedido", "Nº Rectificación", col_art_rect, "Motivo"]
    cols_exist = [c for c in cols_clave_rect if c in df_rect_all.columns]
    df_rect_all = df_rect_all.drop_duplicates(subset=cols_exist, keep="first")

    # --------------------------------------------------------------------------
    # 🛠️ OPCIÓN A: PURGA Y REINFERENCIA DE ÁREA 13 PARA ALMACÉN 514
    # --------------------------------------------------------------------------
    mask_alm514_area13 = (df_rect_all["Almacen"] == "514") & (df_rect_all["Area_Salida"] == "13")
    cant_anuladas_514 = mask_alm514_area13.sum()
    if cant_anuladas_514 > 0:
        df_rect_all.loc[mask_alm514_area13, "Area_Salida"] = "Sin Clasificar"
        print(f"    ⚠️ Se anularon {cant_anuladas_514:,} asignaciones directas de Área 13 en Almacén 514 para forzar inferencia.")

    # --------------------------------------------------------------------------
    # ⚡ INFERENCIA EN CASCADA (NIVEL 3: ALMACÉN + ARTÍCULO | NIVEL 4: ALMACÉN + FAMILIA)
    # --------------------------------------------------------------------------
    df_validos = df_rect_all[df_rect_all["Area_Salida"] != "Sin Clasificar"]

    mapa_art_area = df_validos.groupby(["Almacen", col_art_rect])["Area_Salida"].agg(
        lambda x: x.mode()[0] if not x.empty else "Sin Clasificar"
    ).to_dict()

    mapa_fam_area = df_validos.groupby(["Almacen", "Familia"])["Area_Salida"].agg(
        lambda x: x.mode()[0] if not x.empty else "Sin Clasificar"
    ).to_dict()

    mask_sin_area = df_rect_all["Area_Salida"] == "Sin Clasificar"
    cant_sin_area_ini = mask_sin_area.sum()

    if cant_sin_area_ini > 0:
        # Nivel 3: Almacén + Artículo
        df_rect_all.loc[mask_sin_area, "Area_Salida"] = (
            df_rect_all[mask_sin_area]
            .set_index(["Almacen", col_art_rect])
            .index.map(mapa_art_area)
            .fillna("Sin Clasificar")
        )

        # Nivel 4: Almacén + Familia
        mask_todavia_sin_area = df_rect_all["Area_Salida"] == "Sin Clasificar"
        if mask_todavia_sin_area.any():
            df_rect_all.loc[mask_todavia_sin_area, "Area_Salida"] = (
                df_rect_all[mask_todavia_sin_area]
                .set_index(["Almacen", "Familia"])
                .index.map(mapa_fam_area)
                .fillna("Sin Clasificar")
            )

    print(f"✨ Inferencia completada: {cant_sin_area_ini:,} líneas procesadas mediante (Almacén + Artículo / Familia).")

    # ⚡ ASIGNAR DATOS DE EMPAQUE (UxB, UxM) Y IDENTIFICAR UNIDADES SUELTAS
    def obtener_uxb(sku):
        sku_c = str(sku).strip().lstrip("0")
        d = mapa_uxb.get(sku_c, {})
        return float(d.get("UxB", 0.0))

    def obtener_uxm(sku):
        sku_c = str(sku).strip().lstrip("0")
        d = mapa_uxb.get(sku_c, {})
        return float(d.get("UxM", 0.0))

    df_rect_all["UxB"] = df_rect_all[col_art_rect].apply(obtener_uxb)
    df_rect_all["UxM"] = df_rect_all[col_art_rect].apply(obtener_uxm)
    
    # Marcador de Unidad Suelta: Unidades_Num < UxB (cuando UxB > 1)
    df_rect_all["Es_Unidad_Suelta"] = (df_rect_all["UxB"] > 1.0) & (df_rect_all["Unidades_Num"] > 0.0) & (df_rect_all["Unidades_Num"] < df_rect_all["UxB"])

    # 💾 GUARDAR PARQUET 1: DETALLE DE RECTIFICACIONES
    df_rect_all.to_parquet(PATH_PARQUET_RECT, index=False)
    print(f"    ✓ Archivo Parquet actualizado: {PATH_PARQUET_RECT}")

    # 6. EVALUAR CASUÍSTICA Y SLA
    col_motivo = "Motivo_Clean" if "Motivo_Clean" in df_rect_all.columns else "Motivo"
    df_rect_all["Motivo_Norm"] = df_rect_all[col_motivo].astype(str).str.strip().str.upper()

    def es_linea_error_master(row):
        """Evalúa si una línea individual corresponde a una anomalía de Bulto Máster."""
        sku = str(row.get(col_art_rect, "")).strip().lstrip("0")
        unid = float(row.get("Unidades_Num", 0.0))
        es_m_flag = str(row.get("Es_Master", "")).strip().upper() in ["SI", "SÍ"]
        
        datos_m = mapa_uxb.get(sku, {})
        uxb = float(datos_m.get("UxB", 0.0))
        uxm = float(datos_m.get("UxM", 0.0))
        
        if uxm <= 1.0 and not es_m_flag:
            return False
        if uxm > 0.0 and uxm <= uxb:
            return False
        if uxb > 0.0 and unid == uxb:
            return False
            
        if uxm > 1.0 and unid > 0.0 and (unid == uxm or unid % uxm == 0):
            return True
            
        dif_uxm_uxb = uxm - uxb
        if dif_uxm_uxb > 0.0 and dif_uxm_uxb != uxb and unid > 0.0:
            if unid == dif_uxm_uxb or unid % dif_uxm_uxb == 0:
                return True
                
        return False

    pedidos_clasif = []

    for ped, group in df_rect_all.groupby("Pedido"):
        tot_lineas = len(group)
        
        # Evaluar cuántas líneas del pedido cumplen la regla de Bulto Máster
        lineas_uxb = sum(es_linea_error_master(row) for _, row in group.iterrows())
        
        f_group = group[group["Motivo_Norm"] == "F"]
        s_group = group[group["Motivo_Norm"] == "S"]
        
        cant_f = len(f_group)
        cant_s = len(s_group)
        
        # 1. FALTANTE UXB (100% de rectificaciones por desvío Máster)
        if lineas_uxb > 0 and lineas_uxb == tot_lineas:
            cas, pts = "Faltante UxB", 4.0
        elif cant_f > 0 and cant_s > 0:
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
            # 🆕 REGLA FORMATO NO ENTREGADO: Si el pedido es solo Faltante ('F') y tiene MÁS DE 10 LÍNEAS
            if cant_f > 10:
                cas, pts = "Formato no entregado", 4.0
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
        
        # 💾 GUARDAR PARQUET 2: RESUMEN SLA
        df_sla.to_parquet(PATH_PARQUET_SLA, index=False)
        print(f"    ✓ Archivo Parquet actualizado: {PATH_PARQUET_SLA}")

# 7. CARGAR Y PROCESAR MAESTRO DE CAUSA ANULACIONES / RECTIFICACIONES RECHAZADAS
archivos_anul = glob.glob(os.path.join(DIR_DATOS, "*[Aa]nula*.csv")) + glob.glob(os.path.join(DIR_BASE, "*[Aa]nula*.csv")) + glob.glob(os.path.join(DIR_DATOS, "*[Cc]ausa*.csv")) + glob.glob(os.path.join(DIR_BASE, "*[Cc]ausa*.csv"))

list_anul = []
for f in archivos_anul:
    print(f"📌 Cargando archivo de Causa de Anulaciones: {f}")
    try:
        df_a = pd.read_csv(f, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
        df_a.columns = df_a.columns.str.strip()
        list_anul.append(df_a)
    except Exception as e:
        print(f"    ⚠️ Error leyendo {f}: {e}")

if list_anul:
    df_anul = pd.concat(list_anul, ignore_index=True)
    df_anul.columns = df_anul.columns.str.strip()
    
    mapa_cols_anul = {}
    for c in df_anul.columns:
        clow = c.lower()
        if "almac" in clow: mapa_cols_anul[c] = "Almacen"
        elif "tienda" in clow or "sucursal" in clow: mapa_cols_anul[c] = "Tienda"
        elif "pedido" in clow: mapa_cols_anul[c] = "Pedido"
        elif "nota" in clow or "nro" in clow: mapa_cols_anul[c] = "Nota_Nro"
        elif "fch. modif" in clow or "fch_modif" in clow or "fecha modif" in clow: mapa_cols_anul[c] = "Fecha_Modif"
        elif "fech" in clow and "modif" not in clow: mapa_cols_anul[c] = "Fecha"
        elif "tipo" in clow or "motivo_rect" in clow: mapa_cols_anul[c] = "Tipo"
        elif "cnt" in clow or "blt" in clow or "bulto" in clow or "cant" in clow: mapa_cols_anul[c] = "Cant_Blt"
        elif "imp" in clow or "monto" in clow or "importe" in clow: mapa_cols_anul[c] = "Monto"
        elif "estado rp" in clow: mapa_cols_anul[c] = "Estado_RP"
        elif "estado" in clow: mapa_cols_anul[c] = "Estado"
        elif "motivo" in clow or "causa" in clow: mapa_cols_anul[c] = "Causa_Anulacion"
        elif "lote" in clow or "rpa" in clow: mapa_cols_anul[c] = "Lote_RPA"

    df_anul = df_anul.rename(columns=mapa_cols_anul)
    
    if "Pedido" in df_anul.columns: df_anul["Pedido"] = df_anul["Pedido"].apply(normalizar_pedido)
    if "Tienda" in df_anul.columns: df_anul["Tienda"] = df_anul["Tienda"].apply(normalizar_pedido)
    if "Almacen" in df_anul.columns: df_anul["Almacen"] = df_anul["Almacen"].astype(str).str.strip()
    if "Monto" in df_anul.columns: df_anul["Monto"] = pd.to_numeric(df_anul["Monto"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    if "Cant_Blt" in df_anul.columns: df_anul["Cant_Blt"] = pd.to_numeric(df_anul["Cant_Blt"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    
    if "Tienda" in df_anul.columns:
        df_anul["Responsable_Tienda"] = df_anul["Tienda"].map(mapa_supervisores).fillna("Sin Asignar")
        df_anul["Gestion"] = df_anul["Tienda"].map(mapa_gestion).fillna("Sin Clasificar")

    if "Pedido" in df_anul.columns and "Tienda" in df_anul.columns:
        df_anul["Area_Salida"] = df_anul.set_index(["Pedido", "Tienda"]).index.map(mapa_area_pedido_tienda)
        df_anul["Area_Salida"] = df_anul["Area_Salida"].fillna(df_anul["Pedido"].map(mapa_area_salida_solo)).fillna("Sin Clasificar")

    df_anul.to_parquet(PATH_PARQUET_ANUL, index=False)
    print(f"    ✓ Archivo Parquet de Anulaciones generado: {PATH_PARQUET_ANUL} con {len(df_anul):,} registros.")

print("==================================================================")
print("✨ PROCESO COMPLETADO Y LOS ARCHIVOS PARQUET FUERON GENERADOS CORRECTAMENTE.")
print("==================================================================")
