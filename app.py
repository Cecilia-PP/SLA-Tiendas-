# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

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

        if not df_rect.empty:
            if "BULFM" not in df_rect.columns:
                if "UxM" in df_rect.columns and "UxB" in df_rect.columns:
                    df_rect["BULFM"] = df_rect.apply(lambda r: (r["UxM"] / r["UxB"]) if r["UxB"] > 0 else 1.0, axis=1)
                else:
                    df_rect["BULFM"] = 1.0

        return df_sla, df_rect
    return pd.DataFrame(), pd.DataFrame()

@st.cache_data
def cargar_datos_anulaciones(df_sla=None, df_rect=None):
    df_a = pd.DataFrame()
    if os.path.exists("Tablero_Anulaciones_Detalle.parquet"):
        df_a = pd.read_parquet("Tablero_Anulaciones_Detalle.parquet")
    else:
        archivos = [f for f in os.listdir(".") if ("anula" in f.lower() or "causa" in f.lower()) and f.endswith(".csv")]
        if not archivos and os.path.exists("Datos_mensuales"):
            archivos = [os.path.join("Datos_mensuales", f) for f in os.listdir("Datos_mensuales") if ("anula" in f.lower() or "causa" in f.lower()) and f.endswith(".csv")]
        
        if archivos:
            try:
                df_a = pd.read_csv(archivos[0], sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
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
                if "Pedido" in df_a.columns: df_a["Pedido"] = df_a["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
                if "Tienda" in df_a.columns: df_a["Tienda"] = df_a["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
                if "Almacen" in df_a.columns: df_a["Almacen"] = df_a["Almacen"].astype(str).str.strip()
                if "Monto" in df_a.columns: df_a["Monto"] = pd.to_numeric(df_a["Monto"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
                if "Cant_Blt" in df_a.columns: df_a["Cant_Blt"] = pd.to_numeric(df_a["Cant_Blt"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
            except Exception as e:
                print(f"Error cargando respaldo anulaciones: {e}")

    # ⚡ BUSCAR MAPEO DE ÁREA DIRECTAMENTE EN LOS CSVs DE ÁREA Y RESPALDOS
    if not df_a.empty and "Pedido" in df_a.columns:
        mapa_area = {}

        # 1. Cargar diccionario de los CSVs de Área de Salida disponibles
        import glob
        archivos_area = glob.glob("*[Aa]rea*[Ss]alida*.csv") + glob.glob(os.path.join("Datos_mensuales", "*[Aa]rea*[Ss]alida*.csv"))
        
        for fa in set(archivos_area):
            try:
                df_area_temp = pd.read_csv(fa, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
                df_area_temp.columns = df_area_temp.columns.str.strip().str.upper()
                
                cols_p = [c for c in df_area_temp.columns if any(k in c for k in ["PEDIDO", "Nº DE PEDIDO", "Nº PEDIDO", "NRO_PEDIDO"])]
                cols_a = [c for c in df_area_temp.columns if any(k in c for k in ["AREA", "ÁREA", "SALIDA", "DESCRIPCION", "SECTOR"])]
                cols_t = [c for c in df_area_temp.columns if any(k in c for k in ["TIENDA", "SUCURSAL", "COD_SUC_DES"])]

                if cols_p and cols_a:
                    col_p, col_a = cols_p[0], cols_a[0]
                    df_area_temp["Ped_Clean"] = df_area_temp[col_p].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
                    df_area_temp["Area_Clean"] = df_area_temp[col_a].astype(str).str.strip()
                    
                    df_val = df_area_temp[(df_area_temp["Ped_Clean"] != "") & (~df_area_temp["Area_Clean"].isin(["", "nan", "None", "0"]))]
                    if not df_val.empty:
                        mapa_area.update(df_val.set_index("Ped_Clean")["Area_Clean"].to_dict())
            except Exception as e:
                print(f"Error procesando CSV de área {fa}: {e}")

        # 2. Respaldos desde df_sla y df_rect
        if df_sla is not None and not df_sla.empty and "Pedido" in df_sla.columns and "Area_Salida" in df_sla.columns:
            for k, v in df_sla.set_index("Pedido")["Area_Salida"].to_dict().items():
                if k not in mapa_area or mapa_area[k] == "Sin Clasificar":
                    mapa_area[k] = v

        if df_rect is not None and not df_rect.empty and "Pedido" in df_rect.columns and "Area_Salida" in df_rect.columns:
            df_r_valid = df_rect[df_rect["Area_Salida"] != "Sin Clasificar"]
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

try:
    df_sla, df_rect = cargar_datos_sla()
    df_anul = cargar_datos_anulaciones(df_sla, df_rect)

    if not df_sla.empty:
        st.sidebar.header("🔍 Filtros de Búsqueda")

        # 1. FILTRO DE ALMACÉN
        if "Almacen" in df_sla.columns:
            almacenes = sorted([str(x) for x in df_sla["Almacen"].dropna().unique()])
            almacen_sel = st.sidebar.multiselect("Almacén:", almacenes, default=almacenes)
            df_sla = df_sla[df_sla["Almacen"].astype(str).isin(almacen_sel)]
            if not df_rect.empty and "Almacen" in df_rect.columns:
                df_rect = df_rect[df_rect["Almacen"].astype(str).isin(almacen_sel)]

        # 2. FILTRO DE GESTIÓN / ZONA EN DESPLEGABLE EXPANDIBLE
        if "Gestion" in df_sla.columns and df_sla["Gestion"].notna().any():
            with st.sidebar.expander("🗺️ Gestión / Zona", expanded=False):
                gestiones = sorted([str(x) for x in df_sla["Gestion"].dropna().unique()])
                gestion_sel = st.multiselect("Seleccionar Gestión / Zona:", gestiones, default=gestiones, key="ms_gestion_sidebar")
                df_sla = df_sla[df_sla["Gestion"].astype(str).isin(gestion_sel)]
                if not df_rect.empty and "Gestion" in df_rect.columns:
                    df_rect = df_rect[df_rect["Gestion"].astype(str).isin(gestion_sel)]

        # 3. FILTRO DE FRANQUICIADO / SUPERVISOR EN DESPLEGABLE EXPANDIBLE
        if "Responsable_Tienda" in df_sla.columns and df_sla["Responsable_Tienda"].notna().any():
            with st.sidebar.expander("👤 Franquiciado / Supervisor", expanded=False):
                responsables = sorted([str(x) for x in df_sla["Responsable_Tienda"].dropna().unique()])
                resp_sel = st.multiselect("Seleccionar Supervisor(es):", responsables, default=responsables, key="ms_resp_sidebar")
                df_sla = df_sla[df_sla["Responsable_Tienda"].astype(str).isin(resp_sel)]
                if not df_rect.empty and "Responsable_Tienda" in df_rect.columns:
                    df_rect = df_rect[df_rect["Responsable_Tienda"].astype(str).isin(resp_sel)]

        # 4. FILTRO DE TIENDA EN DESPLEGABLE EXPANDIBLE
        if "Tienda" in df_sla.columns:
            with st.sidebar.expander("🏪 Tienda", expanded=False):
                tiendas = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
                tienda_sel = st.multiselect("Seleccionar Tienda(s):", tiendas, default=tiendas, key="ms_tienda_sidebar")
                df_sla = df_sla[df_sla["Tienda"].astype(str).isin(tienda_sel)]
                if not df_rect.empty and "Tienda" in df_rect.columns:
                    df_rect = df_rect[df_rect["Tienda"].astype(str).isin(tienda_sel)]

        # 5. FILTRO DINÁMICO DE ÁREA DE SALIDA EN DESPLEGABLE EXPANDIBLE
        areas_sla = set(df_sla["Area_Salida"].dropna().astype(str).unique()) if "Area_Salida" in df_sla.columns else set()
        areas_rect = set(df_rect["Area_Salida"].dropna().astype(str).unique()) if not df_rect.empty and "Area_Salida" in df_rect.columns else set()
        areas_universo = areas_sla.union(areas_rect)
        areas_disponibles = sorted([a for a in areas_universo if a.strip() not in ["19", "24"]])

        if areas_disponibles:
            with st.sidebar.expander("📦 Área de Salida", expanded=False):
                area_sel = st.multiselect("Seleccionar Área(s) de Salida:", areas_disponibles, default=areas_disponibles, key="ms_area_sidebar")
                if "Area_Salida" in df_sla.columns:
                    df_sla = df_sla[df_sla["Area_Salida"].astype(str).isin(area_sel)]
                if not df_rect.empty and "Area_Salida" in df_rect.columns:
                    df_rect = df_rect[df_rect["Area_Salida"].astype(str).isin(area_sel)]

        # 6. FILTRO DE CASUÍSTICA / ESTADO PEDIDO EN DESPLEGABLE EXPANDIBLE
        if "Casuistica" in df_sla.columns:
            with st.sidebar.expander("📋 Casuística / Estado Pedido", expanded=False):
                orden_cas_filtro = [
                    "Pedido Perfecto", "Sobrante Neto", 
                    "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                    "Falta/Sobra", "Faltante Neto", "Formato no entregado", "Error facturación master", 
                    "Etiquetas Cambiadas"
                ]
                casuisticas_presentes = [c for c in orden_cas_filtro if c in df_sla["Casuistica"].dropna().unique()]
                otras_cas = [c for c in df_sla["Casuistica"].dropna().unique() if c not in casuisticas_presentes]
                casuisticas_opciones = casuisticas_presentes + otras_cas

                casuistica_sel = st.multiselect("Seleccionar Casuística(s):", casuisticas_opciones, default=casuisticas_opciones, key="ms_casuistica_sidebar")
                df_sla = df_sla[df_sla["Casuistica"].isin(casuistica_sel)]
                
                if not df_rect.empty:
                    pedidos_validos_cas = set(df_sla["Pedido"].dropna().unique())
                    df_rect = df_rect[df_rect["Pedido"].isin(pedidos_validos_cas)]

        # 7. FILTRO DE ESTADO DE RECTIFICACIÓN (M / P / R)
        if not df_rect.empty and "Estado" in df_rect.columns:
            st.sidebar.markdown("---")
            st.sidebar.header("📋 Estado de Rectificación")
            estados_opciones = sorted([str(x) for x in df_rect["Estado"].dropna().unique() if str(x) != "nan"])
            estado_sel = st.sidebar.multiselect(
                "Estado Rectificación (M=Conf, P=Pend, R=Rech):", 
                estados_opciones, 
                default=estados_opciones,
                help="M = Confirmada | P = Pendiente | R = Rechazada"
            )
            df_rect = df_rect[df_rect["Estado"].isin(estado_sel)]

        # 8. FILTROS MAESTROS EN DESPLEGABLE EXPANDIBLE
        if not df_rect.empty:
            st.sidebar.markdown("---")
            with st.sidebar.expander("🏷️ Filtros del Maestro", expanded=False):
                if "Familia" in df_rect.columns and df_rect["Familia"].notna().any():
                    familias = sorted([str(x) for x in df_rect["Familia"].dropna().unique()])
                    fam_sel = st.multiselect("Familia:", familias, default=familias, key="ms_fam_sidebar")
                    df_rect = df_rect[df_rect["Familia"].astype(str).isin(fam_sel)]

                if "Subfamilia" in df_rect.columns and df_rect["Subfamilia"].notna().any():
                    subfamilias = sorted([str(x) for x in df_rect["Subfamilia"].dropna().unique()])
                    subfam_sel = st.multiselect("Subfamilia:", subfamilias, default=subfamilias, key="ms_subfam_sidebar")
                    df_rect = df_rect[df_rect["Subfamilia"].astype(str).isin(subfam_sel)]

                if "Es_Master" in df_rect.columns and df_rect["Es_Master"].notna().any():
                    masters = sorted([str(x) for x in df_rect["Es_Master"].dropna().unique()])
                    master_sel = st.multiselect("Producto Master (Sí/No):", masters, default=masters, key="ms_master_sidebar")
                    df_rect = df_rect[df_rect["Es_Master"].astype(str).isin(master_sel)]

            pedidos_filtrados_maestro = set(df_rect["Pedido"].dropna().unique())
            df_sla = df_sla[df_sla["Pedido"].isin(pedidos_filtrados_maestro) | (df_sla["Casuistica"] == "Pedido Perfecto")]

        if "Año" in df_sla.columns and df_sla["Año"].notna().any():
            anios = sorted([int(x) for x in df_sla["Año"].dropna().unique()], reverse=True)
            anio_sel = st.sidebar.multiselect("Año:", anios, default=anios)
            df_sla = df_sla[df_sla["Año"].isin(anio_sel) | df_sla["Año"].isna()]

        if "Mes" in df_sla.columns and df_sla["Mes"].notna().any():
            meses = sorted([int(x) for x in df_sla["Mes"].dropna().unique()])
            mes_sel = st.sidebar.multiselect("Mes:", meses, default=meses)
            df_sla = df_sla[df_sla["Mes"].isin(mes_sel) | df_sla["Mes"].isna()]

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
            "🏪 2. Auditoría Práctica por Tienda",
            "🔄 3. Análisis de Sustituciones",
            "📦 4. Rectificaciones por Área de Salida",
            "🧩 5. Análisis de Unidades Sueltas",
            "❌ 6. Rectificaciones del Portal",
            "📦 7. Error Facturación Master (Líneas)",
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

            colores_cas = {
                "Sobrante Neto": "#0077B6", "Sustitución Misma Subfamilia": "#80ED99",
                "Sustitución Distinta Subfamilia": "#FF9E00", "Falta/Sobra": "#4CC9F0", 
                "Faltante Neto": "#E63946", "Formato no entregado": "#FFE066", "Error facturación master": "#7209B7", 
                "Etiquetas Cambiadas": "#2B2D42"
            }

            fig_comb = make_subplots(specs=[[{"secondary_y": True}]])
            casuisticas_orden = [
                "Sobrante Neto", "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                "Falta/Sobra", "Faltante Neto", "Formato no entregado", "Error facturación master", "Etiquetas Cambiadas"
            ]
            
            for cas in casuisticas_orden:
                df_c = df_cas_mes[df_cas_mes["Casuistica"] == cas].sort_values("Mes_Num")
                if not df_c.empty:
                    fig_comb.add_trace(go.Bar(
                        x=df_c["Mes_Num"], 
                        y=df_c["Cantidad_Pedidos"], 
                        name=cas, 
                        marker_color=colores_cas.get(cas, "#999999"), 
                        text=df_c["Cantidad_Pedidos"], 
                        textposition="inside"
                    ), secondary_y=False)

            fig_comb.add_trace(go.Scatter(
                x=df_lineas_mes["Mes_Num"], 
                y=df_lineas_mes["Cant_Lineas_Rectificadas"], 
                name="Líneas Rectificadas", 
                mode="lines+markers+text", 
                line=dict(color="#00B4D8", width=4.0), 
                marker=dict(size=10, color="#03045E"), 
                text=[f"{int(x):,}" for x in df_lineas_mes["Cant_Lineas_Rectificadas"]], 
                textposition="top center"
            ), secondary_y=True)

            fig_comb.update_layout(
                barmode="stack", height=420, 
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", 
                legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
                xaxis=dict(
                    title="Mes",
                    tickmode="array",
                    tickvals=meses_ordenados,
                    ticktext=orden_nombres_meses
                )
            )
            st.plotly_chart(fig_comb, use_container_width=True)

            st.markdown("---")
            st.markdown("### 📈 Distribución de rectificaciones por casuística")
            tot_p = len(df_sla)
            df_sla_tab1_cas = df_sla.copy()
            df_sla_tab1_cas["Casuistica"] = df_sla_tab1_cas["Casuistica"].astype(str).str.strip()

            cas_sum = df_sla_tab1_cas.groupby("Casuistica", as_index=False).agg(
                Pedidos_Totales=("Pedido", "count"), 
                Lineas_Rectificadas=("Lineas_Rectificadas_Confirmadas", "sum") if "Lineas_Rectificadas_Confirmadas" in df_sla_tab1_cas.columns else ("Pedido", "count")
            )
            cas_sum["% Participación Pedidos"] = (cas_sum["Pedidos_Totales"] / tot_p) * 100.0 if tot_p > 0 else 0.0
            
            orden_cas = [
                "Pedido Perfecto", "Sobrante Neto", 
                "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                "Falta/Sobra", "Faltante Neto", "Formato no entregado", "Error facturación master", 
                "Etiquetas Cambiadas"
            ]
            cas_sum["Casuistica_Cat"] = pd.Categorical(cas_sum["Casuistica"], categories=orden_cas, ordered=True)
            cas_sum = cas_sum.sort_values("Casuistica_Cat").drop(columns=["Casuistica_Cat"]).reset_index(drop=True)

            cas_sum_display = cas_sum.rename(columns={
                "Casuistica": "Casuística",
                "Pedidos_Totales": "Pedidos Totales",
                "Lineas_Rectificadas": "Líneas Rectificadas",
                "% Participación Pedidos": "% Participación Pedidos"
            })

            st.dataframe(
                cas_sum_display[["Casuística", "Pedidos Totales", "Líneas Rectificadas", "% Participación Pedidos"]],
                hide_index=True,
                column_config={
                    "Casuística": st.column_config.Column("Casuística", width="medium"),
                    "Pedidos Totales": st.column_config.NumberColumn("Pedidos Totales", format="%d", width="medium"),
                    "Líneas Rectificadas": st.column_config.NumberColumn("Líneas Rectificadas", format="%d", width="medium"),
                    "% Participación Pedidos": st.column_config.NumberColumn("% Participación Pedidos", format="%.2f %%", width="medium")
                }
            )

            st.markdown("### 🏪 Detalle por Franquiciado / Supervisor")

            if "Responsable_Tienda" in df_sla.columns:
                lista_supervisores = ["Todos los Franquiciados / Supervisores"] + sorted([str(x) for x in df_sla["Responsable_Tienda"].dropna().unique()])
                sup_sel_hoja1 = st.selectbox("Filtrar por Franquiciado / Supervisor:", lista_supervisores, index=0)
            else:
                sup_sel_hoja1 = "Todos los Franquiciados / Supervisores"

            df_sla_h1_resp = df_sla.copy()
            df_rect_h1_resp = df_rect.copy() if not df_rect.empty else pd.DataFrame()

            if sup_sel_hoja1 != "Todos los Franquiciados / Supervisores":
                df_sla_h1_resp = df_sla_h1_resp[df_sla_h1_resp["Responsable_Tienda"].astype(str) == str(sup_sel_hoja1)]
                if not df_rect_h1_resp.empty and "Responsable_Tienda" in df_rect_h1_resp.columns:
                    df_rect_h1_resp = df_rect_h1_resp[df_rect_h1_resp["Responsable_Tienda"].astype(str) == str(sup_sel_hoja1)]

            col_tiendas_lbl = "Total\nTiendas"
            col_totales_lbl = "Pedidos\nTotales"
            col_rectif_lbl = "Pedidos con\nRectificaciones"
            col_lin_lbl = "Líneas\nRectificadas"
            col_part_lin_lbl = "% Líneas\nConfirmadas"
            col_sla_lbl = "Puntaje SLA\n(1 a 10)"

            group_cols_resp = ["Responsable_Tienda"] if "Responsable_Tienda" in df_sla_h1_resp.columns else ["Tienda"]
            tb_resp_base = df_sla_h1_resp.groupby(group_cols_resp, as_index=False).agg(
                Total_Tiendas=("Tienda", "nunique"), 
                Pedidos_Totales=("Pedido", "count"),
                Pedidos_Con_Rectificaciones=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()), 
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )

            if not df_rect_h1_resp.empty and "Responsable_Tienda" in df_rect_h1_resp.columns:
                col_est = "Estado_Clean" if "Estado_Clean" in df_rect_h1_resp.columns else ("Estado" if "Estado" in df_rect_h1_resp.columns else "Pedido")
                tb_rect_counts = df_rect_h1_resp.groupby("Responsable_Tienda", as_index=False).agg(
                    Lineas_Grabadas_Totales=("Pedido", "count"),
                    Lineas_Confirmadas_M=(col_est, lambda x: (x.astype(str).str.strip().str.upper() == "M").sum() if col_est != "Pedido" else len(x))
                )
                tb_resp = tb_resp_base.merge(tb_rect_counts, on="Responsable_Tienda", how="left").fillna({"Lineas_Grabadas_Totales": 0, "Lineas_Confirmadas_M": 0})
            else:
                tb_resp = tb_resp_base.copy()
                tb_resp["Lineas_Grabadas_Totales"] = 0
                tb_resp["Lineas_Confirmadas_M"] = 0

            tb_resp["Puntos_Posibles"] = tb_resp["Pedidos_Totales"] * 10.0
            tb_resp["Puntaje SLA"] = (tb_resp["Puntos_Obtenidos"] / tb_resp["Puntos_Posibles"]) * 10.0
            tb_resp["Puntaje SLA"] = tb_resp["Puntaje SLA"].fillna(0.0)
            tb_resp["% Líneas Confirmadas"] = (tb_resp["Lineas_Confirmadas_M"] / tb_resp["Lineas_Grabadas_Totales"] * 100.0).fillna(0.0)

            tb_resp_sorted = tb_resp.sort_values(by="Puntaje SLA", ascending=True).reset_index(drop=True)
            tot_tiendas_global = df_sla_h1_resp["Tienda"].nunique() if "Tienda" in df_sla_h1_resp.columns else 0
            tot_lin_grabadas_global = tb_resp["Lineas_Grabadas_Totales"].sum()
            tot_lin_confirmadas_global = tb_resp["Lineas_Confirmadas_M"].sum()
            pct_lineas_conf_global = (tot_lin_confirmadas_global / tot_lin_grabadas_global * 100.0) if tot_lin_grabadas_global > 0 else 0.0

            fila_total_resp = pd.DataFrame([{
                "Responsable_Tienda": "Total General", "Total_Tiendas": tot_tiendas_global, "Pedidos_Totales": tot_pedidos_global,
                "Pedidos_Con_Rectificaciones": tot_pedidos_rectif_global, "Lineas_Grabadas_Totales": tot_lin_grabadas_global,
                "% Líneas Confirmadas": pct_lineas_conf_global, "Puntaje SLA": sla_global
            }])

            tb_resp_display = pd.concat([tb_resp_sorted, fila_total_resp], ignore_index=True)

            tb_resp_disp_clean = tb_resp_display.rename(columns={
                "Responsable_Tienda": "Franquiciado / Supervisor",
                "Total_Tiendas": col_tiendas_lbl,
                "Pedidos_Totales": col_totales_lbl,
                "Pedidos_Con_Rectificaciones": col_rectif_lbl,
                "Lineas_Grabadas_Totales": col_lin_lbl,
                "% Líneas Confirmadas": col_part_lin_lbl,
                "Puntaje SLA": col_sla_lbl
            })

            cols_resp_order = [
                "Franquiciado / Supervisor", col_tiendas_lbl,
                col_totales_lbl, col_rectif_lbl,
                col_lin_lbl, col_part_lin_lbl, col_sla_lbl
            ]

            st.dataframe(
                tb_resp_disp_clean[cols_resp_order],
                hide_index=True,
                column_config={
                    "Franquiciado / Supervisor": st.column_config.Column("Franquiciado / Supervisor", width="large"),
                    col_tiendas_lbl: st.column_config.NumberColumn(col_tiendas_lbl, format="%d", width="small"),
                    col_totales_lbl: st.column_config.NumberColumn(col_totales_lbl, format="%d", width="small"),
                    col_rectif_lbl: st.column_config.NumberColumn(col_rectif_lbl, format="%d", width="small"),
                    col_lin_lbl: st.column_config.NumberColumn(col_lin_lbl, format="%d", width="small"),
                    col_part_lin_lbl: st.column_config.NumberColumn(col_part_lin_lbl, format="%.2f %%", width="small"),
                    col_sla_lbl: st.column_config.NumberColumn(col_sla_lbl, format="%.2f ⭐", width="small")
                }
            )

            st.markdown("---")
            st.markdown("### 🏬 Detalle por Almacén, Tienda y Gestión")

            group_cols_alm = ["Almacen", "Tienda"]
            if "Gestion" in df_sla.columns:
                group_cols_alm.append("Gestion")

            tb_alm_base = df_sla.groupby(group_cols_alm, as_index=False).agg(
                Pedidos_Totales=("Pedido", "count"),
                Pedidos_Con_Rectificaciones=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()),
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )

            if not df_rect.empty and "Tienda" in df_rect.columns:
                col_est_alm = "Estado_Clean" if "Estado_Clean" in df_rect.columns else ("Estado" if "Estado" in df_rect.columns else "Pedido")
                tb_rect_counts_alm = df_rect.groupby("Tienda", as_index=False).agg(
                    Lineas_Grabadas_Totales=("Pedido", "count"),
                    Lineas_Confirmadas_M=(col_est_alm, lambda x: (x.astype(str).str.strip().str.upper() == "M").sum() if col_est_alm != "Pedido" else len(x))
                )
                tb_alm_tienda = tb_alm_base.merge(tb_rect_counts_alm, on="Tienda", how="left").fillna({"Lineas_Grabadas_Totales": 0, "Lineas_Confirmadas_M": 0})
            else:
                tb_alm_tienda = tb_alm_base.copy()
                tb_alm_tienda["Lineas_Grabadas_Totales"] = 0
                tb_alm_tienda["Lineas_Confirmadas_M"] = 0

            tb_alm_tienda["Puntos_Posibles"] = tb_alm_tienda["Pedidos_Totales"] * 10.0
            tb_alm_tienda["Puntaje SLA"] = (tb_alm_tienda["Puntos_Obtenidos"] / tb_alm_tienda["Puntos_Posibles"]) * 10.0
            tb_alm_tienda["Puntaje SLA"] = tb_alm_tienda["Puntaje SLA"].fillna(0.0)
            tb_alm_tienda["% Líneas Confirmadas"] = (tb_alm_tienda["Lineas_Confirmadas_M"] / tb_alm_tienda["Lineas_Grabadas_Totales"] * 100.0).fillna(0.0)

            tb_alm_tienda_sorted = tb_alm_tienda.sort_values(by="Puntaje SLA", ascending=True).reset_index(drop=True)

            tot_lin_grabadas_alm = tb_alm_tienda["Lineas_Grabadas_Totales"].sum()
            tot_lin_conf_alm = tb_alm_tienda["Lineas_Confirmadas_M"].sum()
            pct_lineas_conf_alm_global = (tot_lin_conf_alm / tot_lin_grabadas_alm * 100.0) if tot_lin_grabadas_alm > 0 else 0.0

            fila_dict_alm = {
                "Almacen": "Total General",
                "Tienda": "—",
                "Pedidos_Totales": tot_pedidos_global,
                "Pedidos_Con_Rectificaciones": tot_pedidos_rectif_global,
                "Lineas_Grabadas_Totales": tot_lin_grabadas_alm,
                "% Líneas Confirmadas": pct_lineas_conf_alm_global,
                "Puntaje SLA": sla_global
            }
            if "Gestion" in group_cols_alm:
                fila_dict_alm["Gestion"] = "—"

            fila_total_alm = pd.DataFrame([fila_dict_alm])

            tb_alm_tienda_display = pd.concat([tb_alm_tienda_sorted, fila_total_alm], ignore_index=True)

            rename_dict_alm = {
                "Almacen": "Almacén", "Tienda": "Tienda", "Gestion": "Gestión",
                "Pedidos_Totales": col_totales_lbl, "Pedidos_Con_Rectificaciones": col_rectif_lbl,
                "Lineas_Grabadas_Totales": col_lin_lbl, "% Líneas Confirmadas": col_part_lin_lbl,
                "Puntaje SLA": col_sla_lbl
            }

            tb_alm_tienda_display = tb_alm_tienda_display.rename(columns=rename_dict_alm)

            cols_order_alm = ["Almacén", "Tienda"]
            if "Gestión" in tb_alm_tienda_display.columns:
                cols_order_alm.append("Gestión")

            cols_order_alm.extend([
                col_totales_lbl, col_rectif_lbl, col_lin_lbl, col_part_lin_lbl, col_sla_lbl
            ])

            st.dataframe(
                tb_alm_tienda_display[cols_order_alm],
                hide_index=True,
                column_config={
                    "Almacén": st.column_config.Column("Almacén", width="small"),
                    "Tienda": st.column_config.Column("Tienda", width="small"),
                    "Gestión": st.column_config.Column("Gestión", width="medium"),
                    col_totales_lbl: st.column_config.NumberColumn(col_totales_lbl, format="%d", width="small"),
                    col_rectif_lbl: st.column_config.NumberColumn(col_rectif_lbl, format="%d", width="small"),
                    col_lin_lbl: st.column_config.NumberColumn(col_lin_lbl, format="%d", width="small"),
                    col_part_lin_lbl: st.column_config.NumberColumn(col_part_lin_lbl, format="%.2f %%", width="small"),
                    col_sla_lbl: st.column_config.NumberColumn(col_sla_lbl, format="%.2f ⭐", width="small")
                }
            )

        # HOJA 2: AUDITORÍA PRÁCTICA POR TIENDA
        with tab2:
            st.subheader("🏪 Auditoría Práctica y Detalle de Rectificaciones por Tienda")
            
            tiendas_unicas = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
            opciones_tienda = ["Ninguna", "Todas las Tiendas"] + tiendas_unicas
            
            c_tienda, c_cas = st.columns([2, 2])
            with c_tienda:
                t_sel = st.selectbox("Seleccionar Tienda a Auditar:", opciones_tienda, index=0)
            
            # FILTRO DESPLEGABLE DE CASUÍSTICAS EN HOJA 2
            orden_cas_tab3 = [
                "Todas las Casuísticas",
                "Sobrante Neto", "Sustitución Misma Subfamilia", 
                "Sustitución Distinta Subfamilia", "Falta/Sobra", 
                "Faltante Neto", "Formato no entregado", "Error facturación master", 
                "Etiquetas Cambiadas"
            ]
            casuisticas_presentes_tab3 = [c for c in orden_cas_tab3 if c == "Todas las Casuísticas" or c in df_sla["Casuistica"].dropna().unique()]
            
            with c_cas:
                cas_sel_tab3 = st.selectbox("Filtrar por Casuística / Estado Pedido:", casuisticas_presentes_tab3, index=0)

            if t_sel == "Ninguna":
                st.info("👈 Selecciona una **Tienda** específica o la opción **'Todas las Tiendas'** para desplegar el resumen y detalle de rectificaciones.")
            else:
                # 1. Filtrado por Tienda
                if t_sel == "Todas las Tiendas":
                    df_aud_sla = df_sla.copy()
                    df_aud_rect = df_rect.copy() if not df_rect.empty else pd.DataFrame()
                else:
                    df_aud_sla = df_sla[df_sla["Tienda"].astype(str) == str(t_sel)].copy()
                    df_aud_rect = df_rect[df_rect["Tienda"].astype(str) == str(t_sel)].copy() if not df_rect.empty else pd.DataFrame()

                # 2. Filtrado por Casuística Seleccionada en Hoja 2
                if cas_sel_tab3 != "Todas las Casuísticas":
                    df_aud_sla = df_aud_sla[df_aud_sla["Casuistica"] == cas_sel_tab3]
                    if not df_aud_rect.empty:
                        pedidos_cas_filtrados = set(df_aud_sla["Pedido"].dropna().unique())
                        df_aud_rect = df_aud_rect[df_aud_rect["Pedido"].isin(pedidos_cas_filtrados)]

                tot_p_t = len(df_aud_sla)
                tot_p_rect_t = (df_aud_sla["Casuistica"] != "Pedido Perfecto").sum()
                pts_posibles_t = tot_p_t * 10.0
                pts_obtenidos_t = df_aud_sla["Puntos_Obtenidos"].sum()
                nota_sla_t = (pts_obtenidos_t / pts_posibles_t * 10.0) if pts_posibles_t > 0 else 0.0
                
                tot_lineas_rect_t = len(df_aud_rect) if not df_aud_rect.empty else 0

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("⭐ Puntaje SLA Tienda", f"{nota_sla_t:.2f} / 10.0")
                m2.metric("📦 Pedidos Totales Recibidos", f"{tot_p_t:,}")
                m3.metric("⚠️ Pedidos con Rectificaciones", f"{tot_p_rect_t:,}")
                m4.metric("📉 Líneas Rectificadas Totales", f"{tot_lineas_rect_t:,}")

                st.markdown("---")
                st.subheader("📋 Resumen de Pedidos Rectificados por Tienda")
                
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

                        conteo_f = df_aud_rect[df_aud_rect["Motivo_Norm"] == "F"].groupby("Pedido").size().to_dict()
                        conteo_s = df_aud_rect[df_aud_rect["Motivo_Norm"] == "S"].groupby("Pedido").size().to_dict()
                        conteo_tot = df_aud_rect.groupby("Pedido").size().to_dict()

                        conteo_master_si = df_aud_rect[df_aud_rect["Es_Master"] == "Sí"].groupby("Pedido").size().to_dict()
                        conteo_master_no = df_aud_rect[df_aud_rect["Es_Master"] == "No"].groupby("Pedido").size().to_dict()

                        unid_f = df_aud_rect[df_aud_rect["Motivo_Norm"] == "F"].groupby("Pedido")["Unidades_Num"].sum().to_dict()
                        unid_s = df_aud_rect[df_aud_rect["Motivo_Norm"] == "S"].groupby("Pedido")["Unidades_Num"].sum().to_dict()

                        df_pedidos_rect_tienda["Líneas Faltantes"] = df_pedidos_rect_tienda["Pedido"].map(conteo_f).fillna(0).astype(int)
                        df_pedidos_rect_tienda["Líneas Sobrantes"] = df_pedidos_rect_tienda["Pedido"].map(conteo_s).fillna(0).astype(int)
                        
                        df_pedidos_rect_tienda["Master No"] = df_pedidos_rect_tienda["Pedido"].map(conteo_master_no).fillna(0).astype(int)
                        df_pedidos_rect_tienda["Master Sí"] = df_pedidos_rect_tienda["Pedido"].map(conteo_master_si).fillna(0).astype(int)

                        df_pedidos_rect_tienda["Líneas Totales"] = df_pedidos_rect_tienda["Pedido"].map(conteo_tot).fillna(0).astype(int)

                        df_pedidos_rect_tienda["Unidades Faltantes"] = df_pedidos_rect_tienda["Pedido"].map(unid_f).fillna(0.0).astype(int)
                        df_pedidos_rect_tienda["Unidades Sobrantes"] = df_pedidos_rect_tienda["Pedido"].map(unid_s).fillna(0.0).astype(int)
                    else:
                        df_pedidos_rect_tienda["Líneas Faltantes"] = 0
                        df_pedidos_rect_tienda["Líneas Sobrantes"] = 0
                        df_pedidos_rect_tienda["Master No"] = 0
                        df_pedidos_rect_tienda["Master Sí"] = 0
                        df_pedidos_rect_tienda["Líneas Totales"] = 0
                        df_pedidos_rect_tienda["Unidades Faltantes"] = 0
                        df_pedidos_rect_tienda["Unidades Sobrantes"] = 0

                    df_pedidos_rect_tienda_disp = df_pedidos_rect_tienda[[
                        "Tienda", "Pedido", "Casuistica", 
                        "Líneas Faltantes", "Líneas Sobrantes", 
                        "Master No", "Master Sí",
                        "Unidades Faltantes", "Unidades Sobrantes", 
                        "Líneas Totales", "Puntos_Obtenidos"
                    ]].copy()

                    df_pedidos_rect_tienda_disp = df_pedidos_rect_tienda_disp.rename(columns={
                        "Tienda": "Tienda",
                        "Pedido": "Pedido Rectificado",
                        "Casuistica": "Casuística Obtenida",
                        "Puntos_Obtenidos": "Puntaje SLA (0-10)"
                    })

                    st.dataframe(
                        df_pedidos_rect_tienda_disp,
                        hide_index=True,
                        column_config={
                            "Tienda": st.column_config.NumberColumn("Tienda", format="%d", width="small"),
                            "Pedido Rectificado": st.column_config.Column("Pedido Rectificado", width="medium"),
                            "Casuística Obtenida": st.column_config.Column("Casuística Obtenida", width="large"),
                            "Líneas Faltantes": st.column_config.NumberColumn("Líneas Faltantes (F)", format="%d", width="small"),
                            "Líneas Sobrantes": st.column_config.NumberColumn("Líneas Sobrantes (S)", format="%d", width="small"),
                            "Master No": st.column_config.NumberColumn("Master No", format="%d", width="small"),
                            "Master Sí": st.column_config.NumberColumn("Master Sí", format="%d", width="small"),
                            "Unidades Faltantes": st.column_config.NumberColumn("Unid. Faltantes (F)", format="%d", width="small"),
                            "Unidades Sobrantes": st.column_config.NumberColumn("Unid. Sobrantes (S)", format="%d", width="small"),
                            "Líneas Totales": st.column_config.NumberColumn("Líneas Totales", format="%d", width="small"),
                            "Puntaje SLA (0-10)": st.column_config.NumberColumn("Puntaje SLA", format="%.1f ⭐", width="medium")
                        }
                    )
                else:
                    st.info("ℹ️ No hay pedidos rectificados para la selección realizada.")

                st.markdown("---")
                glosario_txt = """GLOSARIO:
1. Procedencia:
   • 'G' = Almacén (Generado/detectado en Centro de Distribución)
   • 'T' = Tienda (Registrado/detectado en tienda)
2. Motivo:
   • 'F' = Falta (Faltante de mercadería)
   • 'S' = Sobra (Sobrante de mercadería)
3. Estado:
   • 'M' = Confirmada | 'P' = Pendiente | 'R' = Rechazada"""

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
                        "Almacen", "Pedido", "Area_Salida", "Nº Rectificación", "Fecha de Grabación", "Artículo", 
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
                            "Pedido": st.column_config.Column("Pedido", width="small"),
                            "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                            "N° Rectif.": st.column_config.Column("N° Rectif.", width="small"),
                            "Fecha Grabación": st.column_config.Column("Fecha", width="small"),
                            "Artículo": st.column_config.Column("SKU", width="small"),
                            "Descripción": st.column_config.Column("Producto / Descripción", width="large"),
                            "Familia": st.column_config.Column("Familia", width="medium"),
                            "Subfamilia": st.column_config.Column("Subfamilia", width="medium"),
                            "UxB": st.column_config.NumberColumn("UxB", format="%.0f", width="small"),
                            "BxM": st.column_config.NumberColumn("BxM", format="%.0f", width="small"),
                            "Master": st.column_config.Column("Master", width="small"),
                            "Motivo": st.column_config.Column("Motivo", width="small"),
                            "Procedencia": st.column_config.Column("Procedencia", width="small"),
                            "Estado": st.column_config.Column("Estado", width="small"),
                            "Unid. Grabadas": st.column_config.NumberColumn("Unid. Grabadas", format="%d", width="small"),
                            "Unid. Abonadas": st.column_config.NumberColumn("Unid. Abonadas", format="%d", width="small"),
                            "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="small")
                        }
                    )
                else:
                    st.success("🎉 La selección actual no presenta rectificaciones de artículos.")

        # HOJA 3: ANÁLISIS EXCLUSIVO DE SUSTITUCIÓN DISTINTA SUBFAMILIA
        with tab3:
            st.subheader("🔄 Análisis de Casos: Sustitución Distinta Subfamilia (Faltante > Sobrante)")
            st.markdown("Auditoría de pedidos clasificados como **'Sustitución Distinta Subfamilia'** detectados y grabados por la **Tienda (Procedencia 'T')** donde el producto **FALTANTE** posee un valor monetario **mayor** al producto **SOBRANTE** entregado.")

            df_sust_cas = df_sla[df_sla["Casuistica"] == "Sustitución Distinta Subfamilia"].copy()
            pedidos_sust_distinta = set(df_sust_cas["Pedido"].dropna().unique())

            if not df_rect.empty and pedidos_sust_distinta:
                df_r_sust = df_rect[
                    (df_rect["Pedido"].isin(pedidos_sust_distinta)) & 
                    (df_rect["Procedencia"].astype(str).str.strip().str.upper() == "T")
                ].copy()
                
                col_motivo_s = "Motivo_Clean" if "Motivo_Clean" in df_r_sust.columns else ("Motivo" if "Motivo" in df_r_sust.columns else None)
                if col_motivo_s:
                    df_r_sust["Motivo_Norm"] = df_r_sust[col_motivo_s].astype(str).str.strip().str.upper()
                else:
                    df_r_sust["Motivo_Norm"] = "F"

                df_r_sust["Estado_Norm"] = df_r_sust["Estado"].astype(str).str.strip().str.upper() if "Estado" in df_r_sust.columns else "M"

                col_art_lbl = "Artículo" if "Artículo" in df_r_sust.columns else ("SKU" if "SKU" in df_r_sust.columns else "Producto")
                col_desc_lbl = "Descripción" if "Descripción" in df_r_sust.columns else "Producto"

                filas_comparativas = []

                for ped, grp in df_r_sust.groupby("Pedido"):
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

                            if monto_f > monto_s:
                                dif_valor = monto_f - monto_s
                                monto_conf = (monto_f if est_f == "M" else 0.0) - (monto_s if est_s == "M" else 0.0)

                                filas_comparativas.append({
                                    "Almacén": almacen_val,
                                    "Tienda": tienda_val,
                                    "Pedido": ped,
                                    "Área de Salida": area_salida_val,
                                    "SKU Faltante": sku_f,
                                    "Producto Faltante": desc_f,
                                    "Monto Faltante ($)": monto_f,
                                    "SKU Sobrante": sku_s,
                                    "Producto Sobrante": desc_s,
                                    "Monto Sobrante ($)": monto_s,
                                    "Diferencia Valor ($)": dif_valor,
                                    "Diferencia Neta Confirmada ($)": max(0.0, monto_conf)
                                })

                if filas_comparativas:
                    df_sust_analisis = pd.DataFrame(filas_comparativas)

                    tot_pedidos_sust_desf = int(df_sust_analisis["Pedido"].nunique())
                    tot_perdida_monto = float(df_sust_analisis["Diferencia Valor ($)"].sum())

                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("🚨 Pedidos Sustitución Distinta Subfamilia (Desfavorable en Tienda)", f"{tot_pedidos_sust_desf:,}")
                    col_m2.metric("💸 Pérdida de Valor Total ($)", f"${tot_perdida_monto:,.2f}")

                    st.markdown("---")
                    st.markdown("### 🏆 Top 10 de Tiendas con Mayor Cantidad de Pedidos Afectados")

                    tb_top10_tiendas = df_sust_analisis.groupby("Tienda", as_index=False).agg(
                        Pedidos_Afectados=("Pedido", "nunique"),
                        Diferencia_Total_Pérdida=("Diferencia Valor ($)", "sum")
                    ).sort_values(by="Diferencia_Total_Pérdida", ascending=False).head(10).reset_index(drop=True)

                    tb_top10_tiendas = tb_top10_tiendas.rename(columns={
                        "Tienda": "Tienda",
                        "Pedidos_Afectados": "Pedidos Afectados",
                        "Diferencia_Total_Pérdida": "Diferencia Valor ($)"
                    })

                    st.dataframe(
                        tb_top10_tiendas[["Tienda", "Pedidos Afectados", "Diferencia Valor ($)"]],
                        hide_index=True,
                        column_config={
                            "Tienda": st.column_config.Column("Tienda", width="medium"),
                            "Pedidos Afectados": st.column_config.NumberColumn("Pedidos Afectados", format="%d", width="medium"),
                            "Diferencia Valor ($)": st.column_config.NumberColumn("Diferencia Valor ($)", format="$%.2f", width="large")
                        }
                    )

                    st.markdown("---")
                    
                    tiendas_sust_opciones = sorted([str(x) for x in df_sust_analisis["Tienda"].dropna().unique() if str(x) != "nan"])
                    opciones_tienda_sust = ["Todas las Tiendas"] + tiendas_sust_opciones
                    
                    t_sust_sel = st.selectbox("Seleccionar Tienda a Auditar:", opciones_tienda_sust, index=0)
                    tienda_final_filtro = t_sust_sel

                    st.markdown("### 📦 Pedidos con Mayor Diferencia Total de Pérdida")

                    cols_ped_top = [
                        "Almacén", "Tienda", "Pedido", "Área de Salida",
                        "Monto Falta ($)", "Monto Sobra ($)", 
                        "Diferencia Neta Confirmada ($)"
                    ]

                    glosario_sust_txt = """CÁLCULO DE RECTIFICACIÓN DE SUSTITUCIÓN:
1. Monto Falta ($): Suma del importe abonado en ítems faltantes.
2. Monto Sobra ($): Suma del importe abonado en ítems sobrantes.
3. Diferencia Neta Confirmada ($): Pérdida monetaria neta correspondiente exclusivamente a rectificaciones confirmadas por tienda (Estado 'M')."""

                    if True:
                        df_pedidos_top_perdida = df_sust_analisis.groupby(["Almacén", "Tienda", "Pedido", "Área de Salida"], as_index=False).agg(
                            Monto_Falta_Total=("Monto Faltante ($)", "sum"),
                            Monto_Sobra_Total=("Monto Sobrante ($)", "sum"),
                            Monto_Confirmado=("Diferencia Neta Confirmada ($)", "sum"),
                            Diferencia_Total_Pérdida=("Diferencia Valor ($)", "sum")
                        )

                        if tienda_final_filtro != "Todas las Tiendas":
                            df_pedidos_top_perdida = df_pedidos_top_perdida[
                                df_pedidos_top_perdida["Tienda"].astype(str).str.contains(tienda_final_filtro, case=False, na=False)
                            ]

                        df_pedidos_top_perdida = df_pedidos_top_perdida.sort_values(by="Diferencia_Total_Pérdida", ascending=False).reset_index(drop=True)

                        df_pedidos_top_perdida_disp = df_pedidos_top_perdida.rename(columns={
                            "Almacén": "Almacén",
                            "Tienda": "Tienda",
                            "Pedido": "Pedido",
                            "Área de Salida": "Área de Salida",
                            "Monto_Falta_Total": "Monto Falta ($)",
                            "Monto_Sobra_Total": "Monto Sobra ($)",
                            "Monto_Confirmado": "Diferencia Neta Confirmada ($)"
                        })

                        st.dataframe(
                            df_pedidos_top_perdida_disp[cols_ped_top],
                            hide_index=True,
                            column_config={
                                "Almacén": st.column_config.Column("Almacén", width="small"),
                                "Tienda": st.column_config.Column("Tienda", width="small"),
                                "Pedido": st.column_config.Column("Pedido", width="medium"),
                                "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                                "Monto Falta ($)": st.column_config.NumberColumn("Monto Falta ($)", format="$%.2f", width="medium"),
                                "Monto Sobra ($)": st.column_config.NumberColumn("Monto Sobra ($)", format="$%.2f", width="medium"),
                                "Diferencia Neta Confirmada ($)": st.column_config.NumberColumn("Diferencia Neta Confirmada ($)", format="$%.2f", width="large")
                            }
                        )

                        st.markdown("---")

                        st.markdown("### 📋 Detalle Individual por Tienda, Pedido y Artículos de Sustitución", help=glosario_sust_txt)

                        if tienda_final_filtro == "Todas las Tiendas":
                            df_sust_analisis_filtrada = df_sust_analisis.copy()
                        else:
                            df_sust_analisis_filtrada = df_sust_analisis[
                                df_sust_analisis["Tienda"].astype(str).str.contains(tienda_final_filtro, case=False, na=False)
                            ].copy()

                        busqueda_pedido_sust = st.text_input("🔍 Filtrar exclusivamente por Número de Pedido:", "", key="txt_ped_h4_val")
                        if busqueda_pedido_sust:
                            df_sust_analisis_filtrada = df_sust_analisis_filtrada[
                                df_sust_analisis_filtrada["Pedido"].astype(str).str.contains(busqueda_pedido_sust.strip(), case=False, na=False)
                            ]

                        if not df_sust_analisis_filtrada.empty:
                            cols_detalle_sust = [
                                "Almacén", "Tienda", "Pedido", "Área de Salida",
                                "SKU Faltante", "Producto Faltante", "Monto Faltante ($)", 
                                "SKU Sobrante", "Producto Sobrante", "Monto Sobrante ($)", 
                                "Diferencia Neta Confirmada ($)"
                            ]

                            df_sust_analisis_sorted = df_sust_analisis_filtrada[cols_detalle_sust].sort_values(by="Diferencia Neta Confirmada ($)", ascending=False).reset_index(drop=True)

                            st.dataframe(
                                df_sust_analisis_sorted,
                                hide_index=True,
                                column_config={
                                    "Almacén": st.column_config.Column("Almacén", width="small"),
                                    "Tienda": st.column_config.Column("Tienda", width="small"),
                                    "Pedido": st.column_config.Column("Pedido", width="medium"),
                                    "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                                    "SKU Faltante": st.column_config.Column("SKU Falta", width="small"),
                                    "Producto Faltante": st.column_config.Column("Descripción Falta", width="large"),
                                    "Monto Faltante ($)": st.column_config.NumberColumn("Monto Falta ($)", format="$%.2f", width="medium"),
                                    "SKU Sobrante": st.column_config.Column("SKU Sobra", width="small"),
                                    "Producto Sobrante": st.column_config.Column("Descripción Sobra", width="large"),
                                    "Monto Sobrante ($)": st.column_config.NumberColumn("Monto Sobra ($)", format="$%.2f", width="medium"),
                                    "Diferencia Neta Confirmada ($)": st.column_config.NumberColumn("Diferencia Neta Confirmada ($)", format="$%.2f", width="medium")
                                }
                            )
                        else:
                            st.info("ℹ️ No hay pedidos registrados para la tienda o criterio de búsqueda seleccionado.")
                else:
                    st.success("🎉 No se registraron pedidos en Tienda ('T') de 'Sustitución Distinta Subfamilia' donde el artículo faltante sea de mayor valor al sobrante.")
            else:
                st.info("ℹ️ No existen pedidos de 'Sustitución Distinta Subfamilia' para la selección actual de filtros.")

        # HOJA 4: RECTIFICACIONES POR ÁREA DE SALIDA
        with tab4:
            st.subheader("📦 Análisis de Rectificaciones por Área de Salida")
            st.markdown("Consolidado y auditoría de pedidos rectificados por **Área de Salida** (se excluyen automáticamente las rectificaciones rechazadas en **Estado 'R'**).")

            if not df_rect.empty:
                df_r_area = df_rect.copy()

                # Filtro por Tienda en Hoja 4
                tiendas_area_opt = ["Todas las Tiendas"] + sorted([str(x) for x in df_r_area["Tienda"].dropna().unique() if str(x) != "nan"]) if "Tienda" in df_r_area.columns else ["Todas las Tiendas"]
                t_area_sel = st.selectbox("Filtrar por Tienda:", tiendas_area_opt, index=0)

                if t_area_sel != "Todas las Tiendas" and "Tienda" in df_r_area.columns:
                    df_r_area = df_r_area[df_r_area["Tienda"].astype(str) == str(t_area_sel)]
                
                # Excluir de forma predeterminada las rectificaciones rechazadas 'R'
                if "Estado" in df_r_area.columns:
                    df_r_area = df_r_area[df_r_area["Estado"] != "R"].copy()

                if "Area_Salida" not in df_r_area.columns:
                    df_r_area["Area_Salida"] = "Sin Clasificar"
                else:
                    df_r_area["Area_Salida"] = df_r_area["Area_Salida"].fillna("Sin Clasificar").astype(str).str.strip()
                    df_r_area["Area_Salida"] = df_r_area["Area_Salida"].replace(["-", "--", "- ", "", "nan", "None"], "Sin Clasificar")

                col_motivo_area = "Motivo_Clean" if "Motivo_Clean" in df_r_area.columns else ("Motivo" if "Motivo" in df_r_area.columns else None)
                if col_motivo_area:
                    df_r_area["Motivo_Norm"] = df_r_area[col_motivo_area].astype(str).str.strip().str.upper()
                else:
                    df_r_area["Motivo_Norm"] = "F"

                df_r_area["Estado_Norm"] = df_r_area["Estado"].astype(str).str.strip().str.upper() if "Estado" in df_r_area.columns else "M"

                df_r_area["Monto_Falta"] = df_r_area.apply(lambda r: abs(float(r["Monto_Rectif"])) if r["Motivo_Norm"] == "F" else 0.0, axis=1)
                df_r_area["Monto_Sobra"] = df_r_area.apply(lambda r: -abs(float(r["Monto_Rectif"])) if r["Motivo_Norm"] == "S" else 0.0, axis=1)
                df_r_area["Monto_Neto"] = df_r_area["Monto_Falta"] + df_r_area["Monto_Sobra"]
                
                # MONTO CONFIRMADO SOLO ESTADO 'M' (Faltas + / Sobras -)
                df_r_area["Monto_Confirmado"] = df_r_area.apply(lambda r: (r["Monto_Falta"] + r["Monto_Sobra"]) if r["Estado_Norm"] == "M" else 0.0, axis=1)

                tot_areas_unicas = df_r_area["Area_Salida"].nunique()
                tot_pedidos_afect_area = df_r_area["Pedido"].nunique()
                tot_lineas_area = len(df_r_area)
                tot_monto_conf_area = df_r_area["Monto_Confirmado"].sum()

                a1, a2, a3, a4 = st.columns(4)
                a1.metric("📌 Áreas de Salida Involucradas", f"{tot_areas_unicas:,}")
                a2.metric("📦 Pedidos Únicos con Rectificación", f"{tot_pedidos_afect_area:,}")
                a3.metric("📉 Líneas Válidas Totales", f"{tot_lineas_area:,}")
                a4.metric("💰 Monto Confirmado Estado 'M' ($)", f"${tot_monto_conf_area:,.2f}")

                st.markdown("---")
                st.markdown("### 📊 Distribución de Monto Confirmado y Líneas Rectificadas por Área de Salida")

                tb_area_graf = df_r_area.groupby("Area_Salida", as_index=False).agg(
                    Pedidos_Rectificados=("Pedido", "nunique"),
                    Lineas_Rectificadas=("Pedido", "count"),
                    Monto_Confirmado=("Monto_Confirmado", "sum")
                ).reset_index(drop=True)

                col_g1, col_g2 = st.columns(2)

                # GRÁFICO 1: MONTO NETO CONFIRMADO ($) ESTADO 'M'
                with col_g1:
                    tb_area_graf_monto = tb_area_graf.sort_values(by="Monto_Confirmado", ascending=False).reset_index(drop=True)
                    tb_area_graf_monto["Monto_Texto"] = tb_area_graf_monto["Monto_Confirmado"].apply(lambda x: f"${x:,.0f}")

                    fig_area_monto = px.bar(
                        tb_area_graf_monto, x="Area_Salida", y="Monto_Confirmado",
                        color="Area_Salida", text="Monto_Texto",
                        title="<b>Monto Neto Confirmado ($) Estado 'M' por Sector</b>"
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

                # GRÁFICO 2: CANTIDAD DE LÍNEAS RECTIFICADAS POR SECTOR
                with col_g2:
                    tb_area_graf_lineas = tb_area_graf.sort_values(by="Lineas_Rectificadas", ascending=False).reset_index(drop=True)

                    fig_area_lineas = px.bar(
                        tb_area_graf_lineas, x="Area_Salida", y="Lineas_Rectificadas",
                        color="Area_Salida", text="Lineas_Rectificadas",
                        title="<b>Cantidad de Líneas Rectificadas por Sector</b>"
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
                st.markdown("### 📋 Resumen Consolidado por Área de Salida")

                tb_area_matriz = df_r_area.groupby("Area_Salida", as_index=False).agg(
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
                    "Lineas_Rectificadas": "Líneas Rectificadas",
                    "Monto_Falta": "Monto Falta ($)",
                    "Monto_Sobra": "Monto Sobra ($)",
                    "Monto_Confirmado": "Diferencia Neta Confirmada ($)",
                    "% Participación Pedidos": "% Participación Pedidos"
                })

                st.dataframe(
                    tb_area_matriz_disp[["Área de Salida", "Pedidos Afectados", "Líneas Rectificadas", "Monto Falta ($)", "Monto Sobra ($)", "Diferencia Neta Confirmada ($)", "% Participación Pedidos"]],
                    hide_index=True,
                    column_config={
                        "Área de Salida": st.column_config.Column("Área de Salida", width="large"),
                        "Pedidos Afectados": st.column_config.NumberColumn("Pedidos Afectados", format="%d", width="medium"),
                        "Líneas Rectificadas": st.column_config.NumberColumn("Líneas Rectificadas", format="%d", width="medium"),
                        "Monto Falta ($)": st.column_config.NumberColumn("Monto Falta ($)", format="$%.2f", width="medium"),
                        "Monto Sobra ($)": st.column_config.NumberColumn("Monto Sobra ($)", format="$%.2f", width="medium"),
                        "Diferencia Neta Confirmada ($)": st.column_config.NumberColumn("Diferencia Neta Confirmada ($)", format="$%.2f", width="large"),
                        "% Participación Pedidos": st.column_config.NumberColumn("% Participación Pedidos", format="%.2f %%", width="medium")
                    }
                )

                st.markdown("---")
                st.markdown("### 🔎 Detalle Individual de Rectificaciones por Área de Salida")

                areas_list_opt = ["Todas las Áreas"] + sorted([str(x) for x in df_r_area["Area_Salida"].unique()])
                area_especifica_sel = st.selectbox("Seleccionar Área de Salida a Auditar:", areas_list_opt, index=0)

                df_r_area_det = df_r_area.copy()
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
                    "Motivo", "Procedencia", "Estado", "Monto_Rectif"
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
                    "Monto_Signed": "Monto ($)"
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
                        "Estado": st.column_config.Column("Estado", width="small"),
                        "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="medium")
                    }
                )
            else:
                st.info("ℹ️ No hay rectificaciones registradas para el análisis por Área de Salida.")

        # HOJA 5: AUDITORÍA DE UNIDADES SUELTAS (FUERA DE CLASIFICACIÓN SLA)
        with tab5:
            st.subheader("🧩 Análisis de Unidades Sueltas (Rectificaciones Menores a 1 Bulto Común - UxB)")
            st.markdown("Auditoría independiente fuera de la clasificación de SLA para identificar aquellas **líneas rectificadas cuya cantidad enviada o reclamada es menor a un bulto cerrado** (`Unidades < UxB`). Permite auditar la incidencia de preparación por unidades sueltas por tienda y sector.")

            if not df_rect.empty:
                df_sueltas = df_rect.copy()
                
                # Excluir rectificaciones rechazadas 'R'
                if "Estado" in df_sueltas.columns:
                    df_sueltas = df_sueltas[df_sueltas["Estado"] != "R"].copy()

                col_art_s = "Artículo" if "Artículo" in df_sueltas.columns else ("SKU" if "SKU" in df_sueltas.columns else "Producto")
                
                # Si 'Es_Unidad_Suelta' no viniera calculada desde el parquet, la calculamos dinámicamente
                if "Es_Unidad_Suelta" not in df_sueltas.columns:
                    col_unid_s = "Unidades_Num" if "Unidades_Num" in df_sueltas.columns else "Pedido"
                    col_uxb_s = "UxB" if "UxB" in df_sueltas.columns else None
                    if col_uxb_s and col_unid_s != "Pedido":
                        df_sueltas["Es_Unidad_Suelta"] = (df_sueltas["UxB"] > 1.0) & (df_sueltas["Unidades_Num"] > 0.0) & (df_sueltas["Unidades_Num"] < df_sueltas["UxB"])
                    else:
                        df_sueltas["Es_Unidad_Suelta"] = False

                # Filtrar solo las líneas de Unidades Sueltas
                df_sueltas_only = df_sueltas[df_sueltas["Es_Unidad_Suelta"] == True].copy()

                tot_lineas_sueltas = len(df_sueltas_only)
                tot_pedidos_sueltas = df_sueltas_only["Pedido"].nunique() if not df_sueltas_only.empty else 0
                tot_tiendas_sueltas = df_sueltas_only["Tienda"].nunique() if not df_sueltas_only.empty else 0
                tot_monto_sueltas = df_sueltas_only["Monto_Rectif"].sum() if "Monto_Rectif" in df_sueltas_only.columns else 0.0

                s1, s2, s3, s4 = st.columns(4)
                s1.metric("🧩 Líneas de Unidades Sueltas", f"{tot_lineas_sueltas:,}")
                s2.metric("📦 Pedidos Involucrados", f"{tot_pedidos_sueltas:,}")
                s3.metric("🏪 Tiendas Afectadas", f"{tot_tiendas_sueltas:,}")
                s4.metric("💰 Impacto Económico ($)", f"${tot_monto_sueltas:,.2f}")

                st.markdown("---")

                if not df_sueltas_only.empty:
                    st.markdown("### 🏆 Top 15 Tiendas con Mayor Cantidad de Líneas de Unidades Sueltas")

                    group_tienda_sueltas = df_sueltas_only.groupby("Tienda", as_index=False).agg(
                        Líneas_Sueltas=("Pedido", "count"),
                        Pedidos_Afectados=("Pedido", "nunique"),
                        Unidades_Sueltas_Totales=("Unidades_Num", "sum") if "Unidades_Num" in df_sueltas_only.columns else ("Pedido", "count"),
                        Monto_Total_Suelto=("Monto_Rectif", "sum") if "Monto_Rectif" in df_sueltas_only.columns else ("Pedido", "count")
                    ).sort_values(by="Líneas_Sueltas", ascending=False).reset_index(drop=True)

                    # Formato y visualización
                    top15_sueltas = group_tienda_sueltas.head(15).copy()

                    cols_top_sueltas = ["Tienda", "Líneas_Sueltas", "Pedidos_Afectados", "Unidades_Sueltas_Totales", "Monto_Total_Suelto"]
                    top15_sueltas_disp = top15_sueltas[cols_top_sueltas].rename(columns={
                        "Líneas_Sueltas": "Lineas con Unidades sueltas",
                        "Pedidos_Afectados": "Pedidos Afectados",
                        "Unidades_Sueltas_Totales": "Unidades Sueltas Totales",
                        "Monto_Total_Suelto": "Monto Total ($)"
                    })

                    st.dataframe(
                        top15_sueltas_disp,
                        hide_index=True,
                        column_config={
                            "Tienda": st.column_config.Column("Tienda", width="small"),
                            "Lineas con Unidades sueltas": st.column_config.NumberColumn("Lineas con Unidades sueltas", format="%d", width="medium"),
                            "Pedidos Afectados": st.column_config.NumberColumn("Pedidos Afectados", format="%d", width="medium"),
                            "Unidades Sueltas Totales": st.column_config.NumberColumn("Unidades Sueltas Totales", format="%.0f", width="medium"),
                            "Monto Total ($)": st.column_config.NumberColumn("Monto Total ($)", format="$%.2f", width="medium")
                        }
                    )

                    st.markdown("---")
                    st.markdown("### 🔎 Detalle Individual de Líneas Rectificadas como Unidades Sueltas")

                    tiendas_sueltas_opt = ["Todas las Tiendas"] + sorted([str(x) for x in df_sueltas_only["Tienda"].unique()])
                    t_suelta_sel = st.selectbox("Seleccionar Tienda para Auditar Unidades Sueltas:", tiendas_sueltas_opt, index=0)

                    df_det_sueltas = df_sueltas_only.copy()
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
                        "Unidades_Num", "UxB", "Motivo", "Procedencia", "Estado", "Monto_Signed"
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
                            "Estado": st.column_config.Column("Estado", width="small"),
                            "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="medium")
                        }
                    )
                else:
                    st.success("🎉 No se registraron rectificaciones de unidades sueltas (< 1 UxB) para la selección actual.")
            else:
                st.info("ℹ️ No hay rectificaciones disponibles para auditar unidades sueltas.")

        # HOJA 6: ANÁLISIS DE RECTIFICACIONES DE PORTAL
        with tab6:
            st.subheader("❌ Rectificaciones del Portal: Análisis de Causas Anuladas y Aprobadas \nRectificaciones Anuladas y Aprobadas")
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

                # Normalización de mes
                if "Fecha" in df_portal_csv.columns:
                    f_str_p = df_portal_csv["Fecha"].astype(str).str.strip()
                    f_dt_p = pd.to_datetime(f_str_p, format="%Y%m%d", errors="coerce")
                    mask_p_na = f_dt_p.isna()
                    if mask_p_na.any():
                        f_dt_p[mask_p_na] = pd.to_datetime(f_str_p[mask_p_na], dayfirst=True, errors="coerce")
                    df_portal_csv["Mes_Num"] = f_dt_p.dt.month.fillna(0).astype(int)
                elif "Fecha_Modif" in df_portal_csv.columns:
                    f_str_p = df_portal_csv["Fecha_Modif"].astype(str).str.strip()
                    f_dt_p = pd.to_datetime(f_str_p, format="%Y%m%d", errors="coerce")
                    mask_p_na = f_dt_p.isna()
                    if mask_p_na.any():
                        f_dt_p[mask_p_na] = pd.to_datetime(f_str_p[mask_p_na], dayfirst=True, errors="coerce")
                    df_portal_csv["Mes_Num"] = f_dt_p.dt.month.fillna(0).astype(int)
                else:
                    df_portal_csv["Mes_Num"] = 0

                mapa_meses_p = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
                df_portal_csv["Nombre_Mes"] = df_portal_csv["Mes_Num"].map(mapa_meses_p).fillna("Sin Mes")

                if "Almacen" not in df_portal_csv.columns:
                    df_portal_csv["Almacen"] = "501"

                df_portal_csv["Etiqueta_Almacen"] = "Almacén " + df_portal_csv["Almacen"].astype(str)

                # FILTRO DE ALMACÉN ESTILO LISTA DESPLEGABLE MÚLTIPLE (POPOVER)
                almacenes_portal_opt = sorted([str(x) for x in df_portal_csv["Almacen"].dropna().unique() if str(x) != "nan"])
                
                col_m_alm, col_m_space = st.columns([2.5, 1.5])
                with col_m_alm:
                    with st.popover("🏭 Filtrar por Almacén / CD (Selección Múltiple)", use_container_width=True):
                        st.markdown("**Lista de Almacenes / CDs**")
                        alm_todos = st.checkbox("Seleccionar Todos los Almacenes", value=True, key="chk_all_alm_h6")
                        alm_portal_sel = []
                        for alm in almacenes_portal_opt:
                            chk_val = st.checkbox(f"Almacén {alm}", value=alm_todos, key=f"chk_alm_{alm}_h6")
                            if chk_val:
                                alm_portal_sel.append(alm)

                if alm_portal_sel:
                    df_portal_csv = df_portal_csv[df_portal_csv["Almacen"].astype(str).isin(alm_portal_sel)].copy()
                else:
                    df_portal_csv = df_portal_csv.iloc[0:0].copy()

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
                        with st.popover("🔍 Filtrar Sección Anuladas por Causa (Selección Múltiple)", use_container_width=True):
                            st.markdown("**Lista de Causas de Anulación**")
                            causa_anul_all = st.checkbox("Seleccionar Todas las Causas de Anulación", value=True, key="chk_all_causa_anul")
                            causas_sel_anul = []
                            for idx, c_anul in enumerate(causas_anul_unicas):
                                chk_c = st.checkbox(c_anul, value=causa_anul_all, key=f"chk_anul_{idx}")
                                if chk_c:
                                    causas_sel_anul.append(c_anul)

                    df_csv_anul_sec1 = df_csv_anul[df_csv_anul["Motivo_Norm"].isin(causas_sel_anul)].copy() if causas_sel_anul else df_csv_anul.iloc[0:0].copy()

                    if not df_csv_anul_sec1.empty:
                        # 1. Gráfico
                        grp_anul = df_csv_anul_sec1.groupby(["Mes_Num", "Nombre_Mes", "Etiqueta_Almacen"], as_index=False).agg(
                            Cant_Lineas=("Pedido", "count")
                        )

                        tot_mes_anul = grp_anul.groupby(["Mes_Num", "Nombre_Mes"])["Cant_Lineas"].transform("sum")
                        grp_anul["Porcentaje"] = (grp_anul["Cant_Lineas"] / tot_mes_anul * 100.0).fillna(0.0)
                        grp_anul["Etiqueta_Texto"] = grp_anul.apply(lambda r: f"<b>{r['Porcentaje']:.1f}%</b><br>({int(r['Cant_Lineas']):,} líns)", axis=1)

                        meses_presentes_anul = sorted([m for m in grp_anul["Mes_Num"].unique() if m in mapa_meses_p])
                        orden_meses_anul = [mapa_meses_p[m] for m in meses_presentes_anul]

                        mapa_colores_alm_g = {
                            "Almacén 501": "#9B59B6", "Almacén 503": "#2BA884", 
                            "Almacén 504": "#D06A4C", "Almacén 509": "#E09F53", "Almacén 514": "#2B5C8F"
                        }

                        fig_apilado_anul = px.bar(
                            grp_anul,
                            x="Nombre_Mes",
                            y="Porcentaje",
                            color="Etiqueta_Almacen",
                            title="<b>Distribución Porcentual y Cantidad por Almacén - Anuladas</b>",
                            text="Etiqueta_Texto",
                            color_discrete_map=mapa_colores_alm_g,
                            barmode="stack",
                            hover_data={"Cant_Lineas": ":,", "Porcentaje": ":.2f%"}
                        )

                        fig_apilado_anul.update_traces(textposition='inside')
                        fig_apilado_anul.update_layout(
                            xaxis=dict(title="Mes", categoryorder="array", categoryarray=orden_meses_anul),
                            yaxis=dict(title="Porcentaje de Participación (%)", range=[0, 100]),
                            height=410,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            legend_title_text="Almacén"
                        )

                        st.plotly_chart(fig_apilado_anul, use_container_width=True)

                        st.markdown("---")
                        # 2. Resumen por Causa
                        st.markdown("#### 📋 Resumen por Causa de Anulación")

                        df_causas_anul_grp = df_csv_anul_sec1.groupby("Motivo_Norm", as_index=False).agg(
                            Líneas_Anuladas=("Pedido", "count"),
                            Pedidos_Afectados=("Pedido", "nunique"),
                            Monto_Total=("Monto_Signed", "sum")
                        ).sort_values(by="Líneas_Anuladas", ascending=False).reset_index(drop=True)

                        df_causas_anul_disp = df_causas_anul_grp.rename(columns={
                            "Motivo_Norm": "Causa / Motivo de Anulación",
                            "Líneas_Anuladas": "Líneas Anuladas",
                            "Pedidos_Afectados": "Pedidos",
                            "Monto_Total": "Monto Anulado ($)"
                        })

                        st.dataframe(
                            df_causas_anul_disp,
                            hide_index=True,
                            column_config={
                                "Causa / Motivo de Anulación": st.column_config.Column("Causa / Motivo de Anulación", width="large"),
                                "Líneas Anuladas": st.column_config.NumberColumn("Líneas Anuladas", format="%d", width="small"),
                                "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="small"),
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
                        with st.popover("🔍 Filtrar Sección Aprobadas por Causa (Selección Múltiple)", use_container_width=True):
                            st.markdown("**Lista de Causas de Aprobación**")
                            causa_aprob_all = st.checkbox("Seleccionar Todas las Causas de Aprobación", value=True, key="chk_all_causa_aprob")
                            causas_sel_aprob = []
                            for idx, c_aprob in enumerate(causas_aprob_unicas):
                                chk_a = st.checkbox(c_aprob, value=causa_aprob_all, key=f"chk_aprob_{idx}")
                                if chk_a:
                                    causas_sel_aprob.append(c_aprob)

                    df_csv_aprob_sec2 = df_csv_aprob[df_csv_aprob["Motivo_Norm"].isin(causas_sel_aprob)].copy() if causas_sel_aprob else df_csv_aprob.iloc[0:0].copy()

                    if not df_csv_aprob_sec2.empty:
                        # 1. Gráfico
                        grp_aprob = df_csv_aprob_sec2.groupby(["Mes_Num", "Nombre_Mes", "Etiqueta_Almacen"], as_index=False).agg(
                            Cant_Lineas=("Pedido", "count")
                        )

                        tot_mes_aprob = grp_aprob.groupby(["Mes_Num", "Nombre_Mes"])["Cant_Lineas"].transform("sum")
                        grp_aprob["Porcentaje"] = (grp_aprob["Cant_Lineas"] / tot_mes_aprob * 100.0).fillna(0.0)
                        grp_aprob["Etiqueta_Texto"] = grp_aprob.apply(lambda r: f"<b>{r['Porcentaje']:.1f}%</b><br>({int(r['Cant_Lineas']):,} líns)", axis=1)

                        meses_presentes_aprob = sorted([m for m in grp_aprob["Mes_Num"].unique() if m in mapa_meses_p])
                        orden_meses_aprob = [mapa_meses_p[m] for m in meses_presentes_aprob]

                        fig_apilado_aprob = px.bar(
                            grp_aprob,
                            x="Nombre_Mes",
                            y="Porcentaje",
                            color="Etiqueta_Almacen",
                            title="<b>Distribución Porcentual y Cantidad por Almacén - Aprobadas</b>",
                            text="Etiqueta_Texto",
                            color_discrete_map=mapa_colores_alm_g,
                            barmode="stack",
                            hover_data={"Cant_Lineas": ":,", "Porcentaje": ":.2f%"}
                        )

                        fig_apilado_aprob.update_traces(textposition='inside')
                        fig_apilado_aprob.update_layout(
                            xaxis=dict(title="Mes", categoryorder="array", categoryarray=orden_meses_aprob),
                            yaxis=dict(title="Porcentaje de Participación (%)", range=[0, 100]),
                            height=410,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            legend_title_text="Almacén"
                        )

                        st.plotly_chart(fig_apilado_aprob, use_container_width=True)

                        st.markdown("---")
                        # 2. Resumen por Causa
                        st.markdown("#### 📋 Resumen por Causa de Aprobación")

                        df_causas_aprob_grp = df_csv_aprob_sec2.groupby("Motivo_Norm", as_index=False).agg(
                            Líneas_Aprobadas=("Pedido", "count"),
                            Pedidos_Afectados=("Pedido", "nunique"),
                            Monto_Total=("Monto_Signed", "sum")
                        ).sort_values(by="Líneas_Aprobadas", ascending=False).reset_index(drop=True)

                        df_causas_aprob_disp = df_causas_aprob_grp.rename(columns={
                            "Motivo_Norm": "Causa / Motivo de Aprobación",
                            "Líneas_Aprobadas": "Líneas Aprobadas",
                            "Pedidos_Afectados": "Pedidos",
                            "Monto_Total": "Monto Aprobado ($)"
                        })

                        st.dataframe(
                            df_causas_aprob_disp,
                            hide_index=True,
                            column_config={
                                "Causa / Motivo de Aprobación": st.column_config.Column("Causa / Motivo de Aprobación", width="large"),
                                "Líneas Aprobadas": st.column_config.NumberColumn("Líneas Aprobadas", format="%d", width="small"),
                                "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="small"),
                                "Monto Aprobado ($)": st.column_config.NumberColumn("Monto Aprobado ($)", format="$%.0f", width="medium")
                            }
                        )

                        # 3. Distribución por Área de Salida
                        st.markdown("---")
                        st.markdown("#### 📦 Distribución por Área de Salida en Rectificaciones Aprobadas")
                        
                        df_area_aprob_grp = df_csv_aprob_sec2.groupby(["Area_Salida", "Motivo_Norm"], as_index=False).agg(
                            Líneas_Aprobadas=("Pedido", "count"),
                            Pedidos_Unicos=("Pedido", "nunique"),
                            Monto_Total=("Monto_Signed", "sum")
                        ).sort_values(by=["Líneas_Aprobadas"], ascending=False).reset_index(drop=True)

                        df_area_aprob_disp = df_area_aprob_grp.rename(columns={
                            "Area_Salida": "Área de Salida",
                            "Motivo_Norm": "Causa / Motivo",
                            "Líneas_Aprobadas": "Líneas Aprobadas",
                            "Pedidos_Unicos": "Pedidos",
                            "Monto_Total": "Monto Total ($)"
                        })

                        st.dataframe(
                            df_area_aprob_disp,
                            hide_index=True,
                            column_config={
                                "Área de Salida": st.column_config.Column("Área de Salida", width="medium"),
                                "Causa / Motivo": st.column_config.Column("Causa / Motivo", width="large"),
                                "Líneas Aprobadas": st.column_config.NumberColumn("Líneas Aprobadas", format="%d", width="small"),
                                "Pedidos": st.column_config.NumberColumn("Pedidos", format="%d", width="small"),
                                "Monto Total ($)": st.column_config.NumberColumn("Monto Total ($)", format="$%.0f", width="medium")
                            }
                        )

                        st.markdown("---")
                        # 4. Top de Tiendas Aprobadas
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
                
                col_tp1, col_tp2 = st.columns([2.5, 1.5])
                with col_tp1:
                    with st.popover("🏪 Filtrar por Tienda(s) del Portal (Selección Múltiple)", use_container_width=True):
                        st.markdown("**Lista de Tiendas**")
                        t_portal_all = st.checkbox("Seleccionar Todas las Tiendas", value=True, key="chk_all_tiendas_portal_h6")
                        t_portal_sel = []
                        for idx_t, t_code in enumerate(tiendas_portal_opt):
                            chk_t = st.checkbox(f"Tienda {t_code}", value=t_portal_all, key=f"chk_t_portal_{idx_t}")
                            if chk_t:
                                t_portal_sel.append(t_code)

                with col_tp2:
                    busqueda_ped_portal = st.text_input("🔍 Filtrar por Número de Pedido:", "", key="txt_ped_portal")

                df_portal_view = df_portal_csv.copy()

                if t_portal_sel and "Tienda" in df_portal_view.columns:
                    df_portal_view = df_portal_view[df_portal_view["Tienda"].astype(str).isin(t_portal_sel)]
                else:
                    df_portal_view = df_portal_view.iloc[0:0].copy()

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
            st.subheader("📦 Análisis de Líneas con Error de Facturación Master")
            st.markdown("Auditoría enfocada exclusivamente a nivel **línea de artículo / SKU** para identificar todas aquellas rectificaciones que corresponden a desvíos de **Bulto Máster / Empaque**, independientemente de la clasificación SLA del pedido completo.")

            if not df_rect.empty:
                df_m_lines = df_rect.copy()

                # Excluir rectificaciones rechazadas 'R'
                if "Estado" in df_m_lines.columns:
                    df_m_lines = df_m_lines[df_m_lines["Estado"] != "R"].copy()

                col_art_m = "Artículo" if "Artículo" in df_m_lines.columns else ("SKU" if "SKU" in df_m_lines.columns else "Producto")

                def es_linea_master_check(row):
                    sku = str(row.get(col_art_m, "")).strip().lstrip("0")
                    unid = float(row.get("Unidades_Num", 0.0))
                    uxb = float(row.get("UxB", 0.0))
                    bulfm = float(row.get("BULFM", 1.0))
                    uxm = float(row.get("UxM", uxb * bulfm if uxb > 0 else 0.0))
                    es_m_flag = str(row.get("Es_Master", "")).strip().upper() in ["SI", "SÍ"]

                    if not es_m_flag:
                        return False

                    if uxb > 0.0 and unid == uxb:
                        return False

                    if uxm > uxb and unid > 0.0:
                        if unid == uxm or unid % uxm == 0:
                            return True
                        dif = uxm - uxb
                        if dif > 0.0 and dif != uxb and (unid == dif or unid % dif == 0):
                            return True

                    return False

                df_m_lines["Es_Linea_Master"] = df_m_lines.apply(es_linea_master_check, axis=1)
                df_m_only = df_m_lines[df_m_lines["Es_Linea_Master"] == True].copy()

                tiendas_m_opt = ["Todas las Tiendas"] + sorted([str(x) for x in df_m_only["Tienda"].dropna().unique() if str(x) != "nan"]) if "Tienda" in df_m_only.columns else ["Todas las Tiendas"]
                col_tm_1, col_tm_2 = st.columns([2, 1])
                with col_tm_1:
                    t_master_sel = st.selectbox("Filtrar por Tienda:", tiendas_m_opt, index=0)
                with col_tm_2:
                    t_master_escribir = st.text_input("✍️ O escribir Nº de Tienda:", "", key="txt_tienda_h8_val")

                if t_master_escribir.strip() and "Tienda" in df_m_only.columns:
                    df_m_only = df_m_only[df_m_only["Tienda"].astype(str).str.contains(t_master_escribir.strip(), case=False, na=False)]
                elif t_master_sel != "Todas las Tiendas" and "Tienda" in df_m_only.columns:
                    df_m_only = df_m_only[df_m_only["Tienda"].astype(str) == str(t_master_sel)]

                tot_lineas_m = len(df_m_only)
                tot_pedidos_m = df_m_only["Pedido"].nunique() if not df_m_only.empty else 0
                tot_tiendas_m = df_m_only["Tienda"].nunique() if not df_m_only.empty else 0
                tot_monto_m = df_m_only["Monto_Rectif"].sum() if "Monto_Rectif" in df_m_only.columns else 0.0

                b1, b2, b3, b4 = st.columns(4)
                b1.metric("📦 Líneas con Error Master", f"{tot_lineas_m:,}")
                b2.metric("📋 Pedidos Involucrados", f"{tot_pedidos_m:,}")
                b3.metric("🏪 Tiendas Afectadas", f"{tot_tiendas_m:,}")
                b4.metric("💰 Impacto Económico ($)", f"${tot_monto_m:,.2f}")

                st.markdown("---")

                if not df_m_only.empty:
                    st.markdown("### 🏆 Top 15 Tiendas con Mayor Cantidad de Líneas con Error Master")

                    group_tienda_m = df_m_only.groupby("Tienda", as_index=False).agg(
                        Líneas_Master=("Pedido", "count"),
                        Pedidos_Afectados=("Pedido", "nunique"),
                        Unidades_Master_Totales=("Unidades_Num", "sum") if "Unidades_Num" in df_m_only.columns else ("Pedido", "count"),
                        Monto_Total_Master=("Monto_Rectif", "sum") if "Monto_Rectif" in df_m_only.columns else ("Pedido", "count")
                    ).sort_values(by="Líneas_Master", ascending=False).reset_index(drop=True)

                    top15_m = group_tienda_m.head(15).copy()

                    cols_top_m = ["Tienda", "Líneas_Master", "Pedidos_Afectados", "Unidades_Master_Totales", "Monto_Total_Master"]
                    top15_m_disp = top15_m[cols_top_m].rename(columns={
                        "Líneas_Master": "Líneas Error Master",
                        "Pedidos_Afectados": "Pedidos Afectados",
                        "Unidades_Master_Totales": "Unidades Totales",
                        "Monto_Total_Master": "Monto Total ($)"
                    })

                    st.dataframe(
                        top15_m_disp,
                        hide_index=True,
                        column_config={
                            "Tienda": st.column_config.Column("Tienda", width="small"),
                            "Líneas Error Master": st.column_config.NumberColumn("Líneas Error Master", format="%d", width="medium"),
                            "Pedidos Afectados": st.column_config.NumberColumn("Pedidos Afectados", format="%d", width="medium"),
                            "Unidades Totales": st.column_config.NumberColumn("Unidades Totales", format="%.0f", width="medium"),
                            "Monto Total ($)": st.column_config.NumberColumn("Monto Total ($)", format="$%.2f", width="medium")
                        }
                    )

                    st.markdown("---")
                    st.markdown("### 🔎 Detalle Individual de Líneas Rectificadas por Error Master")

                    busqueda_ped_m = st.text_input("🔍 Filtrar por Número de Pedido (Líneas Master):", "", key="txt_ped_h8")
                    df_det_m = df_m_only.copy()
                    if busqueda_ped_m:
                        df_det_m = df_det_m[
                            df_det_m["Pedido"].astype(str).str.contains(busqueda_ped_m.strip(), case=False, na=False)
                        ]

                    col_desc_m = "Descripción" if "Descripción" in df_det_m.columns else "Producto"

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
                            "Unid. Rectificadas": st.column_config.NumberColumn("Unid. Rectificadas", format="%.0f", width="small"),
                            "Motivo": st.column_config.Column("Motivo", width="small"),
                            "Procedencia": st.column_config.Column("Procedencia", width="small"),
                            "Estado": st.column_config.Column("Estado", width="small"),
                            "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="medium")
                        }
                    )
                else:
                    st.success("🎉 No se registraron líneas de rectificación con Error Facturación Master para la selección realizada.")
            else:
                st.info("ℹ️ No hay rectificaciones disponibles para auditar el error de facturación máster a nivel de líneas.")

        # HOJA 8: GLOSARIO Y MODELO SLA
        with tab8:
            st.subheader("📖 Glosario Operativo y Modelo SLA")
            st.markdown("Resumen ejecutivo de reglas de negocio, escalas de puntuación y definiciones de casuísticas aplicadas en el cálculo del SLA.")
            
            st.markdown("### 📋 Reglas de Puntaje y Evaluación SLA por Pedido")
            
            matriz_p = pd.DataFrame([
                {"Casuística Operativa": "Pedido Perfecto", "Descuento Aplicado": "0.0 Pts", "Puntaje por Pedido": "10.0 / 10", "Simplificado": "Pedido sin rectificaciones"},
                {"Casuística Operativa": "Sobrante Neto", "Descuento Aplicado": "0.0 Pts", "Puntaje por Pedido": "10.0 / 10", "Simplificado": "Pedido con rectificación de sobra"},
                {"Casuística Operativa": "Sustitución Misma Subfamilia", "Descuento Aplicado": "-2.5 Pts", "Puntaje por Pedido": "7.5 / 10", "Simplificado": "Pedido con rectificación de falta y sobra en artículos de igual subfamilia"},
                {"Casuística Operativa": "Sustitución Distinta Subfamilia", "Descuento Aplicado": "-4.5 Pts", "Puntaje por Pedido": "5.5 / 10", "Simplificado": "Pedido con rectificación de falta y sobra en artículos de distintas subfamilias"},
                {"Casuística Operativa": "Falta/Sobra", "Descuento Aplicado": "-5.5 Pts", "Puntaje por Pedido": "4.5 / 10", "Simplificado": "Pedido con rectificación de falta y sobra"},
                {"Casuística Operativa": "Faltante Neto", "Descuento Aplicado": "-6.0 Pts", "Puntaje por Pedido": "4.0 / 10", "Simplificado": "Pedido con rectificación de solo falta"},
                {"Casuística Operativa": "Formato no entregado", "Descuento Aplicado": "-6.0 Pts", "Puntaje por Pedido": "4.0 / 10", "Simplificado": "Pedido con rectificación de solo falta de más de 10 líneas"},
                {"Casuística Operativa": "Error facturación master", "Descuento Aplicado": "-6.0 Pts", "Puntaje por Pedido": "4.0 / 10", "Simplificado": "Pedido con rectificación de falta en bultos Master"},
                {"Casuística Operativa": "Etiquetas Cambiadas", "Descuento Aplicado": "-10.0 Pts", "Puntaje por Pedido": "0.0 / 10", "Simplificado": "Faltas y sobras simultáneas mayores o iguales a 12 líneas rectificadas"}
            ])
            st.dataframe(matriz_p, hide_index=True)

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
* **UxM**: Unidades Totales por Bulto Máster ($UxM = UxB \times BxM$).
            """)

except Exception as e:
    st.error(f'Error cargando el tablero: {e}')
