import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Tablero Satisfacción - SLA Tiendas", layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

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
        # HOJA 1: RANKING SLA (PUNTOS OBTENIDOS / PUNTOS POSIBLES)
        # -------------------------------------------------------------
        with tab1:
            st.subheader("📊 Ranking SLA por Almacén y Tienda")
            st.caption("Cálculo: (Suma de Puntos Obtenidos / Suma de Puntos Posibles de Pedidos) × 10. Ordenado de menor a mayor SLA.")

            # Agrupamiento exacto
            tb_sla = df_sla.groupby(["Almacen", "Tienda"], as_index=False).agg(
                Pedidos_Totales=("Pedido", "count"),
                Pedidos_Con_Rectificaciones=("Casuistica", lambda x: (x != "Pedido Perfecto").sum()),
                Puntos_Obtenidos=("Puntos_Obtenidos", "sum")
            )

            # Puntos Posibles = Cantidad de Pedidos * 10 Pts
            tb_sla["Puntos_Posibles"] = tb_sla["Pedidos_Totales"] * 10.0
            
            # Nota Final SLA en Escala 1 a 10
            tb_sla["Puntaje SLA"] = (tb_sla["Puntos_Obtenidos"] / tb_sla["Puntos_Posibles"]) * 10.0
            tb_sla["Puntaje SLA"] = tb_sla["Puntaje SLA"].fillna(0.0)

            # Ordenar de menor a mayor
            tb_sla_sorted = tb_sla.sort_values(by="Puntaje SLA", ascending=True).reset_index(drop=True)

            # Fila de Totales Generales
            tot_pedidos = tb_sla["Pedidos_Totales"].sum()
            tot_rectif = tb_sla["Pedidos_Con_Rectificaciones"].sum()
            tot_pts_obtenidos = tb_sla["Puntos_Obtenidos"].sum()
            tot_pts_posibles = tb_sla["Puntos_Posibles"].sum()
            tot_sla_global = (tot_pts_obtenidos / tot_pts_posibles * 10.0) if tot_pts_posibles > 0 else 0.0

            fila_total = pd.DataFrame([{
                "Almacen": "Total General",
                "Tienda": "—",
                "Pedidos_Totales": tot_pedidos,
                "Pedidos_Con_Rectificaciones": tot_rectif,
                "Puntos_Obtenidos": tot_pts_obtenidos,
                "Puntos_Posibles": tot_pts_posibles,
                "Puntaje SLA": tot_sla_global
            }])

            tb_sla_display = pd.concat([tb_sla_sorted, fila_total], ignore_index=True)

            tb_sla_display = tb_sla_display.rename(columns={
                "Almacen": "Almacén",
                "Tienda": "Tienda",
                "Pedidos_Totales": "Cantidad de Pedidos Totales",
                "Pedidos_Con_Rectificaciones": "Cantidad de Pedidos con Rectificaciones",
                "Puntos_Obtenidos": "Puntos Obtenidos",
                "Puntos_Posibles": "Puntos Posibles"
            })

            st.dataframe(
                tb_sla_display[[
                    "Almacén", "Tienda", "Cantidad de Pedidos Totales", 
                    "Cantidad de Pedidos con Rectificaciones", 
                    "Puntos Obtenidos", "Puntos Posibles", "Puntaje SLA"
                ]],
                width="stretch",
                hide_index=True,
                column_config={
                    "Almacén": st.column_config.Column("Almacén"),
                    "Tienda": st.column_config.Column("Tienda"),
                    "Cantidad de Pedidos Totales": st.column_config.NumberColumn("Cantidad de Pedidos Totales", format="%d"),
                    "Cantidad de Pedidos con Rectificaciones": st.column_config.NumberColumn("Cantidad de Pedidos con Rectificaciones", format="%d"),
                    "Puntos Obtenidos": st.column_config.NumberColumn("Puntos Obtenidos", format="%.1f Pts"),
                    "Puntos Posibles": st.column_config.NumberColumn("Puntos Posibles", format="%.1f Pts"),
                    "Puntaje SLA": st.column_config.NumberColumn("Puntaje SLA (1 a 10)", format="%.2f ⭐")
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
            st.dataframe(cas_sum, width="stretch", hide_index=True)

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
            st.dataframe(matriz_p, width="stretch", hide_index=True)

        # HOJA 4: AUDITORÍA INDIVIDUAL
        with tab4:
            st.subheader("🏪 Auditoría Individual de Sucursal")
            tiendas_l = sorted([str(x) for x in df_sla["Tienda"].dropna().unique() if str(x) != "nan"])
            t_sel = st.selectbox("Seleccionar Tienda a Auditar:", tiendas_l)
            df_aud = df_sla[df_sla["Tienda"].astype(str) == str(t_sel)]
            st.write(f"Total pedidos evaluados: {len(df_aud):,}")

except Exception as e:
    st.error(f"Error cargando el tablero: {e}")
