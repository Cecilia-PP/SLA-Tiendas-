# -*- coding: utf-8 -*-
"""
Script ETL Automatizado y Recurrente para Cierres Mensuales:
============================================================
Diseñado para incorporar automáticamente los nuevos archivos que se sumen mes a mes:
  1. BDMVTAL (*[Bb][Dd][Mm][Vv][Tt][Aa][Ll]*.csv) -> Pedidos de nuevos meses.
  2. AREA DE SALIDA (*[Aa]rea*[Ss]alida*.csv) -> Asignaciones de nuevos sectores.
  3. RECTIFICACIONES (*[Rr]ectif*.csv) -> Reclamos y diferencias de nuevos meses.

Reglas del pipeline:
  • Preserva el histórico oficial consolidado (34,752 pedidos con rectificación iniciales).
  • Actualiza dinámicamente cualquier mes nuevo o sobrescrito calculando sus casuísticas SLA completas
    (sin descartar estados P ni R para evitar pérdida de pedidos).
  • Clasifica las áreas de salida aplicando la regla del negocio: busca en ese MISMO ALMACÉN
    el sector oficial {11, 12, 13, 14, 16, 21, 22, 23, 24, 95} que le corresponde a ese producto.
  • Integra dinámicamente factores UxB (UxB 503.csv y variantes) y Supervisores (ZONA DE SUPERVISION).
"""

import os
import glob
import pandas as pd
import numpy as np

# Catálogo oficial estricto de Áreas de Salida de despacho
AREAS_OFICIALES = {"11", "12", "13", "14", "16", "21", "22", "23", "24", "95"}

# Escala Oficial de Puntuación SLA
MAPA_PUNTOS_SLA = {
    "Pedido Perfecto": 10.0,
    "Sobrante Neto": 10.0,
    "Sustitución Misma Subfamilia": 7.5,
    "Sustitución Distinta Subfamilia": 5.5,
    "Falta/Sobra": 4.5,
    "Faltante Neto": 4.0,
    "Error facturación master": 4.0,
    "Etiquetas Cambiadas": 1.0,     # Descuento -9 pts
    "Formato no entregado": 0.0,     # Descuento -10 pts
    "Rectificación Almacén": 0.0    # Descuento -10 pts (Grabada por Almacén 'G')
}

def corregir_encoding_texto(texto):
    if pd.isna(texto):
        return texto
    s = str(texto)
    try:
        return s.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s

def normalizar_fechas_serie(serie_fechas):
    """Convierte series de fecha multiformato a datetime (DD/MM/YYYY, DD/MM/YY, Excel, ISO)."""
    if serie_fechas is None or serie_fechas.empty:
        return pd.Series(pd.NaT, index=serie_fechas.index if serie_fechas is not None else [], dtype='datetime64[ns]')
    
    s_raw = serie_fechas.astype(str).str.strip().str.replace(".0", "", regex=False)
    
    dt1 = pd.to_datetime(s_raw, format="%d/%m/%Y", errors="coerce")
    dt2 = pd.to_datetime(s_raw, format="%d/%m/%y", errors="coerce")
    dt3 = pd.to_datetime(s_raw, format="%Y%m%d", errors="coerce")
    dt4 = pd.to_datetime(s_raw, format="%Y-%m-%d", errors="coerce")
    
    s_num = pd.to_numeric(s_raw.str.replace(",", "."), errors="coerce")
    mask_excel = s_num.notna() & (s_num > 30000) & (s_num < 70000)
    dt_ex = pd.Series(pd.NaT, index=serie_fechas.index, dtype='datetime64[ns]')
    if mask_excel.any():
        dt_ex[mask_excel] = pd.to_datetime(s_num[mask_excel], unit="D", origin="1899-12-30", errors="coerce")
        
    dt_final = dt1.fillna(dt2).fillna(dt3).fillna(dt4).fillna(dt_ex)
    
    mask_na = dt_final.isna()
    if mask_na.any():
        partes = s_raw[mask_na].str.split(r"[/.-]", expand=True)
        if partes.shape[1] >= 3:
            d = pd.to_numeric(partes[0], errors="coerce")
            m = pd.to_numeric(partes[1], errors="coerce")
            y = pd.to_numeric(partes[2], errors="coerce")
            val = (d >= 1) & (d <= 31) & (m >= 1) & (m <= 12) & y.notna()
            for idx in partes[val].index:
                try:
                    anio = int(y.at[idx])
                    if anio < 100: anio += 2000
                    dt_final.at[idx] = pd.Timestamp(year=anio, month=int(m.at[idx]), day=int(d.at[idx]))
                except Exception:
                    pass

    return dt_final

