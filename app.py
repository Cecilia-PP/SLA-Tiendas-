import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Tablero Satisfacción - SLA Tiendas", layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

# CSS MEJORADO: Permite salto de línea en los encabezados y ajusta padding para evitar recortes
st.markdown("""
<style>
    div[data-testid="stTable"] th, div[data-testid="stDataFrame"] th {
        white-space: normal !important;
        word-wrap: break-word !important;
        text-align: center !important;
        vertical-align: middle !important;
        padding: 8px 4px !important;
    }
    div[data-testid="stDataFrame"] div[role="columnheader"] p {
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("📦 Tablero SLA y Satisfacción de Tienda")

@st.cache_data
def cargar_datos_sla():
    if os.path.exists("Tablero_SLA_Pedidos.parquet"):
        df_sla = pd.read_parquet("Tablero_SLA_Pedidos.parquet")
        df_rect = pd.read_parquet("Tablero_Rectificaciones_Detalle.parquet")
        return df_sla, df_rect
    return pd.DataFrame(), pd.DataFrame()

try:
    df_sla, df_rect = cargar_datos_sla()

    if not df_sla.empty:
        # Sidebar: Filtros
        st.sidebar.header("🔍 Filtros de Búsqueda")

        if "Almacen" in df_sla.columns:
            almacenes = sorted([str(x) for x in df_sla["Almacen"].dropna().unique()])
            almacen_sel = st.sidebar.multiselect("Almacén:", almacenes, default=almacenes)
            df_sla = df_sla[df_sla["Almacen"].astype(str).isin(almacen_sel)]

        if "Gestion" in df_sla.columns and df_sla["Gestion"].notna().any():
            gestiones = sorted([str(x) for x in df_sla["Gestion"].dropna().unique()])
            gestion_sel = st.sidebar.multiselect("Gestión / Zona:", gestiones, default=gestiones)
            df_sla = df_sla[df_sla["Gestion"].astype(str).isin(gestion_sel)]

        if "Responsable_Tienda" in df_sla.columns and df_sla["Responsable_Tienda"].notna().any():
            responsables = sorted([str(x) for x in df_sla["Responsable_Tienda"].dropna().unique()])
            resp_sel = st.sidebar.multiselect("Franquiciado / Supervisor:", responsables, default=responsables)
            df_sla = df_sla[df_sla["Responsable_Tienda"].astype(str).isin(resp_sel)]

        if "Tienda" in df_sla.columns:
            tiendas = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
            tienda_sel = st.sidebar.multiselect("Tienda:", tiendas, default=tiendas)
            df_sla = df_sla[df_sla["Tienda"].astype(str).isin(tienda_sel)]

        if "Año" in df_sla.columns and df_sla["Año"].notna().any():
            anios = sorted([int(x) for x in df_sla["Año"].dropna().unique()], reverse=True)
            anio_sel = st.sidebar.multiselect("Año:", anios, default=anios)
            df_sla = df_sla[df_sla["Año"].isin(anio_sel) | df_sla["Año"].isna()]

        if "Mes" in df_sla.columns and df_sla["Mes"].notna().any():
            meses = sorted([int(x) for x in df_sla["Mes"].dropna().unique()])
            mes_sel = st.sidebar.multiselect("Mes:", meses, default=meses)
            df_sla = df_sla[df_sla["Mes"].isin(mes_sel) | df_sla["Mes"].isna()]

        # -------------------------------------------------------------
        # 🎯 FILTRO DE OUTLIERS: EVALUADO POR RELACIÓN ALMACÉN - TIENDA
        # -------------------------------------------------------------
        st.sidebar.markdown("---")
        st.sidebar.header("⚠️ Filtro de Outliers")
        excluir_outliers = st.sidebar.checkbox("Excluir relaciones bajo volumen", value=False)

        if excluir_outliers:
            min_pedidos_rel = st.sidebar.number_input("Mínimo de pedidos por Tienda:", min_value=1, value=10, step=1)
            
            conteo_rel = df_sla.groupby(["Almacen", "Tienda"])["Pedido"].count().reset_index()
            rel_validas = conteo_rel[conteo_rel["Pedido"] >= min_pedidos_rel]
            
            pedidos_iniciales = len(df_sla)
            df_sla = df_sla.merge(rel_validas[["Almacen", "Tienda"]], on=["Almacen", "Tienda"], how="inner")
            pedidos_filtrados = pedidos_iniciales - len(df_sla)
            
            st.sidebar.caption(f"ℹ️ Se excluyeron **{pedidos_filtrados}** pedidos de tiendas/rutas con menos de {min_pedidos_rel} envíos.")

        # DEFINICIÓN DE PESTAÑAS
        tab1, tab2, tab3 = st.tabs([
            "📊 1. Ranking SLA por Almacén y Tienda",
            "📈 2. Casuísticas y Modelo SLA",
            "🏪 3. Auditoría Práctica por Sucursal"
        ])

        # -------------------------------------------------------------
        # HOJA 1: RANKING SLA
        # -------------------------------------------------------------
        with tab1:
            st.subheader(
                "📊 Ranking SLA por Almacén y Tienda",
                help="Cálculo: (Suma de Puntos Obtenidos / Suma de Puntos Posibles de Pedidos) × 10. Ordenado de menor a mayor SLA."
            )

            # Indicadores Métricos Globales
            tot_pedidos_global = len(df_sla)
            tot_pedidos_rectif_global = (df_sla["Casuistica"] != "Pedido Perfecto").sum()
            tot_pts_obtenidos_global = df_sla["Puntos_Obtenidos"].sum()
            tot_pts_posibles_global = tot_pedidos_global * 10.0
            sla_global = (tot_pts_obtenidos_global / tot_pts_posibles_global * 10.0) if tot_pts_posibles_global > 0 else 0.0

            # PUNTAJE SLA COMO PRIMER INDICADOR
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("⭐ Puntaje SLA Promedio", f"{sla_global:.2f} / 10.0")
            k2.metric("📦 Pedidos Totales", f"{tot_pedidos_global:,}")
            k3.metric("⚠️ Pedidos con Rectificación", f"{tot_pedidos_rectif_global:,}")
            k4.metric("🎯 Puntos Obtenidos / Posibles", f"{tot_pts_obtenidos_global:,.1f} / {tot_pts_posibles_global:,.1f}")

            st.markdown("---")

            # GRÁFICO ESTILIZADO DE BARRAS FINAS
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

            colores_alm = ["#2b5c8f", "#2ba884", "#e07a5f", "#f4a261"]

            fig_mes_alm = px.bar(
                df_alm_mes,
                x="Nombre_Mes",
                y="Puntaje SLA",
                color="Etiqueta_Almacen",
                barmode="group",
                text="Puntaje SLA",
                color_discrete_sequence=colores_alm
            )
            
            fig_mes_alm.update_traces(
                texttemplate='<b>%{text:.2f}</b> ⭐', 
                textposition='outside',
                marker_line_color='rgb(8,48,107)',
                marker_line_width=1,
                opacity=0.9
            )
            
            fig_mes_alm.update_layout(
                yaxis=dict(range=[7.0, 10.2], title="Puntaje SLA (Escala 7 a 10)", dtick=0.5, gridcolor="#e5e5e5"),
                xaxis=dict(title="Mes"),
                legend=dict(title="Almacén", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=380,
                bargap=0.45,
                bargroupgap=0.15,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_mes_alm, use_container_width=True)

            # -------------------------------------------------------------
            # CUADRO 1: DETALLE POR FRANQUICIADO / SUPERVISOR
            # -------------------------------------------------------------
            st.markdown("---")
            st.markdown("### 🏪 Detalle por Franquiciado / Supervisor")

            group_cols_resp = []
            if "Responsable_Tienda" in df_sla.columns:
                group_cols_resp.append("Responsable_Tienda")
            else:
                group_cols_resp = ["Tienda"]

            tb_resp = df_sla.groupby(group_cols_resp, as_index=False).agg(
                Total_Tiendas=("Tienda", "nunique"),
                Pedidos_Totales=("Pedido", "count"),
                Pedidos_Con_Rectificaciones=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()),
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )

            tb_resp["Puntos_Posibles"] = tb_resp["Pedidos_Totales"] * 10.0
            tb_resp["Puntaje SLA"] = (tb_resp["Puntos_Obtenidos"] / tb_resp["Puntos_Posibles"]) * 10.0
            tb_resp["Puntaje SLA"] = tb_resp["Puntaje SLA"].fillna(0.0)
            tb_resp["Tasa_Aprobacion"] = ((tb_resp["Pedidos_Totales"] - tb_resp["Pedidos_Con_Rectificaciones"]) / tb_resp["Pedidos_Totales"]) * 100.0

            tb_resp_sorted = tb_resp.sort_values(by="Puntaje SLA", ascending=True).reset_index(drop=True)

            tasa_aprob_global = ((tot_pedidos_global - tot_pedidos_rectif_global) / tot_pedidos_global * 100.0) if tot_pedidos_global > 0 else 0.0
            tot_tiendas_global = df_sla["Tienda"].nunique() if "Tienda" in df_sla.columns else 0

            fila_total_resp = pd.DataFrame([{
                "Responsable_Tienda": "Total General",
                "Total_Tiendas": tot_tiendas_global,
                "Pedidos_Totales": tot_pedidos_global,
                "Pedidos_Con_Rectificaciones": tot_pedidos_rectif_global,
                "Tasa_Aprobacion": tasa_aprob_global,
                "Puntos_Obtenidos": tot_pts_obtenidos_global,
                "Puntos_Posibles": tot_pts_posibles_global,
                "Puntaje SLA": sla_global
            }])

            tb_resp_display = pd.concat([tb_resp_sorted, fila_total_resp], ignore_index=True)

            col_tiendas_lbl = "Total\nTiendas"
            col_totales_lbl = "Pedidos\nTotales"
            col_rectif_lbl = "Pedidos con\nRectificaciones"
            col_tasa_lbl = "% Tasa\nAprobación"
            col_pts_obtenidos_lbl = "Puntos\nObtenidos"
            col_pts_posibles_lbl = "Puntos\nPosibles"
            col_sla_lbl = "Puntaje SLA\n(1 a 10)"

            tb_resp_display = tb_resp_display.rename(columns={
                "Responsable_Tienda": "Franquiciado / Supervisor",
                "Total_Tiendas": col_tiendas_lbl,
                "Pedidos_Totales": col_totales_lbl,
                "Pedidos_Con_Rectificaciones": col_rectif_lbl,
                "Tasa_Aprobacion": col_tasa_lbl,
                "Puntos_Obtenidos": col_pts_obtenidos_lbl,
                "Puntos_Posibles": col_pts_posibles_lbl,
                "Puntaje SLA": col_sla_lbl
            })

            cols_order_resp = [
                "Franquiciado / Supervisor", col_tiendas_lbl,
                col_totales_lbl, col_rectif_lbl, col_tasa_lbl, 
                col_pts_obtenidos_lbl, col_pts_posibles_lbl, col_sla_lbl
            ]

            st.dataframe(
                tb_resp_display[cols_order_resp],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Franquiciado / Supervisor": st.column_config.Column("Franquiciado / Supervisor", width="large"),
                    col_tiendas_lbl: st.column_config.NumberColumn(col_tiendas_lbl, format="%d", width="small"),
                    col_totales_lbl: st.column_config.NumberColumn(col_totales_lbl, format="%d", width="small"),
                    col_rectif_lbl: st.column_config.NumberColumn(col_rectif_lbl, format="%d", width="medium"),
                    col_tasa_lbl: st.column_config.NumberColumn(col_tasa_lbl, format="%.2f %%", width="medium"),
                    col_pts_obtenidos_lbl: st.column_config.NumberColumn(col_pts_obtenidos_lbl, format="%.1f Pts", width="medium"),
                    col_pts_posibles_lbl: st.column_config.NumberColumn(col_pts_posibles_lbl, format="%.1f Pts", width="medium"),
                    col_sla_lbl: st.column_config.NumberColumn(col_sla_lbl, format="%.2f ⭐", width="medium")
                }
            )

            # -------------------------------------------------------------
            # CUADRO 2: DETALLE POR ALMACÉN, TIENDA Y GESTIÓN
            # -------------------------------------------------------------
            st.markdown("---")
            st.markdown("### 🏬 Detalle por Almacén, Tienda y Gestión")

            group_cols_alm = ["Almacen", "Tienda"]
            if "Gestion" in df_sla.columns:
                group_cols_alm.append("Gestion")

            tb_alm_tienda = df_sla.groupby(group_cols_alm, as_index=False).agg(
                Pedidos_Totales=("Pedido", "count"),
                Pedidos_Con_Rectificaciones=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()),
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )

            tb_alm_tienda["Puntos_Posibles"] = tb_alm_tienda["Pedidos_Totales"] * 10.0
            tb_alm_tienda["Puntaje SLA"] = (tb_alm_tienda["Puntos_Obtenidos"] / tb_alm_tienda["Puntos_Posibles"]) * 10.0
            tb_alm_tienda["Puntaje SLA"] = tb_alm_tienda["Puntaje SLA"].fillna(0.0)
            tb_alm_tienda["Tasa_Aprobacion"] = ((tb_alm_tienda["Pedidos_Totales"] - tb_alm_tienda["Pedidos_Con_Rectificaciones"]) / tb_alm_tienda["Pedidos_Totales"]) * 100.0

            tb_alm_tienda_sorted = tb_alm_tienda.sort_values(by="Puntaje SLA", ascending=True).reset_index(drop=True)

            fila_dict_alm = {
                "Almacen": "Total General",
                "Tienda": "—",
                "Pedidos_Totales": tot_pedidos_global,
                "Pedidos_Con_Rectificaciones": tot_pedidos_rectif_global,
                "Tasa_Aprobacion": tasa_aprob_global,
                "Puntos_Obtenidos": tot_pts_obtenidos_global,
                "Puntos_Posibles": tot_pts_posibles_global,
                "Puntaje SLA": sla_global
            }
            if "Gestion" in group_cols_alm:
                fila_dict_alm["Gestion"] = "—"

            fila_total_alm = pd.DataFrame([fila_dict_alm])

            tb_alm_tienda_display = pd.concat([tb_alm_tienda_sorted, fila_total_alm], ignore_index=True)

            rename_dict_alm = {
                "Almacen": "Almacén",
                "Tienda": "Tienda",
                "Gestion": "Gestión",
                "Pedidos_Totales": col_totales_lbl,
                "Pedidos_Con_Rectificaciones": col_rectif_lbl,
                "Tasa_Aprobacion": col_tasa_lbl,
                "Puntos_Obtenidos": col_pts_obtenidos_lbl,
                "Puntos_Posibles": col_pts_posibles_lbl,
                "Puntaje SLA": col_sla_lbl
            }

            tb_alm_tienda_display = tb_alm_tienda_display.rename(columns=rename_dict_alm)

            cols_order_alm = ["Almacén", "Tienda"]
            if "Gestión" in tb_alm_tienda_display.columns:
                cols_order_alm.append("Gestión")

            cols_order_alm.extend([
                col_totales_lbl, col_rectif_lbl, col_tasa_lbl, 
                col_pts_obtenidos_lbl, col_pts_posibles_lbl, col_sla_lbl
            ])

            st.dataframe(
                tb_alm_tienda_display[cols_order_alm],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Almacén": st.column_config.Column("Almacén", width="small"),
                    "Tienda": st.column_config.Column("Tienda", width="small"),
                    "Gestión": st.column_config.Column("Gestión", width="small"),
                    col_totales_lbl: st.column_config.NumberColumn(col_totales_lbl, format="%d", width="small"),
                    col_rectif_lbl: st.column_config.NumberColumn(col_rectif_lbl, format="%d", width="medium"),
                    col_tasa_lbl: st.column_config.NumberColumn(col_tasa_lbl, format="%.2f %%", width="medium"),
                    col_pts_obtenidos_lbl: st.column_config.NumberColumn(col_pts_obtenidos_lbl, format="%.1f Pts", width="medium"),
                    col_pts_posibles_lbl: st.column_config.NumberColumn(col_pts_posibles_lbl, format="%.1f Pts", width="medium"),
                    col_sla_lbl: st.column_config.NumberColumn(col_sla_lbl, format="%.2f ⭐", width="medium")
                }
            )

            # -------------------------------------------------------------
            # CUADRO 3: DESGLOSE DE ERRORES POR CASUÍSTICA Y ORIGEN
            # -------------------------------------------------------------
            st.markdown("---")
            st.markdown("### 📊 Desglose de Errores por Casuística y Origen (Tienda vs. Almacén)")
            
            df_errores_filtro = df_sla[df_sla["Casuistica"] != "Pedido Perfecto"].copy()

            if not df_errores_filtro.empty:
                tot_ped_error = len(df_errores_filtro)
                
                pedidos_filtrados_set = set(df_errores_filtro["Pedido"].dropna().unique())
                df_rect_fil = df_rect[df_rect["Pedido"].isin(pedidos_filtrados_set) & (df_rect["Estado"].astype(str).str.upper() != "A")].copy()
                
                proc_por_pedido = df_rect_fil.groupby("Pedido")["Procedencia"].apply(lambda x: list(set(x.astype(str).str.upper()))).to_dict()

                def calc_origen(pedido):
                    procs = proc_por_pedido.get(pedido, [])
                    if "T" in procs and "G" in procs:
                        return "Mixto"
                    elif "T" in procs:
                        return "Tienda (T)"
                    elif "G" in procs:
                        return "Almacén (G)"
                    return "Sin Datos"

                df_errores_filtro["Origen_Grabacion"] = df_errores_filtro["Pedido"].apply(calc_origen)

                tb_cas_origen = df_errores_filtro.groupby("Casuistica", as_index=False).agg(
                    Cantidad_Pedidos=("Pedido", "count"),
                    Origen_Tienda=("Origen_Grabacion", lambda x: (x == "Tienda (T)").sum()),
                    Origen_Almacen=("Origen_Grabacion", lambda x: (x == "Almacén (G)").sum()),
                    Origen_Mixto=("Origen_Grabacion", lambda x: (x == "Mixto").sum())
                )

                tb_cas_origen["% Part. sobre Errores"] = (tb_cas_origen["Cantidad_Pedidos"] / tot_ped_error) * 100
                tb_cas_origen["% Origen Tienda (T)"] = (tb_cas_origen["Origen_Tienda"] / tb_cas_origen["Cantidad_Pedidos"]) * 100
                tb_cas_origen["% Origen Almacén (G)"] = (tb_cas_origen["Origen_Almacen"] / tb_cas_origen["Cantidad_Pedidos"]) * 100

                orden_cas = ["Sobrante Neto", "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", "Faltante Neto", "Etiquetas Cambiadas"]
                tb_cas_origen["Casuistica"] = pd.Categorical(tb_cas_origen["Casuistica"], categories=orden_cas, ordered=True)
                tb_cas_origen = tb_cas_origen.sort_values("Casuistica").reset_index(drop=True)

                st.dataframe(
                    tb_cas_origen[[
                        "Casuistica", "Cantidad_Pedidos", "% Part. sobre Errores",
                        "% Origen Tienda (T)", "% Origen Almacén (G)"
                    ]],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Casuistica": st.column_config.Column("Casuística / Tipo de Error", width="medium"),
                        "Cantidad_Pedidos": st.column_config.NumberColumn("Cantidad Pedidos", format="%d", width="small"),
                        "% Part. sobre Errores": st.column_config.NumberColumn("% Part. sobre Errores", format="%.2f %%", width="medium"),
                        "% Origen Tienda (T)": st.column_config.NumberColumn("% Origen Tienda (T)", format="%.1f %%", width="medium"),
                        "% Origen Almacén (G)": st.column_config.NumberColumn("% Origen Almacén (G)", format="%.1f %%", width="medium")
                    }
                )
            else:
                st.success("🎉 No hay errores ni rectificaciones registradas para la selección actual.")

        # -------------------------------------------------------------
        # HOJA 2: CASUÍSTICAS Y MODELO SLA
        # -------------------------------------------------------------
        with tab2:
            st.subheader("📈 Matriz Ejecutiva de Casuísticas por Pedido")
            tot_p = len(df_sla)
            
            cas_sum = df_sla.groupby("Casuistica", as_index=False).agg(
                Cantidad_Pedidos=("Pedido", "count"),
                Lineas_Rectificadas=("Lineas_Rectificadas", "sum")
            )
            cas_sum["% Participación Pedidos"] = (cas_sum["Cantidad_Pedidos"] / tot_p) * 100
            
            orden_cas = ["Pedido Perfecto", "Sobrante Neto", "Sustitución Misma Subfamilia", "Sustitución Distinta Subfamilia", "Faltante Neto", "Etiquetas Cambiadas"]
            cas_sum["Casuistica"] = pd.Categorical(cas_sum["Casuistica"], categories=orden_cas, ordered=True)
            cas_sum = cas_sum.sort_values("Casuistica").reset_index(drop=True)

            st.dataframe(
                cas_sum,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Casuistica": st.column_config.Column("Casuística Operativa"),
                    "Cantidad_Pedidos": st.column_config.NumberColumn("Cantidad de Pedidos", format="%d"),
                    "Lineas_Rectificadas": st.column_config.NumberColumn("Líneas Rectificadas", format="%d"),
                    "% Participación Pedidos": st.column_config.NumberColumn("% Part. Pedidos", format="%.2f %%")
                }
            )

            st.markdown("---")
            st.subheader("📋 Reglas de Puntaje y Evaluación SLA por Pedido")
            
            matriz_p = pd.DataFrame([
                {"Casuística Operativa": "Pedido Perfecto", "Descuento Aplicado": "0.0 Pts", "Puntaje por Pedido": "10.0 / 10", "Justificación Cualitativa y Operacional": "Envío sin rectificaciones. Servicio 100% conforme."},
                {"Casuística Operativa": "Sobrante Neto", "Descuento Aplicado": "0.0 Pts", "Puntaje por Pedido": "10.0 / 10", "Justificación Cualitativa y Operacional": "Excedente físico entregado. No descuenta puntaje SLA."},
                {"Casuística Operativa": "Sustitución Misma Subfamilia", "Descuento Aplicado": "-2.5 Pts", "Puntaje por Pedido": "7.5 / 10", "Justificación Cualitativa y Operacional": "Error de picking de productos equivalentes (ej. Yogur Entero por Light)."},
                {"Casuística Operativa": "Sustitución Distinta Subfamilia", "Descuento Aplicado": "-4.5 Pts", "Puntaje por Pedido": "5.5 / 10", "Justificación Cualitativa y Operacional": "Error grave de picking entre categorías disímiles."},
                {"Casuística Operativa": "Faltante Neto", "Descuento Aplicado": "-6.0 Pts", "Puntaje por Pedido": "4.0 / 10", "Justificación Cualitativa y Operacional": "Despacho incompleto. Quiebre de stock en góndola."},
                {"Casuística Operativa": "Etiquetas Cambiadas", "Descuento Aplicado": "-10.0 Pts", "Puntaje por Pedido": "0.0 / 10", "Justificación Cualitativa y Operacional": "Error masivo logístico (>10 líneas cruzadas). Requerimiento de auditoría total."}
            ])
            st.dataframe(matriz_p, hide_index=True, use_container_width=True)

        # -------------------------------------------------------------
        # HOJA 3: AUDITORÍA INDIVIDUAL
        # -------------------------------------------------------------
        with tab3:
            st.subheader("🏪 Auditoría Práctica y Detalle de Rectificaciones por Sucursal")
            
            tiendas_l = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
            t_sel = st.selectbox("Seleccionar Tienda a Auditar:", tiendas_l)
            
            df_aud_sla = df_sla[df_sla["Tienda"].astype(str) == str(t_sel)].copy()
            df_aud_rect = df_rect[df_rect["Tienda"].astype(str) == str(t_sel)].copy() if not df_rect.empty else pd.DataFrame()

            tot_p_t = len(df_aud_sla)
            tot_p_rect_t = (df_aud_sla["Casuistica"] != "Pedido Perfecto").sum()
            pts_posibles_t = tot_p_t * 10.0
            pts_obtenidos_t = df_aud_sla["Puntos_Obtenidos"].sum()
            nota_sla_t = (pts_obtenidos_t / pts_posibles_t * 10.0) if pts_posibles_t > 0 else 0.0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("⭐ Puntaje SLA Tienda", f"{nota_sla_t:.2f} / 10.0")
            m2.metric("📦 Pedidos Totales Recibidos", f"{tot_p_t:,}")
            m3.metric("⚠️ Pedidos con Rectificaciones", f"{tot_p_rect_t:,}")
            m4.metric("🎯 Puntos Obtenidos / Posibles", f"{pts_obtenidos_t:,.1f} / {pts_posibles_t:,.1f}")

            st.markdown("---")
            
            glosario_txt = """GLOSARIO:

1. Procedencia:
   • 'G' = Almacén (Generado/detectado en Centro de Distribución)
   • 'T' = Tienda (Registrado/detectado en tienda)

2. Motivo:
   • 'F' = Falta (Faltante de mercadería)
   • 'S' = Sobra (Sobrante de mercadería)

3. Estado:
   • 'A' = Automática (Mercadería no facturada / regularización) 
           ⚠ EXCLUIDA DEL CÁLCULO DEL SLA (No penaliza el puntaje).
   • 'M' = Confirmada (Afecta SLA según motivo)
   • 'P' = Pendiente (Afecta SLA según motivo)
   • 'R' = Rechazada (Afecta SLA según motivo)

📌 NOTA TÉCNICA CÁLCULO SLA:
Las líneas con Estado 'A' se muestran en la tabla inferior para trazabilidad, pero se excluyen del cálculo de penalizaciones SLA, considerándose como Pedidos Perfectos si no registran otros motivos R, M o P."""

            st.subheader("🔎 Detalle de Rectificaciones Registradas", help=glosario_txt)

            if not df_aud_rect.empty:
                busqueda_sku = st.text_input("🔍 Filtrar por Descripción o Código SKU:", "")
                if busqueda_sku:
                    df_aud_rect = df_aud_rect[
                        df_aud_rect["Descripción"].astype(str).str.contains(busqueda_sku, case=False, na=False) |
                        df_aud_rect["Artículo"].astype(str).str.contains(busqueda_sku, case=False, na=False)
                    ]

                cols_rect_disp = [
                    "Pedido", "Nº Rectificación", "Fecha de Grabación", "Artículo", 
                    "Descripción", "Motivo", "Procedencia", "Estado", 
                    "Unid_Grabadas", "Unid_Abonadas", "Monto_Rectif"
                ]
                
                cols_rect_exist = [c for c in cols_rect_disp if c in df_aud_rect.columns]

                df_aud_rect_disp = df_aud_rect[cols_rect_exist].copy()
                df_aud_rect_disp = df_aud_rect_disp.rename(columns={
                    "Nº Rectificación": "N° Rectif.",
                    "Fecha de Grabación": "Fecha Grabación",
                    "Unid_Grabadas": "Unid. Grabadas",
                    "Unid_Abonadas": "Unid. Abonadas",
                    "Monto_Rectif": "Monto ($)"
                })

                st.dataframe(
                    df_aud_rect_disp,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Pedido": st.column_config.Column("Pedido", width="small"),
                        "N° Rectif.": st.column_config.Column("N° Rectif.", width="small"),
                        "Fecha Grabación": st.column_config.Column("Fecha", width="small"),
                        "Artículo": st.column_config.Column("SKU", width="small"),
                        "Descripción": st.column_config.Column("Producto / Descripción", width="large"),
                        "Motivo": st.column_config.Column("Motivo", width="small"),
                        "Procedencia": st.column_config.Column("Procedencia", width="small"),
                        "Estado": st.column_config.Column("Estado", width="small"),
                        "Unid. Grabadas": st.column_config.NumberColumn("Unid. Grabadas", format="%d", width="small"),
                        "Unid. Abonadas": st.column_config.NumberColumn("Unid. Abonadas", format="%d", width="small"),
                        "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="$%.2f", width="small")
                    }
                )
            else:
                st.success("🎉 Esta tienda no registra rectificaciones de artículos.")

except Exception as e:
    st.error(f"Error cargando el tablero: {e}")
