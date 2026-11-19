# -*- coding: utf-8 -*-
"""
Script ETL Automatizado y Recurrente para Cierres Mensuales:
============================================================
Diseñado para incorporar automáticamente los nuevos archivos que se sumen mes a mes:
  1. BDMVTAL (*[Bb][Dd][Mm][Vv][Tt][Aa][Ll]*.csv) -> Pedidos y conteo total de líneas por pedido.
  2. AREA DE SALIDA (*[Aa]rea*[Ss]alida*.csv) -> Asignaciones de nuevos sectores.
  3. RECTIFICACIONES (*[Rr]ectif*.csv) -> Reclamos y diferencias de nuevos meses.

Reglas del pipeline:
  • Preserva el histórico oficial consolidado (34,752 pedidos con rectificación iniciales).
  • Actualiza dinámicamente cualquier mes nuevo o sobrescrito calculando sus casuísticas SLA completas
    (sin descartar estados P ni R para evitar pérdida de pedidos).
  • Asigna el puntaje oficial SLA (incluyendo Sobrante Neto = 9.0 pts, descuento -1 pt).
  • Calcula la cantidad total de líneas solicitadas por pedido desde BDMVTAL (`Lineas_Pedido`)
    para medir el porcentaje real del pedido que fue rectificado.
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
    "Sobrante Neto": 9.0,            # Descuento -1 pt
    "Sustitución Misma Subfamilia": 7.5,
    "Sustitución Distinta Subfamilia": 5.5,
    "Falta/Sobra": 4.5,
    "Faltante Neto": 4.0,
    "Error facturación master": 4.0,
    "Etiquetas Cambiadas": 1.0,      # Descuento -9 pts
    "Formato no entregado": 0.0,     # Descuento -10 pts
    "Rectificación Almacén": 0.0     # Descuento -10 pts (Grabada por Almacén 'G')
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
    
    mapa_alm_pedido_area = {}
    mapa_pedido_area = {}
    if not archivos_unicos:
        print("⚠️ No se encontraron archivos de Área de Salida.")
        return mapa_alm_pedido_area, mapa_pedido_area

    print(f"📦 Procesando {len(archivos_unicos)} archivos de Área de Salida encontrados...")
    for arch in archivos_unicos:
        try:
            print(f"   • Leyendo: {arch}")
            df_temp = leer_csv_robusto(arch)
            df_temp.columns = df_temp.columns.str.strip().str.upper()
            
            col_alm = next((c for c in df_temp.columns if any(k in c for k in ["ALMAC", "CD", "CENTRO"])), None)
            col_p = next((c for c in df_temp.columns if any(k in c for k in ["PEDIDO", "Nº DE PEDIDO", "Nº PEDIDO", "NRO_PEDIDO", "NRO PEDIDO"])), None)
            col_a = next((c for c in df_temp.columns if any(k in c for k in ["AREA", "ÁREA", "SALIDA", "SECTOR"])), None)

            if col_p and col_a:
                df_temp["Ped_Clean"] = df_temp[col_p].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                df_temp["Area_Clean"] = df_temp[col_a].astype(str).str.strip()
                df_temp["Alm_Clean"] = df_temp[col_alm].astype(str).str.strip().str.replace(".0", "", regex=False) if col_alm else ""
                df_val = df_temp[(df_temp["Ped_Clean"] != "") & (df_temp["Area_Clean"].isin(AREAS_OFICIALES))]
                if not df_val.empty:
                    if col_alm:
                        df_val_alm = df_val[df_val["Alm_Clean"] != ""]
                        if not df_val_alm.empty:
                            dict_ap = df_val_alm.drop_duplicates(["Alm_Clean", "Ped_Clean"]).set_index(["Alm_Clean", "Ped_Clean"])["Area_Clean"].to_dict()
                            mapa_alm_pedido_area.update(dict_ap)
                    dict_ped = df_val.drop_duplicates("Ped_Clean").set_index("Ped_Clean")["Area_Clean"].to_dict()
                    mapa_pedido_area.update(dict_ped)
        except Exception as e:
            print(f"   ⚠️ Error en {arch}: {e}")

    print(f"   -> Mapeados {len(mapa_alm_pedido_area):,} pares (Almacén, Pedido) y {len(mapa_pedido_area):,} pedidos con Área Oficial desde los CSV.")
    return mapa_alm_pedido_area, mapa_pedido_area

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
    # ⚡ ASIGNACIÓN DE ÁREAS DESDE CSV + HISTÓRICO DEL SKU EN ESE MISMO ALMACÉN
    # =========================================================================
    if isinstance(mapa_ped_area, tuple):
        mapa_ap, mapa_p = mapa_ped_area
    else:
        mapa_ap, mapa_p = {}, (mapa_ped_area if mapa_ped_area else {})

    # Paso 1: Match directo por (Almacén, Pedido) desde los CSV oficiales de Área de Salida
    idx_r_ap = pd.MultiIndex.from_frame(df_r[["Almacen", "Pedido"]])
    s_area_ap = pd.Series(idx_r_ap.map(mapa_ap), index=df_r.index) if mapa_ap else pd.Series(np.nan, index=df_r.index)
    s_area_p = df_r["Pedido"].map(mapa_p) if mapa_p else pd.Series(np.nan, index=df_r.index)
    df_r["Area_Raw"] = s_area_ap.fillna(s_area_p).fillna("")
    df_r["Area_Salida"] = np.where(df_r["Area_Raw"].isin(AREAS_OFICIALES), df_r["Area_Raw"], "")

    # Paso 2: Construir histórico por (Almacén, Artículo) SOLO desde las líneas que SÍ tuvieron match oficial en CSV
    df_con_area_csv = df_r[df_r["Area_Salida"].isin(AREAS_OFICIALES)]
    mapa_hist_alm_sku = {}
    if not df_con_area_csv.empty:
        mapa_hist_alm_sku = (
            df_con_area_csv.groupby(["Almacen", "Artículo"])["Area_Salida"]
            .agg(lambda s: s.mode().iloc[0] if not s.empty else "")
            .to_dict()
        )

    # Paso 3: Rellenar las rectificaciones sin match en CSV usando el histórico en ESE MISMO ALMACÉN:
    #         1° por (Almacén, Artículo) -> 2° por (Almacén, Subfamilia) -> 3° por (Almacén, Familia)
    mask_sin_area = ~df_r["Area_Salida"].isin(AREAS_OFICIALES)
    if mask_sin_area.any() and mapa_hist_alm_sku:
        idx_sin = pd.MultiIndex.from_frame(df_r.loc[mask_sin_area, ["Almacen", "Artículo"]])
        s_hist_ap = pd.Series(idx_sin.map(mapa_hist_alm_sku), index=df_r.loc[mask_sin_area].index).fillna("")
        df_r.loc[mask_sin_area, "Area_Salida"] = np.where(s_hist_ap.isin(AREAS_OFICIALES), s_hist_ap, "")

    mask_sin_area = ~df_r["Area_Salida"].isin(AREAS_OFICIALES)
    if mask_sin_area.any() and not df_con_area_csv.empty and "Subfamilia" in df_r.columns:
        df_con_sf = df_con_area_csv[df_con_area_csv["Subfamilia"].notna() & (~df_con_area_csv["Subfamilia"].isin(["", "nan", "None"]))]
        if not df_con_sf.empty:
            mapa_hist_alm_sf = (
                df_con_sf.groupby(["Almacen", "Subfamilia"])["Area_Salida"]
                .agg(lambda s: s.mode().iloc[0] if not s.empty else "")
                .to_dict()
            )
            idx_sin_sf = pd.MultiIndex.from_frame(df_r.loc[mask_sin_area, ["Almacen", "Subfamilia"]])
            s_hist_sf = pd.Series(idx_sin_sf.map(mapa_hist_alm_sf), index=df_r.loc[mask_sin_area].index).fillna("")
            df_r.loc[mask_sin_area, "Area_Salida"] = np.where(s_hist_sf.isin(AREAS_OFICIALES), s_hist_sf, "")

    mask_sin_area = ~df_r["Area_Salida"].isin(AREAS_OFICIALES)
    if mask_sin_area.any() and not df_con_area_csv.empty and "Familia" in df_r.columns:
        df_con_fam = df_con_area_csv[df_con_area_csv["Familia"].notna() & (~df_con_area_csv["Familia"].isin(["", "nan", "None"]))]
        if not df_con_fam.empty:
            mapa_hist_alm_fam = (
                df_con_fam.groupby(["Almacen", "Familia"])["Area_Salida"]
                .agg(lambda s: s.mode().iloc[0] if not s.empty else "")
                .to_dict()
            )
            idx_sin_fam = pd.MultiIndex.from_frame(df_r.loc[mask_sin_area, ["Almacen", "Familia"]])
            s_hist_fam = pd.Series(idx_sin_fam.map(mapa_hist_alm_fam), index=df_r.loc[mask_sin_area].index).fillna("")
            df_r.loc[mask_sin_area, "Area_Salida"] = np.where(s_hist_fam.isin(AREAS_OFICIALES), s_hist_fam, "Sin Area")
        else:
            df_r.loc[mask_sin_area, "Area_Salida"] = "Sin Area"
    else:
        df_r.loc[mask_sin_area, "Area_Salida"] = "Sin Area"

    # Paso 4 (Excepción puntual solicitada solo para casos remanentes en "Sin Area"):
    mask_rem = df_r["Area_Salida"] == "Sin Area"
    if mask_rem.any():
        # Determinar el área habitual de artículos de limpieza en cada almacén (fallback "11")
        mapa_limp_alm = {}
        df_ok_l = df_r[df_r["Area_Salida"].isin(AREAS_OFICIALES)]
        if not df_ok_l.empty and "Descripción" in df_ok_l.columns:
            mask_l_desc = df_ok_l["Descripción"].astype(str).str.upper().str.contains("LIMPIEZA|LAVANDINA|DETERGENTE|JABON|PIEDRITAS|PEDRITAS", na=False)
            if mask_l_desc.any():
                mapa_limp_alm = (
                    df_ok_l[mask_l_desc].groupby("Almacen")["Area_Salida"]
                    .agg(lambda s: s.mode().iloc[0] if not s.empty else "11")
                    .to_dict()
                )

        desc_rem = df_r.loc[mask_rem, "Descripción"].fillna("").astype(str).str.upper() if "Descripción" in df_r.columns else pd.Series("", index=df_r.loc[mask_rem].index)
        sku_rem = df_r.loc[mask_rem, "Artículo"].fillna("").astype(str).str.strip()
        alm_rem = df_r.loc[mask_rem, "Almacen"].fillna("501").astype(str).str.strip()

        nuevas_areas = []
        for idx_r, d_txt, s_txt, a_txt in zip(df_r.loc[mask_rem].index, desc_rem, sku_rem, alm_rem):
            if "CONGELAD" in d_txt or "MERLUZA" in d_txt:
                nuevas_areas.append("22")
            elif "LEBERWURST" in d_txt:
                nuevas_areas.append("21")
            elif "VINO" in d_txt or "TINTO DE VERANO" in d_txt or "VEGETALES DESHIDRATADOS" in d_txt or s_txt == "285777":
                nuevas_areas.append("11")
            elif "PEDRITAS SANITARIAS" in d_txt or "PIEDRITAS SANITARIAS" in d_txt or s_txt in {"308410", "300436"}:
                nuevas_areas.append(mapa_limp_alm.get(a_txt, "11"))
            else:
                nuevas_areas.append("Sin Area")
        df_r.loc[mask_rem, "Area_Salida"] = nuevas_areas

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
    """Calcula la casuística SLA por clave compuesta (Almacén, Pedido).
       Prioriza 'Rectificación Almacén' (-10 pts) si el pedido tiene al menos 1 línea con Procedencia 'G'.
    """
    if df_pedidos_eval.empty or df_rect_eval is None or df_rect_eval.empty:
        df_pedidos_eval["Casuistica"] = "Pedido Perfecto"
        return df_pedidos_eval
        
    df_all_r = df_rect_eval.copy()
    df_all_r["Almacen"] = df_all_r["Almacen"].fillna("501").astype(str).str.strip()
    df_all_r["Pedido"] = df_all_r["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    col_proc = "Procedencia" if "Procedencia" in df_all_r.columns else None

    # 1. Identificar pares (Almacén, Pedido) con rectificaciones grabadas por almacén ('G')
    pares_g = set()
    if col_proc:
        df_g = df_all_r[df_all_r[col_proc].astype(str).str.strip().str.upper() == "G"]
        pares_g = set(zip(df_g["Almacen"], df_g["Pedido"]))

    # 2. Filtrar líneas grabadas por tienda ('T') para evaluar casuísticas estándar
    df_v = df_all_r[df_all_r[col_proc].astype(str).str.strip().str.upper() == "T"].copy() if col_proc else df_all_r.copy()
    
    col_mo = "Motivo" if "Motivo" in df_v.columns else None
    df_v["Motivo_Norm"] = df_v[col_mo].astype(str).str.strip().str.upper() if col_mo else "F"
    df_v["Es_Falta"] = df_v["Motivo_Norm"] == "F"
    df_v["Es_Sobra"] = df_v["Motivo_Norm"] == "S"

    mapa_cas_ap = {}
    for (alm, ped), grp in df_v.groupby(["Almacen", "Pedido"]):
        cf = grp["Es_Falta"].sum()
        cs = grp["Es_Sobra"].sum()
        ct = cf + cs
        
        if ct == 0:
            mapa_cas_ap[(alm, ped)] = "Pedido Perfecto"
        elif cf == 0 and cs > 0:
            mapa_cas_ap[(alm, ped)] = "Sobrante Neto"
        elif cs == 0 and cf > 0:
            if cf <= 10:
                mapa_cas_ap[(alm, ped)] = "Faltante Neto"
            else:
                mapa_cas_ap[(alm, ped)] = "Formato no entregado"
        else:
            if ct >= 12 and cf != cs:
                mapa_cas_ap[(alm, ped)] = "Etiquetas Cambiadas"
            elif cf == cs and ct < 12:
                sub_f = set(grp[grp["Es_Falta"]]["Subfamilia"].dropna().unique())
                sub_s = set(grp[grp["Es_Sobra"]]["Subfamilia"].dropna().unique())
                if sub_f and sub_f == sub_s:
                    mapa_cas_ap[(alm, ped)] = "Sustitución Misma Subfamilia"
                else:
                    mapa_cas_ap[(alm, ped)] = "Sustitución Distinta Subfamilia"
            else:
                mapa_cas_ap[(alm, ped)] = "Falta/Sobra"

    # Prioridad absoluta: si el pedido tiene rectificación grabada por Almacén ('G'), se asigna 'Rectificación Almacén'
    for pair_g in pares_g:
        mapa_cas_ap[pair_g] = "Rectificación Almacén"

    idx_eval = pd.MultiIndex.from_arrays([
        df_pedidos_eval["Almacen"].fillna("501").astype(str).str.strip(),
        df_pedidos_eval["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
    ])
    df_pedidos_eval["Casuistica"] = pd.Series(idx_eval.map(mapa_cas_ap), index=df_pedidos_eval.index).fillna("Pedido Perfecto")
    return df_pedidos_eval

def procesar_pedidos_sla(carpeta=".", df_rect=None, mapa_sup=None, mapa_ped_area=None):
    """Combina el histórico protegido cerrado (Jun-Sep) con los meses activos/nuevos cargados por CSV
       y suma el total de líneas solicitadas por pedido desde los archivos BDMVTAL (`Lineas_Pedido`).
    """
    
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

    # 2. Cargar dinámicamente todos los archivos BDMVTAL (presentes y futuros) y contar líneas por pedido
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
    conteos_bdmvtal_lista = []
    df_506_lookup_list = []

    if archivos_bdm_unicos:
        lista_bdm_dfs = []
        for arch in archivos_bdm_unicos:
            print(f"📊 Leyendo archivo de pedidos/ventas BDMVTAL: {arch}")
            try:
                df_t = leer_csv_robusto(arch)
                df_t.columns = df_t.columns.str.strip()

                # Capturar explícitamente la Columna F (índice 5, 0-based) antes de renombrar
                col_f_original = df_t.columns[5] if len(df_t.columns) > 5 else None

                mapa_c = {}
                for idx_c, c in enumerate(df_t.columns):
                    clow = c.lower().replace(".", "").replace("_", " ").strip()
                    if idx_c == 5:
                        mapa_c[c] = "Lineas_Pedido"
                    elif "pedido" in clow: mapa_c[c] = "Pedido"
                    elif "tienda" in clow or "sucursal" in clow or "cod suc des" in clow: mapa_c[c] = "Tienda"
                    elif "almac" in clow or clow == "cd": mapa_c[c] = "Almacen"
                    elif "fech" in clow: mapa_c[c] = "Fecha_DT"
                    elif "gest" in clow or "zona" in clow: mapa_c[c] = "Gestion"
                    elif any(k in clow for k in ["linea", "línea", "cant lin", "q lin", "registros"]) and "Lineas_Pedido" not in mapa_c.values():
                        mapa_c[c] = "Lineas_Pedido"
                    elif any(k in clow for k in ["imp", "monto", "pvp"]): mapa_c[c] = "Importe"

                if "Lineas_Pedido" not in mapa_c.values() and col_f_original:
                    mapa_c[col_f_original] = "Lineas_Pedido"

                df_t = df_t.rename(columns=mapa_c)
                df_t = df_t.loc[:, ~df_t.columns.duplicated()]
                
                df_t["Pedido"] = df_t["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                df_t["Tienda"] = df_t["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                df_t["Almacen"] = df_t["Almacen"].fillna("501").astype(str).str.strip()

                # ⚡ LEER Y SUMAR LA COLUMNA F (CANTIDAD DE LÍNEAS YA AGRUPADA POR PEDIDO EN BDMVTAL)
                if "Lineas_Pedido" in df_t.columns:
                    df_t["Lineas_Pedido"] = pd.to_numeric(
                        df_t["Lineas_Pedido"].astype(str).str.strip().str.replace(",", "."),
                        errors="coerce"
                    ).fillna(0).astype(int)
                else:
                    df_t["Lineas_Pedido"] = 1

                df_t_valid = df_t[~df_t["Pedido"].isin(["", "0", "nan", "None"])]
                if not df_t_valid.empty:
                    vc_ped = df_t_valid.groupby(["Almacen", "Pedido"], as_index=False)["Lineas_Pedido"].sum()
                    conteos_bdmvtal_lista.append(vc_ped)
                    print(f"   -> Sumadas {vc_ped['Lineas_Pedido'].sum():,} líneas (Columna F) en {len(vc_ped):,} pedidos desde {os.path.basename(arch)}.")

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

                # Deduplicar cabecera de pedido antes de evaluar casuísticas SLA
                df_t_ped = df_t.drop_duplicates(subset=["Almacen", "Pedido"]).copy()

                # Almacén 506 (Cross-Docking) se usa como tabla auxiliar de búsqueda y para completar los Pedidos Perfectos de las tiendas en su almacén regional (509/514)
                cols_506_keep = [c for c in ["Almacen", "Tienda", "Pedido", "Lineas_Pedido", "Fecha_DT", "Mes", "Año", "Importe", "Gestion"] if c in df_t_ped.columns]
                if (df_t_ped["Almacen"] == "506").all():
                    df_506_lookup_list.append(df_t_ped[cols_506_keep].copy())
                    continue
                if (df_t_ped["Almacen"] == "506").any():
                    df_506_lookup_list.append(df_t_ped[df_t_ped["Almacen"] == "506"][cols_506_keep].copy())
                    df_t_ped = df_t_ped[df_t_ped["Almacen"] != "506"].copy()

                # Calcular las casuísticas SLA para estos pedidos nuevos usando el detalle de rectificaciones
                if df_rect is not None and not df_rect.empty:
                    df_r_sub = df_rect[df_rect["Pedido"].isin(set(df_t_ped["Pedido"]))].copy()
                    df_t_ped = evaluar_casuisticas_sla_pedidos(df_t_ped, df_r_sub)
                else:
                    df_t_ped["Casuistica"] = "Pedido Perfecto"

                lista_bdm_dfs.append(df_t_ped)
            except Exception as e:
                print(f"   ⚠️ Error en {arch}: {e}")

        if lista_bdm_dfs:
            df_nuevos_meses = pd.concat(lista_bdm_dfs, ignore_index=True).drop_duplicates(subset=["Almacen", "Pedido"])

    # Consolidar diccionario maestro de líneas por pedido desde BDMVTAL (Columna F)
    # Incluye respaldo Cross-Docking (Almacén 506 -> Tienda + Pedido) para pedidos despachados por 506 y rectificados en 509/514
    mapa_lineas_bdmvtal_alm = {}
    mapa_lineas_bdmvtal = {}
    mapa_506_tp_lineas = {}
    mapa_506_p_lineas = {}
    pares_506_reconciliados = set()

    if conteos_bdmvtal_lista:
        df_bd_lineas_alm = pd.concat(conteos_bdmvtal_lista, ignore_index=True).groupby(["Almacen", "Pedido"], as_index=False)["Lineas_Pedido"].sum()
        mapa_lineas_bdmvtal_alm = df_bd_lineas_alm.set_index(["Almacen", "Pedido"])["Lineas_Pedido"].to_dict()
        df_bd_lineas = df_bd_lineas_alm.groupby("Pedido", as_index=False)["Lineas_Pedido"].sum()
        mapa_lineas_bdmvtal = df_bd_lineas.set_index("Pedido")["Lineas_Pedido"].to_dict()

        if df_506_lookup_list:
            df_506_sub = pd.concat(df_506_lookup_list, ignore_index=True)
            mapa_506_tp_lineas = df_506_sub.drop_duplicates(["Tienda", "Pedido"]).set_index(["Tienda", "Pedido"])["Lineas_Pedido"].to_dict()
            mapa_506_p_lineas = df_506_sub.drop_duplicates("Pedido").set_index("Pedido")["Lineas_Pedido"].to_dict()

        # Vincular pedidos de rectificaciones que vinieron sin match directo en su almacén pero sí existen en Cross-Docking 506
        if df_rect is not None and not df_rect.empty and (mapa_506_tp_lineas or mapa_506_p_lineas):
            df_r_unicos = df_rect.drop_duplicates(subset=["Almacen", "Tienda", "Pedido"])
            filas_extra_506 = []
            for _, rr in df_r_unicos.iterrows():
                a_r = str(rr["Almacen"]).strip()
                t_r = str(rr["Tienda"]).strip()
                p_r = str(rr["Pedido"]).strip()
                if (a_r, p_r) not in mapa_lineas_bdmvtal_alm:
                    lin_506 = mapa_506_tp_lineas.get((t_r, p_r), mapa_506_p_lineas.get(p_r, 0))
                    if lin_506 and int(lin_506) > 0:
                        mapa_lineas_bdmvtal_alm[(a_r, p_r)] = int(lin_506)
                        filas_extra_506.append({"Almacen": a_r, "Pedido": p_r, "Lineas_Pedido": int(lin_506)})
                        pares_506_reconciliados.add((t_r, p_r))
            if filas_extra_506:
                df_bd_lineas_alm = pd.concat([df_bd_lineas_alm, pd.DataFrame(filas_extra_506)], ignore_index=True).drop_duplicates(["Almacen", "Pedido"])
                print(f"🔀 Cross-Docking 506: vinculados {len(filas_extra_506):,} pedidos rectificados (509/514) contra BDMVTAL_506.")

        # Guardar caché auxiliar ligero para el tablero (incluyendo Almacen_Key y esquema v3_colF)
        try:
            df_bd_save = df_bd_lineas_alm.rename(columns={"Almacen": "Almacen_Key", "Pedido": "Pedido_Key"}).copy()
            df_bd_save["Esquema_BD"] = "v3_colF"
            df_bd_save.to_parquet("Tablero_Lineas_Pedido_BDMVTAL.parquet", index=False)
            print(f"📏 Guardado Tablero_Lineas_Pedido_BDMVTAL.parquet ({len(df_bd_save):,} registros Almacén-Pedido con Columna F).")
        except Exception:
            pass

    # 3. Fusión Inteligente:
    # Si tenemos meses nuevos (ej. Mes 10, 11, etc.), se reemplazan esos meses específicos
    # manteniendo el histórico de meses cerrados anteriores intacto (Jun-Sep).
    if not df_hist.empty:
        if not df_nuevos_meses.empty and meses_actualizados:
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

    # ⚡ GARANTÍA DE INTEGRIDAD: Incorporar todo pedido rectificado de `df_rect` que no esté en `df_p`
    # (ej. pedidos de Tienda 815 en Sep/Oct/Nov cuyo número corto o almacén no cruzó en BDMVTAL)
    if df_rect is not None and not df_rect.empty:
        pares_en_sla = set(zip(df_p["Almacen"], df_p["Pedido"]))
        df_r_cab = df_rect.drop_duplicates(subset=["Almacen", "Pedido"]).copy()
        df_r_cab["Almacen"] = df_r_cab["Almacen"].fillna("501").astype(str).str.strip()
        df_r_cab["Pedido"] = df_r_cab["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
        df_r_cab["Tienda"] = df_r_cab["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
        mask_faltantes = [
            (a, p) not in pares_en_sla and p not in ["", "0", "nan", "None"]
            for a, p in zip(df_r_cab["Almacen"], df_r_cab["Pedido"])
        ]
        df_r_faltantes = df_r_cab[mask_faltantes].copy()
        if not df_r_faltantes.empty:
            df_r_faltantes = evaluar_casuisticas_sla_pedidos(df_r_faltantes, df_rect)
            if "Fecha de Grabación" in df_r_faltantes.columns:
                dt_f = normalizar_fechas_serie(df_r_faltantes["Fecha de Grabación"])
                df_r_faltantes["Mes"] = dt_f.dt.month.fillna(df_r_faltantes.get("Mes", 0)).astype(int)
                df_r_faltantes["Año"] = dt_f.dt.year.fillna(2026).astype(int)
            else:
                df_r_faltantes["Mes"] = pd.to_numeric(df_r_faltantes.get("Mes", 0), errors="coerce").fillna(0).astype(int)
                df_r_faltantes["Año"] = 2026
            cols_comunes = [c for c in ["Almacen", "Tienda", "Pedido", "Mes", "Año", "Casuistica", "Area_Salida", "Responsable_Tienda"] if c in df_r_faltantes.columns]
            df_p = pd.concat([df_p, df_r_faltantes[cols_comunes]], ignore_index=True)
            print(f"🛡️ Recuperados {len(df_r_faltantes):,} pedidos rectificados (incluyendo Tienda 815 / pedidos cortos) que faltaban en BDMVTAL.")

    # Almacén 506 no se clasifica como almacén propio en SLA, pero sus pedidos perfectos (sin rectificación) se asignan al almacén regional (509/514) de cada tienda
    if (df_p["Almacen"] == "506").any():
        cant_506_excl = int((df_p["Almacen"] == "506").sum())
        df_p = df_p[df_p["Almacen"] != "506"].copy()
        print(f"🚫 Excluidos {cant_506_excl:,} registros directos del Almacén 506 del cálculo SLA.")

    if df_506_lookup_list:
        df_506_all_rows = pd.concat(df_506_lookup_list, ignore_index=True).drop_duplicates(subset=["Tienda", "Pedido"])
        # Almacén regional habitual por Tienda (ej. 509 o 514)
        mapa_tienda_alm_reg = (
            df_p[df_p["Almacen"].isin(["501", "503", "504", "509", "514"])]
            .groupby("Tienda")["Almacen"]
            .agg(lambda s: s.mode().iloc[0] if not s.empty else "509")
            .to_dict()
        )
        pares_tp_exist = set(zip(df_p["Tienda"], df_p["Pedido"]))
        df_506_perf = df_506_all_rows[
            [(t, p) not in pares_tp_exist and p not in ["", "0", "nan", "None"] and t in mapa_tienda_alm_reg
             for t, p in zip(df_506_all_rows["Tienda"], df_506_all_rows["Pedido"])]
        ].copy()
        if not df_506_perf.empty:
            df_506_perf["Almacen"] = df_506_perf["Tienda"].map(mapa_tienda_alm_reg)
            df_506_perf["Casuistica"] = "Pedido Perfecto"
            cols_add_506 = [c for c in df_506_perf.columns if c in df_p.columns or c in ["Almacen", "Tienda", "Pedido", "Lineas_Pedido", "Fecha_DT", "Mes", "Año", "Importe", "Gestion", "Casuistica"]]
            df_p = pd.concat([df_p, df_506_perf[cols_add_506]], ignore_index=True)
            print(f"✅ Incorporados {len(df_506_perf):,} pedidos perfectos de Cross-Docking (BDMVTAL_506) al almacén regional (509/514) de cada tienda.")

    # ⚡ ASIGNACIÓN DE TOTAL DE LÍNEAS POR PEDIDO (Lineas_Pedido)
    if "Lineas_Pedido" not in df_p.columns:
        df_p["Lineas_Pedido"] = 0
    df_p["Lineas_Pedido"] = pd.to_numeric(df_p["Lineas_Pedido"], errors="coerce").fillna(0).astype(int)
    if mapa_lineas_bdmvtal_alm or mapa_lineas_bdmvtal:
        idx_ap = pd.MultiIndex.from_frame(df_p[["Almacen", "Pedido"]])
        lineas_ap = pd.Series(idx_ap.map(mapa_lineas_bdmvtal_alm), index=df_p.index)
        lineas_p = df_p["Pedido"].map(mapa_lineas_bdmvtal)
        lineas_mapeadas = lineas_ap.fillna(lineas_p)
        df_p["Lineas_Pedido"] = np.where(lineas_mapeadas.notna(), lineas_mapeadas.fillna(0).astype(int), df_p["Lineas_Pedido"])
    print(f"📏 Total de líneas pedidas vinculadas en SLA: {df_p['Lineas_Pedido'].sum():,} líneas en {(df_p['Lineas_Pedido'] > 0).sum():,} pedidos.")

    if "Fecha_DT" in df_p.columns:
        dt = normalizar_fechas_serie(df_p["Fecha_DT"])
        df_p["Mes"] = dt.dt.month.fillna(df_p.get("Mes", 0)).astype(int)
        df_p["Año"] = dt.dt.year.fillna(2026).astype(int)

    # Asignar Supervisores
    if mapa_sup:
        df_p["Responsable_Tienda"] = df_p["Tienda"].map(mapa_sup).fillna("Sin Asignar")
    elif "Responsable_Tienda" not in df_p.columns:
        df_p["Responsable_Tienda"] = "Sin Asignar"

    # Asignar Área de Salida oficial a Pedidos por (Almacén, Pedido) desde los CSV (sin match -> "Sin Area")
    if isinstance(mapa_ped_area, tuple):
        mapa_ap, mapa_p = mapa_ped_area
    else:
        mapa_ap, mapa_p = {}, (mapa_ped_area if mapa_ped_area else {})
    idx_p_ap = pd.MultiIndex.from_frame(df_p[["Almacen", "Pedido"]])
    s_p_ap = pd.Series(idx_p_ap.map(mapa_ap), index=df_p.index) if mapa_ap else pd.Series(np.nan, index=df_p.index)
    s_p_only = df_p["Pedido"].map(mapa_p) if mapa_p else pd.Series(np.nan, index=df_p.index)
    df_p["Area_Salida"] = s_p_ap.fillna(s_p_only).fillna("")
    if df_rect is not None and not df_rect.empty:
        df_r_ok = df_rect[df_rect["Area_Salida"].isin(AREAS_OFICIALES)].drop_duplicates(subset=["Almacen", "Pedido"])
        if not df_r_ok.empty:
            mapa_r_ap = df_r_ok.set_index(["Almacen", "Pedido"])["Area_Salida"].to_dict()
            s_r_ap = pd.Series(idx_p_ap.map(mapa_r_ap), index=df_p.index).fillna("")
            mask_s = ~df_p["Area_Salida"].isin(AREAS_OFICIALES)
            df_p.loc[mask_s, "Area_Salida"] = s_r_ap[mask_s]
    mask_invalida = ~df_p["Area_Salida"].isin(AREAS_OFICIALES)
    df_p.loc[mask_invalida, "Area_Salida"] = "Sin Area"

    # Reclasificación prioritaria a 'Rectificación Almacén' (-10 Pts) por clave exacta (Almacén, Pedido) con Procedencia 'G'
    if df_rect is not None and not df_rect.empty and "Procedencia" in df_rect.columns:
        df_g_glob = df_rect[df_rect["Procedencia"].astype(str).str.strip().str.upper() == "G"]
        pares_g_global = set(zip(df_g_glob["Almacen"].astype(str).str.strip(), df_g_glob["Pedido"].astype(str).str.strip()))
        if pares_g_global:
            mask_g = [(a, p) in pares_g_global for a, p in zip(df_p["Almacen"], df_p["Pedido"])]
            df_p.loc[mask_g, "Casuistica"] = "Rectificación Almacén"
            print(f"🏢 Asignados {sum(mask_g):,} pedidos con 'Rectificación Almacén' (Procedencia 'G', 0.0 Pts)")

    # Aplicación de Puntos SLA (incluye Sobrante Neto = 9.0 pts)
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
        ("3. Anulaciones Detalle", "Tablero_Anulaciones_Detalle.parquet"),
        ("4. Líneas por Pedido (BDMVTAL)", "Tablero_Lineas_Pedido_BDMVTAL.parquet")
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
