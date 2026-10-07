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

        if "Año" not in df_sla.columns:
            df_sla["Año"] = 2026
            
        if "Mes" not in df_sla.columns:
            if "Fecha_DT" in df_sla.columns:
                df_sla["Mes"] = pd.to_datetime(df_sla["Fecha_DT"]).dt.month.fillna(0).astype(int)
            else:
                df_sla["Mes"] = 0

        if not df_rect.empty:
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

        return df_sla, df_rect
    return pd.DataFrame(), pd.DataFrame()

try:
    df_sla, df_rect = cargar_datos_sla()

    if not df_sla.empty:
        st.sidebar.header("🔍 Filtros de Búsqueda")

        if "Almacen" in df_sla.columns:
            almacenes = sorted([str(x) for x in df_sla["Almacen"].dropna().unique()])
            almacen_sel = st.sidebar.multiselect("Almacén:", almacenes, default=almacenes)
            df_sla = df_sla[df_sla["Almacen"].astype(str).isin(almacen_sel)]
            if not df_rect.empty and "Almacen" in df_rect.columns:
                df_rect = df_rect[df_rect["Almacen"].astype(str).isin(almacen_sel)]

        if "Gestion" in df_sla.columns and df_sla["Gestion"].notna().any():
            gestiones = sorted([str(x) for x in df_sla["Gestion"].dropna().unique()])
            gestion_sel = st.sidebar.multiselect("Gestión / Zona:", gestiones, default=gestiones)
            df_sla = df_sla[df_sla["Gestion"].astype(str).isin(gestion_sel)]
            if not df_rect.empty and "Gestion" in df_rect.columns:
                df_rect = df_rect[df_rect["Gestion"].astype(str).isin(gestion_sel)]

        if "Responsable_Tienda" in df_sla.columns and df_sla["Responsable_Tienda"].notna().any():
            responsables = sorted([str(x) for x in df_sla["Responsable_Tienda"].dropna().unique()])
            resp_sel = st.sidebar.multiselect("Franquiciado / Supervisor:", responsables, default=responsables)
            df_sla = df_sla[df_sla["Responsable_Tienda"].astype(str).isin(resp_sel)]
            if not df_rect.empty and "Responsable_Tienda" in df_rect.columns:
                df_rect = df_rect[df_rect["Responsable_Tienda"].astype(str).isin(resp_sel)]

        if "Tienda" in df_sla.columns:
            tiendas = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
            tienda_sel = st.sidebar.multiselect("Tienda:", tiendas, default=tiendas)
            df_sla = df_sla[df_sla["Tienda"].astype(str).isin(tienda_sel)]
            if not df_rect.empty and "Tienda" in df_rect.columns:
                df_rect = df_rect[df_rect["Tienda"].astype(str).isin(tienda_sel)]

        if "Casuistica" in df_sla.columns:
            orden_cas_filtro = [
                "Pedido Perfecto", "Sobrante Neto", 
                "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                "Falta/Sobra", "Faltante Neto", "Faltante UxB", 
                "Etiquetas Cambiadas"
            ]
            casuisticas_presentes = [c for c in orden_cas_filtro if c in df_sla["Casuistica"].dropna().unique()]
            otras_cas = [c for c in df_sla["Casuistica"].dropna().unique() if c not in casuisticas_presentes]
            casuisticas_opciones = casuisticas_presentes + otras_cas

            casuistica_sel = st.sidebar.multiselect("Casuística / Estado Pedido:", casuisticas_opciones, default=casuisticas_opciones)
            df_sla = df_sla[df_sla["Casuistica"].isin(casuistica_sel)]
            
            if not df_rect.empty:
                pedidos_validos_cas = set(df_sla["Pedido"].dropna().unique())
                df_rect = df_rect[df_rect["Pedido"].isin(pedidos_validos_cas)]

        if not df_rect.empty:
            st.sidebar.markdown("---")
            st.sidebar.header("🏷️ Filtros del Maestro")

            if "Familia" in df_rect.columns and df_rect["Familia"].notna().any():
                familias = sorted([str(x) for x in df_rect["Familia"].dropna().unique()])
                fam_sel = st.sidebar.multiselect("Familia:", familias, default=familias)
                df_rect = df_rect[df_rect["Familia"].astype(str).isin(fam_sel)]

            if "Subfamilia" in df_rect.columns and df_rect["Subfamilia"].notna().any():
                subfamilias = sorted([str(x) for x in df_rect["Subfamilia"].dropna().unique()])
                subfam_sel = st.sidebar.multiselect("Subfamilia:", subfamilias, default=subfamilias)
                df_rect = df_rect[df_rect["Subfamilia"].astype(str).isin(subfam_sel)]

            if "Es_Master" in df_rect.columns and df_rect["Es_Master"].notna().any():
                masters = sorted([str(x) for x in df_rect["Es_Master"].dropna().unique()])
                master_sel = st.sidebar.multiselect("Producto Master (Sí/No):", masters, default=masters)
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
            help="Excluye sucursales con muy pocos pedidos para evitar distorsiones estadísticas en el promedio SLA."
        )
        
        tiendas_pocas_compras = set(pedidos_por_tienda[pedidos_por_tienda < umbral_min_pedidos].index)
        activar_filtro_outliers = st.sidebar.checkbox("Excluir Tiendas con Pocos Pedidos", value=False)
        
        if activar_filtro_outliers and len(tiendas_pocas_compras) > 0:
            df_sla = df_sla[~df_sla["Tienda"].isin(tiendas_pocas_compras)]
            if not df_rect.empty:
                df_rect = df_rect[~df_rect["Tienda"].isin(tiendas_pocas_compras)]
            st.sidebar.warning(f"Excluidas {len(tiendas_pocas_compras):,} tiendas con < {umbral_min_pedidos} pedidos.")

        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 1. Ranking SLA por Almacén y Tienda",
            "📈 2. Casuísticas y Modelo SLA",
            "🏪 3. Auditoría Práctica por Sucursal",
            "🔄 4. Análisis de Sustituciones"
        ])

        # HOJA 1
        with tab1:
            st.subheader("📊 Ranking SLA por Almacén y Tienda")

            tot_pedidos_global = len(df_sla)
            tot_pedidos_rectif_global = (df_sla["Casuistica"] != "Pedido Perfecto").sum()
            tot_pts_obtenidos_global = df_sla["Puntos_Obtenidos"].sum()
            tot_pts_posibles_global = tot_pedidos_global * 10.0
            sla_global = (tot_pts_obtenidos_global / tot_pts_posibles_global * 10.0) if tot_pts_posibles_global > 0 else 0.0

            k1, k2, k3 = st.columns(3)
            k1.metric("⭐ Puntaje SLA Promedio", f"{sla_global:.2f} / 10.0")
            k2.metric("📦 Pedidos Totales", f"{tot_pedidos_global:,}")
            k3.metric("⚠️ Pedidos con Rectificación", f"{tot_pedidos_rectif_global:,}")

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
            df_meses_base["Nombre_Mes"] = df_meses_base["Mes_Num"].map(mapa_meses)
            
            df_lineas_mes = df_meses_base.merge(df_lineas_mes, on="Mes_Num", how="left").fillna({"Cant_Lineas_Rectificadas": 0})
            df_lineas_mes = df_lineas_mes.sort_values("Mes_Num").reset_index(drop=True)

            colores_cas = {
                "Sobrante Neto": "#0077B6", "Sustitución Misma Subfamilia": "#80ED99",
                "Sustitución Distinta Subfamilia": "#FF9E00", "Falta/Sobra": "#4CC9F0", 
                "Faltante Neto": "#E63946", "Faltante UxB": "#7209B7", "Etiquetas Cambiadas": "#2B2D42"
            }

            fig_comb = make_subplots(specs=[[{"secondary_y": True}]])
            casuisticas_orden = [
                "Sobrante Neto", "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                "Falta/Sobra", "Faltante Neto", "Faltante UxB", "Etiquetas Cambiadas"
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
            st.markdown("### 🏪 Detalle por Franquiciado / Supervisor")

            col_tiendas_lbl = "Total\nTiendas"
            col_totales_lbl = "Pedidos\nTotales"
            col_rectif_lbl = "Pedidos con\nRectificaciones"
            col_lin_lbl = "Líneas\nRectificadas"
            col_part_lin_lbl = "% Líneas\nConfirmadas"
            col_sla_lbl = "Puntaje SLA\n(1 a 10)"

            group_cols_resp = ["Responsable_Tienda"] if "Responsable_Tienda" in df_sla.columns else ["Tienda"]
            tb_resp_base = df_sla.groupby(group_cols_resp, as_index=False).agg(
                Total_Tiendas=("Tienda", "nunique"), 
                Pedidos_Totales=("Pedido", "count"),
                Pedidos_Con_Rectificaciones=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()), 
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )

            if not df_rect.empty and "Responsable_Tienda" in df_rect.columns:
                col_est = "Estado_Clean" if "Estado_Clean" in df_rect.columns else ("Estado" if "Estado" in df_rect.columns else "Pedido")
                tb_rect_counts = df_rect.groupby("Responsable_Tienda", as_index=False).agg(
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
            tot_tiendas_global = df_sla["Tienda"].nunique() if "Tienda" in df_sla.columns else 0
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

        # HOJA 2
        with tab2:
            st.subheader("📈 Matriz Ejecutiva de Casuísticas por Pedido")
            tot_p = len(df_sla)
            df_sla_tab2 = df_sla.copy()
            df_sla_tab2["Casuistica"] = df_sla_tab2["Casuistica"].astype(str).str.strip()

            cas_sum = df_sla_tab2.groupby("Casuistica", as_index=False).agg(Cantidad_Pedidos=("Pedido", "count"), Lineas_Rectificadas=("Lineas_Rectificadas_Confirmadas", "sum") if "Lineas_Rectificadas_Confirmadas" in df_sla_tab2.columns else ("Pedido", "count"))
            cas_sum["% Participación Pedidos"] = (cas_sum["Cantidad_Pedidos"] / tot_p) * 100
            
            orden_cas = [
                "Pedido Perfecto", "Sobrante Neto", 
                "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", 
                "Falta/Sobra", "Faltante Neto", "Faltante UxB", 
                "Etiquetas Cambiadas"
            ]
            cas_sum["Casuistica_Cat"] = pd.Categorical(cas_sum["Casuistica"], categories=orden_cas, ordered=True)
            cas_sum = cas_sum.sort_values("Casuistica_Cat").drop(columns=["Casuistica_Cat"]).reset_index(drop=True)

            st.dataframe(cas_sum, hide_index=True)
            st.markdown("---")
            st.subheader("📋 Reglas de Puntaje y Evaluación SLA por Pedido")
            
            matriz_p = pd.DataFrame([
                {"Casuística Operativa": "Pedido Perfecto", "Descuento Aplicado": "0.0 Pts", "Puntaje por Pedido": "10.0 / 10", "Simplificado": "Pedido sin rectificaciones"},
                {"Casuística Operativa": "Sobrante Neto", "Descuento Aplicado": "0.0 Pts", "Puntaje por Pedido": "10.0 / 10", "Simplificado": "Pedido con rectificación de sobra"},
                {"Casuística Operativa": "Sustitución Misma Subfamilia", "Descuento Aplicado": "-2.5 Pts", "Puntaje por Pedido": "7.5 / 10", "Simplificado": "Pedido con rectificación de falta y sobra en artículos de igual subfamilia"},
                {"Casuística Operativa": "Sustitución Distinta Subfamilia", "Descuento Aplicado": "-4.5 Pts", "Puntaje por Pedido": "5.5 / 10", "Simplificado": "Pedido con rectificación de falta y sobra en artículos de distintas subfamilias"},
                {"Casuística Operativa": "Falta/Sobra", "Descuento Aplicado": "-5.5 Pts", "Puntaje por Pedido": "4.5 / 10", "Simplificado": "Pedido con rectificación de falta y sobra"},
                {"Casuística Operativa": "Faltante Neto", "Descuento Aplicado": "-6.0 Pts", "Puntaje por Pedido": "4.0 / 10", "Simplificado": "Pedido con rectificación de solo falta"},
                {"Casuística Operativa": "Faltante UxB", "Descuento Aplicado": "-6.0 Pts", "Puntaje por Pedido": "4.0 / 10", "Simplificado": "Pedido con rectificación de falta en bultos Master"},
                {"Casuística Operativa": "Etiquetas Cambiadas", "Descuento Aplicado": "-10.0 Pts", "Puntaje por Pedido": "0.0 / 10", "Simplificado": "Faltas y sobras simultáneas mayores o iguales a 12 líneas rectificadas"}
            ])
            st.dataframe(matriz_p, hide_index=True)

        # HOJA 3
        with tab3:
            st.subheader("🏪 Auditoría Práctica y Detalle de Rectificaciones por Sucursal")
            
            tiendas_unicas = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
            opciones_tienda = ["Ninguna", "Todas las Tiendas"] + tiendas_unicas
            
            t_sel = st.selectbox("Seleccionar Tienda a Auditar:", opciones_tienda, index=0)
            
            if t_sel == "Ninguna":
                st.info("👈 Selecciona una **Tienda** específica o la opción **'Todas las Tiendas'** para desplegar el resumen y detalle de rectificaciones.")
            else:
                if t_sel == "Todas las Tiendas":
                    df_aud_sla = df_sla.copy()
                    df_aud_rect = df_rect.copy() if not df_rect.empty else pd.DataFrame()
                else:
                    df_aud_sla = df_sla[df_sla["Tienda"].astype(str) == str(t_sel)].copy()
                    df_aud_rect = df_rect[df_rect["Tienda"].astype(str) == str(t_sel)].copy() if not df_rect.empty else pd.DataFrame()

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
                    busqueda_pedido = st.text_input("🔍 Filtrar exclusivamente por Número de Pedido:", "")
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
                        "Almacen", "Pedido", "Nº Rectificación", "Fecha de Grabación", "Artículo", 
                        "Descripción", "Familia", "Subfamilia", "Es_Master", "Motivo", "Procedencia", "Estado"
                    ]

                    if col_unid_grab:
                        cols_rect_disp.append(col_unid_grab)
                    if col_unid_abon:
                        cols_rect_disp.append(col_unid_abon)

                    cols_rect_disp.append("Monto_Signed")
                    
                    cols_rect_exist = [c for c in cols_rect_disp if c in df_aud_rect.columns]

                    df_aud_rect_disp = df_aud_rect[cols_rect_exist].copy()
                    
                    rename_dict_det = {
                        "Almacen": "Almacén",
                        "Nº Rectificación": "N° Rectif.",
                        "Fecha de Grabación": "Fecha Grabación",
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
                            "N° Rectif.": st.column_config.Column("N° Rectif.", width="small"),
                            "Fecha Grabación": st.column_config.Column("Fecha", width="small"),
                            "Artículo": st.column_config.Column("SKU", width="small"),
                            "Descripción": st.column_config.Column("Producto / Descripción", width="large"),
                            "Familia": st.column_config.Column("Familia", width="medium"),
                            "Subfamilia": st.column_config.Column("Subfamilia", width="medium"),
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

        # HOJA 4: ANÁLISIS EXCLUSIVO DE SUSTITUCIÓN DISTINTA SUBFAMILIA (APAREAMIENTO ÍTEM A ÍTEM POR MONTO)
        with tab4:
            st.subheader("🔄 Análisis de Casos: Sustitución Distinta Subfamilia (Faltante > Sobrante)")
            st.markdown("Auditoría de pedidos clasificados como **'Sustitución Distinta Subfamilia'** donde el producto **FALTANTE** posee un valor monetario **mayor** al producto **SOBRANTE** entregado.")

            df_sust_cas = df_sla[df_sla["Casuistica"] == "Sustitución Distinta Subfamilia"].copy()
            pedidos_sust_distinta = set(df_sust_cas["Pedido"].dropna().unique())

            if not df_rect.empty and pedidos_sust_distinta:
                df_r_sust = df_rect[df_rect["Pedido"].isin(pedidos_sust_distinta)].copy()
                
                col_motivo_s = "Motivo_Clean" if "Motivo_Clean" in df_r_sust.columns else ("Motivo" if "Motivo" in df_r_sust.columns else None)
                if col_motivo_s:
                    df_r_sust["Motivo_Norm"] = df_r_sust[col_motivo_s].astype(str).str.strip().str.upper()
                else:
                    df_r_sust["Motivo_Norm"] = "F"

                col_art_lbl = "Artículo" if "Artículo" in df_r_sust.columns else ("SKU" if "SKU" in df_r_sust.columns else "Producto")
                col_desc_lbl = "Descripción" if "Descripción" in df_r_sust.columns else "Producto"

                filas_comparativas = []

                for ped, grp in df_r_sust.groupby("Pedido"):
                    f_items = grp[grp["Motivo_Norm"] == "F"].sort_values(by="Monto_Rectif", ascending=False).reset_index(drop=True)
                    s_items = grp[grp["Motivo_Norm"] == "S"].sort_values(by="Monto_Rectif", ascending=False).reset_index(drop=True)

                    if not f_items.empty and not s_items.empty:
                        tienda_val = grp["Tienda"].iloc[0] if "Tienda" in grp.columns else "—"
                        almacen_val = grp["Almacen"].iloc[0] if "Almacen" in grp.columns else "501"

                        max_pairs = max(len(f_items), len(s_items))

                        for i in range(max_pairs):
                            if i < len(f_items):
                                row_f = f_items.iloc[i]
                                sku_f = str(row_f[col_art_lbl])
                                desc_f = str(row_f[col_desc_lbl]) if col_desc_lbl in row_f else sku_f
                                monto_f = float(row_f["Monto_Rectif"])
                            else:
                                sku_f, desc_f, monto_f = "—", "—", 0.0

                            if i < len(s_items):
                                row_s = s_items.iloc[i]
                                sku_s = str(row_s[col_art_lbl])
                                desc_s = str(row_s[col_desc_lbl]) if col_desc_lbl in row_s else sku_s
                                monto_s = float(row_s["Monto_Rectif"])
                            else:
                                sku_s, desc_s, monto_s = "—", "—", 0.0

                            if monto_f > monto_s:
                                dif_valor = monto_f - monto_s
                                filas_comparativas.append({
                                    "Almacén": almacen_val,
                                    "Tienda": tienda_val,
                                    "Pedido": ped,
                                    "SKU Faltante": sku_f,
                                    "Producto Faltante": desc_f,
                                    "Monto Faltante ($)": monto_f,
                                    "SKU Sobrante": sku_s,
                                    "Producto Sobrante": desc_s,
                                    "Monto Sobrante ($)": monto_s,
                                    "Diferencia Valor ($)": dif_valor
                                })

                if filas_comparativas:
                    df_sust_analisis = pd.DataFrame(filas_comparativas)

                    # CONVERSIÓN Y FORMATO LIMPIO PARA EVITAR VALORES EN BLANCO EN EL KPI
                    tot_pedidos_sust_desf = int(df_sust_analisis["Pedido"].nunique())
                    tot_perdida_monto = float(df_sust_analisis["Diferencia Valor ($)"].sum())

                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("🚨 Pedidos Sustitución Distinta Subfamilia (Desfavorable)", f"{tot_pedidos_sust_desf:,}")
                    col_m2.metric("💸 Pérdida de Valor Total ($)", f"".replace(",", "X").replace(".", ",").replace("X", "."))

                    st.markdown("---")
                    st.markdown("### 🏆 Top 10 de Tiendas con Mayor Cantidad de Pedidos Afectados")

                    # TABLA TOP 10 TIENDAS CON DIFERENCIA DE VALOR TOTAL ACUMULADO
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
                    opciones_tienda_sust = ["Ninguna", "Todas las Tiendas"] + tiendas_sust_opciones
                    
                    t_sust_sel = st.selectbox("Seleccionar Tienda a Auditar:", opciones_tienda_sust, index=0)

                    st.markdown("### 📋 Detalle Individual por Tienda, Pedido y Artículos de Sustitución")

                    if t_sust_sel == "Ninguna":
                        st.info("👈 Selecciona una **Tienda** específica o la opción **'Todas las Tiendas'** para desplegar el detalle individual de artículos.")
                    else:
                        if t_sust_sel == "Todas las Tiendas":
                            df_sust_analisis_filtrada = df_sust_analisis.copy()
                        else:
                            df_sust_analisis_filtrada = df_sust_analisis[df_sust_analisis["Tienda"].astype(str) == str(t_sust_sel)].copy()

                        busqueda_pedido_sust = st.text_input("🔍 Filtrar exclusivamente por Número de Pedido (Pestaña Sustituciones):", "")
                        if busqueda_pedido_sust:
                            df_sust_analisis_filtrada = df_sust_analisis_filtrada[
                                df_sust_analisis_filtrada["Pedido"].astype(str).str.contains(busqueda_pedido_sust.strip(), case=False, na=False)
                            ]

                        if not df_sust_analisis_filtrada.empty:
                            cols_detalle_sust = [
                                "Almacén", "Tienda", "Pedido", 
                                "SKU Faltante", "Producto Faltante", "Monto Faltante ($)", 
                                "SKU Sobrante", "Producto Sobrante", "Monto Sobrante ($)", 
                                "Diferencia Valor ($)"
                            ]

                            df_sust_analisis_sorted = df_sust_analisis_filtrada[cols_detalle_sust].sort_values(by="Diferencia Valor ($)", ascending=False).reset_index(drop=True)

                            st.dataframe(
                                df_sust_analisis_sorted,
                                hide_index=True,
                                column_config={
                                    "Almacén": st.column_config.Column("Almacén", width="small"),
                                    "Tienda": st.column_config.Column("Tienda", width="small"),
                                    "Pedido": st.column_config.Column("Pedido", width="medium"),
                                    "SKU Faltante": st.column_config.Column("SKU Falta", width="small"),
                                    "Producto Faltante": st.column_config.Column("Producto Faltante", width="large"),
                                    "Monto Faltante ($)": st.column_config.NumberColumn("Monto Falta ($)", format="$%.2f", width="medium"),
                                    "SKU Sobrante": st.column_config.Column("SKU Sobra", width="small"),
                                    "Producto Sobrante": st.column_config.Column("Producto Sobrante", width="large"),
                                    "Monto Sobrante ($)": st.column_config.NumberColumn("Monto Sobra ($)", format="$%.2f", width="medium"),
                                    "Diferencia Valor ($)": st.column_config.NumberColumn("Diferencia Valor ($)", format="$%.2f", width="medium")
                                }
                            )
                        else:
                            st.info("ℹ️ No hay pedidos registrados para la tienda o criterio de búsqueda seleccionado.")
                else:
                    st.success("🎉 No se registraron pedidos de 'Sustitución Distinta Subfamilia' donde el artículo faltante sea de mayor valor al sobrante.")
            else:
                st.info("ℹ️ No existen pedidos de 'Sustitución Distinta Subfamilia' para la selección actual de filtros.")

except Exception as e:
    st.error(f"Error cargando el tablero: {e}")