def leer_csv_robusto(ruta):
    """Lee un archivo CSV probando diferentes separadores y codificaciones habituales."""
    try:
        return pd.read_csv(ruta, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    except Exception:
        try:
            return pd.read_csv(ruta, sep=";", encoding="latin1", dtype=str, on_bad_lines="skip")
        except Exception:
            return pd.read_csv(ruta, sep=",", encoding="utf-8", dtype=str, on_bad_lines="skip")

# ==============================================================================
# 1. CARGA DINÁMICA DE SUPERVISORES (ZONA DE SUPERVISION)
# ==============================================================================
def cargar_mapeo_supervisores(carpeta="."):
    patrones = [
        os.path.join(carpeta, "*[Ss][Uu][Pp][Ee][Rr][Vv][Ii][Ss][Ii]*.csv"),
        os.path.join(carpeta, "*[Zz][Oo][Nn][Aa]*.csv"),
        os.path.join(carpeta, "Datos_mensuales", "*[Ss][Uu][Pp][Ee][Rr][Vv][Ii][Ss][Ii]*.csv"),
        os.path.join(carpeta, "Datos_mensuales", "*[Zz][Oo][Nn][Aa]*.csv")
    ]
    archivos = []
    for pat in patrones:
        archivos.extend(glob.glob(pat))
    archivos_unicos = sorted(list(set(archivos)))
    if not archivos_unicos:
        print("⚠️ No se encontró archivo de ZONA DE SUPERVISION.")
        return {}

    archivo_sup = archivos_unicos[0]
    print(f"👤 Procesando Supervisores: {archivo_sup}")
    try:
        df_sup = leer_csv_robusto(archivo_sup)
        df_sup.columns = df_sup.columns.str.strip().str.upper()
        
        col_t = next((c for c in df_sup.columns if any(k in c for k in ["TIENDA", "SUCURSAL", "COD"])), df_sup.columns[0])
        col_r = next((c for c in df_sup.columns if any(k in c for k in ["RESPONSABLE", "SUPERVISOR", "FRANQUICIADO", "SOCIO"])), df_sup.columns[1])
        
        df_sup["T_Key"] = df_sup[col_t].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
        df_sup["Resp_Val"] = df_sup[col_r].apply(corregir_encoding_texto).astype(str).str.strip()
        mapa = df_sup.drop_duplicates(subset=["T_Key"]).set_index("T_Key")["Resp_Val"].to_dict()
        print(f"   -> Asignadas {len(mapa):,} tiendas con supervisor.")
        return mapa
    except Exception as e:
        print(f"   ❌ Error en supervisores: {e}")
        return {}

# ==============================================================================
# 2. CARGA DE TODOS LOS ARCHIVOS DE ÁREA DE SALIDA (PRESENTES Y FUTUROS)
# ==============================================================================
def cargar_mapeo_area_salida(carpeta="."):
    """Busca y procesa dinámicamente cualquier archivo de Área de Salida en la carpeta raíz o en Datos_mensuales."""
    patrones = [
        os.path.join(carpeta, "*[Aa]rea*[Ss]alida*.csv"),
        os.path.join(carpeta, "Datos_mensuales", "*[Aa]rea*[Ss]alida*.csv"),
        os.path.join(carpeta, "*[Ss]ector*.csv"),
        os.path.join(carpeta, "Datos_mensuales", "*[Ss]ector*.csv")
    ]
    archivos = []
    for pat in patrones:
        archivos.extend(glob.glob(pat))
    archivos_unicos = sorted(list(set(archivos)))
    
    mapa_pedido_area = {}
    if not archivos_unicos:
        print("⚠️ No se encontraron archivos de Área de Salida.")
        return mapa_pedido_area

    print(f"📦 Procesando {len(archivos_unicos)} archivos de Área de Salida encontrados...")
    for arch in archivos_unicos:
        try:
            print(f"   • Leyendo: {arch}")
            df_temp = leer_csv_robusto(arch)
            df_temp.columns = df_temp.columns.str.strip().str.upper()
            
            col_p = next((c for c in df_temp.columns if any(k in c for k in ["PEDIDO", "Nº DE PEDIDO", "Nº PEDIDO", "NRO_PEDIDO", "NRO PEDIDO"])), None)
            col_a = next((c for c in df_temp.columns if any(k in c for k in ["AREA", "ÁREA", "SALIDA", "SECTOR"])), None)

            if col_p and col_a:
                df_temp["Ped_Clean"] = df_temp[col_p].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                df_temp["Area_Clean"] = df_temp[col_a].astype(str).str.strip()
                df_val = df_temp[(df_temp["Ped_Clean"] != "") & (df_temp["Area_Clean"].isin(AREAS_OFICIALES))]
                if not df_val.empty:
                    dict_ped = df_val.drop_duplicates("Ped_Clean").set_index("Ped_Clean")["Area_Clean"].to_dict()
                    mapa_pedido_area.update(dict_ped)
        except Exception as e:
            print(f"   ⚠️ Error en {arch}: {e}")

    print(f"   -> Mapeados {len(mapa_pedido_area):,} pedidos con Área Oficial desde los archivos.")
    return mapa_pedido_area

# ==============================================================================
# 3. MAESTRO DE ARTÍCULOS Y FACTORES UXB (TODOS LOS ARCHIVOS UXB)
# ==============================================================================
def procesar_maestro_articulos(carpeta="."):
    archivos_m = sorted(list(set(glob.glob(os.path.join(carpeta, "*[Mm]aestro*.csv")) + glob.glob(os.path.join(carpeta, "Datos_mensuales", "*[Mm]aestro*.csv")))))
    if not archivos_m:
        print("⚠️ No se encontró Maestro.csv.")
        return pd.DataFrame()

    print(f"📦 Procesando Catálogo Maestro: {archivos_m[0]}")
    df_m = leer_csv_robusto(archivos_m[0])
    df_m.columns = df_m.columns.str.strip().str.upper()

    col_sku = next((c for c in df_m.columns if any(k in c for k in ["ARTICULO", "ARTÍCULO", "SKU", "COD_ART"])), df_m.columns[0])
    col_desc = next((c for c in df_m.columns if any(k in c for k in ["DESCRIPCION", "DESCRIPCIÓN", "PRODUCTO"])), None)
    col_fam = next((c for c in df_m.columns if any(k in c for k in ["FAMILIA", "RUBRO"])), None)
    col_subfam = next((c for c in df_m.columns if any(k in c for k in ["SUBFAMILIA", "SUB_RUBRO"])), None)
    col_flag_m = next((c for c in df_m.columns if any(k in c for k in ["BULTO MASTER", "BULFM", "MASTER"]) and "DESC" not in c), None)

    res = pd.DataFrame()
    res["Artículo"] = df_m[col_sku].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    if col_desc: res["Descripción"] = df_m[col_desc].apply(corregir_encoding_texto)
    if col_fam: res["Familia"] = df_m[col_fam].astype(str).str.strip()
    if col_subfam: res["Subfamilia"] = df_m[col_subfam].astype(str).str.strip()
    
    # ⚡ BANDERA BINARIA MAESTRO: Solo 1 es Máster ('Sí'). Códigos 2, 0, vacíos o NaN son 'No'.
    if col_flag_m:
        flag_master = pd.to_numeric(df_m[col_flag_m].astype(str).str.replace(",", "."), errors="coerce").fillna(0).astype(int)
    else:
        flag_master = pd.Series(0, index=df_m.index)
    res["Es_Master"] = np.where(flag_master == 1, "Sí", "No")

    # ⚡ CARGA DUAL DE ARCHIVOS UXB (Extrae UxB y el factor real BxM desde UxB 503.csv)
    patrones_uxb = [
        os.path.join(carpeta, "*[Uu][Xx][Bb]*.csv"),
        os.path.join(carpeta, "Datos_mensuales", "*[Uu][Xx][Bb]*.csv")
    ]
    archivos_uxb = []
    for p in patrones_uxb:
        archivos_uxb.extend(glob.glob(p))
    archivos_uxb_unicos = sorted(list(set(archivos_uxb)))

    mapa_uxb_acumulado = {}
    mapa_bxm_acumulado = {}
    articulos_master_uxb = set()

    if archivos_uxb_unicos:
        for f_uxb in archivos_uxb_unicos:
            print(f"   -> Incorporando factores UxB y BxM desde: {f_uxb}")
            try:
                df_u = leer_csv_robusto(f_uxb)
                df_u.columns = df_u.columns.str.strip().str.upper()
                c_sk = next((c for c in df_u.columns if any(k in c for k in ["ARTICULO", "ARTÍCULO", "SKU", "COD_ART"])), df_u.columns[0])
                c_ux = next((c for c in df_u.columns if "UXB" in c or "BULTO" in c or "UNID" in c), (df_u.columns[1] if len(df_u.columns) > 1 else None))
                c_form = next((c for c in df_u.columns if any(k in c for k in ["FORMATO", "TIPO", "FORMA"])), None)
                c_bx = next((c for c in df_u.columns if c != c_ux and any(k in c for k in ["BULFM", "BXM", "MASTER", "FACTOR", "BX M", "BULTOS X MASTER", "BULTOS POR MASTER"])), None)

                df_u["Art_Key"] = df_u[c_sk].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                if c_ux:
                    df_u["UxB_Val"] = pd.to_numeric(df_u[c_ux].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
                    m_uxb = df_u.dropna(subset=["UxB_Val"]).groupby("Art_Key")["UxB_Val"].first().to_dict()
                    mapa_uxb_acumulado.update(m_uxb)

                if c_bx:
                    df_u["BULFM_Val"] = pd.to_numeric(df_u[c_bx].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
                    if c_form:
                        # ⚡ En UxB 503, la fila con Formato == 'M' contiene el factor BxM real (ej. 4, 6, 12)
                        df_m_rows = df_u[df_u[c_form].astype(str).str.strip().str.upper() == 'M']
                        if not df_m_rows.empty:
                            m_bxm = df_m_rows.groupby("Art_Key")["BULFM_Val"].max().to_dict()
                            mapa_bxm_acumulado.update(m_bxm)
                            articulos_master_uxb.update(set(df_m_rows["Art_Key"].unique()))
                    else:
                        df_m_rows = df_u[df_u["BULFM_Val"] > 1.0]
                        if not df_m_rows.empty:
                            m_bxm = df_m_rows.groupby("Art_Key")["BULFM_Val"].max().to_dict()
                            mapa_bxm_acumulado.update(m_bxm)
                            articulos_master_uxb.update(set(df_m_rows["Art_Key"].unique()))
            except Exception as e:
                print(f"   ⚠️ Error en {f_uxb}: {e}")

    res["UxB"] = res["Artículo"].map(mapa_uxb_acumulado).fillna(1.0)
    
    # ⚡ CONDICIÓN MASTER ESTRICTA:
    # Es Máster si en Maestro.csv Bulto Master == 1, o si en UxB 503 tiene fila Formato 'M'
    cond_master = (res["Es_Master"] == "Sí") | (res["Artículo"].isin(articulos_master_uxb))
    res["Es_Master"] = np.where(cond_master, "Sí", "No")

    # ⚡ FACTOR BxM (BULFM):
    # Para los máster, toma el BxM real de UxB 503 (ej. 4 para 13821, 6 para 126454, 12 para 127196).
    # Para los no máster, BxM es 1.0.
    res["BxM_Real"] = pd.to_numeric(res["Artículo"].map(mapa_bxm_acumulado), errors="coerce").fillna(1.0)
    res["BULFM"] = np.where(res["Es_Master"] == "Sí", res["BxM_Real"], 1.0)
    res["UxM"] = res["UxB"] * res["BULFM"]
    res.drop(columns=["BxM_Real"], inplace=True, errors="ignore")
    return res.drop_duplicates(subset=["Artículo"])

# ==============================================================================
# 4. PROCESAMIENTO RECURRENTE DE TODAS LAS RECTIFICACIONES
# ==============================================================================
def procesar_rectificaciones(carpeta=".", df_maestro=None, mapa_sup=None, mapa_ped_area=None):
    """Procesa dinámicamente todos los archivos mensuales de rectificaciones presentes y futuros."""
    patrones_r = [
        os.path.join(carpeta, "*[Rr]ectif*.csv"),
        os.path.join(carpeta, "Datos_mensuales", "*[Rr]ectif*.csv")
    ]
    archivos = []
    for p in patrones_r:
        archivos.extend(glob.glob(p))
    archivos_unicos = sorted(list(set(archivos)))
    if not archivos_unicos:
        print("⚠️ No se encontraron archivos de rectificaciones.")
        return pd.DataFrame()

    print(f"📋 Procesando {len(archivos_unicos)} archivos de Rectificaciones...")
    lista_dfs = []
    for arch in archivos_unicos:
        print(f"   • Leyendo: {arch}")
        df_temp = leer_csv_robusto(arch)
        df_temp.columns = df_temp.columns.str.strip()
        lista_dfs.append(df_temp)

    df_r = pd.concat(lista_dfs, ignore_index=True)

    mapa = {}
    for c in df_r.columns:
        clow = c.lower().replace(".", "").replace("_", " ").strip()
        if "almac" in clow or clow == "cd": mapa[c] = "Almacen"
        elif "tienda" in clow or "sucursal" in clow or "cod suc des" in clow: mapa[c] = "Tienda"
        elif "pedido" in clow: mapa[c] = "Pedido"
        elif "art" in clow or "sku" in clow or "material" in clow: mapa[c] = "Artículo"
        elif "desc" in clow or "prod" in clow: mapa[c] = "Descripción"
        elif "motivo" in clow: mapa[c] = "Motivo"
        elif "proc" in clow: mapa[c] = "Procedencia"
        elif "estado" in clow: mapa[c] = "Estado"
        elif "rectif" in clow and ("n" in clow or "num" in clow): mapa[c] = "Nº Rectificación"
        elif "grab" in clow and "fech" in clow: mapa[c] = "Fecha de Grabación"
        elif "grab" in clow and ("unid" in clow or "cant" in clow): mapa[c] = "Unid/Kgs grabados"
        elif "abon" in clow and ("unid" in clow or "cant" in clow): mapa[c] = "Unid/Kgs abonados"
        elif any(k in clow for k in ["imp", "monto", "pvp", "importe"]): mapa[c] = "Monto_Rectif"

    df_r = df_r.rename(columns=mapa)
    df_r["Pedido"] = df_r["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    df_r["Tienda"] = df_r["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    df_r["Artículo"] = df_r["Artículo"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    df_r["Almacen"] = df_r["Almacen"].fillna("501").astype(str).str.strip()
    df_r["Monto_Rectif"] = pd.to_numeric(df_r.get("Monto_Rectif", 0.0).astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    # ⚡ LIMPIEZA DE RECTIFICACIONES EN ESTADO 'A' (No se analizan en el tablero)
    if "Estado" in df_r.columns:
        df_r["Estado"] = df_r["Estado"].astype(str).str.strip().str.upper()
        cant_inicial = len(df_r)
        df_r = df_r[df_r["Estado"] != "A"]
        print(f"🧹 Excluidas {cant_inicial - len(df_r):,} líneas con Estado 'A' (no se analizan).")

    if "Fecha de Grabación" in df_r.columns:
        dt_g = normalizar_fechas_serie(df_r["Fecha de Grabación"])
        df_r["Fecha de Grabación"] = dt_g.dt.strftime("%d/%m/%Y").fillna(df_r["Fecha de Grabación"])
        df_r["Mes"] = dt_g.dt.month.fillna(0).astype(int)

    # Cruce con Maestro (BULFM, UxB, Descripción, Familia, Subfamilia, Es_Master)
    if df_maestro is not None and not df_maestro.empty:
        cols_m = [c for c in ["Descripción", "Familia", "Subfamilia", "UxB", "BULFM", "Es_Master"] if c in df_maestro.columns]
        df_r = df_r.merge(df_maestro[["Artículo"] + cols_m], on="Artículo", how="left", suffixes=("", "_m"))
        for col in cols_m:
            if f"{col}_m" in df_r.columns:
                df_r[col] = df_r[col].fillna(df_r[f"{col}_m"]) if col in df_r.columns else df_r[f"{col}_m"]
                df_r.drop(columns=[f"{col}_m"], inplace=True)

    col_u = next((c for c in ["Unid/Kgs grabados", "Unidades_Num", "Cantidad"] if c in df_r.columns), None)
    df_r["Unidades_Num"] = pd.to_numeric(df_r[col_u].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0) if col_u else 1.0
    df_r["UxB"] = pd.to_numeric(df_r.get("UxB", 1.0), errors="coerce").fillna(1.0)
    # ⚡ Preserva Es_Master y factor real BxM (BULFM) cruzado del Maestro y UxB 503
    df_r["Es_Master"] = df_r["Es_Master"].fillna("No") if "Es_Master" in df_r.columns else "No"
    df_r["BULFM"] = pd.to_numeric(df_r.get("BULFM", 1.0), errors="coerce").fillna(1.0)
    # Si no es master, BxM es 1.0. Si es master, conserva su BxM real proveniente de UxB 503
    df_r["BULFM"] = np.where(df_r["Es_Master"] == "Sí", df_r["BULFM"], 1.0)
    df_r["UxM"] = df_r["UxB"] * df_r["BULFM"]
    df_r["Es_Unidad_Suelta"] = (df_r["UxB"] > 1.0) & (df_r["Unidades_Num"] > 0.0) & (df_r["Unidades_Num"] < df_r["UxB"])

    # Asignar Supervisores
    if mapa_sup:
        df_r["Responsable_Tienda"] = df_r["Tienda"].map(mapa_sup).fillna("Sin Asignar")
    else:
        df_r["Responsable_Tienda"] = "Sin Asignar"

    # =========================================================================
    # ⚡ ASIGNACIÓN INTELIGENTE DE ÁREAS (ALMACÉN + ARTÍCULO)
    # =========================================================================
    mapa_p = mapa_ped_area if mapa_ped_area else {}

    # Paso 1: Asignar directamente por Pedido si viene en los archivos de área
    df_r["Area_Raw"] = df_r["Pedido"].map(mapa_p).fillna("")
    df_r["Area_Salida"] = np.where(df_r["Area_Raw"].isin(AREAS_OFICIALES), df_r["Area_Raw"], "")

    # Paso 2: Matriz histórica viva: relación (Almacén, Artículo) -> Área Oficial en pedidos con área
    df_conocidos = df_r[df_r["Area_Salida"] != ""]
    mapa_alm_art = {}
    mapa_art_global = {}

    if not df_conocidos.empty:
        # Moda por Almacén y Artículo
        grp_aa = df_conocidos.groupby(["Almacen", "Artículo"])["Area_Salida"].agg(lambda s: s.mode().iloc[0] if not s.empty else "")
        mapa_alm_art = grp_aa.to_dict()

        # Moda general por Artículo
        grp_ag = df_conocidos.groupby("Artículo")["Area_Salida"].agg(lambda s: s.mode().iloc[0] if not s.empty else "")
        mapa_art_global = grp_ag.to_dict()

    # Paso 3: Reclasificación según la regla de negocio:
    # "fijarse en ese mismo almacén y los productos que tiene en los pedidos con área y asignarle el área de ese almacén"
    def reclasificar_linea(row):
        area_actual = row["Area_Salida"]
        if area_actual in AREAS_OFICIALES:
            return area_actual

        alm = str(row.get("Almacen", "")).strip()
        art = str(row.get("Artículo", "")).strip()

        # A) Buscar ese producto en ESE MISMO ALMACÉN
        if (alm, art) in mapa_alm_art and mapa_alm_art[(alm, art)] in AREAS_OFICIALES:
            return mapa_alm_art[(alm, art)]

        # B) Buscar ese producto a nivel general en la cadena
        if art in mapa_art_global and mapa_art_global[art] in AREAS_OFICIALES:
            return mapa_art_global[art]

        # C) Mapeo controlado por Familia hacia áreas oficiales (evita secciones erróneas 1, 2, 5, etc.)
        fam = str(row.get("Familia", "")).upper()
        if any(k in fam for k in ["LACTEO", "FRESCO", "FIAMBRE", "QUESO", "POLLO", "CARNE"]):
            return "21"
        elif any(k in fam for k in ["CONGELADO"]):
            return "22"
        elif any(k in fam for k in ["FRUTA", "VERDURA", "PANADERIA"]):
            return "23"
        elif any(k in fam for k in ["BAZAR", "TEXTIL", "HOGAR"]):
            return "14"
        elif any(k in fam for k in ["LIMPIEZA", "PERFUMERIA", "DROGUERIA"]):
            return "16"
        elif any(k in fam for k in ["BEBIDA", "LIQUIDO", "CERVEZA", "VINO", "AGUA"]):
            return "95"
        elif any(k in fam for k in ["GOLOSINA", "SNACK", "CANDY"]):
            return "12"
        elif any(k in fam for k in ["ROTISERIA", "FIAMBRERIA"]):
            return "13"
        elif fam and fam not in ["", "NAN", "NONE", "SIN CLASIFICAR"]:
            return "11"

        if alm == "506":
            return "24"

        return "11"

    df_r["Area_Salida"] = df_r.apply(reclasificar_linea, axis=1)
    df_r.drop(columns=["Area_Raw"], inplace=True, errors="ignore")

    df_r.to_parquet("Tablero_Rectificaciones_Detalle.parquet", index=False)
    print(f"✅ Guardado Tablero_Rectificaciones_Detalle.parquet ({len(df_r):,} registros)")
    print(f"   -> Líneas con UxB > 1: {(df_r['UxB'] > 1.0).sum():,}")
    print(f"   -> Líneas de Unidades Sueltas: {df_r['Es_Unidad_Suelta'].sum():,}")
    print(f"   -> Líneas de Artículos Master (Bulto Master == 1): {(df_r['Es_Master'] == 'Sí').sum():,}")
    print(f"   -> Distribución de Líneas por Áreas Oficiales:")
    for a_val, a_cnt in df_r["Area_Salida"].value_counts().items():
        print(f"       • Sector {a_val}: {a_cnt:,} líneas")
    return df_r

# ==============================================================================
# 5. PEDIDOS SLA: PRESERVACIÓN HISTÓRICA Y ACTUALIZACIÓN MENSUAL AUTOMÁTICA
# ==============================================================================
def evaluar_casuisticas_sla_pedidos(df_pedidos_eval, df_rect_eval):
    """Calcula la casuística SLA para un lote de pedidos.
       Prioriza 'Rectificación Almacén' (-10 pts) si el pedido tiene al menos 1 línea con Procedencia 'G'.
    """
    if df_pedidos_eval.empty or df_rect_eval is None or df_rect_eval.empty:
        df_pedidos_eval["Casuistica"] = "Pedido Perfecto"
        return df_pedidos_eval
        
    df_all_r = df_rect_eval.copy()
    col_proc = "Procedencia" if "Procedencia" in df_all_r.columns else None

    # 1. Identificar pedidos con rectificaciones grabadas por almacén ('G')
    pedidos_g = set()
    if col_proc:
        pedidos_g = set(df_all_r[df_all_r[col_proc].astype(str).str.strip().str.upper() == "G"]["Pedido"].dropna().unique())

    # 2. Filtrar líneas grabadas por tienda ('T') para evaluar casuísticas estándar
    df_v = df_all_r[df_all_r[col_proc].astype(str).str.strip().str.upper() == "T"].copy() if col_proc else df_all_r.copy()
    
    col_mo = "Motivo" if "Motivo" in df_v.columns else None
    df_v["Motivo_Norm"] = df_v[col_mo].astype(str).str.strip().str.upper() if col_mo else "F"
    df_v["Es_Falta"] = df_v["Motivo_Norm"] == "F"
    df_v["Es_Sobra"] = df_v["Motivo_Norm"] == "S"

    mapa_cas = {}
    for ped, grp in df_v.groupby("Pedido"):
        cf = grp["Es_Falta"].sum()
        cs = grp["Es_Sobra"].sum()
        ct = cf + cs
        
        if ct == 0:
            mapa_cas[ped] = "Pedido Perfecto"
        elif cf == 0 and cs > 0:
            mapa_cas[ped] = "Sobrante Neto"
        elif cs == 0 and cf > 0:
            if cf <= 10:
                mapa_cas[ped] = "Faltante Neto"
            else:
                mapa_cas[ped] = "Formato no entregado"
        else:
            if ct >= 12 and cf != cs:
                mapa_cas[ped] = "Etiquetas Cambiadas"
            elif cf == cs and ct < 12:
                sub_f = set(grp[grp["Es_Falta"]]["Subfamilia"].dropna().unique())
                sub_s = set(grp[grp["Es_Sobra"]]["Subfamilia"].dropna().unique())
                if sub_f and sub_f == sub_s:
                    mapa_cas[ped] = "Sustitución Misma Subfamilia"
                else:
                    mapa_cas[ped] = "Sustitución Distinta Subfamilia"
            else:
                mapa_cas[ped] = "Falta/Sobra"

    # Prioridad absoluta: si el pedido tiene rectificación grabada por Almacén ('G'), se asigna 'Rectificación Almacén'
    for p_g in pedidos_g:
        mapa_cas[p_g] = "Rectificación Almacén"

    df_pedidos_eval["Casuistica"] = df_pedidos_eval["Pedido"].map(mapa_cas).fillna("Pedido Perfecto")
    return df_pedidos_eval

def procesar_pedidos_sla(carpeta=".", df_rect=None, mapa_sup=None, mapa_ped_area=None):
    """Combina el histórico protegido cerrado (Jun-Sep) con los meses activos/nuevos cargados por CSV."""
    
    # 1. Cargar Base Histórica Oficial (Junio a Septiembre o base cerrada protegida)
    df_hist = pd.DataFrame()
    rutas_parquet_base = [
        os.path.join(carpeta, "Datos_mensuales", "BK", "Tablero_SLA_Pedidos.parquet"),
        os.path.join(carpeta, "BK", "Tablero_SLA_Pedidos.parquet"),
        os.path.join(carpeta, "Tablero_SLA_Pedidos.parquet")
    ]
    
    for r in rutas_parquet_base:
        if os.path.exists(r):
            print(f"📖 Leyendo base histórica desde: {r}")
            df_temp = pd.read_parquet(r)
            if "Casuistica" in df_temp.columns and (df_temp["Casuistica"] != "Pedido Perfecto").sum() > 30000:
                df_hist = df_temp
                print(f"   🎯 ¡Histórico oficial cargado: {(df_hist['Casuistica'] != 'Pedido Perfecto').sum():,} pedidos rectificados!")
                break
            elif df_hist.empty:
                df_hist = df_temp

    # 2. Cargar dinámicamente todos los archivos BDMVTAL (presentes y futuros)
    patrones_bdm = [
        os.path.join(carpeta, "*[Bb][Dd][Mm][Vv][Tt][Aa][Ll]*.csv"),
        os.path.join(carpeta, "Datos_mensuales", "*[Bb][Dd][Mm][Vv][Tt][Aa][Ll]*.csv")
    ]
    archivos_bdm = []
    for p in patrones_bdm:
        archivos_bdm.extend(glob.glob(p))
    archivos_bdm_unicos = sorted(list(set(archivos_bdm)))

    df_nuevos_meses = pd.DataFrame()
    meses_actualizados = set()

    if archivos_bdm_unicos:
        lista_bdm_dfs = []
        for arch in archivos_bdm_unicos:
            # Detectar mes 10, 11, 12, etc. o archivos actualizados recientemente
            base_name = os.path.basename(arch).lower()
            # Si el archivo corresponde a Octubre en adelante (o meses que se van sumando):
            # Se detecta si el mes está en el nombre (ej. _10_, _11_, _12_, _01_, etc.)
            print(f"📊 Leyendo archivo de pedidos/ventas BDMVTAL: {arch}")
            try:
                df_t = leer_csv_robusto(arch)
                df_t.columns = df_t.columns.str.strip()

                mapa_c = {}
                for c in df_t.columns:
                    clow = c.lower().replace(".", "").replace("_", " ").strip()
                    if "pedido" in clow: mapa_c[c] = "Pedido"
                    elif "tienda" in clow or "sucursal" in clow or "cod suc des" in clow: mapa_c[c] = "Tienda"
                    elif "almac" in clow or clow == "cd": mapa_c[c] = "Almacen"
                    elif "fech" in clow: mapa_c[c] = "Fecha_DT"
                    elif "gest" in clow or "zona" in clow: mapa_c[c] = "Gestion"
                    elif any(k in clow for k in ["imp", "monto", "pvp"]): mapa_c[c] = "Importe"
                df_t = df_t.rename(columns=mapa_c)
                
                df_t["Pedido"] = df_t["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                df_t["Tienda"] = df_t["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                df_t["Almacen"] = df_t["Almacen"].fillna("501").astype(str).str.strip()

                if "Fecha_DT" in df_t.columns:
                    dt = normalizar_fechas_serie(df_t["Fecha_DT"])
                    df_t["Mes"] = dt.dt.month.fillna(0).astype(int)
                    df_t["Año"] = dt.dt.year.fillna(2026).astype(int)
                else:
                    df_t["Mes"] = 0
                    df_t["Año"] = 2026

                # Identificar qué meses están presentes en este archivo BDMVTAL
                meses_en_arch = set(df_t["Mes"].dropna().unique())
                meses_actualizados.update(meses_en_arch)

                # Calcular las casuísticas SLA para estos pedidos nuevos usando el detalle de rectificaciones
                if df_rect is not None and not df_rect.empty:
                    peds_con_rect = set(df_rect["Pedido"].unique())
                    df_r_sub = df_rect[df_rect["Pedido"].isin(set(df_t["Pedido"]))].copy()
                    df_t = evaluar_casuisticas_sla_pedidos(df_t, df_r_sub)

                lista_bdm_dfs.append(df_t)
            except Exception as e:
                print(f"   ⚠️ Error en {arch}: {e}")

        if lista_bdm_dfs:
            df_nuevos_meses = pd.concat(lista_bdm_dfs, ignore_index=True).drop_duplicates(subset=["Pedido"])

    # 3. Fusión Inteligente:
    # Si tenemos meses nuevos (ej. Mes 10, 11, etc.), se reemplazan esos meses específicos
    # manteniendo el histórico de meses cerrados anteriores intacto (Jun-Sep).
    if not df_hist.empty:
        if not df_nuevos_meses.empty and meses_actualizados:
            # Filtrar del histórico aquellos meses que se están actualizando por CSV
            meses_reemplazo = [m for m in meses_actualizados if m >= 10]  # Octubre en adelante se actualiza
            if meses_reemplazo:
                df_hist_preservado = df_hist[~df_hist["Mes"].isin(meses_reemplazo)].copy()
                df_p = pd.concat([df_hist_preservado, df_nuevos_meses[df_nuevos_meses["Mes"].isin(meses_reemplazo)]], ignore_index=True)
                print(f"🔄 Fusión: {len(df_hist_preservado):,} pedidos históricos cerrados + {len(df_nuevos_meses[df_nuevos_meses['Mes'].isin(meses_reemplazo)]):,} pedidos de meses activos ({meses_reemplazo}).")
            else:
                df_p = df_hist
        else:
            df_p = df_hist
    elif not df_nuevos_meses.empty:
        df_p = df_nuevos_meses
    elif df_rect is not None and not df_rect.empty:
        cols_p = [c for c in ["Pedido", "Tienda", "Almacen", "Fecha de Grabación", "Mes", "Area_Salida"] if c in df_rect.columns]
        df_p = df_rect[cols_p].drop_duplicates("Pedido").copy()

    df_p["Pedido"] = df_p["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    df_p["Tienda"] = df_p["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    df_p["Almacen"] = df_p["Almacen"].fillna("501").astype(str).str.strip()

    if "Fecha_DT" in df_p.columns:
        dt = normalizar_fechas_serie(df_p["Fecha_DT"])
        df_p["Mes"] = dt.dt.month.fillna(df_p.get("Mes", 0)).astype(int)
        df_p["Año"] = dt.dt.year.fillna(2026).astype(int)

    # Asignar Supervisores
    if mapa_sup:
        df_p["Responsable_Tienda"] = df_p["Tienda"].map(mapa_sup).fillna("Sin Asignar")
    elif "Responsable_Tienda" not in df_p.columns:
        df_p["Responsable_Tienda"] = "Sin Asignar"

    # Asignar Área de Salida oficial a Pedidos
    mapa_p = mapa_ped_area if mapa_ped_area else {}
    df_p["Area_Salida"] = df_p["Pedido"].map(mapa_p).fillna("")
    
    # Respaldo desde rectificaciones
    if df_rect is not None and not df_rect.empty:
        df_r_areas = df_rect[df_rect["Area_Salida"].isin(AREAS_OFICIALES)][["Pedido", "Area_Salida"]].drop_duplicates("Pedido")
        m_r_area = df_r_areas.set_index("Pedido")["Area_Salida"].to_dict()
        mask_sin = ~df_p["Area_Salida"].isin(AREAS_OFICIALES)
        df_p.loc[mask_sin, "Area_Salida"] = df_p.loc[mask_sin, "Pedido"].map(m_r_area).fillna("")

    # Fallback final a área oficial
    mask_invalida = ~df_p["Area_Salida"].isin(AREAS_OFICIALES)
    df_p.loc[mask_invalida, "Area_Salida"] = np.where(df_p.loc[mask_invalida, "Almacen"] == "506", "24", "11")

    # Reclasificación prioritaria a 'Rectificación Almacén' (-10 Pts) para cualquier pedido con Procedencia 'G'
    if df_rect is not None and not df_rect.empty and "Procedencia" in df_rect.columns:
        pedidos_g_global = set(df_rect[df_rect["Procedencia"].astype(str).str.strip().str.upper() == "G"]["Pedido"].dropna().unique())
        if pedidos_g_global:
            mask_g = df_p["Pedido"].isin(pedidos_g_global)
            df_p.loc[mask_g, "Casuistica"] = "Rectificación Almacén"
            print(f"🏢 Asignados {mask_g.sum():,} pedidos con 'Rectificación Almacén' (Procedencia 'G', 0.0 Pts)")

    # Aplicación de Puntos SLA
    df_p["Puntos_Obtenidos"] = df_p["Casuistica"].map(MAPA_PUNTOS_SLA).fillna(10.0)

    print(f"📊 Total Pedidos con Rectificación: {(df_p['Casuistica'] != 'Pedido Perfecto').sum():,} ({(df_p['Casuistica'] != 'Pedido Perfecto').sum()/len(df_p)*100:.2f}%)")
    print("   -> Resumen de Casuísticas SLA:")
    for cas, cant in df_p["Casuistica"].value_counts().items():
        print(f"       • {cas} ({MAPA_PUNTOS_SLA.get(cas, 10.0)} pts): {cant:,} pedidos")

    df_p.to_parquet("Tablero_SLA_Pedidos.parquet", index=False)
    print(f"✅ Guardado Tablero_SLA_Pedidos.parquet ({len(df_p):,} pedidos)")
    return df_p

# ==============================================================================
# 6. ANULACIONES DEL PORTAL (DINÁMICO)
# ==============================================================================
def procesar_anulaciones(carpeta="."):
    archivos = sorted(list(set(
        glob.glob(os.path.join(carpeta, "*[Aa]nula*.csv")) +
        glob.glob(os.path.join(carpeta, "*[Cc]ausa*.csv")) +
        glob.glob(os.path.join(carpeta, "Datos_mensuales", "*[Cc]ausa*.csv"))
    )))
    if not archivos:
        print("⚠️ No se encontró archivo de anulaciones.")
        return pd.DataFrame()

    print(f"❌ Procesando Anulaciones Portal: {archivos[0]}")
    df_a = leer_csv_robusto(archivos[0])
    df_a.columns = df_a.columns.str.strip()

    mapa = {}
    for c in df_a.columns:
        clow = c.lower().strip()
        if "almac" in clow: mapa[c] = "Almacen"
        elif "tienda" in clow or "sucursal" in clow: mapa[c] = "Tienda"
        elif "pedido" in clow: mapa[c] = "Pedido"
        elif "nota" in clow or "nro" in clow: mapa[c] = "Nota_Nro"
        elif "fch. modif" in clow or "fecha modif" in clow: mapa[c] = "Fecha_Modif"
        elif "fech" in clow: mapa[c] = "Fecha"
        elif "tipo" in clow: mapa[c] = "Tipo"
        elif "cnt" in clow or "blt" in clow: mapa[c] = "Cant_Blt"
        elif "imp" in clow or "monto" in clow: mapa[c] = "Monto"
        elif "motivo" in clow or "causa" in clow: mapa[c] = "Causa_Anulacion"
        elif "estado rpa" in clow or "estado rp" in clow: mapa[c] = "Estado_RPA"
        elif "lote" in clow: mapa[c] = "Lote_RPA"
        elif clow == "estado": mapa[c] = "Estado"

    df_a = df_a.rename(columns=mapa)
    df_a = df_a.loc[:, ~df_a.columns.duplicated()]
    df_a = df_a.dropna(how="all")
    
    if "Pedido" in df_a.columns: df_a["Pedido"] = df_a["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Tienda" in df_a.columns: df_a["Tienda"] = df_a["Tienda"].fillna("").astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Monto" in df_a.columns: df_a["Monto"] = pd.to_numeric(df_a["Monto"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    col_f = "Fecha" if "Fecha" in df_a.columns else ("Fecha_Modif" if "Fecha_Modif" in df_a.columns else None)
    if col_f:
        dt = normalizar_fechas_serie(df_a[col_f])
        df_a["Mes_Num"] = dt.dt.month.fillna(0).astype(int)
        df_a["Año"] = dt.dt.year.fillna(2026).astype(int)
        mapa_meses = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                      7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
        df_a["Nombre_Mes"] = df_a["Mes_Num"].map(mapa_meses).fillna("Sin Mes")
        df_a["Fecha"] = dt.dt.strftime("%d/%m/%Y").fillna(df_a[col_f])

    df_a.to_parquet("Tablero_Anulaciones_Detalle.parquet", index=False)
    print(f"✅ Guardado Tablero_Anulaciones_Detalle.parquet ({len(df_a):,} registros)")
    return df_a

# ==============================================================================
# 7. AUDITORÍA FINAL DE INTEGRIDAD DE TODOS LOS PARQUETS
# ==============================================================================
def auditar_todos_los_parquets():
    print("")
    print("=" * 70)
    print("📊 ANÁLISIS DE INTEGRIDAD DE TODOS LOS PARQUETS")
    print("=" * 70)
    parquets = [
        ("1. Pedidos SLA", "Tablero_SLA_Pedidos.parquet"),
        ("2. Rectificaciones Detalle", "Tablero_Rectificaciones_Detalle.parquet"),
        ("3. Anulaciones Detalle", "Tablero_Anulaciones_Detalle.parquet")
    ]
    mapa_meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre", 0: "⚠️ Sin Mes"
    }

    for nombre, arch in parquets:
        print("")
        print(f"🔍 [{nombre}] Archivo: {arch}")
        if not os.path.exists(arch):
            print("   ❌ No existe en disco.")
            continue
        df_p = pd.read_parquet(arch)
        peso_mb = os.path.getsize(arch) / (1024 * 1024)
        print(f"   • Filas: {len(df_p):,} | Columnas: {len(df_p.columns)} | Peso: {peso_mb:.2f} MB")
        print(f"   • Columnas: {list(df_p.columns)}")
        col_m = "Mes" if "Mes" in df_p.columns else ("Mes_Num" if "Mes_Num" in df_p.columns else None)
        if col_m:
            for m_nom, cant in df_p[col_m].value_counts().rename(index=mapa_meses).items():
                print(f"       - {m_nom}: {cant:,} registros")

    print("")
    print("=" * 70)
    print("✨ DIAGNÓSTICO DE PARQUETS FINALIZADO")
    print("=" * 70)

if __name__ == "__main__":
    print("🚀 Iniciando pipeline ETL automatizado y recurrente...")
    mapa_sup = cargar_mapeo_supervisores()
    mapa_ped_area = cargar_mapeo_area_salida()
    df_maestro = procesar_maestro_articulos()
    df_rect = procesar_rectificaciones(
        df_maestro=df_maestro, 
        mapa_sup=mapa_sup, 
        mapa_ped_area=mapa_ped_area
    )
    df_sla = procesar_pedidos_sla(
        df_rect=df_rect, 
        mapa_sup=mapa_sup, 
        mapa_ped_area=mapa_ped_area
    )
    df_anul = procesar_anulaciones()
    print("✨ Pipeline ETL completado exitosamente.")
    auditar_todos_los_parquets()
