# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import numpy as np

st.set_page_config(page_title="Tablero Satisfacción - SLA Tiendas", layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.markdown("""
<style>
    div[data-testid="stTable"] th, div[data-testid="stDataFrame"] th {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        text-align: center !important;
        vertical-align: middle !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# MÓDULO DE AUTENTICACIÓN (LOGIN)
# ==============================================================================
USUARIO_CORRECTO = "Tiendas_SLA"
PASSWORD_CORRECTO = "SLA1234"

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

def login():
    st.markdown("### 🔐 Acceso al Tablero SLA y Satisfacción de Tienda")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            st.subheader("Iniciar Sesión")
            usuario_input = st.text_input("Usuario", key="login_usr")
            password_input = st.text_input("Contraseña", type="password", key="login_pwd")
            submit_button = st.form_submit_button("Ingresar 🚀")

            if submit_button:
                if usuario_input.strip() == USUARIO_CORRECTO and password_input.strip() == PASSWORD_CORRECTO:
                    st.session_state["autenticado"] = True
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("⚠️ Usuario o contraseña incorrectos")

if not st.session_state["autenticado"]:
    login()
    st.stop()

st.sidebar.button("🔒 Cerrar Sesión", on_click=lambda: st.session_state.update({"autenticado": False}))

# ==============================================================================
# APLICACIÓN PRINCIPAL
# ==============================================================================
st.title("📦 Tablero SLA y Satisfacción de Tienda")

def corregir_encoding_texto(texto):
    if pd.isna(texto):
        return texto
    s = str(texto)
    try:
        return s.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s

def normalizar_fechas_a_mes(serie_fechas):
    if serie_fechas is None or serie_fechas.empty:
        return pd.Series(0, index=serie_fechas.index if serie_fechas is not None else [], dtype=int)
    
    s_clean = serie_fechas.astype(str).str.strip().str.replace(".0", "", regex=False)
    
    # 1. Probar formato estándar DD/MM/YYYY
    dt1 = pd.to_datetime(s_clean, format="%d/%m/%Y", errors="coerce")
    
    # 2. Probar formato DD/MM/YY (ej: 19/10/26 -> Octubre)
    dt2 = pd.to_datetime(s_clean, format="%d/%m/%y", errors="coerce")
    
    # 3. Formato compacto YYYYMMDD o ISO
    dt3 = pd.to_datetime(s_clean, format="%Y%m%d", errors="coerce")
    dt4 = pd.to_datetime(s_clean, format="%Y-%m-%d", errors="coerce")
    
    # 4. Formato serial numérico de Excel
    s_num = pd.to_numeric(s_clean.str.replace(",", "."), errors="coerce")
    mask_ex = s_num.notna() & (s_num > 30000) & (s_num < 70000)
    dt_ex = pd.Series(pd.NaT, index=serie_fechas.index, dtype='datetime64[ns]')
    if mask_ex.any():
        dt_ex[mask_ex] = pd.to_datetime(s_num[mask_ex], unit="D", origin="1899-12-30", errors="coerce")
        
    dt_final = dt1.fillna(dt2).fillna(dt3).fillna(dt4).fillna(dt_ex)
    meses = dt_final.dt.month.fillna(0).astype(int)
    
    # Respaldo textual
    mask_cero = (meses == 0)
    if mask_cero.any():
        partes = s_clean[mask_cero].str.split(r"[/.-]", expand=True)
        if partes.shape[1] >= 2:
            mes_candidato = pd.to_numeric(partes[1], errors="coerce").fillna(0).astype(int)
            valido = (mes_candidato >= 1) & (mes_candidato <= 12)
            for idx_m in partes[valido].index:
                meses.at[idx_m] = int(mes_candidato.at[idx_m])
                
    return meses

@st.cache_data
def cargar_datos_sla():
    if os.path.exists("Tablero_SLA_Pedidos.parquet"):
        df_sla = pd.read_parquet("Tablero_SLA_Pedidos.parquet")
        df_rect = pd.read_parquet("Tablero_Rectificaciones_Detalle.parquet") if os.path.exists("Tablero_Rectificaciones_Detalle.parquet") else pd.DataFrame()
        
        if "Almacen" not in df_sla.columns:
            col_alm = [c for c in df_sla.columns if any(k in c.lower() for k in ["almacen", "almacén", "cd", "cod_almacen"])]
            df_sla["Almacen"] = df_sla[col_alm[0]].astype(str).str.strip() if col_alm else "501"
            
        if "Tienda" not in df_sla.columns:
            col_t = [c for c in df_sla.columns if any(k in c.lower() for k in ["tienda", "sucursal", "cod_suc_des"])]
            df_sla["Tienda"] = df_sla[col_t[0]].astype(str).str.strip() if col_t else "Sin Tienda"

        if "Gestion" not in df_sla.columns:
            col_g = [c for c in df_sla.columns if any(k in c.lower() for k in ["gestion", "gestión", "zona"])]
            df_sla["Gestion"] = df_sla[col_g[0]].astype(str).str.strip() if col_g else "Sin Clasificar"
        
        df_sla["Gestion"] = df_sla["Gestion"].fillna("Sin Clasificar").astype(str).str.strip()
        df_sla["Gestion"] = df_sla["Gestion"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Clasificar")

        if "Responsable_Tienda" not in df_sla.columns:
            df_sla["Responsable_Tienda"] = "Sin Asignar"
        else:
            df_sla["Responsable_Tienda"] = df_sla["Responsable_Tienda"].apply(corregir_encoding_texto)
            df_sla["Responsable_Tienda"] = df_sla["Responsable_Tienda"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Asignar")

        # ⚡ CARGA Y CRUCE DINÁMICO DE SUPERVISORES / FRANQUICIADOS
        necesita_supervisores = ("Responsable_Tienda" not in df_sla.columns) or (df_sla["Responsable_Tienda"].isin(["Sin Asignar", "nan", ""]).all())
        if necesita_supervisores and "Tienda" in df_sla.columns:
            import glob
            pats_sup = [
                "*[Ss][Uu][Pp][Ee][Rr][Vv][Ii][Ss][Ii]*.xlsx", "*[Ss][Uu][Pp][Ee][Rr][Vv][Ii][Ss][Ii]*.csv",
                "*[Zz][Oo][Nn][Aa]*.xlsx", "*[Zz][Oo][Nn][Aa]*.csv",
                os.path.join("Datos_mensuales", "*[Ss][Uu][Pp][Ee][Rr][Vv][Ii][Ss][Ii]*.xlsx"),
                os.path.join("Datos_mensuales", "*[Ss][Uu][Pp][Ee][Rr][Vv][Ii][Ss][Ii]*.csv"),
                os.path.join("Datos_mensuales", "*[Zz][Oo][Nn][Aa]*.xlsx"),
                os.path.join("Datos_mensuales", "*[Zz][Oo][Nn][Aa]*.csv")
            ]
            f_sup_list = []
            for p in pats_sup:
                f_sup_list.extend(glob.glob(p))
            f_sup_list = sorted(list(set(f_sup_list)))
            if f_sup_list:
                try:
                    f_s = f_sup_list[0]
                    if f_s.endswith(".xlsx") or f_s.endswith(".xls"):
                        xls_s = pd.ExcelFile(f_s)
                        df_s_temp = pd.read_excel(xls_s, sheet_name=xls_s.sheet_names[0], dtype=str)
                    else:
                        try:
                            df_s_temp = pd.read_csv(f_s, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
                        except Exception:
                            df_s_temp = pd.read_csv(f_s, sep=";", encoding="latin1", dtype=str, on_bad_lines="skip")
                    
                    df_s_temp.columns = df_s_temp.columns.str.strip()
                    def b_col(claves):
                        for col_name in df_s_temp.columns:
                            cn = col_name.lower().replace(".", "").replace("_", " ").strip()
                            if any(k in cn for k in claves): return col_name
                        return None
                    
                    c_tienda = b_col(["tienda", "sucursal", "cod suc", "nro tienda", "numero tienda", "id tienda", "codigo"]) or df_s_temp.columns[0]
                    c_resp = b_col(["supervisor", "franquiciado", "responsable", "encargado", "franquicia", "nombre", "supervisor zona", "zona"]) or (df_s_temp.columns[1] if len(df_s_temp.columns) > 1 else df_s_temp.columns[0])
                    
                    df_s_temp["T_Key"] = df_s_temp[c_tienda].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                    df_s_temp["Resp_Clean"] = df_s_temp[c_resp].apply(corregir_encoding_texto).astype(str).str.strip()
                    mapa_supervisores = df_s_temp.drop_duplicates(subset=["T_Key"]).set_index("T_Key")["Resp_Clean"].to_dict()
                    
                    df_sla["T_Key"] = df_sla["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                    df_sla["Responsable_Tienda"] = df_sla["T_Key"].map(mapa_supervisores).fillna("Sin Asignar")
                    df_sla.drop(columns=["T_Key"], inplace=True, errors="ignore")
                    
                    if not df_rect.empty and "Tienda" in df_rect.columns:
                        df_rect["T_Key"] = df_rect["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                        df_rect["Responsable_Tienda"] = df_rect["T_Key"].map(mapa_supervisores).fillna("Sin Asignar")
                        df_rect.drop(columns=["T_Key"], inplace=True, errors="ignore")
                except Exception:
                    pass

        if "Area_Salida" not in df_sla.columns:
            df_sla["Area_Salida"] = "Sin Clasificar"
        else:
            df_sla["Area_Salida"] = df_sla["Area_Salida"].fillna("Sin Clasificar").astype(str).str.strip()
            df_sla["Area_Salida"] = df_sla["Area_Salida"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Clasificar")

        if "Año" not in df_sla.columns:
            df_sla["Año"] = 2026
            
        if "Mes" not in df_sla.columns:
            if "Fecha_DT" in df_sla.columns:
                df_sla["Mes"] = pd.to_datetime(df_sla["Fecha_DT"]).dt.month.fillna(0).astype(int)
            else:
                df_sla["Mes"] = 0

        if not df_rect.empty:
            col_est_raw = "Estado_Clean" if "Estado_Clean" in df_rect.columns else ("Estado" if "Estado" in df_rect.columns else None)
            if col_est_raw:
                df_rect["Estado"] = df_rect[col_est_raw].astype(str).str.strip().str.upper()
            else:
                df_rect["Estado"] = "M"

            if "Monto_Rectif" not in df_rect.columns:
                col_m = None
                for c in ["Imp.tien.PVP S/IVA mon.BD", "Monto", "Importe"]:
                    if c in df_rect.columns:
                        col_m = c
                        break
                if col_m:
                    df_rect["Monto_Rectif"] = pd.to_numeric(df_rect[col_m].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
                else:
                    df_rect["Monto_Rectif"] = 0.0

            if "Area_Salida" not in df_rect.columns or df_rect["Area_Salida"].isna().any():
                if "Area_Salida" in df_sla.columns and "Pedido" in df_rect.columns:
                    mapa_area_p = df_sla[["Pedido", "Area_Salida"]].drop_duplicates().set_index("Pedido")["Area_Salida"].to_dict()
                    df_rect["Area_Salida"] = df_rect["Pedido"].map(mapa_area_p).fillna("Sin Clasificar")
                else:
                    df_rect["Area_Salida"] = "Sin Clasificar"
            
            df_rect["Area_Salida"] = df_rect["Area_Salida"].fillna("Sin Clasificar").astype(str).str.strip()
            df_rect["Area_Salida"] = df_rect["Area_Salida"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Clasificar")

            if "Tienda" in df_rect.columns and "Tienda" in df_sla.columns:
                if "Responsable_Tienda" in df_sla.columns:
                    mapa_resp = df_sla[["Tienda", "Responsable_Tienda"]].drop_duplicates().set_index("Tienda")["Responsable_Tienda"].to_dict()
                    df_rect["Responsable_Tienda"] = df_rect["Tienda"].map(mapa_resp).fillna("Sin Asignar")
                    df_rect["Responsable_Tienda"] = df_rect["Responsable_Tienda"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Asignar")

                if "Almacen" in df_sla.columns and "Almacen" not in df_rect.columns:
                    mapa_alm = df_sla[["Tienda", "Almacen"]].drop_duplicates().set_index("Tienda")["Almacen"].to_dict()
                    df_rect["Almacen"] = df_rect["Tienda"].map(mapa_alm).fillna("501")

                if "Gestion" in df_sla.columns:
                    mapa_gest = df_sla[["Tienda", "Gestion"]].drop_duplicates().set_index("Tienda")["Gestion"].to_dict()
                    df_rect["Gestion"] = df_rect["Tienda"].map(mapa_gest).fillna("Sin Clasificar")
                    df_rect["Gestion"] = df_rect["Gestion"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Clasificar")

            # ⚡ ENRIQUECIMIENTO EN CALIENTE SI UxB O BULFM NO VIENEN EN EL PARQUET
            necesita_maestro = ("UxB" not in df_rect.columns) or (pd.to_numeric(df_rect.get("UxB", 1.0), errors="coerce").fillna(1.0) > 1.0).sum() == 0
            if necesita_maestro and "Artículo" in df_rect.columns:
                import glob
                m_archivos = glob.glob("*[Mm]aestro*.csv") + glob.glob(os.path.join("Datos_mensuales", "*[Mm]aestro*.csv"))
                if m_archivos:
                    try:
                        df_m_app = pd.read_csv(m_archivos[0], sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
                        df_m_app.columns = df_m_app.columns.str.strip().str.upper()
                        col_s = next((c for c in df_m_app.columns if any(k in c for k in ["ARTICULO", "ARTÍCULO", "SKU", "COD_ART"])), None)
                        col_u = next((c for c in df_m_app.columns if "UXB" in c or "BULTO" in c or "CAJA" in c), None)
                        col_b = next((c for c in df_m_app.columns if "BULFM" in c or "BXM" in c or "MASTER" in c), None)
                        if col_s:
                            df_m_app["Art_Key"] = df_m_app[col_s].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                            df_rect["Art_Key"] = df_rect["Artículo"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0").replace("", "0")
                            if col_u:
                                m_uxb = df_m_app.set_index("Art_Key")[col_u].to_dict()
                                df_rect["UxB"] = pd.to_numeric(df_rect["Art_Key"].map(m_uxb).astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
                            if col_b:
                                m_bxm = df_m_app.set_index("Art_Key")[col_b].to_dict()
                                df_rect["BULFM"] = pd.to_numeric(df_rect["Art_Key"].map(m_bxm).astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
                            df_rect.drop(columns=["Art_Key"], inplace=True, errors="ignore")
                    except Exception:
                        pass

            # Asegurar tipos y cálculo de unidades / master
            col_u_raw = next((c for c in ["Unid/Kgs grabados", "Unidades_Num", "Cantidad", "Cant"] if c in df_rect.columns), None)
            if col_u_raw:
                df_rect["Unidades_Num"] = pd.to_numeric(df_rect[col_u_raw].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
            else:
                df_rect["Unidades_Num"] = 1.0

            df_rect["UxB"] = pd.to_numeric(df_rect.get("UxB", 1.0), errors="coerce").fillna(1.0)
            df_rect["BULFM"] = pd.to_numeric(df_rect.get("BULFM", 1.0), errors="coerce").fillna(1.0)
            df_rect["UxM"] = df_rect["UxB"] * df_rect["BULFM"]
            df_rect["Es_Master"] = np.where(pd.to_numeric(df_rect.get("BULFM", 0), errors="coerce").fillna(0).astype(int) == 1, "Sí", "No")
            df_rect["Es_Unidad_Suelta"] = (df_rect["UxB"] > 1.0) & (df_rect["Unidades_Num"] > 0.0) & (df_rect["Unidades_Num"] < df_rect["UxB"])

        return df_sla, df_rect
    return pd.DataFrame(), pd.DataFrame()


def cargar_datos_anulaciones(_df_sla=None, _df_rect=None):
    df_a = pd.DataFrame()
    archivos_csv = [f for f in os.listdir(".") if ("anula" in f.lower() or "causa" in f.lower()) and f.endswith(".csv")]
    if not archivos_csv and os.path.exists("Datos_mensuales"):
        archivos_csv = [os.path.join("Datos_mensuales", f) for f in os.listdir("Datos_mensuales") if ("anula" in f.lower() or "causa" in f.lower()) and f.endswith(".csv")]

    parquet_file = "Tablero_Anulaciones_Detalle.parquet"
    leer_desde_csv = False
    if archivos_csv:
        if not os.path.exists(parquet_file):
            leer_desde_csv = True
        else:
            mtime_csv = os.path.getmtime(archivos_csv[0])
            mtime_parquet = os.path.getmtime(parquet_file)
            if mtime_csv > mtime_parquet:
                leer_desde_csv = True

    if leer_desde_csv:
        try:
            archivo_seleccionado = archivos_csv[0]
            df_a = pd.read_csv(archivo_seleccionado, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
            df_a.columns = df_a.columns.str.strip()
            
            mapa = {}
            for c in df_a.columns:
                clow = c.lower()
                if "almac" in clow: mapa[c] = "Almacen"
                elif "tienda" in clow or "sucursal" in clow: mapa[c] = "Tienda"
                elif "pedido" in clow: mapa[c] = "Pedido"
                elif "nota" in clow or "nro" in clow: mapa[c] = "Nota_Nro"
                elif "fch. modif" in clow or "fch_modif" in clow or "fecha modif" in clow: mapa[c] = "Fecha_Modif"
                elif "fech" in clow and "modif" not in clow: mapa[c] = "Fecha"
                elif "tipo" in clow or "motivo_rect" in clow: mapa[c] = "Tipo"
                elif "cnt" in clow or "blt" in clow or "bulto" in clow or "cant" in clow: mapa[c] = "Cant_Blt"
                elif "imp" in clow or "monto" in clow or "importe" in clow: mapa[c] = "Monto"
                elif "estado rp" in clow: mapa[c] = "Estado_RP"
                elif "estado" in clow: mapa[c] = "Estado"
                elif "motivo" in clow or "causa" in clow: mapa[c] = "Causa_Anulacion"
                elif "lote" in clow or "rpa" in clow: mapa[c] = "Lote_RPA"

            df_a = df_a.rename(columns=mapa)
            
            # Limpiar filas vacías del final para evitar valores flotantes/nulos que rompen los filtros
            df_a = df_a.dropna(how="all")
            if "Pedido" in df_a.columns:
                df_a = df_a[df_a["Pedido"].notna() & (df_a["Pedido"].astype(str).str.strip().isin(["", "nan", "None"]) == False)]
                df_a["Pedido"] = df_a["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
            
            if "Tienda" in df_a.columns:
                df_a["Tienda"] = df_a["Tienda"].fillna("").astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
            if "Almacen" in df_a.columns:
                df_a["Almacen"] = df_a["Almacen"].fillna("501").astype(str).str.strip()
            if "Monto" in df_a.columns:
                df_a["Monto"] = pd.to_numeric(df_a["Monto"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
            if "Cant_Blt" in df_a.columns:
                df_a["Cant_Blt"] = pd.to_numeric(df_a["Cant_Blt"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
            
            col_f = "Fecha" if "Fecha" in df_a.columns else ("Fecha_Modif" if "Fecha_Modif" in df_a.columns else None)
            if col_f:
                df_a["Mes_Num"] = normalizar_fechas_a_mes(df_a[col_f])
                mapa_m = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                          7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
                df_a["Nombre_Mes"] = df_a["Mes_Num"].map(mapa_m).fillna("Sin Mes")

            try:
                df_a.to_parquet(parquet_file, index=False)
            except Exception:
                pass
        except Exception as e:
            if os.path.exists(parquet_file):
                df_a = pd.read_parquet(parquet_file)
    elif os.path.exists(parquet_file):
        df_a = pd.read_parquet(parquet_file)

    if not df_a.empty and "Pedido" in df_a.columns:
        # Asegurar descarte de filas vacías
        df_a = df_a.dropna(how="all")
        df_a = df_a[df_a["Pedido"].notna() & (df_a["Pedido"].astype(str).str.strip().isin(["", "nan", "None"]) == False)]

        mapa_area = {}
        import glob
        archivos_area = glob.glob("*[Aa]rea*[Ss]alida*.csv") + glob.glob(os.path.join("Datos_mensuales", "*[Aa]rea*[Ss]alida*.csv"))
        
        for fa in set(archivos_area):
            try:
                df_area_temp = pd.read_csv(fa, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
                df_area_temp.columns = df_area_temp.columns.str.strip().str.upper()
                cols_p = [c for c in df_area_temp.columns if any(k in c for k in ["PEDIDO", "Nº DE PEDIDO", "Nº PEDIDO", "NRO_PEDIDO"])]
                cols_a = [c for c in df_area_temp.columns if any(k in c for k in ["AREA", "ÁREA", "SALIDA", "DESCRIPCION", "SECTOR"])]

                if cols_p and cols_a:
                    col_p, col_a = cols_p[0], cols_a[0]
                    df_area_temp["Ped_Clean"] = df_area_temp[col_p].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
                    df_area_temp["Area_Clean"] = df_area_temp[col_a].astype(str).str.strip()
                    df_val = df_area_temp[(df_area_temp["Ped_Clean"] != "") & (~df_area_temp["Area_Clean"].isin(["", "nan", "None", "0"]))]
                    if not df_val.empty:
                        mapa_area.update(df_val.set_index("Ped_Clean")["Area_Clean"].to_dict())
            except Exception as e:
                pass

        if _df_sla is not None and not _df_sla.empty and "Pedido" in _df_sla.columns and "Area_Salida" in _df_sla.columns:
            for k, v in _df_sla.set_index("Pedido")["Area_Salida"].to_dict().items():
                if k not in mapa_area or mapa_area[k] == "Sin Clasificar":
                    mapa_area[k] = v

        if _df_rect is not None and not _df_rect.empty and "Pedido" in _df_rect.columns and "Area_Salida" in _df_rect.columns:
            df_r_valid = _df_rect[_df_rect["Area_Salida"] != "Sin Clasificar"]
            if not df_r_valid.empty:
                for k, v in df_r_valid.set_index("Pedido")["Area_Salida"].to_dict().items():
                    if k not in mapa_area or mapa_area[k] == "Sin Clasificar":
                        mapa_area[k] = v

        if mapa_area:
            df_a["Area_Salida"] = df_a["Pedido"].map(mapa_area).fillna("Sin Clasificar")
        elif "Area_Salida" not in df_a.columns:
            df_a["Area_Salida"] = "Sin Clasificar"

        df_a["Area_Salida"] = df_a["Area_Salida"].replace(["", "nan", "None", "-"], "Sin Clasificar")

    return df_a

@st.cache_data(show_spinner=False)
def procesar_analisis_sustituciones_cache(_df_sla, _df_rect):
    if _df_sla.empty or _df_rect.empty:
        return pd.DataFrame()

    df_sust_cas = _df_sla[_df_sla["Casuistica"].isin(["Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia"])].copy()
    if df_sust_cas.empty:
        return pd.DataFrame()

    mapa_cas_pedido = df_sust_cas.set_index("Pedido")["Casuistica"].to_dict()
    pedidos_sust_todos = set(df_sust_cas["Pedido"].dropna().unique())

    df_r_sust = _df_rect[
        (_df_rect["Pedido"].isin(pedidos_sust_todos)) & 
        (_df_rect["Procedencia"].astype(str).str.strip().str.upper() == "T")
    ].copy()
    
    if df_r_sust.empty:
        return pd.DataFrame()

    col_motivo_s = "Motivo_Clean" if "Motivo_Clean" in df_r_sust.columns else ("Motivo" if "Motivo" in df_r_sust.columns else None)
    df_r_sust["Motivo_Norm"] = df_r_sust[col_motivo_s].astype(str).str.strip().str.upper() if col_motivo_s else "F"
    df_r_sust["Estado_Norm"] = df_r_sust["Estado"].astype(str).str.strip().str.upper() if "Estado" in df_r_sust.columns else "M"

    col_art_lbl = "Artículo" if "Artículo" in df_r_sust.columns else ("SKU" if "SKU" in df_r_sust.columns else "Producto")
    col_desc_lbl = "Descripción" if "Descripción" in df_r_sust.columns else "Producto"

    filas_comparativas = []
    for ped, grp in df_r_sust.groupby("Pedido"):
        casuistica_ped = mapa_cas_pedido.get(ped, "Sustitución")
        f_items = grp[grp["Motivo_Norm"] == "F"].sort_values(by="Monto_Rectif", ascending=False).reset_index(drop=True)
        s_items = grp[grp["Motivo_Norm"] == "S"].sort_values(by="Monto_Rectif", ascending=False).reset_index(drop=True)

        if not f_items.empty and not s_items.empty:
            tienda_val = grp["Tienda"].iloc[0] if "Tienda" in grp.columns else "—"
            almacen_val = grp["Almacen"].iloc[0] if "Almacen" in grp.columns else "501"
            area_salida_val = grp["Area_Salida"].iloc[0] if "Area_Salida" in grp.columns else "Sin Clasificar"

            max_pairs = max(len(f_items), len(s_items))
            for i in range(max_pairs):
                if i < len(f_items):
                    row_f = f_items.iloc[i]
                    sku_f = str(row_f[col_art_lbl])
                    desc_f = str(row_f[col_desc_lbl]) if col_desc_lbl in row_f else sku_f
                    monto_f = float(row_f["Monto_Rectif"])
                    est_f = str(row_f["Estado_Norm"])
                else:
                    sku_f, desc_f, monto_f, est_f = "—", "—", 0.0, "—"

                if i < len(s_items):
                    row_s = s_items.iloc[i]
                    sku_s = str(row_s[col_art_lbl])
                    desc_s = str(row_s[col_desc_lbl]) if col_desc_lbl in row_s else sku_s
                    monto_s = float(row_s["Monto_Rectif"])
                    est_s = str(row_s["Estado_Norm"])
                else:
                    sku_s, desc_s, monto_s, est_s = "—", "—", 0.0, "—"

                dif_neto = monto_f - monto_s
                monto_conf = (monto_f if est_f == "M" else 0.0) - (monto_s if est_s == "M" else 0.0)

                filas_comparativas.append({
                    "Almacén": almacen_val,
                    "Tienda": tienda_val,
                    "Pedido": ped,
                    "Tipo Sustitución": casuistica_ped,
                    "Área de Salida": area_salida_val,
                    "SKU Faltante": sku_f,
                    "Producto Faltante": desc_f,
                    "Monto Faltante ($)": monto_f,
                    "Estado Falta": est_f,
                    "SKU Sobrante": sku_s,
                    "Producto Sobrante": desc_s,
                    "Monto Sobrante ($)": monto_s,
                    "Estado Sobra": est_s,
                    "Diferencia Monto Neto ($)": dif_neto,
                    "Diferencia Neta Confirmada ($)": monto_conf
                })

    return pd.DataFrame(filas_comparativas)

try:
    df_sla, df_rect = cargar_datos_sla()
    df_anul = cargar_datos_anulaciones(df_sla, df_rect)

    if not df_sla.empty:
        st.sidebar.header("🔍 Filtros de Búsqueda")

        def reset_todos_los_filtros():
            keys_a_limpiar = [
                "sb_alm", "sb_gest", "sb_resp", "sb_tienda", "sb_area", "sb_cas",
                "sb_est", "sb_fam", "sb_subfam", "sb_anio", "sb_mes",
                "h6_flt_alm", "h6_flt_causa_anul", "h6_flt_causa_aprob", "h6_flt_tienda", "h6_flt_motivo", "txt_ped_portal"
            ]
            for k in keys_a_limpiar:
                if k in st.session_state:
                    del st.session_state[k]

        st.sidebar.button("🔄 Restablecer Filtros (Ver Todo)", on_click=reset_todos_los_filtros, use_container_width=True, help="Limpia todos los filtros activos y vuelve a incluir el 100% de los datos")

        # 1. FILTRO DE ALMACÉN
        if "Almacen" in df_sla.columns:
            almacenes = sorted([str(x) for x in df_sla["Almacen"].dropna().unique()])
            almacen_sel = st.sidebar.multiselect(
                "🏭 Almacén",
                options=almacenes,
                default=[],
                key="sb_alm",
                placeholder="Todos los Almacenes",
                help="Selecciona uno o varios almacenes. Si no seleccionas ninguno, se consideran todos."
            )
            if almacen_sel:
                df_sla = df_sla[df_sla["Almacen"].astype(str).isin(almacen_sel)]
                if not df_rect.empty and "Almacen" in df_rect.columns:
                    df_rect = df_rect[df_rect["Almacen"].astype(str).isin(almacen_sel)]

        # 2. FILTRO DE GESTIÓN / ZONA
        if "Gestion" in df_sla.columns and df_sla["Gestion"].notna().any():
            gestiones = sorted([str(x) for x in df_sla["Gestion"].dropna().unique() if str(x) != "nan"])
            gestion_sel = st.sidebar.multiselect(
                "🗺️ Gestión / Zona",
                options=gestiones,
                default=[],
                key="sb_gest",
                placeholder="Todas las Gestiones / Zonas",
                help="Selecciona una o varias gestiones. Si está vacío, se muestran todas."
            )
            if gestion_sel:
                df_sla = df_sla[df_sla["Gestion"].astype(str).isin(gestion_sel)]
                if not df_rect.empty and "Gestion" in df_rect.columns:
                    df_rect = df_rect[df_rect["Gestion"].astype(str).isin(gestion_sel)]

        # 3. FILTRO DE FRANQUICIADO / SUPERVISOR
        if "Responsable_Tienda" in df_sla.columns and df_sla["Responsable_Tienda"].notna().any():
            responsables = sorted([str(x) for x in df_sla["Responsable_Tienda"].dropna().unique() if str(x) not in ["nan", "Sin Asignar"]])
            resp_sel = st.sidebar.multiselect(
                "👤 Franquiciado / Supervisor",
                options=responsables,
                default=[],
                key="sb_resp",
                placeholder="Todos los Supervisores",
                help="Escribe para buscar franquiciados/supervisores. Si está vacío, se incluyen todos."
            )
            if resp_sel:
                df_sla = df_sla[df_sla["Responsable_Tienda"].astype(str).isin(resp_sel)]
                if not df_rect.empty and "Responsable_Tienda" in df_rect.columns:
                    df_rect = df_rect[df_rect["Responsable_Tienda"].astype(str).isin(resp_sel)]

        # 4. FILTRO DE TIENDA
        if "Tienda" in df_sla.columns:
            tiendas = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) not in ["nan", "Sin Tienda"]])
            tienda_sel = st.sidebar.multiselect(
                "🏪 Tienda / Sucursal",
                options=tiendas,
                default=[],
                key="sb_tienda",
                placeholder="Todas las Tiendas",
                help="Escribe el número o código de tienda para buscar. Si está vacío, se incluyen todas."
            )
            if tienda_sel:
                df_sla = df_sla[df_sla["Tienda"].astype(str).isin(tienda_sel)]
                if not df_rect.empty and "Tienda" in df_rect.columns:
                    df_rect = df_rect[df_rect["Tienda"].astype(str).isin(tienda_sel)]

        # 5. FILTRO DE ÁREA DE SALIDA
        areas_sla = set(df_sla["Area_Salida"].dropna().astype(str).unique()) if "Area_Salida" in df_sla.columns else set()
        areas_rect = set(df_rect["Area_Salida"].dropna().astype(str).unique()) if not df_rect.empty and "Area_Salida" in df_rect.columns else set()
        areas_universo = areas_sla.union(areas_rect)
        areas_disponibles = sorted([a for a in areas_universo if a.strip() not in ["19", "24", "nan", "Sin Clasificar"]])

        if areas_disponibles:
            area_sel = st.sidebar.multiselect(
                "📦 Área de Salida",
                options=areas_disponibles,
                default=[],
                key="sb_area",
                placeholder="Todas las Áreas de Salida",
                help="Filtra por sector o área de salida."
            )
            if area_sel:
                if "Area_Salida" in df_sla.columns:
                    df_sla = df_sla[df_sla["Area_Salida"].astype(str).isin(area_sel)]
                if not df_rect.empty and "Area_Salida" in df_rect.columns:
                    df_rect = df_rect[df_rect["Area_Salida"].astype(str).isin(area_sel)]

        # 6. FILTRO DE CASUÍSTICA
        if "Casuistica" in df_sla.columns:
            orden_cas_filtro = [
                "Pedido Perfecto", "Sobrante Neto",
                "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia",
                "Falta/Sobra", "Faltante Neto", "Formato no entregado", "Error facturación master",
                "Etiquetas Cambiadas", "Rectificación Almacén"
            ]
            casuisticas_presentes = [c for c in orden_cas_filtro if c in df_sla["Casuistica"].dropna().unique()]
            otras_cas = [c for c in df_sla["Casuistica"].dropna().unique() if c not in casuisticas_presentes]
            casuisticas_opciones = casuisticas_presentes + otras_cas

            casuistica_sel = st.sidebar.multiselect(
                "📋 Casuística / Estado Pedido",
                options=casuisticas_opciones,
                default=[],
                key="sb_cas",
                placeholder="Todas las Casuísticas",
                help="Selecciona casuísticas específicas de SLA."
            )
            if casuistica_sel:
                df_sla = df_sla[df_sla["Casuistica"].isin(casuistica_sel)]
                if not df_rect.empty:
                    pedidos_validos_cas = set(df_sla["Pedido"].dropna().unique())
                    df_rect = df_rect[df_rect["Pedido"].isin(pedidos_validos_cas)]

        # 7. FILTRO DE ESTADO DE RECTIFICACIÓN (M / P / R)
        if not df_rect.empty and "Estado" in df_rect.columns:
            estados_opciones = sorted([str(x) for x in df_rect["Estado"].dropna().unique() if str(x) != "nan"])
            mapa_nombres_est = {"M": "M (Confirmada)", "P": "P (Pendiente)", "R": "R (Rechazada)"}
            opciones_est_labels = [mapa_nombres_est.get(e, e) for e in estados_opciones]
            mapa_label_a_val = {mapa_nombres_est.get(e, e): e for e in estados_opciones}

            estado_sel_labels = st.sidebar.multiselect(
                "📋 Estado Rectificación (M/P/R)",
                options=opciones_est_labels,
                default=[],
                key="sb_est",
                placeholder="Todos los Estados (M/P/R)",
                help="Filtra por estado de rectificación: M (Confirmada), P (Pendiente), R (Rechazada)."
            )
            if estado_sel_labels:
                estados_elegidos = [mapa_label_a_val[lbl] for lbl in estado_sel_labels]
                df_rect = df_rect[df_rect["Estado"].isin(estados_elegidos)]

        # 8. FILTROS DEL MAESTRO
        if not df_rect.empty:
            familias = sorted([str(x) for x in df_rect["Familia"].dropna().unique() if str(x) != "nan"]) if "Familia" in df_rect.columns and df_rect["Familia"].notna().any() else []
            subfamilias = sorted([str(x) for x in df_rect["Subfamilia"].dropna().unique() if str(x) != "nan"]) if "Subfamilia" in df_rect.columns and df_rect["Subfamilia"].notna().any() else []

            if familias:
                fam_sel = st.sidebar.multiselect(
                    "🏷️ Familia",
                    options=familias,
                    default=[],
                    key="sb_fam",
                    placeholder="Todas las Familias"
                )
                if fam_sel:
                    df_rect = df_rect[df_rect["Familia"].astype(str).isin(fam_sel)]
                    pedidos_filtrados_maestro = set(df_rect["Pedido"].dropna().unique())
                    df_sla = df_sla[df_sla["Pedido"].isin(pedidos_filtrados_maestro) | (df_sla["Casuistica"] == "Pedido Perfecto")]

            if subfamilias:
                subfam_sel = st.sidebar.multiselect(
                    "🏷️ Subfamilia",
                    options=subfamilias,
                    default=[],
                    key="sb_subfam",
                    placeholder="Todas las Subfamilias"
                )
                if subfam_sel:
                    df_rect = df_rect[df_rect["Subfamilia"].astype(str).isin(subfam_sel)]
                    pedidos_filtrados_maestro = set(df_rect["Pedido"].dropna().unique())
                    df_sla = df_sla[df_sla["Pedido"].isin(pedidos_filtrados_maestro) | (df_sla["Casuistica"] == "Pedido Perfecto")]

        # 9. FILTRO DE AÑO Y MES
        if ("Año" in df_sla.columns and df_sla["Año"].notna().any()) or ("Mes" in df_sla.columns and df_sla["Mes"].notna().any()):
            if "Año" in df_sla.columns and df_sla["Año"].notna().any():
                anios = sorted([int(x) for x in df_sla["Año"].dropna().unique()], reverse=True)
                anio_sel = st.sidebar.multiselect(
                    "📅 Año",
                    options=anios,
                    default=[],
                    key="sb_anio",
                    placeholder="Todos los Años"
                )
                if anio_sel:
                    df_sla = df_sla[df_sla["Año"].isin(anio_sel) | df_sla["Año"].isna()]

            if "Mes" in df_sla.columns and df_sla["Mes"].notna().any():
                mapa_meses = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
                meses_num = sorted([int(x) for x in df_sla["Mes"].dropna().unique() if int(x) > 0])
                nombres_meses_disp = [mapa_meses.get(m, str(m)) for m in meses_num]
                mapa_mes_nombre_a_num = {mapa_meses.get(m, str(m)): m for m in meses_num}

                mes_sel_nombres = st.sidebar.multiselect(
                    "📅 Mes",
                    options=nombres_meses_disp,
                    default=[],
                    key="sb_mes",
                    placeholder="Todos los Meses"
                )
                if mes_sel_nombres:
                    meses_elegidos = [mapa_mes_nombre_a_num[nom] for nom in mes_sel_nombres]
                    df_sla = df_sla[df_sla["Mes"].isin(meses_elegidos) | df_sla["Mes"].isna()]

        st.sidebar.markdown("---")

        st.sidebar.header("⚠️ Filtro de Outliers (Pocos Pedidos)")
        
        pedidos_por_tienda = df_sla.groupby("Tienda")["Pedido"].nunique()
        umbral_min_pedidos = st.sidebar.number_input(
            "Mínimo de pedidos recibidos por tienda:",
            min_value=1, max_value=100, value=5, step=1,
            help="Excluye tiendas con muy pocos pedidos para evitar distorsiones estadísticas en el promedio SLA."
        )
        
        tiendas_pocas_compras = set(pedidos_por_tienda[pedidos_por_tienda < umbral_min_pedidos].index)
        activar_filtro_outliers = st.sidebar.checkbox("Excluir Tiendas con Pocos Pedidos", value=False)
        
        if activar_filtro_outliers and len(tiendas_pocas_compras) > 0:
            df_sla = df_sla[~df_sla["Tienda"].isin(tiendas_pocas_compras)]
            if not df_rect.empty:
                df_rect = df_rect[~df_rect["Tienda"].isin(tiendas_pocas_compras)]
            st.sidebar.warning(f"Excluidas {len(tiendas_pocas_compras):,} tiendas con < {umbral_min_pedidos} pedidos.")

        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "📊 1. Ranking SLA por Almacén y Tienda",
            "🏪 2. Detalle de Rectificaciones por Tienda",
            "🔄 3. Análisis de Sustituciones",
            "📦 4. Rectificaciones por Área de Salida",
            "🧩 5. Rectificaciones de Unidades Sueltas",
            "❌ 6. Rectificaciones del Portal",
            "📦 7. Rectificaciones con Error de Facturación Master",
            "📖 8. Glosario"
        ])

        # HOJA 1
        with tab1:
            st.subheader("📊 Ranking SLA por Almacén y Tienda")

            tot_pedidos_global = len(df_sla)
            tot_pedidos_rectif_global = (df_sla["Casuistica"] != "Pedido Perfecto").sum()
            tot_pts_obtenidos_global = df_sla["Puntos_Obtenidos"].sum()
            tot_pts_posibles_global = tot_pedidos_global * 10.0
            sla_global = (tot_pts_obtenidos_global / tot_pts_posibles_global * 10.0) if tot_pts_posibles_global > 0 else 0.0

            pct_pedidos_rectif = (tot_pedidos_rectif_global / tot_pedidos_global * 100.0) if tot_pedidos_global > 0 else 0.0

            k1, k2, k3 = st.columns(3)
            k1.metric("⭐ Puntaje SLA Promedio", f"{sla_global:.2f} / 10.0")
            k2.metric("📦 Pedidos Totales", f"{tot_pedidos_global:,}")
            k3.metric("⚠️ Pedidos con Rectificación", f"{tot_pedidos_rectif_global:,} ({pct_pedidos_rectif:.2f}%)")

            st.markdown("---")
            st.markdown("### 🏬 Evolución Mensual del SLA por Almacén")
            
            mapa_meses = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
            
            df_sla_mes = df_sla.copy()
            df_sla_mes["Mes_Num"] = pd.to_numeric(df_sla_mes["Mes"], errors="coerce").fillna(0).astype(int)
            df_sla_mes["Nombre_Mes"] = df_sla_mes["Mes_Num"].map(mapa_meses).fillna("Sin Mes")

            df_alm_mes = df_sla_mes.groupby(["Mes_Num", "Nombre_Mes", "Almacen"], as_index=False).agg(
                Pedidos_Totales=("Pedido", "count"),
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )
            df_alm_mes["Puntos_Posibles"] = df_alm_mes["Pedidos_Totales"] * 10.0
            df_alm_mes["Puntaje SLA"] = (df_alm_mes["Puntos_Obtenidos"] / df_alm_mes["Puntos_Posibles"]) * 10.0
            df_alm_mes["Puntaje SLA"] = df_alm_mes["Puntaje SLA"].fillna(0.0)
            df_alm_mes["Etiqueta_Almacen"] = "Almacén " + df_alm_mes["Almacen"].astype(str)
            
            df_alm_mes = df_alm_mes.sort_values(by=["Mes_Num", "Etiqueta_Almacen"]).reset_index(drop=True)
            meses_ordenados = sorted([m for m in df_sla_mes["Mes_Num"].unique() if m in mapa_meses])
            orden_nombres_meses = [mapa_meses[m] for m in meses_ordenados]

            mapa_colores_alm = {
                "Almacén 501": "#9B59B6", "Almacén 503": "#2BA884", 
                "Almacén 504": "#D06A4C", "Almacén 509": "#E09F53", "Almacén 514": "#2B5C8F"
            }

            fig_mes_alm = px.bar(
                df_alm_mes, x="Nombre_Mes", y="Puntaje SLA", color="Etiqueta_Almacen",
                barmode="group", text="Puntaje SLA", color_discrete_map=mapa_colores_alm
            )
            fig_mes_alm.update_traces(texttemplate='<b>%{text:.2f} ⭐</b>', textposition='outside', cliponaxis=False)
            fig_mes_alm.update_layout(
                yaxis=dict(range=[7.0, 10.25], title="Puntaje SLA (Escala 7 a 10)"), 
                xaxis=dict(title="Mes", categoryorder="array", categoryarray=orden_nombres_meses), 
                height=390, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_mes_alm, use_container_width=True)

            st.markdown("### 📊 Evolución Mensual de Casuísticas y Cantidad de Líneas Rectificadas")

            df_sla_cas_errores = df_sla_mes[df_sla_mes["Casuistica"] != "Pedido Perfecto"].copy()
            df_cas_mes = df_sla_cas_errores.groupby(["Mes_Num", "Nombre_Mes", "Casuistica"], as_index=False).agg(Cantidad_Pedidos=("Pedido", "count"))

            tot_ped_error_mes = df_cas_mes.groupby(["Mes_Num", "Nombre_Mes"])["Cantidad_Pedidos"].transform("sum")
            df_cas_mes["Pct_Cas_Mes"] = (df_cas_mes["Cantidad_Pedidos"] / tot_ped_error_mes * 100.0).fillna(0.0)
            df_cas_mes["Etiqueta_Barra"] = df_cas_mes.apply(lambda r: f"<b>{int(r['Cantidad_Pedidos']):,}</b><br>({r['Pct_Cas_Mes']:.1f}%)", axis=1)

            df_cas_mes = df_cas_mes.sort_values(by=["Mes_Num"]).reset_index(drop=True)

            if not df_rect.empty:
                df_rect_m = df_rect.copy()
                if "Fecha de Grabación" in df_rect_m.columns:
                    fec_rect_str = df_rect_m["Fecha de Grabación"].astype(str).str.strip()
                    fec_rect_dt = pd.to_datetime(fec_rect_str, format="%Y%m%d", errors="coerce")
                    mask_r_na = fec_rect_dt.isna()
                    if mask_r_na.any():
                        fec_rect_dt[mask_r_na] = pd.to_datetime(fec_rect_str[mask_r_na], dayfirst=True, errors="coerce")
                    df_rect_m["Mes_Num"] = fec_rect_dt.dt.month.fillna(0).astype(int)
                elif "Mes" in df_rect_m.columns:
                    df_rect_m["Mes_Num"] = pd.to_numeric(df_rect_m["Mes"], errors="coerce").fillna(0).astype(int)
                else:
                    df_rect_m["Mes_Num"] = 0

                df_lineas_mes = df_rect_m.groupby(["Mes_Num"], as_index=False).size().rename(columns={"size": "Cant_Lineas_Rectificadas"})
            else:
                df_lineas_mes = pd.DataFrame(columns=["Mes_Num", "Cant_Lineas_Rectificadas"])

            df_meses_base = pd.DataFrame({"Mes_Num": meses_ordenados})
            df_meses_base["Mes_Num"] = pd.to_numeric(df_meses_base["Mes_Num"], errors="coerce").fillna(0).astype(int)
            df_meses_base["Nombre_Mes"] = df_meses_base["Mes_Num"].map(mapa_meses)

            if not df_lineas_mes.empty and "Mes_Num" in df_lineas_mes.columns:
                df_lineas_mes["Mes_Num"] = pd.to_numeric(df_lineas_mes["Mes_Num"], errors="coerce").fillna(0).astype(int)

            df_lineas_mes = df_meses_base.merge(df_lineas_mes, on="Mes_Num", how="left").fillna({"Cant_Lineas_Rectificadas": 0})
            df_lineas_mes = df_lineas_mes.sort_values("Mes_Num").reset_index(drop=True)

            # Totalizador de Pedidos Rectificados por Mes
            df_tot_ped_mes = df_cas_mes.groupby("Mes_Num", as_index=False)["Cantidad_Pedidos"].sum()
            df_tot_ped_mes = df_meses_base.merge(df_tot_ped_mes, on="Mes_Num", how="left").fillna({"Cantidad_Pedidos": 0})
            df_tot_ped_mes = df_tot_ped_mes.sort_values("Mes_Num").reset_index(drop=True)

            colores_cas = {
                "Sobrante Neto": "#0077B6",                  # Azul cobalto
                "Sustitución Misma Subfamilia": "#2EC4B6",   # Verde menta / esmeralda
                "Sustitución Distinta Subfamilia": "#F77F00", # Naranja cálido
                "Falta/Sobra": "#48CAE4",                    # Celeste cielo
                "Faltante Neto": "#E63946",                  # Rojo vivo
                "Formato no entregado": "#FFD166",           # Amarillo dorado
                "Error facturación master": "#9B5DE5",        # Violeta eléctrico
                "Etiquetas Cambiadas": "#343A40",            # Carbón grafito oscuro
                "Rectificación Almacén": "#F4ACB7"           # 🌸 Rosa pálido
            }

            fig_comb = make_subplots(specs=[[{"secondary_y": True}]])
            casuisticas_orden = [
                "Sobrante Neto", "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                "Falta/Sobra", "Faltante Neto", "Formato no entregado", "Error facturación master", "Etiquetas Cambiadas",
                "Rectificación Almacén"
            ]

            for cas in casuisticas_orden:
                df_c = df_cas_mes[df_cas_mes["Casuistica"] == cas].sort_values("Mes_Num")
                if not df_c.empty:
                    # Si es rosa pálido, usamos texto oscuro dentro de la barra para máxima legibilidad
                    text_color_inside = "#2B2D42" if cas == "Rectificación Almacén" else "white"
                    fig_comb.add_trace(go.Bar(
                        x=df_c["Mes_Num"], 
                        y=df_c["Cantidad_Pedidos"], 
                        name=cas, 
                        marker_color=colores_cas.get(cas, "#999999"), 
                        text=df_c["Etiqueta_Barra"], 
                        textposition="inside",
                        insidetextfont=dict(color=text_color_inside),
                        hovertemplate="<b>%{data.name}</b><br>Pedidos: %{y:,}<extra></extra>"
                    ), secondary_y=False)

            # Totalizador acumulado de pedidos arriba de cada barra
            fig_comb.add_trace(go.Scatter(
                x=df_tot_ped_mes["Mes_Num"],
                y=df_tot_ped_mes["Cantidad_Pedidos"],
                name="Total Pedidos",
                mode="text",
                text=[f"<b>{int(x):,}</b>" if x > 0 else "" for x in df_tot_ped_mes["Cantidad_Pedidos"]],
                textposition="top center",
                textfont=dict(size=12, color="#1D3557"),
                showlegend=False,
                hovertemplate="<b>%{y:,} Pedidos</b><extra></extra>"
            ), secondary_y=False)

            # Línea de Líneas Rectificadas (Eje Secundario en Azul Marino Noche oscuro con marcadores blancos)
            fig_comb.add_trace(go.Scatter(
                x=df_lineas_mes["Mes_Num"], 
                y=df_lineas_mes["Cant_Lineas_Rectificadas"], 
                name="Líneas Rectificadas", 
                mode="lines+markers+text", 
                line=dict(color="#03045E", width=3.5), 
                marker=dict(size=9, color="#03045E", line=dict(width=2, color="#FFFFFF")), 
                text=[f"<b>{int(x):,}</b> lín." for x in df_lineas_mes["Cant_Lineas_Rectificadas"]], 
                textposition="top center",
                hovertemplate="<b>Líneas Rectificadas</b>: %{y:,}<extra></extra>"
            ), secondary_y=True)

            max_ped_stack = df_tot_ped_mes["Cantidad_Pedidos"].max() if not df_tot_ped_mes.empty else 10000

            fig_comb.update_layout(
                barmode="stack", height=460,
                hovermode="closest",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
                xaxis=dict(
                    title="Mes",
                    tickmode="array",
                    tickvals=meses_ordenados,
                    ticktext=orden_nombres_meses
                ),
                yaxis=dict(
                    title="Cantidad de Pedidos Rectificados",
                    range=[0, max_ped_stack * 1.25]
                ),
                yaxis2=dict(
                    title="Cantidad de Líneas Rectificadas",
                    showgrid=False
                )
            )
            st.plotly_chart(fig_comb, use_container_width=True)

            st.markdown("---")
            st.markdown("### 📈 Distribución de rectificaciones por casuística")
            df_sla_tab1_cas = df_sla[df_sla["Casuistica"].astype(str).str.strip() != "Pedido Perfecto"].copy()
            df_sla_tab1_cas["Casuistica"] = df_sla_tab1_cas["Casuistica"].astype(str).str.strip()
            tot_p_rect = len(df_sla_tab1_cas)

            cas_sum = df_sla_tab1_cas.groupby("Casuistica", as_index=False).agg(
                Pedidos_Totales=("Pedido", "count"), 
                Lineas_Rectificadas=("Lineas_Rectificadas_Confirmadas", "sum") if "Lineas_Rectificadas_Confirmadas" in df_sla_tab1_cas.columns else ("Pedido", "count")
            )
            cas_sum["% Participación Pedidos"] = (cas_sum["Pedidos_Totales"] / tot_p_rect) * 100.0 if tot_p_rect > 0 else 0.0

            if not df_rect.empty and "Pedido" in df_rect.columns:
                pedidos_por_cas = df_sla_tab1_cas.set_index("Pedido")["Casuistica"].to_dict()
                df_rect_cas_temp = df_rect.copy()
                df_rect_cas_temp["Casuistica_Mapped"] = df_rect_cas_temp["Pedido"].map(pedidos_por_cas).fillna("Sin Clasificar")

                col_est_cas = "Estado_Clean" if "Estado_Clean" in df_rect_cas_temp.columns else ("Estado" if "Estado" in df_rect_cas_temp.columns else "Pedido")

                grp_acep = df_rect_cas_temp.groupby("Casuistica_Mapped", as_index=False).agg(
                    Lin_Grabadas=("Pedido", "count"),
                    Lin_Aprobadas=(col_est_cas, lambda x: (x.astype(str).str.strip().str.upper() == "M").sum() if col_est_cas != "Pedido" else len(x))
                )
                grp_acep["% Aceptación"] = (grp_acep["Lin_Aprobadas"] / grp_acep["Lin_Grabadas"] * 100.0).fillna(0.0)
                mapa_acep = grp_acep.set_index("Casuistica_Mapped")["% Aceptación"].to_dict()

                cas_sum["% Aceptación"] = cas_sum["Casuistica"].map(mapa_acep).fillna(0.0)
            else:
                cas_sum["% Aceptación"] = 100.0

            orden_cas = [
                "Sobrante Neto", 
                "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                "Falta/Sobra", "Faltante Neto", "Formato no entregado", "Error facturación master", 
                "Etiquetas Cambiadas", "Rectificación Almacén"
            ]
            casuisticas_cat = pd.Categorical(cas_sum["Casuistica"], categories=orden_cas, ordered=True)
            cas_sum["Casuistica_Cat"] = casuisticas_cat
            cas_sum = cas_sum.sort_values("Casuistica_Cat").drop(columns=["Casuistica_Cat"]).reset_index(drop=True)

            cas_sum_display = cas_sum.rename(columns={
                "Casuistica": "Casuística",
                "Pedidos_Totales": "Pedidos Totales",
                "Lineas_Rectificadas": "Líneas Rectificadas",
                "% Participación Pedidos": "% Participación Pedidos",
                "% Aceptación": "% Aceptación"
            })

            st.dataframe(
                cas_sum_display[["Casuística", "Pedidos Totales", "Líneas Rectificadas", "% Participación Pedidos", "% Aceptación"]],
                hide_index=True,
                column_config={
                    "Casuística": st.column_config.Column("Casuística", width="medium"),
                    "Pedidos Totales": st.column_config.NumberColumn("Pedidos Totales", format="%d", width="medium"),
                    "Líneas Rectificadas": st.column_config.NumberColumn("Líneas Rectificadas", format="%d", width="medium"),
                    "% Participación Pedidos": st.column_config.NumberColumn("% Participación Pedidos", format="%.2f %%", width="medium"),
                    "% Aceptación": st.column_config.NumberColumn("% Aceptación", format="%.2f %%", width="medium")
                }
            )

            st.markdown("---")
            st.markdown("### 👤 Ranking y Puntaje SLA por Franquiciado / Supervisor")
            st.caption("Puntaje SLA ponderado (escala 0-10 ⭐), pedidos recibidos, pedidos rectificados y tasa de aceptación por franquiciado / supervisor.")

            if "Responsable_Tienda" in df_sla.columns and df_sla["Responsable_Tienda"].notna().any():
                df_sla_resp = df_sla[~df_sla["Responsable_Tienda"].isin(["Sin Asignar", "nan", ""])].copy()
                if not df_sla_resp.empty:
                    df_resp_grp = df_sla_resp.groupby("Responsable_Tienda", as_index=False).agg(
                        Tiendas_Asignadas=("Tienda", "nunique"),
                        Pedidos_Totales=("Pedido", "count"),
                        Pedidos_Rectificados=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()),
                        Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
                    )
                    df_resp_grp["Puntos_Posibles"] = df_resp_grp["Pedidos_Totales"] * 10.0
                    df_resp_grp["Puntaje SLA"] = (df_resp_grp["Puntos_Obtenidos"] / df_resp_grp["Puntos_Posibles"]) * 10.0
                    df_resp_grp["% Pedidos con Rectificación"] = (df_resp_grp["Pedidos_Rectificados"] / df_resp_grp["Pedidos_Totales"]) * 100.0

                    if not df_rect.empty and "Responsable_Tienda" in df_rect.columns:
                        col_est_r = "Estado_Clean" if "Estado_Clean" in df_rect.columns else ("Estado" if "Estado" in df_rect.columns else "Pedido")
                        grp_rect_resp = df_rect.groupby("Responsable_Tienda", as_index=False).agg(
                            Lineas_Grabadas=("Pedido", "count"),
                            Lineas_Aprobadas=(col_est_r, lambda x: (x.astype(str).str.strip().str.upper() == "M").sum() if col_est_r != "Pedido" else len(x))
                        )
                        grp_rect_resp["% Aceptación"] = (grp_rect_resp["Lineas_Aprobadas"] / grp_rect_resp["Lineas_Grabadas"] * 100.0).fillna(0.0)
                        mapa_acep_resp = grp_rect_resp.set_index("Responsable_Tienda")["% Aceptación"].to_dict()
                        mapa_lin_resp = grp_rect_resp.set_index("Responsable_Tienda")["Lineas_Aprobadas"].to_dict()
                        df_resp_grp["Líneas Confirmadas"] = df_resp_grp["Responsable_Tienda"].map(mapa_lin_resp).fillna(0).astype(int)
                        df_resp_grp["% Aceptación"] = df_resp_grp["Responsable_Tienda"].map(mapa_acep_resp).fillna(100.0)
                    else:
                        df_resp_grp["Líneas Confirmadas"] = 0
                        df_resp_grp["% Aceptación"] = 100.0

                    df_resp_grp = df_resp_grp.sort_values(by=["Puntaje SLA", "Pedidos_Totales"], ascending=[True, True]).reset_index(drop=True)

                    st.dataframe(
                        df_resp_grp[[
                            "Responsable_Tienda", "Tiendas_Asignadas", "Pedidos_Totales",
                            "Pedidos_Rectificados", "% Pedidos con Rectificación", "Líneas Confirmadas", "% Aceptación", "Puntaje SLA"
                        ]].rename(columns={
                            "Responsable_Tienda": "Franquiciado / Supervisor",
                            "Tiendas_Asignadas": "Tiendas",
                            "Pedidos_Totales": "Pedidos Totales",
                            "Pedidos_Rectificados": "Pedidos Rectificados"
                        }),
                        hide_index=True,
                        column_config={
                            "Franquiciado / Supervisor": st.column_config.Column("Franquiciado / Supervisor", width="large"),
                            "Tiendas": st.column_config.NumberColumn("Tiendas", format="%d", width="small"),
                            "Pedidos Totales": st.column_config.NumberColumn("Pedidos Totales", format="%d", width="small"),
                            "Pedidos Rectificados": st.column_config.NumberColumn("Pedidos Rectificados", format="%d", width="small"),
                            "% Pedidos con Rectificación": st.column_config.NumberColumn("% Pedidos Rectificados", format="%.1f %%", width="medium"),
                            "Líneas Confirmadas": st.column_config.NumberColumn("Líneas Conf.", format="%d", width="small"),
                            "% Aceptación": st.column_config.NumberColumn("% Aceptación", format="%.1f %%", width="small"),
                            "Puntaje SLA": st.column_config.NumberColumn("Puntaje SLA", format="%.2f ⭐", width="medium")
                        }
                    )
                else:
                    st.info("ℹ️ No hay datos disponibles de franquiciados/supervisores para la selección actual.")

        with tab2:
                st.subheader("🏪 Detalle de Rectificaciones por Tienda")
                st.markdown("Detalle consolidado por sucursal para evaluar el nivel de aceptación de rectificaciones, distribución de estados (M/P/R), impacto económico y desgloses por casuística.")
    
                tiendas_unicas = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
                opciones_tienda = ["Ninguna", "Todas las Tiendas"] + tiendas_unicas
                
                c_tienda, c_cas = st.columns([2, 2])
                with c_tienda:
                    t_sel = st.selectbox("Seleccionar Tienda a Consultar:", opciones_tienda, index=0)
                
                orden_cas_tab2 = [
                    "Todas las Casuísticas",
                    "Sobrante Neto", "Sustitución Misma Subfamilia", 
                    "Sustitución Distinta Subfamilia", "Falta/Sobra", 
                    "Faltante Neto", "Formato no entregado", "Error facturación master", 
                    "Etiquetas Cambiadas", "Rectificación Almacén"
                ]
                casuisticas_presentes_tab2 = [c for c in orden_cas_tab2 if c == "Todas las Casuísticas" or c in df_sla["Casuistica"].dropna().unique()]
                
                with c_cas:
                    cas_sel_tab2 = st.selectbox("Filtrar por Casuística / Estado Pedido:", casuisticas_presentes_tab2, index=0)
    
                if t_sel == "Ninguna":
                    st.info("👈 Selecciona una **Tienda** específica o la opción **'Todas las Tiendas'** para desplegar el resumen consolidado y detalle de rectificaciones.")
                else:
                    if t_sel == "Todas las Tiendas":
                        df_aud_sla = df_sla.copy()
                        df_aud_rect = df_rect.copy() if not df_rect.empty else pd.DataFrame()
                    else:
                        df_aud_sla = df_sla[df_sla["Tienda"].astype(str) == str(t_sel)].copy()
                        df_aud_rect = df_rect[df_rect["Tienda"].astype(str) == str(t_sel)].copy() if not df_rect.empty else pd.DataFrame()
    
                    if cas_sel_tab2 != "Todas las Casuísticas":
                        df_aud_sla = df_aud_sla[df_aud_sla["Casuistica"] == cas_sel_tab2]
                        if not df_aud_rect.empty:
                            pedidos_cas_filtrados = set(df_aud_sla["Pedido"].dropna().unique())
                            df_aud_rect = df_aud_rect[df_aud_rect["Pedido"].isin(pedidos_cas_filtrados)]
    
                    tot_p_t = len(df_aud_sla)
                    tot_p_rect_t = (df_aud_sla["Casuistica"] != "Pedido Perfecto").sum()
                    pts_posibles_t = tot_p_t * 10.0
                    pts_obtenidos_t = df_aud_sla["Puntos_Obtenidos"].sum()
                    nota_sla_t = (pts_obtenidos_t / pts_posibles_t * 10.0) if pts_posibles_t > 0 else 0.0
    
                    if not df_aud_rect.empty:
                        col_est_m = "Estado_Clean" if "Estado_Clean" in df_aud_rect.columns else ("Estado" if "Estado" in df_aud_rect.columns else "Pedido")
                        df_aud_rect["Estado_Clean_M"] = df_aud_rect[col_est_m].astype(str).str.strip().str.upper()
    
                        tot_lineas_grabadas = len(df_aud_rect)
                        lin_m = (df_aud_rect["Estado_Clean_M"] == "M").sum()
                        lin_r = (df_aud_rect["Estado_Clean_M"] == "R").sum()
                        lin_p = (df_aud_rect["Estado_Clean_M"] == "P").sum()
    
                        pct_aceptacion = (lin_m / tot_lineas_grabadas * 100.0) if tot_lineas_grabadas > 0 else 100.0
    
                        monto_grabado_tot = df_aud_rect["Monto_Rectif"].sum() if "Monto_Rectif" in df_aud_rect.columns else 0.0
                        monto_confirmado_tot = df_aud_rect[df_aud_rect["Estado_Clean_M"] == "M"]["Monto_Rectif"].sum() if "Monto_Rectif" in df_aud_rect.columns else 0.0
                    else:
                        tot_lineas_grabadas = 0
                        lin_m, lin_r, lin_p = 0, 0, 0
                        pct_aceptacion = 100.0
                        monto_grabado_tot = 0.0
                        monto_confirmado_tot = 0.0
    
                    k1, k2, k3, k4, k5 = st.columns(5)
                    k1.metric("⭐ Puntaje SLA Tienda", f"{nota_sla_t:.2f} / 10.0")
                    k2.metric("📦 Pedidos Recibidos", f"{tot_p_t:,}")
                    k3.metric("📉 Líneas Rectificadas", f"{tot_lineas_grabadas:,}")
                    k4.metric("✅ % Aceptación", f"{pct_aceptacion:.1f}%", help="Proporción de líneas confirmadas 'M' sobre el total rectificado por la tienda")
                    k5.metric("💰 Monto Confirmado", f"${monto_confirmado_tot:,.0f}", delta=f"de ${monto_grabado_tot:,.0f} Rectificados")
    
                    st.markdown("---")
                    st.markdown("### 📊 Desglose de Estados de Rectificación e Impacto Monetario")
                    e1, e2, e3 = st.columns(3)
                    e1.metric("✅ Confirmadas / Aprobadas (Estado M)", f"{lin_m:,}", help="Líneas confirmadas y aceptadas")
                    e2.metric("❌ Rechazadas / Anuladas (Estado R)", f"{lin_r:,}", help="Líneas rechazadas")
                    e3.metric("⏳ Pendientes (Estado P)", f"{lin_p:,}", help="Líneas en proceso de evaluación")
    
                    st.markdown("---")
                    st.subheader("📋 Resumen de Pedidos y Líneas Rectificadas por Tienda")
                    
                    df_pedidos_rect_tienda = df_aud_sla[df_aud_sla["Casuistica"] != "Pedido Perfecto"].copy()
                    
                    if not df_pedidos_rect_tienda.empty:
                        if not df_aud_rect.empty:
                            col_motivo = "Motivo_Clean" if "Motivo_Clean" in df_aud_rect.columns else ("Motivo" if "Motivo" in df_aud_rect.columns else None)
                            if col_motivo:
                                df_aud_rect["Motivo_Norm"] = df_aud_rect[col_motivo].astype(str).str.strip().str.upper()
                            else:
                                df_aud_rect["Motivo_Norm"] = "F"
    
                            col_unid = None
                            for c in ["Unid/Kgs grabados", "Unid_Grabadas", "Unidades Grabadas", "Unid/Kgs abonados"]:
                                if c in df_aud_rect.columns:
                                    col_unid = c
                                    break
                            if col_unid:
                                df_aud_rect["Unidades_Num"] = pd.to_numeric(df_aud_rect[col_unid].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
                            else:
                                df_aud_rect["Unidades_Num"] = 1.0
    
                            conteo_tot = df_aud_rect.groupby("Pedido").size().to_dict()
                            conteo_f = df_aud_rect[df_aud_rect["Motivo_Norm"] == "F"].groupby("Pedido").size().to_dict()
                            conteo_s = df_aud_rect[df_aud_rect["Motivo_Norm"] == "S"].groupby("Pedido").size().to_dict()
    
                            conteo_master_si = df_aud_rect[df_aud_rect["Es_Master"] == "Sí"].groupby("Pedido").size().to_dict()
                            conteo_master_no = df_aud_rect[df_aud_rect["Es_Master"] == "No"].groupby("Pedido").size().to_dict()
    
                            unid_f = df_aud_rect[df_aud_rect["Motivo_Norm"] == "F"].groupby("Pedido")["Unidades_Num"].sum().to_dict()
                            unid_s = df_aud_rect[df_aud_rect["Motivo_Norm"] == "S"].groupby("Pedido")["Unidades_Num"].sum().to_dict()
    
                            df_pedidos_rect_tienda["Líneas Totales"] = df_pedidos_rect_tienda["Pedido"].map(conteo_tot).fillna(0).astype(int)
                            df_pedidos_rect_tienda["Líneas Faltantes"] = df_pedidos_rect_tienda["Pedido"].map(conteo_f).fillna(0).astype(int)
                            df_pedidos_rect_tienda["Líneas Sobrantes"] = df_pedidos_rect_tienda["Pedido"].map(conteo_s).fillna(0).astype(int)
                            
                            df_pedidos_rect_tienda["Master No"] = df_pedidos_rect_tienda["Pedido"].map(conteo_master_no).fillna(0).astype(int)
                            df_pedidos_rect_tienda["Master Sí"] = df_pedidos_rect_tienda["Pedido"].map(conteo_master_si).fillna(0).astype(int)
    
                            df_pedidos_rect_tienda["Unidades Faltantes"] = df_pedidos_rect_tienda["Pedido"].map(unid_f).fillna(0.0).astype(int)
                            df_pedidos_rect_tienda["Unidades Sobrantes"] = df_pedidos_rect_tienda["Pedido"].map(unid_s).fillna(0.0).astype(int)
                        else:
                            df_pedidos_rect_tienda["Líneas Totales"] = 0
                            df_pedidos_rect_tienda["Líneas Faltantes"] = 0
                            df_pedidos_rect_tienda["Líneas Sobrantes"] = 0
                            df_pedidos_rect_tienda["Master No"] = 0
                            df_pedidos_rect_tienda["Master Sí"] = 0
                            df_pedidos_rect_tienda["Unidades Faltantes"] = 0
                            df_pedidos_rect_tienda["Unidades Sobrantes"] = 0
    
                        df_pedidos_rect_tienda_disp = df_pedidos_rect_tienda[[
                            "Tienda", "Pedido", "Líneas Totales", "Casuistica", 
                            "Líneas Faltantes", "Líneas Sobrantes", 
                            "Master No", "Master Sí",
                            "Unidades Faltantes", "Unidades Sobrantes", 
                            "Puntos_Obtenidos"
                        ]].copy()
    
                        df_pedidos_rect_tienda_disp = df_pedidos_rect_tienda_disp.rename(columns={
                            "Tienda": "Tienda",
                            "Pedido": "Pedido Rectificado",
                            "Líneas Totales": "Líneas Totales",
                            "Casuistica": "Casuística",
                            "Puntos_Obtenidos": "Puntaje SLA (0-10)"
                        })
    
                        st.dataframe(
                            df_pedidos_rect_tienda_disp,
                            hide_index=True,
                            column_config={
                                "Tienda": st.column_config.NumberColumn("Tienda", format="%d", width="small"),
                                "Pedido Rectificado": st.column_config.Column("Pedido Rectificado", width="medium"),
                                "Líneas Totales": st.column_config.NumberColumn("Líneas Totales", format="%d", width="small"),
                                "Casuística": st.column_config.Column("Casuística", width="large"),
                                "Líneas Faltantes": st.column_config.NumberColumn("Líneas Faltantes (F)", format="%d", width="small"),
                                "Líneas Sobrantes": st.column_config.NumberColumn("Líneas Sobrantes (S)", format="%d", width="small"),
                                "Master No": st.column_config.NumberColumn("Master No", format="%d", width="small"),
                                "Master Sí": st.column_config.NumberColumn("Master Sí", format="%d", width="small"),
                                "Unidades Faltantes": st.column_config.NumberColumn("Unid. Faltantes (F)", format="%d", width="small"),
                                "Unidades Sobrantes": st.column_config.NumberColumn("Unid. Sobrantes (S)", format="%d", width="small"),
                                "Puntaje SLA (0-10)": st.column_config.NumberColumn("Puntaje SLA", format="%.1f ⭐", width="medium")
                            }
                        )
                    else:
                        st.info("ℹ️ No hay pedidos rectificados para la selección realizada.")
    
                    st.markdown("---")
                    glosario_txt = """GLOSARIO OPERATIVO:
    1. Procedencia:
       • 'T' = Grabada por tienda
       • 'G' = Grabada por CD
    2. Motivo:
       • 'F' = Falta (Faltante de mercadería)
       • 'S' = Sobra (Sobrante de mercadería)
    3. Estado:
       • 'M' = Confirmada
       • 'P' = Rectificación pendiente
       • 'R' = Rechazada"""
    
                    st.subheader("🔎 Detalle de Rectificaciones Registradas (Líneas de SKUs)", help=glosario_txt)
    
                    if not df_aud_rect.empty:
                        busqueda_pedido = st.text_input("🔍 Filtrar exclusivamente por Número de Pedido:", "", key="txt_ped_h3_val")
                        if busqueda_pedido:
                            df_aud_rect = df_aud_rect[
                                df_aud_rect["Pedido"].astype(str).str.contains(busqueda_pedido.strip(), case=False, na=False)
                            ]
    
                        col_motivo = "Motivo_Clean" if "Motivo_Clean" in df_aud_rect.columns else ("Motivo" if "Motivo" in df_aud_rect.columns else None)
                        if col_motivo:
                            df_aud_rect["Factor_Signo"] = df_aud_rect[col_motivo].astype(str).str.strip().str.upper().apply(lambda x: -1.0 if x == "S" else 1.0)
                        else:
                            df_aud_rect["Factor_Signo"] = 1.0
    
                        df_aud_rect["Monto_Signed"] = df_aud_rect["Monto_Rectif"] * df_aud_rect["Factor_Signo"]
    
                        col_unid_grab = None
                        for c in ["Unid/Kgs grabados", "Unid_Grabadas", "Unidades Grabadas"]:
                            if c in df_aud_rect.columns:
                                col_unid_grab = c
                                break
    
                        col_unid_abon = None
                        for c in ["Unid/Kgs abonados", "Unid_Abonadas", "Unidades Abonadas"]:
                            if c in df_aud_rect.columns:
                                col_unid_abon = c
                                break
    
                        cols_rect_disp = [
                            "Almacen", "Tienda", "Pedido", "Area_Salida", "Nº Rectificación", "Fecha de Grabación", "Artículo", 
                            "Descripción", "UxB", "BULFM", "Es_Master", "Motivo", "Procedencia", "Estado"
                        ]
    
                        if col_unid_grab:
                            cols_rect_disp.append(col_unid_grab)
                        if col_unid_abon:
                            cols_rect_disp.append(col_unid_abon)
    
                        cols_rect_disp.append("Monto_Signed")
                        cols_rect_exist = [c for c in cols_rect_disp if c in df_aud_rect.columns]
    
                        df_aud_rect_disp = df_aud_rect[cols_rect_exist].copy()
                        if "Fecha de Grabación" in df_aud_rect_disp.columns:
                            f_str = df_aud_rect_disp["Fecha de Grabación"].astype(str).str.strip()
                            f_dt = pd.to_datetime(f_str, format="%Y%m%d", errors="coerce")
                            mask_na = f_dt.isna()
                            if mask_na.any():
                                f_dt[mask_na] = pd.to_datetime(f_str[mask_na], dayfirst=True, errors="coerce")
                            df_aud_rect_disp["Fecha de Grabación"] = f_dt.dt.strftime("%d/%m/%Y").fillna(f_str)
                        elif "Fecha" in df_aud_rect_disp.columns:
                            f_str = df_aud_rect_disp["Fecha"].astype(str).str.strip()
                            f_dt = pd.to_datetime(f_str, format="%Y%m%d", errors="coerce")
                            mask_na = f_dt.isna()
                            if mask_na.any():
                                f_dt[mask_na] = pd.to_datetime(f_str[mask_na], dayfirst=True, errors="coerce")
                            df_aud_rect_disp["Fecha"] = f_dt.dt.strftime("%d/%m/%Y").fillna(f_str)
                        
                        rename_dict_det = {
                            "Almacen": "Almacén",
                            "Area_Salida": "Área de Salida",
                            "Nº Rectificación": "N° Rectif.",
                            "Fecha de Grabación": "Fecha Grabación",
                            "UxB": "UxB",
                            "BULFM": "BxM",
                            "Es_Master": "Master",
                            "Monto_Signed": "Monto ($)"
                        }
                        if col_unid_grab:
                            rename_dict_det[col_unid_grab] = "Unid. Grabadas"
                        if col_unid_abon:
                            rename_dict_det[col_unid_abon] = "Unid. Abonadas"
    
                        df_aud_rect_disp = df_aud_rect_disp.rename(columns=rename_dict_det)
    
                        st.dataframe(
                            df_aud_rect_disp,
                            hide_index=True,
                            column_config={
                                "Almacén": st.column_config.Column("Almacén", width="small"),
                                "Tienda": st.column_config.Column("Tienda", width="small"),
                                "Pedido": st.column_config.Column("Pedido", width="small"),
                                "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                                "N° Rectif.": st.column_config.Column("N° Rectif.", width="small"),
                                "Fecha Grabación": st.column_config.Column("Fecha", width="small"),
                                "Artículo": st.column_config.Column("SKU", width="small"),
                                "Descripción": st.column_config.Column("Producto / Descripción", width="large"),
                                "UxB": st.column_config.NumberColumn("UxB", format="%.0f", width="small"),
                                "BxM": st.column_config.NumberColumn("BxM", format="%.0f", width="small"),
                                "Master": st.column_config.Column("Master", width="small"),
                                "Motivo": st.column_config.Column("Motivo", width="small"),
                                "Procedencia": st.column_config.Column("Procedencia", width="small"),
                                "Estado": st.column_config.Column("Estado", width="small"),
                                "Unid. Grabadas": st.column_config.NumberColumn("Unid. Grabadas", format="%d", width="small"),
                                "Unid. Abonadas": st.column_config.NumberColumn("Unid. Abonadas", format="%d", width="small"),
                                "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="medium")
                            }
                        )
                    else:
                        st.success("🎉 La selección actual no presenta rectificaciones de artículos.")


        with tab3:
            st.subheader("🔄 Análisis de Sustituciones")
            st.markdown("Análisis de rectificaciones con casuística de sustitución misma y diferente familia grabadas por la tienda para evaluar el impacto monetario.")

            df_sust_analisis_completo = procesar_analisis_sustituciones_cache(df_sla, df_rect)

            if not df_sust_analisis_completo.empty:
                pedidos_sla_activos = set(df_sla["Pedido"].dropna().unique())
                df_sust_analisis = df_sust_analisis_completo[df_sust_analisis_completo["Pedido"].isin(pedidos_sla_activos)].copy()
            else:
                df_sust_analisis = pd.DataFrame()

            if not df_sust_analisis.empty:

                    tot_pedidos_sust_all = int(df_sust_analisis["Pedido"].nunique())
                    tot_monto_falta_bruto = float(df_sust_analisis["Monto Faltante ($)"].sum())
                    tot_monto_sobra_bruto = float(df_sust_analisis["Monto Sobrante ($)"].sum())
                    tot_diferencia_bruta = float(df_sust_analisis["Diferencia Monto Neto ($)"].sum())

                    k1_s, k2_s, k3_s, k4_s = st.columns(4)
                    k1_s.metric("📦 Total Pedidos Sustitución", f"{tot_pedidos_sust_all:,}")
                    k2_s.metric("💸 Importe Faltante ($)", f"${tot_monto_falta_bruto:,.0f}")
                    k3_s.metric("💰 Importe Sobrante ($)", f"${tot_monto_sobra_bruto:,.0f}")
                    k4_s.metric("⚖️ Diferencia Monto Neto ($)", f"${tot_diferencia_bruta:,.0f}", help="Balance monetario: Monto Faltante - Monto Sobrante")

                    st.markdown("---")

                    lin_m_sust = (df_sust_analisis["Estado Falta"] == "M").sum() + (df_sust_analisis["Estado Sobra"] == "M").sum()
                    lin_r_sust = (df_sust_analisis["Estado Falta"] == "R").sum() + (df_sust_analisis["Estado Sobra"] == "R").sum()
                    lin_p_sust = (df_sust_analisis["Estado Falta"] == "P").sum() + (df_sust_analisis["Estado Sobra"] == "P").sum()
                    tot_lin_sust_total = len(df_sust_analisis) * 2
                    pct_acep_sust = (lin_m_sust / tot_lin_sust_total * 100.0) if tot_lin_sust_total > 0 else 100.0

                    monto_conf_neto = df_sust_analisis["Diferencia Neta Confirmada ($)"].sum()

                    st.markdown("### 🎯 Montos Confirmados y Nivel de Aceptación de la Tienda")
                    c_conf1, c_conf2, c_conf3 = st.columns(3)
                    c_conf1.metric("✅ Monto Confirmado Neto ($)", f"${monto_conf_neto:,.0f}", help="Importe efectivamente aprobado y confirmado")
                    c_conf2.metric("🎯 % Aceptación Rectificaciones", f"{pct_acep_sust:.1f}%")
                    c_conf3.metric("❌ Tasa de Rechazo", f"{100.0 - pct_acep_sust:.1f}%")

                    st.markdown("---")
                    st.markdown("### 🏪 Resumen de Pedidos con Sustituciones por Tienda", help="La Diferencia Monto Neto refleja exclusivamente el importe de rectificaciones confirmadas (Estado 'M'). El % a Favor indica la proporción de pedidos donde el faltante superó al sobrante rectificado.")

                    filas_tienda_resumen = []
                    for t_val, grp_t in df_sust_analisis.groupby("Tienda"):
                        tot_ped_t = grp_t["Pedido"].nunique()
                        lin_m_t = (grp_t["Estado Falta"] == "M").sum() + (grp_t["Estado Sobra"] == "M").sum()
                        tot_lin_t = len(grp_t) * 2
                        pct_acep_t = (lin_m_t / tot_lin_t * 100.0) if tot_lin_t > 0 else 100.0
                        
                        monto_neto_conf_t = grp_t["Diferencia Neta Confirmada ($)"].sum()
                        ped_netos_t = grp_t.groupby("Pedido")["Diferencia Neta Confirmada ($)"].sum()
                        ped_a_favor_t = (ped_netos_t > 0).sum()
                        pct_favor_t = (ped_a_favor_t / tot_ped_t * 100.0) if tot_ped_t > 0 else 0.0
                        
                        monto_falta_conf_t = grp_t[grp_t["Estado Falta"] == "M"]["Monto Faltante ($)"].sum()
                        monto_sobra_conf_t = grp_t[grp_t["Estado Sobra"] == "M"]["Monto Sobrante ($)"].sum()
                        
                        filas_tienda_resumen.append({
                            "Tienda": t_val,
                            "Pedidos": tot_ped_t,
                            "% Aceptación": pct_acep_t,
                            "% a Favor de Tienda": pct_favor_t,
                            "Monto Falta Conf. ($)": monto_falta_conf_t,
                            "Monto Sobra Conf. ($)": monto_sobra_conf_t,
                            "Diferencia Monto Neto ($)": monto_neto_conf_t
                        })

                    tb_todas_tiendas_disp = pd.DataFrame(filas_tienda_resumen).sort_values(by="Pedidos", ascending=False).reset_index(drop=True)

                    st.dataframe(
                        tb_todas_tiendas_disp[[
                            "Tienda", "Pedidos", "% Aceptación", "% a Favor de Tienda",
                            "Monto Falta Conf. ($)", "Monto Sobra Conf. ($)", "Diferencia Monto Neto ($)"
                        ]],
                        hide_index=True,
                        column_config={
                            "Tienda": st.column_config.Column("Tienda", width="small"),
                            "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="small"),
                            "% Aceptación": st.column_config.NumberColumn("% Aceptación", format="%.1f %%", width="small"),
                            "% a Favor de Tienda": st.column_config.NumberColumn("% a Favor Tienda", format="%.1f %%", width="medium", help="Porcentaje de pedidos donde el faltante superó al sobrante rectificado"),
                            "Monto Falta Conf. ($)": st.column_config.NumberColumn("Falta Conf. ($)", format="$%.0f", width="small"),
                            "Monto Sobra Conf. ($)": st.column_config.NumberColumn("Sobra Conf. ($)", format="$%.0f", width="small"),
                            "Diferencia Monto Neto ($)": st.column_config.NumberColumn("Dif. Monto Neto ($)", format="$%.0f", width="medium", help="Diferencia neta correspondiente a rectificaciones confirmadas 'M'")
                        }
                    )

                    st.markdown("---")
                    tiendas_sust_opciones = sorted([str(x) for x in df_sust_analisis["Tienda"].dropna().unique() if str(x) != "nan"])
                    opciones_tienda_sust = ["Todas las Tiendas"] + tiendas_sust_opciones
                    tienda_final_filtro = st.selectbox("Seleccionar Tienda a Analizar:", opciones_tienda_sust, index=0)

                    df_sust_analisis_filtrada = df_sust_analisis if tienda_final_filtro == "Todas las Tiendas" else df_sust_analisis[df_sust_analisis["Tienda"].astype(str).str.contains(tienda_final_filtro, case=False, na=False)].copy()

                    busqueda_pedido_sust = st.text_input("🔍 Filtrar exclusivamente por Número de Pedido:", "", key="txt_ped_h4_val")
                    if busqueda_pedido_sust:
                        df_sust_analisis_filtrada = df_sust_analisis_filtrada[df_sust_analisis_filtrada["Pedido"].astype(str).str.contains(busqueda_pedido_sust.strip(), case=False, na=False)]

                    st.markdown("### 🔎 Detalle de Rectificaciones de Sustitución y Estados", help="Rectificaciones por sustitución misma familia y diferente familia (Estado: Confirmado, Rechazado y Pendiente)")
                    st.caption("Detalle de sustituciones misma y diferente familia, comparando el costo del faltante y sobrante y el estado de cada rectificación.")

                    cols_detalle_sust = [
                        "Almacén", "Tienda", "Pedido", "Tipo Sustitución", "Área de Salida",
                        "SKU Faltante", "Producto Faltante", "Monto Faltante ($)", "Estado Falta",
                        "SKU Sobrante", "Producto Sobrante", "Monto Sobrante ($)", "Estado Sobra",
                        "Diferencia Monto Neto ($)", "Diferencia Neta Confirmada ($)"
                    ]

                    df_sust_analisis_sorted = df_sust_analisis_filtrada[cols_detalle_sust].sort_values(by="Diferencia Monto Neto ($)", ascending=False).reset_index(drop=True)

                    st.dataframe(
                        df_sust_analisis_sorted,
                        hide_index=True,
                        column_config={
                            "Almacén": st.column_config.Column("Almacén", width="small"),
                            "Tienda": st.column_config.Column("Tienda", width="small"),
                            "Pedido": st.column_config.Column("Pedido", width="medium"),
                            "Tipo Sustitución": st.column_config.Column("Tipo Sustitución", width="medium"),
                            "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                            "SKU Faltante": st.column_config.Column("SKU Falta", width="small"),
                            "Producto Faltante": st.column_config.Column("Descripción Falta", width="large"),
                            "Monto Faltante ($)": st.column_config.NumberColumn("Monto Falta ($)", format="$%.0f", width="small"),
                            "Estado Falta": st.column_config.Column("Estado Falta (M/P/R)", width="small"),
                            "SKU Sobrante": st.column_config.Column("SKU Sobra", width="small"),
                            "Producto Sobrante": st.column_config.Column("Descripción Sobra", width="large"),
                            "Monto Sobrante ($)": st.column_config.NumberColumn("Monto Sobra ($)", format="$%.0f", width="small"),
                            "Estado Sobra": st.column_config.Column("Estado Sobra (M/P/R)", width="small"),
                            "Diferencia Monto Neto ($)": st.column_config.NumberColumn("Dif. Monto Neto ($)", format="$%.0f", width="medium"),
                            "Diferencia Neta Confirmada ($)": st.column_config.NumberColumn("Dif. Neta Conf. ($)", format="$%.0f", width="medium")
                        }
                    )
            else:
                st.info("ℹ️ No existen pedidos de Sustituciones para la selección actual de filtros.")

        with tab4:
            st.subheader("📦 Análisis de Rectificaciones por Área de Salida")
            st.markdown("Consolidado y análisis de pedidos rectificados por **Área de Salida**. Las métricas, gráficos y resumen por sector se enfocan en las rectificaciones confirmadas, mientras que el detalle individual incluye todos los estados (P, R y C).")

            if not df_rect.empty:
                df_r_area_base = df_rect.copy()

                tiendas_area_opt = ["Todas las Tiendas"] + sorted([str(x) for x in df_r_area_base["Tienda"].dropna().unique() if str(x) != "nan"]) if "Tienda" in df_r_area_base.columns else ["Todas las Tiendas"]
                t_area_sel = st.selectbox("Filtrar por Tienda:", tiendas_area_opt, index=0)

                if t_area_sel != "Todas las Tiendas" and "Tienda" in df_r_area_base.columns:
                    df_r_area_base = df_r_area_base[df_r_area_base["Tienda"].astype(str) == str(t_area_sel)]

                if "Area_Salida" not in df_r_area_base.columns:
                    df_r_area_base["Area_Salida"] = "Sin Clasificar"
                else:
                    df_r_area_base["Area_Salida"] = df_r_area_base["Area_Salida"].fillna("Sin Clasificar").astype(str).str.strip()
                    df_r_area_base["Area_Salida"] = df_r_area_base["Area_Salida"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Clasificar")

                col_motivo_area = "Motivo_Clean" if "Motivo_Clean" in df_r_area_base.columns else ("Motivo" if "Motivo" in df_r_area_base.columns else None)
                if col_motivo_area:
                    df_r_area_base["Motivo_Norm"] = df_r_area_base[col_motivo_area].astype(str).str.strip().str.upper()
                else:
                    df_r_area_base["Motivo_Norm"] = "F"

                col_est_tab4 = "Estado_Clean" if "Estado_Clean" in df_r_area_base.columns else ("Estado" if "Estado" in df_r_area_base.columns else None)
                df_r_area_base["Estado_Norm"] = df_r_area_base[col_est_tab4].astype(str).str.strip().str.upper() if col_est_tab4 else "M"
                df_r_area_base["Estado_PRC"] = df_r_area_base["Estado_Norm"].replace({"M": "C"})

                df_r_area_conf = df_r_area_base[df_r_area_base["Estado_Norm"] == "M"].copy()
                df_r_area_conf["Monto_Falta"] = df_r_area_conf.apply(lambda r: abs(float(r["Monto_Rectif"])) if r["Motivo_Norm"] == "F" else 0.0, axis=1)
                df_r_area_conf["Monto_Sobra"] = df_r_area_conf.apply(lambda r: -abs(float(r["Monto_Rectif"])) if r["Motivo_Norm"] == "S" else 0.0, axis=1)
                df_r_area_conf["Monto_Confirmado"] = df_r_area_conf["Monto_Falta"] + df_r_area_conf["Monto_Sobra"]

                tot_areas_unicas = df_r_area_conf["Area_Salida"].nunique()
                tot_pedidos_afect_area = df_r_area_conf["Pedido"].nunique()
                tot_lineas_conf_area = len(df_r_area_conf)
                tot_monto_conf_area = df_r_area_conf["Monto_Confirmado"].sum()

                a1, a2, a3, a4 = st.columns(4)
                a1.metric("📌 Áreas de Salida Involucradas", f"{tot_areas_unicas:,}")
                a2.metric("📦 Pedidos con Rectificación Confirmada", f"{tot_pedidos_afect_area:,}")
                a3.metric("📉 Líneas Confirmadas Totales", f"{tot_lineas_conf_area:,}")
                a4.metric("💰 Monto Confirmado Neto ($)", f"${tot_monto_conf_area:,.2f}")

                st.markdown("---")
                st.markdown("### 📊 Distribución de Monto Confirmado y Líneas Confirmadas por Área de Salida")

                tb_area_graf = df_r_area_conf.groupby("Area_Salida", as_index=False).agg(
                    Pedidos_Rectificados=("Pedido", "nunique"),
                    Lineas_Rectificadas=("Pedido", "count"),
                    Monto_Confirmado=("Monto_Confirmado", "sum")
                ).reset_index(drop=True)

                col_g1, col_g2 = st.columns(2)

                with col_g1:
                    tb_area_graf_monto = tb_area_graf.sort_values(by="Monto_Confirmado", ascending=False).reset_index(drop=True)
                    tb_area_graf_monto["Monto_Texto"] = tb_area_graf_monto["Monto_Confirmado"].apply(lambda x: f"${x:,.0f}")

                    fig_area_monto = px.bar(
                        tb_area_graf_monto, x="Area_Salida", y="Monto_Confirmado",
                        color="Area_Salida", text="Monto_Texto",
                        title="<b>Monto Neto Confirmado ($) por Sector</b>"
                    )
                    fig_area_monto.update_traces(textposition='outside')
                    fig_area_monto.update_layout(
                        xaxis_title="Área de Salida", 
                        yaxis_title="Monto Confirmado ($)",
                        height=390, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        showlegend=False,
                        xaxis=dict(type='category')
                    )
                    st.plotly_chart(fig_area_monto, use_container_width=True)

                with col_g2:
                    tb_area_graf_lineas = tb_area_graf.sort_values(by="Lineas_Rectificadas", ascending=False).reset_index(drop=True)

                    fig_area_lineas = px.bar(
                        tb_area_graf_lineas, x="Area_Salida", y="Lineas_Rectificadas",
                        color="Area_Salida", text="Lineas_Rectificadas",
                        title="<b>Cantidad de Líneas Confirmadas por Sector</b>"
                    )
                    fig_area_lineas.update_traces(textposition='outside')
                    fig_area_lineas.update_layout(
                        xaxis_title="Área de Salida", 
                        yaxis_title="Cantidad de Líneas",
                        height=390, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        showlegend=False,
                        xaxis=dict(type='category')
                    )
                    st.plotly_chart(fig_area_lineas, use_container_width=True)

                st.markdown("---")
                st.markdown("### 📋 Resumen Consolidado por Área de Salida (Solo Rectificaciones Confirmadas)")

                tb_area_matriz = df_r_area_conf.groupby("Area_Salida", as_index=False).agg(
                    Pedidos_Afectados=("Pedido", "nunique"),
                    Lineas_Rectificadas=("Pedido", "count"),
                    Monto_Falta=("Monto_Falta", "sum"),
                    Monto_Sobra=("Monto_Sobra", "sum"),
                    Monto_Confirmado=("Monto_Confirmado", "sum")
                )

                tb_area_matriz["% Participación Pedidos"] = (tb_area_matriz["Pedidos_Afectados"] / tot_pedidos_afect_area * 100.0) if tot_pedidos_afect_area > 0 else 0.0
                tb_area_matriz = tb_area_matriz.sort_values(by="Pedidos_Afectados", ascending=False).reset_index(drop=True)

                tb_area_matriz_disp = tb_area_matriz.rename(columns={
                    "Area_Salida": "Área de Salida",
                    "Pedidos_Afectados": "Pedidos Afectados",
                    "Lineas_Rectificadas": "Líneas Confirmadas",
                    "Monto_Falta": "Monto Falta Conf. ($)",
                    "Monto_Sobra": "Monto Sobra Conf. ($)",
                    "Monto_Confirmado": "Diferencia Neta Confirmada ($)",
                    "% Participación Pedidos": "% Participación Pedidos"
                })

                st.dataframe(
                    tb_area_matriz_disp[["Área de Salida", "Pedidos Afectados", "Líneas Confirmadas", "Monto Falta Conf. ($)", "Monto Sobra Conf. ($)", "Diferencia Neta Confirmada ($)", "% Participación Pedidos"]],
                    hide_index=True,
                    column_config={
                        "Área de Salida": st.column_config.Column("Área de Salida", width="large"),
                        "Pedidos Afectados": st.column_config.NumberColumn("Pedidos Afectados", format="%d", width="medium"),
                        "Líneas Confirmadas": st.column_config.NumberColumn("Líneas Confirmadas", format="%d", width="medium"),
                        "Monto Falta Conf. ($)": st.column_config.NumberColumn("Monto Falta Conf. ($)", format="$%.2f", width="medium"),
                        "Monto Sobra Conf. ($)": st.column_config.NumberColumn("Monto Sobra Conf. ($)", format="$%.2f", width="medium"),
                        "Diferencia Neta Confirmada ($)": st.column_config.NumberColumn("Diferencia Neta Confirmada ($)", format="$%.2f", width="large"),
                        "% Participación Pedidos": st.column_config.NumberColumn("% Participación Pedidos", format="%.2f %%", width="medium")
                    }
                )

                st.markdown("---")
                # ==============================================================
                # 2. DETALLE INDIVIDUAL DE RECTIFICACIONES (P, R Y C)
                # ==============================================================
                st.markdown("### 🔎 Detalle Individual de Rectificaciones por Área de Salida (Estados P, R y C)")

                areas_list_opt = ["Todas las Áreas"] + sorted([str(x) for x in df_r_area_base["Area_Salida"].unique()])
                area_especifica_sel = st.selectbox("Seleccionar Área de Salida a Analizar:", areas_list_opt, index=0)

                df_r_area_det = df_r_area_base.copy()
                if area_especifica_sel != "Todas las Áreas":
                    df_r_area_det = df_r_area_det[df_r_area_det["Area_Salida"].astype(str) == str(area_especifica_sel)]

                busqueda_ped_area = st.text_input("🔍 Filtrar exclusivamente por Número de Pedido:", "", key="txt_ped_h5_val")
                if busqueda_ped_area:
                    df_r_area_det = df_r_area_det[
                        df_r_area_det["Pedido"].astype(str).str.contains(busqueda_ped_area.strip(), case=False, na=False)
                    ]

                col_art_area = "Artículo" if "Artículo" in df_r_area_det.columns else ("SKU" if "SKU" in df_r_area_det.columns else "Producto")
                col_desc_area = "Descripción" if "Descripción" in df_r_area_det.columns else "Producto"

                cols_area_det_disp = [
                    "Almacen", "Tienda", "Pedido", "Area_Salida", 
                    col_art_area, col_desc_area, 
                    "Motivo", "Procedencia", "Estado_PRC", "Monto_Rectif"
                ]

                cols_exist_area = [c for c in cols_area_det_disp if c in df_r_area_det.columns]
                df_area_det_clean = df_r_area_det[cols_exist_area].copy()

                df_area_det_clean = df_area_det_clean.rename(columns={
                    "Almacen": "Almacén",
                    "Tienda": "Tienda",
                    "Pedido": "Pedido",
                    "Area_Salida": "Área de Salida",
                    col_art_area: "SKU",
                    col_desc_area: "Producto / Descripción",
                    "Estado_PRC": "Estado (P/R/C)",
                    "Monto_Rectif": "Monto ($)"
                })

                st.dataframe(
                    df_area_det_clean,
                    hide_index=True,
                    column_config={
                        "Almacén": st.column_config.Column("Almacén", width="small"),
                        "Tienda": st.column_config.Column("Tienda", width="small"),
                        "Pedido": st.column_config.Column("Pedido", width="medium"),
                        "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                        "SKU": st.column_config.Column("SKU", width="small"),
                        "Producto / Descripción": st.column_config.Column("Producto / Descripción", width="large"),
                        "Familia": st.column_config.Column("Familia", width="medium"),
                        "Subfamilia": st.column_config.Column("Subfamilia", width="medium"),
                        "Motivo": st.column_config.Column("Motivo", width="small"),
                        "Procedencia": st.column_config.Column("Procedencia", width="small"),
                        "Estado (P/R/C)": st.column_config.Column("Estado (P/R/C)", width="small", help="'C' = Confirmada | 'P' = Pendiente | 'R' = Rechazada"),
                        "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="medium")
                    }
                )
            else:
                st.info("ℹ️ No hay rectificaciones registradas para el análisis por Área de Salida.")

        with tab5:
            st.subheader("🧩 Rectificaciones de Unidades Sueltas")
            st.markdown("Análisis independiente fuera de la clasificación de SLA para identificar aquellas **líneas rectificadas cuya cantidad enviada o reclamada es menor a un bulto cerrado** (`Unidades < UxB`). Permite **controlar** la incidencia de preparación por unidades sueltas por tienda y sector.")

            if not df_rect.empty:
                df_sueltas = df_rect.copy()
                
                col_est_s = "Estado_Clean" if "Estado_Clean" in df_sueltas.columns else ("Estado" if "Estado" in df_sueltas.columns else None)
                if col_est_s:
                    df_sueltas["Estado_Norm"] = df_sueltas[col_est_s].astype(str).str.strip().str.upper()
                else:
                    df_sueltas["Estado_Norm"] = "M"

                col_art_s = "Artículo" if "Artículo" in df_sueltas.columns else ("SKU" if "SKU" in df_sueltas.columns else "Producto")
                
                if "Es_Unidad_Suelta" not in df_sueltas.columns:
                    col_unid_s = "Unidades_Num" if "Unidades_Num" in df_sueltas.columns else "Pedido"
                    col_uxb_s = "UxB" if "UxB" in df_sueltas.columns else None
                    if col_uxb_s and col_unid_s != "Pedido":
                        df_sueltas["Es_Unidad_Suelta"] = (df_sueltas["UxB"] > 1.0) & (df_sueltas["Unidades_Num"] > 0.0) & (df_sueltas["Unidades_Num"] < df_sueltas["UxB"])
                    else:
                        df_sueltas["Es_Unidad_Suelta"] = False

                df_sueltas_all = df_sueltas[df_sueltas["Es_Unidad_Suelta"] == True].copy()
                df_sueltas_conf = df_sueltas_all[df_sueltas_all["Estado_Norm"].isin(["M", "C", "CONFIRMADA", "APROBADA"])].copy()

                tot_lineas_sueltas = len(df_sueltas_conf)
                tot_pedidos_sueltas = df_sueltas_conf["Pedido"].nunique() if not df_sueltas_conf.empty else 0
                tot_tiendas_sueltas = df_sueltas_conf["Tienda"].nunique() if not df_sueltas_conf.empty else 0
                tot_monto_sueltas = df_sueltas_conf["Monto_Rectif"].sum() if "Monto_Rectif" in df_sueltas_conf.columns else 0.0

                s1, s2, s3, s4 = st.columns(4)
                s1.metric("🧩 Líneas de Unidades Sueltas", f"{tot_lineas_sueltas:,}", help="Total de líneas confirmadas con cantidad menor a un bulto cerrado (UxB)")
                s2.metric("📦 Pedidos Involucrados", f"{tot_pedidos_sueltas:,}", help="Pedidos con rectificaciones confirmadas de unidades sueltas")
                s3.metric("🏪 Tiendas Afectadas", f"{tot_tiendas_sueltas:,}", help="Cantidad de sucursales con rectificaciones confirmadas")
                s4.metric("💰 Impacto Económico ($)", f"${tot_monto_sueltas:,.2f}", help="Monto acumulado correspondiente a rectificaciones confirmadas")

                st.markdown("---")

                if not df_sueltas_all.empty:
                    st.markdown(
                        "### 🏆 Top 15 Tiendas con Mayor Cantidad de Líneas de Unidades Sueltas",
                        help="El Monto Total refleja exclusivamente las rectificaciones confirmadas (Estado 'M'). El % de Aceptación representa la proporción de líneas confirmadas sobre el total de unidades sueltas grabadas por la tienda."
                    )

                    filas_top15_sueltas = []
                    for t_val, grp_t in df_sueltas_all.groupby("Tienda"):
                        tot_grab_t = len(grp_t)
                        grp_conf_t = grp_t[grp_t["Estado_Norm"].isin(["M", "C", "CONFIRMADA", "APROBADA"])]
                        lin_conf_t = len(grp_conf_t)
                        ped_conf_t = grp_conf_t["Pedido"].nunique()
                        unid_conf_t = grp_conf_t["Unidades_Num"].sum() if "Unidades_Num" in grp_conf_t.columns else lin_conf_t
                        monto_conf_t = grp_conf_t["Monto_Rectif"].sum() if "Monto_Rectif" in grp_conf_t.columns else 0.0
                        pct_acep_t = (lin_conf_t / tot_grab_t * 100.0) if tot_grab_t > 0 else 100.0

                        filas_top15_sueltas.append({
                            "Tienda": t_val,
                            "Lineas con Unidades sueltas": lin_conf_t,
                            "Pedidos Afectados": ped_conf_t,
                            "% Aceptación": pct_acep_t,
                            "Unidades Sueltas Totales": unid_conf_t,
                            "Monto Total ($)": monto_conf_t
                        })

                    df_top15_sueltas_disp = pd.DataFrame(filas_top15_sueltas).sort_values(
                        by="Lineas con Unidades sueltas", ascending=False
                    ).head(15).reset_index(drop=True)

                    st.dataframe(
                        df_top15_sueltas_disp[[
                            "Tienda", "Lineas con Unidades sueltas", "Pedidos Afectados",
                            "% Aceptación", "Unidades Sueltas Totales", "Monto Total ($)"
                        ]],
                        hide_index=True,
                        column_config={
                            "Tienda": st.column_config.Column("Tienda", width="small"),
                            "Lineas con Unidades sueltas": st.column_config.NumberColumn("Lineas con Unidades sueltas", format="%d", width="medium"),
                            "Pedidos Afectados": st.column_config.NumberColumn("Pedidos Afectados", format="%d", width="medium"),
                            "% Aceptación": st.column_config.NumberColumn("% Aceptación", format="%.1f %%", width="medium", help="Porcentaje de líneas confirmadas sobre el total grabado por la tienda"),
                            "Unidades Sueltas Totales": st.column_config.NumberColumn("Unidades Sueltas Totales", format="%.0f", width="medium"),
                            "Monto Total ($)": st.column_config.NumberColumn("Monto Total ($)", format="$%.2f", width="medium", help="Monto correspondiente a rectificaciones confirmadas (Estado 'M')")
                        }
                    )

                    st.markdown("---")
                    st.markdown(
                        "### 🔎 Detalle Individual de Líneas Rectificadas como Unidades Sueltas",
                        help="Detalle completo de líneas de unidades sueltas incluyendo estados: M (Confirmada), P (Pendiente) y R (Rechazada)."
                    )

                    tiendas_sueltas_opt = ["Todas las Tiendas"] + sorted([str(x) for x in df_sueltas_all["Tienda"].dropna().unique() if str(x) != "nan"])
                    t_suelta_sel = st.selectbox("Seleccionar Tienda para Controlar Unidades Sueltas:", tiendas_sueltas_opt, index=0)

                    df_det_sueltas = df_sueltas_all.copy()
                    if t_suelta_sel != "Todas las Tiendas":
                        df_det_sueltas = df_det_sueltas[df_det_sueltas["Tienda"].astype(str) == str(t_suelta_sel)]

                    busqueda_ped_suelta = st.text_input("🔍 Filtrar por Número de Pedido (Unidades Sueltas):", "", key="txt_ped_h6")
                    if busqueda_ped_suelta:
                        df_det_sueltas = df_det_sueltas[
                            df_det_sueltas["Pedido"].astype(str).str.contains(busqueda_ped_suelta.strip(), case=False, na=False)
                        ]

                    col_desc_s = "Descripción" if "Descripción" in df_det_sueltas.columns else "Producto"

                    col_motivo_s = "Motivo_Clean" if "Motivo_Clean" in df_det_sueltas.columns else ("Motivo" if "Motivo" in df_det_sueltas.columns else None)
                    if col_motivo_s:
                        df_det_sueltas["Factor_Signo"] = df_det_sueltas[col_motivo_s].astype(str).str.strip().str.upper().apply(lambda x: -1.0 if x == "S" else 1.0)
                    else:
                        df_det_sueltas["Factor_Signo"] = 1.0

                    df_det_sueltas["Monto_Signed"] = df_det_sueltas["Monto_Rectif"] * df_det_sueltas["Factor_Signo"]

                    cols_sueltas_disp = [
                        "Almacen", "Tienda", "Pedido", "Area_Salida", col_art_s, col_desc_s, 
                        "Unidades_Num", "UxB", "Motivo", "Procedencia", "Estado_Norm", "Monto_Signed"
                    ]
                    cols_exist_s = [c for c in cols_sueltas_disp if c in df_det_sueltas.columns]

                    df_sueltas_det_clean = df_det_sueltas[cols_exist_s].copy()
                    df_sueltas_det_clean = df_sueltas_det_clean.rename(columns={
                        "Almacen": "Almacén",
                        "Area_Salida": "Área de Salida",
                        col_art_s: "SKU",
                        col_desc_s: "Producto / Descripción",
                        "Unidades_Num": "Unid. Rectificadas",
                        "UxB": "Cant. por Bulto (UxB)",
                        "Estado_Norm": "Estado (M/P/R)",
                        "Monto_Signed": "Monto ($)"
                    })

                    st.dataframe(
                        df_sueltas_det_clean,
                        hide_index=True,
                        column_config={
                            "Almacén": st.column_config.Column("Almacén", width="small"),
                            "Tienda": st.column_config.Column("Tienda", width="small"),
                            "Pedido": st.column_config.Column("Pedido", width="medium"),
                            "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                            "SKU": st.column_config.Column("SKU", width="small"),
                            "Producto / Descripción": st.column_config.Column("Producto / Descripción", width="large"),
                            "Familia": st.column_config.Column("Familia", width="medium"),
                            "Unid. Rectificadas": st.column_config.NumberColumn("Unid. Rectificadas", format="%.0f", width="small"),
                            "Cant. por Bulto (UxB)": st.column_config.NumberColumn("Cant. por Bulto (UxB)", format="%.0f", width="small"),
                            "Motivo": st.column_config.Column("Motivo", width="small"),
                            "Procedencia": st.column_config.Column("Procedencia", width="small"),
                            "Estado (M/P/R)": st.column_config.Column("Estado (M/P/R)", width="small", help="'M' = Confirmada | 'P' = Pendiente | 'R' = Rechazada"),
                            "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="medium")
                        }
                    )
                else:
                    st.success("🎉 No se registraron rectificaciones de unidades sueltas (< 1 UxB) para la selección actual.")
            else:
                st.info("ℹ️ No hay rectificaciones disponibles para controlar unidades sueltas.")

        with tab6:
            st.subheader("❌ Rectificaciones del Portal: Análisis de Causas Anuladas y Aprobadas")
            st.markdown("Analisis independiente fuera del cálculo del SLA basada exclusivamente en los datos del portal de rectificaciones. Esta vista procesa la totalidad de las rectificaciones Anuladas y Aprobadas, analizando sus motivos registrados y su distribución por Almacén, Área de Salida, Tienda y Mes.")

            if not df_anul.empty:
                df_portal_csv = df_anul.copy()

                # Cruzar área de salida por Pedido de respaldo si no viniera definida
                if "Area_Salida" not in df_portal_csv.columns or df_portal_csv["Area_Salida"].isna().all():
                    mapa_a = {}
                    if not df_sla.empty and "Pedido" in df_sla.columns and "Area_Salida" in df_sla.columns:
                        mapa_a.update(df_sla.set_index("Pedido")["Area_Salida"].to_dict())
                    if not df_rect.empty and "Pedido" in df_rect.columns and "Area_Salida" in df_rect.columns:
                        df_r_v = df_rect[df_rect["Area_Salida"] != "Sin Clasificar"]
                        if not df_r_v.empty:
                            mapa_a.update(df_r_v.set_index("Pedido")["Area_Salida"].to_dict())
                    df_portal_csv["Area_Salida"] = df_portal_csv["Pedido"].map(mapa_a).fillna("Sin Clasificar")

                df_portal_csv["Area_Salida"] = df_portal_csv["Area_Salida"].fillna("Sin Clasificar").astype(str).str.strip()
                df_portal_csv["Area_Salida"] = df_portal_csv["Area_Salida"].replace(["", "nan", "None", "-"], "Sin Clasificar")

                # Normalización de mes probada (soporta explícitamente %d/%m/%Y y %d/%m/%y para 19/10/26 de Octubre)
                col_fec_eval = "Fecha" if ("Fecha" in df_portal_csv.columns and df_portal_csv["Fecha"].notna().any()) else ("Fecha_Modif" if "Fecha_Modif" in df_portal_csv.columns else None)
                if col_fec_eval:
                    s_fec_raw = df_portal_csv[col_fec_eval].astype(str).str.strip().str.replace(".0", "", regex=False)
                    dt_4dig = pd.to_datetime(s_fec_raw, format="%d/%m/%Y", errors="coerce")
                    dt_2dig = pd.to_datetime(s_fec_raw, format="%d/%m/%y", errors="coerce")
                    dt_ymd = pd.to_datetime(s_fec_raw, format="%Y%m%d", errors="coerce")
                    
                    s_num = pd.to_numeric(s_fec_raw.str.replace(",", "."), errors="coerce")
                    mask_excel = s_num.notna() & (s_num > 30000) & (s_num < 70000)
                    dt_ex = pd.Series(pd.NaT, index=df_portal_csv.index, dtype='datetime64[ns]')
                    if mask_excel.any():
                        dt_ex[mask_excel] = pd.to_datetime(s_num[mask_excel], unit="D", origin="1899-12-30", errors="coerce")
                    
                    dt_res = dt_4dig.fillna(dt_2dig).fillna(dt_ymd).fillna(dt_ex)
                    meses_res = dt_res.dt.month.fillna(0).astype(int)
                    
                    # Respaldo por partes de fecha
                    mask_cero = (meses_res == 0)
                    if mask_cero.any():
                        partes = s_fec_raw[mask_cero].str.split(r"[/.-]", expand=True)
                        if partes.shape[1] >= 2:
                            m_cand = pd.to_numeric(partes[1], errors="coerce").fillna(0).astype(int)
                            val = (m_cand >= 1) & (m_cand <= 12)
                            for idx_v in partes[val].index:
                                meses_res.at[idx_v] = int(m_cand.at[idx_v])
                    
                    df_portal_csv["Mes_Num"] = meses_res
                else:
                    df_portal_csv["Mes_Num"] = 0

                mapa_meses_p = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
                df_portal_csv["Nombre_Mes"] = df_portal_csv["Mes_Num"].map(mapa_meses_p).fillna("Sin Mes")

                if "Almacen" not in df_portal_csv.columns:
                    df_portal_csv["Almacen"] = "501"

                df_portal_csv["Etiqueta_Almacen"] = "Almacén " + df_portal_csv["Almacen"].astype(str)

                # FILTRO DE ALMACÉN CON MULTISELECT Y BUSCADOR
                almacenes_portal_opt = sorted([str(x) for x in df_portal_csv["Almacen"].dropna().unique() if str(x) != "nan"])
                
                col_m_alm, col_m_space = st.columns([2.5, 1.5])
                with col_m_alm:
                    alm_portal_sel = st.multiselect(
                        "🏭 Filtrar por Almacén / CD:",
                        options=almacenes_portal_opt,
                        default=[],
                        placeholder="Todos los Almacenes",
                        key="h6_flt_alm",
                        help="Escribe o selecciona almacenes. Si no seleccionas ninguno, se incluyen todos."
                    )

                if alm_portal_sel:
                    df_portal_csv = df_portal_csv[df_portal_csv["Almacen"].astype(str).isin(alm_portal_sel)].copy()

                # Signo: Falta = +, Sobra = -
                if "Tipo" in df_portal_csv.columns and "Monto" in df_portal_csv.columns:
                    df_portal_csv["Factor_Signo"] = df_portal_csv["Tipo"].astype(str).str.strip().str.capitalize().apply(lambda x: -1.0 if "Sobra" in x or x == "S" else 1.0)
                    df_portal_csv["Monto_Signed"] = df_portal_csv["Monto"] * df_portal_csv["Factor_Signo"]
                else:
                    df_portal_csv["Monto_Signed"] = df_portal_csv["Monto"] if "Monto" in df_portal_csv.columns else 0.0

                col_causa_csv = "Causa_Anulacion" if "Causa_Anulacion" in df_portal_csv.columns else ("Motivo" if "Motivo" in df_portal_csv.columns else "Tipo")
                df_portal_csv["Motivo_Norm"] = df_portal_csv[col_causa_csv].fillna("Sin Motivo Especificado").astype(str).str.strip()
                df_portal_csv["Motivo_Norm"] = df_portal_csv["Motivo_Norm"].replace(["", "nan", "None"], "Sin Motivo Especificado")

                col_estado_csv = "Estado" if "Estado" in df_portal_csv.columns else None
                if col_estado_csv:
                    df_portal_csv["Estado_Clean"] = df_portal_csv[col_estado_csv].astype(str).str.strip().str.capitalize()
                else:
                    df_portal_csv["Estado_Clean"] = "Anulada"

                # Separar dataframes Anuladas (Rechazadas) y Aprobadas (Confirmadas)
                df_csv_anul = df_portal_csv[df_portal_csv["Estado_Clean"].str.contains("Anulada|Rechazada|R", case=False, na=False)].copy()
                df_csv_aprob = df_portal_csv[df_portal_csv["Estado_Clean"].str.contains("Aprobada|Confirmada|M", case=False, na=False)].copy()

                if df_csv_anul.empty and df_csv_aprob.empty:
                    df_csv_anul = df_portal_csv.copy()

                tot_lin_anul_csv = len(df_csv_anul)
                tot_monto_anul_csv = df_csv_anul["Monto_Signed"].sum() if not df_csv_anul.empty else 0.0

                tot_lin_aprob_csv = len(df_csv_aprob)
                tot_monto_aprob_csv = df_csv_aprob["Monto_Signed"].sum() if not df_csv_aprob.empty else 0.0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("❌ Líneas Anuladas / Rechazadas", f"{tot_lin_anul_csv:,}")
                c2.metric("💸 Importe Total Anulado ($)", f"${tot_monto_anul_csv:,.0f}")
                c3.metric("✅ Líneas Aprobadas / Confirmadas", f"{tot_lin_aprob_csv:,}")
                c4.metric("💰 Importe Total Aprobado ($)", f"${tot_monto_aprob_csv:,.0f}")

                st.markdown("---")

                # ==============================================================
                # 1. SECCIÓN: CAUSAS DE ANULACIÓN (ANULADAS)
                # ==============================================================
                st.markdown("### 📊 Distribución Porcentual y Cantidad por Causa de Anulación")

                if not df_csv_anul.empty:
                    causas_anul_unicas = sorted([str(x) for x in df_csv_anul["Motivo_Norm"].unique() if str(x).strip() != ""])

                    col_fa1, col_fa2 = st.columns([2.5, 1.5])
                    with col_fa1:
                        causas_sel_anul = st.multiselect(
                            "🔍 Filtrar Sección Anuladas por Causa:",
                            options=causas_anul_unicas,
                            default=[],
                            placeholder="Todas las Causas de Anulación",
                            key="h6_flt_causa_anul",
                            help="Escribe o selecciona causas de anulación. Si no seleccionas ninguna, se muestran todas."
                        )

                    df_csv_anul_sec1 = df_csv_anul[df_csv_anul["Motivo_Norm"].isin(causas_sel_anul)].copy() if causas_sel_anul else df_csv_anul.copy()

                    if not df_csv_anul_sec1.empty:
                        # 1. Gráfico (Adaptativo: Cantidad Absoluta si hay 1 almacén / Porcentaje si hay varios)
                        grp_anul = df_csv_anul_sec1.groupby(["Mes_Num", "Nombre_Mes", "Etiqueta_Almacen"], as_index=False).agg(
                            Cant_Pedidos=("Pedido", "nunique")
                        )

                        meses_presentes_anul = sorted([m for m in grp_anul["Mes_Num"].unique() if m in mapa_meses_p])
                        orden_meses_anul = [mapa_meses_p[m] for m in meses_presentes_anul]

                        mapa_colores_alm_g = {
                            "Almacén 501": "#9B59B6", "Almacén 503": "#2BA884", 
                            "Almacén 504": "#D06A4C", "Almacén 509": "#E09F53", "Almacén 514": "#2B5C8F"
                        }

                        grp_anul["Pedidos"] = grp_anul["Cant_Pedidos"]
                        cant_alm_anul = grp_anul["Etiqueta_Almacen"].nunique()
                        if cant_alm_anul <= 1:
                            # Modo 1 solo Almacén: Mostrar evolución en Cantidad de Pedidos (evita barras planas al 100%)
                            eje_y_anul = "Cant_Pedidos"
                            titulo_y_anul = "Cantidad de Pedidos"
                            rango_y_anul = None
                            grp_anul["Etiqueta_Texto"] = grp_anul["Cant_Pedidos"].apply(lambda v: f"<b>{int(v):,}</b><br>Pedidos")
                            alm_nombre_tit = grp_anul["Etiqueta_Almacen"].iloc[0] if not grp_anul.empty else "Almacén"
                            titulo_graf_anul = f"<b>Evolución Mensual de Pedidos Anulados - {alm_nombre_tit}</b>"
                            hover_dict_anul = {"Pedidos": ":,", "Cant_Pedidos": False}
                        else:
                            # Modo Varios Almacenes: Mostrar Distribución Porcentual Apilada
                            eje_y_anul = "Porcentaje"
                            titulo_y_anul = "Porcentaje de Participación (%)"
                            rango_y_anul = [0, 100]
                            tot_mes_anul = grp_anul.groupby(["Mes_Num", "Nombre_Mes"])["Cant_Pedidos"].transform("sum")
                            grp_anul["Porcentaje"] = (grp_anul["Cant_Pedidos"] / tot_mes_anul * 100.0).fillna(0.0)
                            grp_anul["Etiqueta_Texto"] = grp_anul.apply(lambda r: f"<b>{r['Porcentaje']:.1f}%</b><br>({int(r['Cant_Pedidos']):,} Pedidos)", axis=1)
                            titulo_graf_anul = "<b>Distribución Porcentual y Cantidad por Almacén - Pedidos Anulados</b>"
                            hover_dict_anul = {"Pedidos": ":,", "Porcentaje": ":.2f%", "Cant_Pedidos": False}

                        fig_apilado_anul = px.bar(
                            grp_anul,
                            x="Nombre_Mes",
                            y=eje_y_anul,
                            color="Etiqueta_Almacen",
                            title=titulo_graf_anul,
                            text="Etiqueta_Texto",
                            color_discrete_map=mapa_colores_alm_g,
                            barmode="stack",
                            hover_data=hover_dict_anul
                        )

                        fig_apilado_anul.update_traces(textposition='inside')
                        layout_dict_anul = dict(
                            xaxis=dict(title="Mes", categoryorder="array", categoryarray=orden_meses_anul),
                            yaxis=dict(title=titulo_y_anul),
                            height=410,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            legend_title_text="Almacén"
                        )
                        if rango_y_anul:
                            layout_dict_anul["yaxis"]["range"] = rango_y_anul
                        fig_apilado_anul.update_layout(**layout_dict_anul)

                        st.plotly_chart(fig_apilado_anul, use_container_width=True)

                        st.markdown("---")
                        # 2. Resumen por Causa (incluyendo Tiendas Afectadas)
                        st.markdown("#### 📋 Resumen por Causa de Anulación")

                        df_causas_anul_grp = df_csv_anul_sec1.groupby("Motivo_Norm", as_index=False).agg(
                            Tiendas_Afectadas=("Tienda", "nunique") if "Tienda" in df_csv_anul_sec1.columns else ("Pedido", "nunique"),
                            Pedidos_Afectados=("Pedido", "nunique"),
                            Líneas_Anuladas=("Pedido", "count"),
                            Monto_Total=("Monto_Signed", "sum")
                        ).sort_values(by="Pedidos_Afectados", ascending=False).reset_index(drop=True)

                        df_causas_anul_disp = df_causas_anul_grp.rename(columns={
                            "Motivo_Norm": "Causa / Motivo de Anulación",
                            "Tiendas_Afectadas": "Tiendas Afectadas",
                            "Pedidos_Afectados": "Pedidos",
                            "Líneas_Anuladas": "Líneas Anuladas",
                            "Monto_Total": "Monto Anulado ($)"
                        })

                        st.dataframe(
                            df_causas_anul_disp,
                            hide_index=True,
                            column_config={
                                "Causa / Motivo de Anulación": st.column_config.Column("Causa / Motivo de Anulación", width="large"),
                                "Tiendas Afectadas": st.column_config.NumberColumn("Tiendas Afectadas", format="%d", width="small"),
                                "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="small"),
                                "Líneas Anuladas": st.column_config.NumberColumn("Líneas Anuladas", format="%d", width="small"),
                                "Monto Anulado ($)": st.column_config.NumberColumn("Monto Anulado ($)", format="$%.0f", width="medium")
                            }
                        )

                        st.markdown("---")
                        # 3. Top de Tiendas
                        st.markdown("### 🏆 Top de Tiendas con Mayor Cantidad de Líneas Anuladas")

                        if "Tienda" in df_csv_anul_sec1.columns:
                            tb_top_anul_csv = df_csv_anul_sec1.groupby("Tienda", as_index=False).agg(
                                Líneas_Anuladas=("Pedido", "count"),
                                Pedidos_Afectados=("Pedido", "nunique"),
                                Monto_Total_Anulado=("Monto_Signed", "sum")
                            ).sort_values(by="Líneas_Anuladas", ascending=False).head(15).reset_index(drop=True)

                            tb_top_anul_csv_disp = tb_top_anul_csv[["Tienda", "Líneas_Anuladas", "Pedidos_Afectados", "Monto_Total_Anulado"]].rename(columns={
                                "Líneas_Anuladas": "Líneas Anuladas",
                                "Pedidos_Afectados": "Pedidos",
                                "Monto_Total_Anulado": "Monto Total Anulado ($)"
                            })

                            st.dataframe(
                                tb_top_anul_csv_disp,
                                hide_index=True,
                                column_config={
                                    "Tienda": st.column_config.Column("Tienda", width="medium"),
                                    "Líneas Anuladas": st.column_config.NumberColumn("Líneas Anuladas", format="%d", width="medium"),
                                    "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="medium"),
                                    "Monto Total Anulado ($)": st.column_config.NumberColumn("Monto Total Anulado ($)", format="$%.0f", width="large")
                                }
                            )
                    else:
                        st.info("ℹ️ No hay datos para las causas de anulación seleccionadas.")
                else:
                    st.info("ℹ️ No hay rectificaciones anuladas en la selección actual del portal.")

                st.markdown("---")

                # ==============================================================
                # 2. SECCIÓN: CAUSAS DE APROBACIÓN (APROBADAS)
                # ==============================================================
                st.markdown("### 📊 Distribución Porcentual y Cantidad por Causa de Aprobación")

                if not df_csv_aprob.empty:
                    causas_aprob_unicas = sorted([str(x) for x in df_csv_aprob["Motivo_Norm"].unique() if str(x).strip() != ""])

                    col_fb1, col_fb2 = st.columns([2.5, 1.5])
                    with col_fb1:
                        causas_sel_aprob = st.multiselect(
                            "🔍 Filtrar Sección Aprobadas por Causa:",
                            options=causas_aprob_unicas,
                            default=[],
                            placeholder="Todas las Causas de Aprobación",
                            key="h6_flt_causa_aprob",
                            help="Escribe o selecciona causas de aprobación. Si no seleccionas ninguna, se muestran todas."
                        )

                    df_csv_aprob_sec2 = df_csv_aprob[df_csv_aprob["Motivo_Norm"].isin(causas_sel_aprob)].copy() if causas_sel_aprob else df_csv_aprob.copy()

                    if not df_csv_aprob_sec2.empty:
                        # 1. Gráfico (Adaptativo: Cantidad Absoluta si hay 1 almacén / Porcentaje si hay varios)
                        grp_aprob = df_csv_aprob_sec2.groupby(["Mes_Num", "Nombre_Mes", "Etiqueta_Almacen"], as_index=False).agg(
                            Cant_Pedidos=("Pedido", "nunique")
                        )

                        meses_presentes_aprob = sorted([m for m in grp_aprob["Mes_Num"].unique() if m in mapa_meses_p])
                        orden_meses_aprob = [mapa_meses_p[m] for m in meses_presentes_aprob]

                        grp_aprob["Pedidos"] = grp_aprob["Cant_Pedidos"]
                        cant_alm_aprob = grp_aprob["Etiqueta_Almacen"].nunique()
                        if cant_alm_aprob <= 1:
                            # Modo 1 solo Almacén: Mostrar evolución en Cantidad de Pedidos (evita barras planas al 100%)
                            eje_y_aprob = "Cant_Pedidos"
                            titulo_y_aprob = "Cantidad de Pedidos"
                            rango_y_aprob = None
                            grp_aprob["Etiqueta_Texto"] = grp_aprob["Cant_Pedidos"].apply(lambda v: f"<b>{int(v):,}</b><br>Pedidos")
                            alm_nombre_tit = grp_aprob["Etiqueta_Almacen"].iloc[0] if not grp_aprob.empty else "Almacén"
                            titulo_graf_aprob = f"<b>Evolución Mensual de Pedidos Aprobados - {alm_nombre_tit}</b>"
                            hover_dict_aprob = {"Pedidos": ":,", "Cant_Pedidos": False}
                        else:
                            # Modo Varios Almacenes: Mostrar Distribución Porcentual Apilada
                            eje_y_aprob = "Porcentaje"
                            titulo_y_aprob = "Porcentaje de Participación (%)"
                            rango_y_aprob = [0, 100]
                            tot_mes_aprob = grp_aprob.groupby(["Mes_Num", "Nombre_Mes"])["Cant_Pedidos"].transform("sum")
                            grp_aprob["Porcentaje"] = (grp_aprob["Cant_Pedidos"] / tot_mes_aprob * 100.0).fillna(0.0)
                            grp_aprob["Etiqueta_Texto"] = grp_aprob.apply(lambda r: f"<b>{r['Porcentaje']:.1f}%</b><br>({int(r['Cant_Pedidos']):,} Pedidos)", axis=1)
                            titulo_graf_aprob = "<b>Distribución Porcentual y Cantidad por Almacén - Pedidos Aprobados</b>"
                            hover_dict_aprob = {"Pedidos": ":,", "Porcentaje": ":.2f%", "Cant_Pedidos": False}

                        fig_apilado_aprob = px.bar(
                            grp_aprob,
                            x="Nombre_Mes",
                            y=eje_y_aprob,
                            color="Etiqueta_Almacen",
                            title=titulo_graf_aprob,
                            text="Etiqueta_Texto",
                            color_discrete_map=mapa_colores_alm_g,
                            barmode="stack",
                            hover_data=hover_dict_aprob
                        )

                        fig_apilado_aprob.update_traces(textposition='inside')
                        layout_dict_aprob = dict(
                            xaxis=dict(title="Mes", categoryorder="array", categoryarray=orden_meses_aprob),
                            yaxis=dict(title=titulo_y_aprob),
                            height=410,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            legend_title_text="Almacén"
                        )
                        if rango_y_aprob:
                            layout_dict_aprob["yaxis"]["range"] = rango_y_aprob
                        fig_apilado_aprob.update_layout(**layout_dict_aprob)

                        st.plotly_chart(fig_apilado_aprob, use_container_width=True)

                        st.markdown("---")
                        # 2. Resumen por Causa (incluyendo Tiendas Afectadas)
                        st.markdown("#### 📋 Resumen por Causa de Aprobación")

                        df_causas_aprob_grp = df_csv_aprob_sec2.groupby("Motivo_Norm", as_index=False).agg(
                            Tiendas_Afectadas=("Tienda", "nunique") if "Tienda" in df_csv_aprob_sec2.columns else ("Pedido", "nunique"),
                            Pedidos_Afectados=("Pedido", "nunique"),
                            Líneas_Aprobadas=("Pedido", "count"),
                            Monto_Total=("Monto_Signed", "sum")
                        ).sort_values(by="Pedidos_Afectados", ascending=False).reset_index(drop=True)

                        df_causas_aprob_disp = df_causas_aprob_grp.rename(columns={
                            "Motivo_Norm": "Causa / Motivo de Aprobación",
                            "Tiendas_Afectadas": "Tiendas Afectadas",
                            "Pedidos_Afectados": "Pedidos",
                            "Líneas_Aprobadas": "Líneas Aprobadas",
                            "Monto_Total": "Monto Aprobado ($)"
                        })

                        st.dataframe(
                            df_causas_aprob_disp,
                            hide_index=True,
                            column_config={
                                "Causa / Motivo de Aprobación": st.column_config.Column("Causa / Motivo de Aprobación", width="large"),
                                "Tiendas Afectadas": st.column_config.NumberColumn("Tiendas Afectadas", format="%d", width="small"),
                                "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="small"),
                                "Líneas Aprobadas": st.column_config.NumberColumn("Líneas Aprobadas", format="%d", width="small"),
                                "Monto Aprobado ($)": st.column_config.NumberColumn("Monto Aprobado ($)", format="$%.0f", width="medium")
                            }
                        )

                        st.markdown("---")
                        # 3. Top de Tiendas Aprobadas
                        st.markdown("### 🏆 Top de Tiendas con Mayor Cantidad de Líneas Aprobadas")

                        if "Tienda" in df_csv_aprob_sec2.columns:
                            tb_top_aprob_csv = df_csv_aprob_sec2.groupby("Tienda", as_index=False).agg(
                                Líneas_Aprobadas=("Pedido", "count"),
                                Pedidos_Afectados=("Pedido", "nunique"),
                                Monto_Total_Aprobado=("Monto_Signed", "sum")
                            ).sort_values(by="Líneas_Aprobadas", ascending=False).head(15).reset_index(drop=True)

                            tb_top_aprob_csv_disp = tb_top_aprob_csv[["Tienda", "Líneas_Aprobadas", "Pedidos_Afectados", "Monto_Total_Aprobado"]].rename(columns={
                                "Líneas_Aprobadas": "Líneas Aprobadas",
                                "Pedidos_Afectados": "Pedidos",
                                "Monto_Total_Aprobado": "Monto Total Aprobado ($)"
                            })

                            st.dataframe(
                                tb_top_aprob_csv_disp,
                                hide_index=True,
                                column_config={
                                    "Tienda": st.column_config.Column("Tienda", width="medium"),
                                    "Líneas Aprobadas": st.column_config.NumberColumn("Líneas Aprobadas", format="%d", width="medium"),
                                    "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="medium"),
                                    "Monto Total Aprobado ($)": st.column_config.NumberColumn("Monto Total Aprobado ($)", format="$%.0f", width="large")
                                }
                            )
                    else:
                        st.info("ℹ️ No hay datos para las causas de aprobación seleccionadas.")
                else:
                    st.info("ℹ️ No hay rectificaciones aprobadas registradas en el archivo del portal.")

                st.markdown("---")

                # ==============================================================
                # 3. SECCIÓN: DETALLE INDIVIDUAL DE RECTIFICACIONES REGISTRADAS
                # ==============================================================
                st.markdown("### 🔎 Detalle Individual de Reclamos del Portal")

                tiendas_portal_opt = sorted([str(x) for x in df_portal_csv["Tienda"].dropna().unique() if str(x) != "nan"]) if "Tienda" in df_portal_csv.columns else []
                motivos_portal_opt = sorted([str(x) for x in df_portal_csv["Motivo_Norm"].dropna().unique() if str(x).strip() != ""]) if "Motivo_Norm" in df_portal_csv.columns else []
                
                col_tp1, col_tp2, col_tp3 = st.columns([1.5, 1.5, 1.0])
                with col_tp1:
                    t_portal_sel = st.multiselect(
                        "🏪 Filtrar por Tienda(s) del Portal:",
                        options=tiendas_portal_opt,
                        default=[],
                        placeholder="Todas las Tiendas",
                        key="h6_flt_tienda",
                        help="Escribe o busca tiendas del portal. Si está vacío, se muestran todas."
                    )

                with col_tp2:
                    motivo_portal_sel = st.multiselect(
                        "📋 Filtrar por Motivo / Causa:",
                        options=motivos_portal_opt,
                        default=[],
                        placeholder="Todos los Motivos / Causas",
                        key="h6_flt_motivo",
                        help="Escribe o selecciona uno o varios motivos/causas del portal. Si está vacío, se muestran todos."
                    )

                with col_tp3:
                    busqueda_ped_portal = st.text_input("🔍 Filtrar por Pedido:", "", key="txt_ped_portal")

                df_portal_view = df_portal_csv.copy()

                if t_portal_sel and "Tienda" in df_portal_view.columns:
                    df_portal_view = df_portal_view[df_portal_view["Tienda"].astype(str).isin(t_portal_sel)]

                if motivo_portal_sel and "Motivo_Norm" in df_portal_view.columns:
                    df_portal_view = df_portal_view[df_portal_view["Motivo_Norm"].astype(str).isin(motivo_portal_sel)]

                if busqueda_ped_portal.strip() and "Pedido" in df_portal_view.columns:
                    df_portal_view = df_portal_view[df_portal_view["Pedido"].astype(str).str.contains(busqueda_ped_portal.strip(), case=False, na=False)]

                cols_portal_disp = ["Almacen", "Tienda", "Pedido", "Area_Salida", "Nota_Nro", "Fecha", "Tipo", "Cant_Blt", "Monto_Signed", "Fecha_Modif", "Estado_Clean", "Motivo_Norm", "Estado_RP", "Lote_RPA"]
                cols_portal_exist = [c for c in cols_portal_disp if c in df_portal_view.columns]

                df_portal_clean = df_portal_view[cols_portal_exist].rename(columns={
                    "Almacen": "Almacén",
                    "Tienda": "Tienda",
                    "Pedido": "Pedido",
                    "Area_Salida": "Área de Salida",
                    "Nota_Nro": "Nota Nro",
                    "Fecha": "Fecha",
                    "Tipo": "Tipo (Falta/Sobra)",
                    "Cant_Blt": "Cnt. Blt.",
                    "Monto_Signed": "Monto ($)",
                    "Fecha_Modif": "Fch. Modif.",
                    "Estado_Clean": "Estado Portal",
                    "Motivo_Norm": "Motivo / Causa",
                    "Estado_RP": "Estado RP",
                    "Lote_RPA": "Lote RPA"
                })

                st.dataframe(
                    df_portal_clean,
                    hide_index=True,
                    column_config={
                        "Almacén": st.column_config.Column("Almacén", width="small"),
                        "Tienda": st.column_config.Column("Tienda", width="small"),
                        "Pedido": st.column_config.Column("Pedido", width="medium"),
                        "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                        "Nota Nro": st.column_config.Column("Nota Nro", width="small"),
                        "Fecha": st.column_config.Column("Fecha", width="small"),
                        "Tipo (Falta/Sobra)": st.column_config.Column("Tipo", width="small"),
                        "Cnt. Blt.": st.column_config.NumberColumn("Cnt. Blt.", format="%.2f", width="small"),
                        "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.0f", width="medium"),
                        "Fch. Modif.": st.column_config.Column("Fch. Modif.", width="medium"),
                        "Estado Portal": st.column_config.Column("Estado Portal", width="small"),
                        "Motivo / Causa": st.column_config.Column("Motivo / Causa", width="large"),
                        "Estado RP": st.column_config.Column("Estado RP", width="small"),
                        "Lote RPA": st.column_config.Column("Lote RPA", width="small")
                    }
                )
            else:
                st.info("ℹ️ No se cargaron datos del archivo CSV del portal de rectificaciones.")


        with tab7:
            st.subheader("📦 Rectificaciones con Error de Facturación Master")
            st.markdown("Análisis enfocado exclusivamente a nivel **línea de artículo** para identificar todas aquellas rectificaciones confirmadas que corresponden a desvíos de **Bulto Máster**, independientemente de la clasificación SLA del pedido completo.")

            if not df_rect.empty:
                df_m_lines = df_rect.copy()

                # Filtrar EXCLUSIVAMENTE rectificaciones confirmadas (Estado 'M')
                col_est_tab7 = "Estado_Clean" if "Estado_Clean" in df_m_lines.columns else ("Estado" if "Estado" in df_m_lines.columns else None)
                if col_est_tab7:
                    df_m_lines = df_m_lines[df_m_lines[col_est_tab7].astype(str).str.strip().str.upper().isin(["M", "C", "CONFIRMADA", "APROBADA"])].copy()

                col_art_m = "Artículo" if "Artículo" in df_m_lines.columns else ("SKU" if "SKU" in df_m_lines.columns else "Producto")
                col_desc_m = "Descripción" if "Descripción" in df_m_lines.columns else "Producto"

                def es_linea_master_check(row):
                    es_m_flag = str(row.get("Es_Master", "")).strip().upper() in ["SI", "SÍ"]
                    if not es_m_flag:
                        return False

                    unid = float(row.get("Unidades_Num", 0.0))
                    uxb = float(row.get("UxB", 0.0))
                    bulfm = float(row.get("BULFM", 1.0))

                    # Si las unidades rectificadas son mayores a 0 en un artículo catalogado como Máster
                    if unid > 0.0:
                        return True

                    return False
                df_m_lines["Es_Linea_Master"] = df_m_lines.apply(es_linea_master_check, axis=1)
                df_m_only = df_m_lines[df_m_lines["Es_Linea_Master"] == True].copy()

                tiendas_m_opt = ["Todas las Tiendas"] + sorted([str(x) for x in df_m_only["Tienda"].dropna().unique() if str(x) != "nan"]) if "Tienda" in df_m_only.columns else ["Todas las Tiendas"]
                t_master_sel = st.selectbox("🏪 Filtrar por Tienda:", tiendas_m_opt, index=0, key="sb_tienda_h7")

                if t_master_sel != "Todas las Tiendas" and "Tienda" in df_m_only.columns:
                    df_m_only = df_m_only[df_m_only["Tienda"].astype(str) == str(t_master_sel)]

                tot_lineas_m = len(df_m_only)
                tot_pedidos_m = df_m_only["Pedido"].nunique() if not df_m_only.empty else 0
                tot_tiendas_m = df_m_only["Tienda"].nunique() if not df_m_only.empty else 0
                tot_monto_m = df_m_only["Monto_Rectif"].sum() if "Monto_Rectif" in df_m_only.columns else 0.0

                b1, b2, b3, b4 = st.columns(4)
                b1.metric("📦 Líneas con Error Master", f"{tot_lineas_m:,}", help="Total de líneas confirmadas con error en bulto máster")
                b2.metric("📋 Pedidos Involucrados", f"{tot_pedidos_m:,}", help="Pedidos con rectificaciones confirmadas por error máster")
                b3.metric("🏪 Tiendas Afectadas", f"{tot_tiendas_m:,}", help="Cantidad de sucursales con rectificaciones confirmadas")
                b4.metric("💰 Impacto Económico ($)", f"${tot_monto_m:,.2f}", help="Monto acumulado de las rectificaciones confirmadas")

                st.markdown("---")

                if not df_m_only.empty:
                    st.markdown("### 🏆 Top de Artículos con Mayor Cantidad de Líneas Rectificadas")
                    st.caption("Detalle de artículos con cantidad total de líneas rectificadas confirmadas y desglose de líneas por cada almacén.")

                    # Agrupación base por Artículo
                    base_art = df_m_only.groupby([col_art_m, col_desc_m], as_index=False).agg(
                        Líneas_Totales=("Pedido", "count"),
                        Unidades_Totales=("Unidades_Num", "sum") if "Unidades_Num" in df_m_only.columns else ("Pedido", "count"),
                        Monto_Total=("Monto_Rectif", "sum") if "Monto_Rectif" in df_m_only.columns else ("Pedido", "count")
                    )

                    # Desglose de cantidad de líneas por Almacén
                    alm_cols = sorted([str(x) for x in df_m_only["Almacen"].dropna().unique() if str(x) != "nan"])
                    if alm_cols:
                        pv_alm = df_m_only.pivot_table(
                            index=[col_art_m, col_desc_m],
                            columns="Almacen",
                            values="Pedido",
                            aggfunc="count",
                            fill_value=0
                        )
                        pv_alm.columns = [f"Alm. {c}" for c in pv_alm.columns]
                        pv_alm = pv_alm.reset_index()
                        tb_art_resumen = base_art.merge(pv_alm, on=[col_art_m, col_desc_m], how="left")
                    else:
                        tb_art_resumen = base_art

                    tb_art_resumen = tb_art_resumen.sort_values(by="Líneas_Totales", ascending=False).reset_index(drop=True)

                    tb_art_disp = tb_art_resumen.rename(columns={
                        col_art_m: "SKU",
                        col_desc_m: "Descripción del Artículo",
                        "Líneas_Totales": "Líneas Rectificadas",
                        "Unidades_Totales": "Unidades Totales",
                        "Monto_Total": "Monto Total ($)"
                    })

                    # Construir configuración dinámica de columnas
                    col_config_top_art = {
                        "SKU": st.column_config.Column("SKU", width="small"),
                        "Descripción del Artículo": st.column_config.Column("Descripción del Artículo", width="large"),
                        "Líneas Rectificadas": st.column_config.NumberColumn("Líneas Rectif.", format="%d", width="small"),
                        "Unidades Totales": st.column_config.NumberColumn("Unidades Totales", format="%.0f", width="small"),
                        "Monto Total ($)": st.column_config.NumberColumn("Monto Total ($)", format="$%.2f", width="medium")
                    }
                    for alm_name in alm_cols:
                        col_config_top_art[f"Alm. {alm_name}"] = st.column_config.NumberColumn(f"Alm. {alm_name}", format="%d", width="small")

                    st.dataframe(
                        tb_art_disp,
                        hide_index=True,
                        column_config=col_config_top_art
                    )

                    st.markdown("---")
                    st.markdown("### 🔎 Detalle Individual de Líneas Rectificadas por Error Master")

                    busqueda_ped_m = st.text_input("🔍 Filtrar por Número de Pedido (Líneas Master):", "", key="txt_ped_h8")
                    df_det_m = df_m_only.copy()
                    if busqueda_ped_m:
                        df_det_m = df_det_m[
                            df_det_m["Pedido"].astype(str).str.contains(busqueda_ped_m.strip(), case=False, na=False)
                        ]

                    cols_m_disp = [
                        "Almacen", "Tienda", "Pedido", "Area_Salida", col_art_m, col_desc_m, 
                        "UxB", "BULFM", "Es_Master", "Unidades_Num", "Motivo", "Procedencia", "Estado", "Monto_Rectif"
                    ]
                    cols_exist_m = [c for c in cols_m_disp if c in df_det_m.columns]

                    df_m_det_clean = df_det_m[cols_exist_m].copy()

                    if "Fecha de Grabación" in df_det_m.columns:
                        f_s = df_det_m["Fecha de Grabación"].astype(str).str.strip()
                        f_d = pd.to_datetime(f_s, format="%Y%m%d", errors="coerce")
                        m_na = f_d.isna()
                        if m_na.any():
                            f_d[m_na] = pd.to_datetime(f_s[m_na], dayfirst=True, errors="coerce")
                        df_m_det_clean["Fecha Grabación"] = f_d.dt.strftime("%d/%m/%Y").fillna(f_s)

                    df_m_det_clean = df_m_det_clean.rename(columns={
                        "Almacen": "Almacén",
                        "Area_Salida": "Área de Salida",
                        col_art_m: "SKU",
                        col_desc_m: "Producto / Descripción",
                        "BULFM": "BxM",
                        "Es_Master": "Master",
                        "Unidades_Num": "Unid. Rectificadas",
                        "Monto_Signed": "Monto ($)"
                    })

                    st.dataframe(
                        df_m_det_clean,
                        hide_index=True,
                        column_config={
                            "Almacén": st.column_config.Column("Almacén", width="small"),
                            "Tienda": st.column_config.Column("Tienda", width="small"),
                            "Pedido": st.column_config.Column("Pedido", width="medium"),
                            "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                            "SKU": st.column_config.Column("SKU", width="small"),
                            "Producto / Descripción": st.column_config.Column("Producto / Descripción", width="large"),
                            "UxB": st.column_config.NumberColumn("UxB", format="%.0f", width="small"),
                            "BxM": st.column_config.NumberColumn("BxM", format="%.0f", width="small"),
                            "Master": st.column_config.Column("Master", width="small"),
                            "Unid. Rectificadas": st.column_config.NumberColumn("Unid. Rectificadas", format="%.0f", width="small"),
                            "Motivo": st.column_config.Column("Motivo", width="small"),
                            "Procedencia": st.column_config.Column("Procedencia", width="small"),
                            "Estado": st.column_config.Column("Estado", width="small"),
                            "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="medium")
                        }
                    )
                else:
                    st.success("🎉 No se registraron líneas de rectificación confirmadas con Error Facturación Master para la selección realizada.")
            else:
                st.info("ℹ️ No hay rectificaciones confirmadas disponibles para analizar el error de facturación máster.")

        with tab8:
            st.subheader("📖 Glosario Operativo y Modelo SLA")
            st.markdown("Resumen ejecutivo de reglas de negocio, escalas de puntuación y definiciones de casuísticas aplicadas en el cálculo del SLA.")
            
            st.markdown("### 📋 Reglas de Puntaje y Evaluación SLA por Pedido")
            
            matriz_p = pd.DataFrame([
                {
                    "Casuística Operativa": "Pedido Perfecto",
                    "Descuento Aplicado": "0",
                    "Descripción": "Pedido sin rectificaciones",
                    "Lógica y Límites": ""
                },
                {
                    "Casuística Operativa": "Sobrante Neto",
                    "Descuento Aplicado": "0",
                    "Descripción": "Pedido con rectificación de sobra",
                    "Lógica y Límites": "Solo sobra"
                },
                {
                    "Casuística Operativa": "Sustitución Misma Subfamilia",
                    "Descuento Aplicado": "-2.5",
                    "Descripción": "Pedido con rectificación de falta y sobra en artículos de igual subfamilia",
                    "Lógica y Límites": "Igual cantidad de lineas S=F misma sub familia"
                },
                {
                    "Casuística Operativa": "Sustitución Distinta Subfamilia",
                    "Descuento Aplicado": "-4.5",
                    "Descripción": "Pedido con rectificación de falta y sobra en artículos de distintas subfamilias",
                    "Lógica y Límites": "Igual cantidad de lineas S=F distinta sub familia"
                },
                {
                    "Casuística Operativa": "Falta/Sobra",
                    "Descuento Aplicado": "-5.5",
                    "Descripción": "Pedido con rectificación de falta y sobra",
                    "Lógica y Límites": "S y F < a 12 lineas no equitativas"
                },
                {
                    "Casuística Operativa": "Faltante Neto",
                    "Descuento Aplicado": "-6",
                    "Descripción": "Pedido con rectificación de solo falta",
                    "Lógica y Límites": "< 10 lineas solo F"
                },
                {
                    "Casuística Operativa": "Formato no entregado",
                    "Descuento Aplicado": "-10",
                    "Descripción": "Pedido con rectificación de solo falta de más de 10 líneas",
                    "Lógica y Límites": "> 10 lineas solo F"
                },
                {
                    "Casuística Operativa": "Error facturación master",
                    "Descuento Aplicado": "-6",
                    "Descripción": "Pedido con rectificación de falta en bultos Master",
                    "Lógica y Límites": "Solo master,la cantidad rectificada coincide con múltiplos de caja máster o diferencia máster"
                },
                {
                    "Casuística Operativa": "Etiquetas Cambiadas",
                    "Descuento Aplicado": "-9",
                    "Descripción": "Faltas y sobras simultáneas mayores o iguales a 12 líneas rectificadas",
                    "Lógica y Límites": "S y F > a 12 lineas no equitativas"
                },
                {
                    "Casuística Operativa": "Rectificación Almacén",
                    "Descuento Aplicado": "-10",
                    "Descripción": "Pedido con rectificaciones grabadas directamente por el centro de distribución / almacén (Procedencia 'G')",
                    "Lógica y Límites": "Al menos 1 línea grabada con Procedencia 'G'"
                }
            ])
            st.dataframe(
                matriz_p,
                hide_index=True,
                column_config={
                    "Casuística Operativa": st.column_config.Column("Casuística Operativa", width="medium"),
                    "Descuento Aplicado": st.column_config.Column("Descuento Aplicado", width="small"),
                    "Descripción": st.column_config.Column("Descripción", width="large"),
                    "Lógica y Límites": st.column_config.Column("Lógica y Límites", width="large")
                }
            )

            st.markdown("---")
            st.markdown("### 📚 Glosario de Conceptos y Siglas Operativas")
            st.markdown("""
* **SLA (Service Level Agreement)**: Nivel de servicio medido en escala de 1.0 a 10.0 puntos por pedido entregado.
* **Procedencia 'G'**: Generado / detectado en Centro de Distribución (Almacén).
* **Procedencia 'T'**: Registrado / detectado por la Tienda.
* **Motivo 'F'**: Rectificación por Falta de mercadería.
* **Motivo 'S'**: Rectificación por Sobra de mercadería.
* **Estado 'M'**: Rectificación Confirmada.
* **Estado 'P'**: Rectificación Pendiente.
* **Estado 'R'**: Rectificación Rechazada / Anulada.
* **UxB**: Unidades por Bulto / Caja estándar.
* **BxM**: Bultos por Bulto Máster.
* **UxM**: Unidades Totales por Bulto Máster ($UxM = UxB 	imes BxM$).
            """)

except Exception as e:
    st.error(f'Error cargando el tablero: {e}')