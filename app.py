import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Tablero Satisfacción - SLA Tiendas", layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

# CSS para centrar y permitir saltos de línea limpios en encabezados
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

        # DEFINICIÓN DE PESTAÑAS
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 1. Ranking SLA por Almacén y Tienda",
            "📈 2. Matriz de Casuísticas por Pedido",
            "📋 3. Modelo SLA y Reglas de Penalización",
            "🏪 4. Auditoría Práctica por Sucursal"
        ])

        # -------------------------------------------------------------
        # HOJA 1: RANKING SLA + METRICAS GLOBALES DE PEDIDOS TOTALES
        # -------------------------------------------------------------
        with tab1:
            st.subheader("📊 Ranking SLA por Almacén y Tienda")
            st.caption("Cálculo: (Suma de Puntos Obtenidos / Suma de Puntos Posibles de Pedidos) × 10. Ordenado de menor a mayor SLA.")

            # Indicadores Metricos Globales
            tot_pedidos_global = len(df_sla)
            tot_pedidos_rectif_global = (df_sla["Casuistica"] != "Pedido Perfecto").sum()
            tot_pts_obtenidos_global = df_sla["Puntos_Obtenidos"].sum()
            tot_pts_posibles_global = tot_pedidos_global * 10.0
            sla_global = (tot_pts_obtenidos_global / tot_pts_posibles_global * 10.0) if tot_pts_posibles_global > 0 else 0.0

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("📦 Pedidos Totales (BDMVTAL)", f"{tot_pedidos_global:,}")
            k2.metric("⚠️ Pedidos con Rectificación", f"{tot_pedidos_rectif_global:,}")
            k3.metric("🎯 Puntos Obtenidos / Posibles", f"{tot_pts_obtenidos_global:,.1f} / {tot_pts_posibles_global:,.1f}")
            k4.metric("⭐ SLA Promedio Red", f"{sla_global:.2f} / 10.0")

            st.markdown("---")

            tb_sla = df_sla.groupby(["Almacen", "Tienda"], as_index=False).agg(
                Pedidos_Totales=("Pedido", "count"),
                Pedidos_Con_Rectificaciones=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()),
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )

            tb_sla["Puntos_Posibles"] = tb_sla["Pedidos_Totales"] * 10.0
            tb_sla["Puntaje SLA"] = (tb_sla["Puntos_Obtenidos"] / tb_sla["Puntos_Posibles"]) * 10.0
            tb_sla["Puntaje SLA"] = tb_sla["Puntaje SLA"].fillna(0.0)

            tb_sla_sorted = tb_sla.sort_values(by="Puntaje SLA", ascending=True).reset_index(drop=True)

            fila_total = pd.DataFrame([{
                "Almacen": "Total General",
                "Tienda": "—",
                "Pedidos_Totales": tot_pedidos_global,
                "Pedidos_Con_Rectificaciones": tot_pedidos_rectif_global,
                "Puntos_Obtenidos": tot_pts_obtenidos_global,
                "Puntos_Posibles": tot_pts_posibles_global,
                "Puntaje SLA": sla_global
            }])

            tb_sla_display = pd.concat([tb_sla_sorted, fila_total], ignore_index=True)

            col_totales_lbl = "Pedidos\nTotales"
            col_rectif_lbl = "Pedidos con\nRectificaciones"
            col_pts_obtenidos_lbl = "Puntos\nObtenidos"
            col_pts_posibles_lbl = "Puntos\nPosibles"
            col_sla_lbl = "Puntaje SLA\n(1 a 10)"

            tb_sla_display = tb_sla_display.rename(columns={
                "Almacen": "Almacén",
                "Tienda": "Tienda",
                "Pedidos_Totales": col_totales_lbl,
                "Pedidos_Con_Rectificaciones": col_rectif_lbl,
                "Puntos_Obtenidos": col_pts_obtenidos_lbl,
                "Puntos_Posibles": col_pts_posibles_lbl,
                "Puntaje SLA": col_sla_lbl
            })

            st.dataframe(
                tb_sla_display[[
                    "Almacén", "Tienda", col_totales_lbl, 
                    col_rectif_lbl, col_pts_obtenidos_lbl, 
                    col_pts_posibles_lbl, col_sla_lbl
                ]],
                hide_index=True,
                column_config={
                    "Almacén": st.column_config.Column("Almacén", width="small"),
                    "Tienda": st.column_config.Column("Tienda", width="small"),
                    col_totales_lbl: st.column_config.NumberColumn(col_totales_lbl, format="%d", width="small"),
                    col_rectif_lbl: st.column_config.NumberColumn(col_rectif_lbl, format="%d", width="small"),
                    col_pts_obtenidos_lbl: st.column_config.NumberColumn(col_pts_obtenidos_lbl, format="%.1f Pts", width="small"),
                    col_pts_posibles_lbl: st.column_config.NumberColumn(col_pts_posibles_lbl, format="%.1f Pts", width="small"),
                    col_sla_lbl: st.column_config.NumberColumn(col_sla_lbl, format="%.2f ⭐", width="small")
                }
            )

        # HOJA 2: MATRIZ GENERAL DE CASUÍSTICAS
        with tab2:
            st.subheader("📈 Matriz Ejecutiva de Casuísticas por Pedido")
            tot_p = len(df_sla)
            cas_sum = df_sla.groupby("Casuistica", as_index=False).agg(
                Cantidad_Pedidos=("Pedido", "count"),
                Lineas_Rectificadas=("Lineas_Rectificadas", "sum"),
                Monto_Total=("Monto_Rectificacion", "sum")
            )
            cas_sum["% Part. Pedidos"] = (cas_sum["Cantidad_Pedidos"] / tot_p) * 100
            st.dataframe(cas_sum, hide_index=True)

        # HOJA 3: MODELO Y REGLAS DE PENALIZACIÓN
        with tab3:
            st.subheader("📋 Matriz Oficial de Penalizaciones SLA")
            matriz_p = pd.DataFrame([
                {"Casuística": "Pedido Perfecto", "Descuento": "0.0 Pts", "Nota Pedido": "10.0 / 10"},
                {"Casuística": "Sobrante Neto", "Descuento": "-1.0 Pt", "Nota Pedido": "9.0 / 10"},
                {"Casuística": "Sustitución Misma Subfamilia", "Descuento": "-2.5 Pts", "Nota Pedido": "7.5 / 10"},
                {"Casuística": "Sustitución Distinta Subfamilia", "Descuento": "-4.5 Pts", "Nota Pedido": "5.5 / 10"},
                {"Casuística": "Faltante Neto", "Descuento": "-6.0 Pts", "Nota Pedido": "4.0 / 10"},
                {"Casuística": "Etiquetas Cambiadas", "Descuento": "-10.0 Pts", "Nota Pedido": "0.0 / 10"}
            ])
            st.dataframe(matriz_p, hide_index=True)

        # HOJA 4: AUDITORÍA INDIVIDUAL
        with tab4:
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
            m1.metric("📦 Pedidos Totales Recibidos", f"{tot_p_t:,}")
            m2.metric("⚠️ Pedidos con Rectificaciones", f"{tot_p_rect_t:,}")
            m3.metric("🎯 Puntos Obtenidos / Posibles", f"{pts_obtenidos_t:,.1f} / {pts_posibles_t:,.1f}")
            m4.metric("⭐ Nota SLA Tienda", f"{nota_sla_t:.2f} / 10.0")

            st.markdown("---")
            st.subheader("🔎 Detalle de Rectificaciones Registradas")

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
