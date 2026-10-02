Set-Location "C:\Users\cpe021ar\Documents\Python\Tablero_Satifacción_de_Tienda"

@"
import pandas as pd
import glob
import os

print("🔄 Iniciando procesamiento de datos y reevaluación de casuísticas...")

# 1. Cargar Maestro de Productos
path_maestro_csv = glob.glob("Datos_mensuales/*[Mm]aestro*.csv") + glob.glob("*[Mm]aestro*.csv")
df_maestro = pd.DataFrame()

if path_maestro_csv:
    path_maestro = path_maestro_csv[0]
    try:
        df_maestro = pd.read_csv(path_maestro, sep=";", encoding="latin1", dtype=str)
        df_maestro.columns = df_maestro.columns.str.strip()
        
        col_master = [c for c in df_maestro.columns if "bulto master" in c.lower() or "master" in c.lower()]
        if col_master:
            c_name = col_master[0]
            df_maestro["Es_Master"] = df_maestro[c_name].astype(str).str.strip().map({"1": "Sí", "2": "No"}).fillna("No")
        else:
            df_maestro["Es_Master"] = "No"

        cols = list(df_maestro.columns)
        if cols.count("Descripción Familia") > 1:
            idx_sub = [i for i, col in enumerate(cols) if col == "Descripción Familia"]
            if len(idx_sub) > 1:
                cols[idx_sub[1]] = "Descripción Subfamilia"
            df_maestro.columns = cols

        print(f"✅ Maestro cargado desde '{path_maestro}'.")
    except Exception as e:
        print(f"⚠️ Error cargando Maestro: {e}")

# 2. Cargar Detalle de Rectificaciones
archivos_rect = glob.glob("Datos_mensuales/*Rectif*.csv") + glob.glob("Datos_mensuales/*rectif*.csv")
list_rect = []

for f in archivos_rect:
    try:
        df_tmp = pd.read_csv(f, sep=";", encoding="latin1", dtype=str)
        list_rect.append(df_tmp)
    except Exception as e:
        print(f"Error cargando {f}: {e}")

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
        elif "Familia" in df_maestro.columns:
            cols_a_traer.append("Familia")

        if "Descripción Subfamilia" in df_maestro.columns:
            cols_a_traer.append("Descripción Subfamilia")
        elif "Subfamilia" in df_maestro.columns:
            cols_a_traer.append("Subfamilia")

        if "Es_Master" in df_maestro.columns:
            cols_a_traer.append("Es_Master")

        df_maestro_clean = df_maestro[cols_a_traer].drop_duplicates(subset=[col_art_mae])
        df_rect_all = df_rect_all.merge(df_maestro_clean, left_on=col_art_rect, right_on=col_art_mae, how="left")

        if "Descripción Familia" in df_rect_all.columns:
            df_rect_all["Familia"] = df_rect_all["Descripción Familia"]
        if "Descripción Subfamilia" in df_rect_all.columns:
            df_rect_all["Subfamilia"] = df_rect_all["Descripción Subfamilia"]

    df_rect_all["Familia"] = df_rect_all.get("Familia", pd.Series()).fillna("Sin Familia")
    df_rect_all["Subfamilia"] = df_rect_all.get("Subfamilia", pd.Series()).fillna("Sin Subfamilia")
    df_rect_all["Es_Master"] = df_rect_all.get("Es_Master", pd.Series()).fillna("No")

    # Mapeo de Monto
    col_monto = None
    for c in ["Monto_Rectif", "Imp.tien.PVP S/IVA mon.BD", "Monto", "Importe"]:
        if c in df_rect_all.columns:
            col_monto = c
            break

    if col_monto:
        df_rect_all["Monto_Rectif"] = pd.to_numeric(df_rect_all[col_monto].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    else:
        df_rect_all["Monto_Rectif"] = 0.0

    df_rect_all.to_parquet("Tablero_Rectificaciones_Detalle.parquet", index=False)
    print(f"📦 Tablero_Rectificaciones_Detalle.parquet guardado con {len(df_rect_all):,} filas.")

    # 3. Actualizar Parquet de SLA Pedidos con Casuística Faltante Neto Master (UXB)
    if os.path.exists("Tablero_SLA_Pedidos.parquet"):
        df_sla = pd.read_parquet("Tablero_SLA_Pedidos.parquet")
        
        # Identificar pedidos con al menos un faltante ('F') en artículo Bulto Master ('Sí')
        col_motivo = "Motivo_Clean" if "Motivo_Clean" in df_rect_all.columns else "Motivo"
        pedidos_falt_master = set(
            df_rect_all[
                (df_rect_all[col_motivo].astype(str).str.strip().str.upper() == "F") & 
                (df_rect_all["Es_Master"] == "Sí")
            ]["Pedido"].dropna().unique()
        )

        def reevaluar_casuistica(row):
            cas = str(row["Casuistica"])
            ped = str(row["Pedido"])
            if cas in ["Faltante Neto", "Faltante Neto Fraccionado", "Faltante Neto Master (UXB)"]:
                if ped in pedidos_falt_master:
                    return "Faltante Neto Master (UXB)"
                else:
                    return "Faltante Neto Fraccionado"
            return cas

        df_sla["Casuistica"] = df_sla.apply(reevaluar_casuistica, axis=1)
        df_sla.to_parquet("Tablero_SLA_Pedidos.parquet", index=False)
        print("✅ Tablero_SLA_Pedidos.parquet actualizado con las nuevas casuísticas UXB.")

print("🚀 Procesamiento finalizado.")
"@ | Out-File -FilePath procesar_articulos.py -Encoding utf8

.\python_env\python.exe procesar_articulos.py