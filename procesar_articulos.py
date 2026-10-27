# -*- coding: utf-8 -*-
"""
Script ETL: Procesar Artículos, Rectificaciones, Pedidos SLA y Anulaciones
========================================================================
Genera e inspecciona los archivos Parquet optimizados consumidos por app.py:
  1. Tablero_SLA_Pedidos.parquet
  2. Tablero_Rectificaciones_Detalle.parquet
  3. Tablero_Anulaciones_Detalle.parquet

Incluye análisis exhaustivo de integridad y distribución mensual de cada Parquet.
"""

import os
import glob
import pandas as pd
import numpy as np

def corregir_encoding_texto(texto):
    if pd.isna(texto):
        return texto
    s = str(texto)
    try:
        return s.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s

def normalizar_fechas_serie(serie_fechas):
    """
    Convierte series de fecha multiformato a datetime estandarizado:
    - Formato estándar latinoamericano con año de 4 dígitos (%d/%m/%Y, ej: 1/6/2026)
    - Formato latinoamericano con año de 2 dígitos (%d/%m/%y, ej: 19/10/26 -> ¡Octubre!)
    - Formato serial de Excel (ej: 46175, 46312)
    - Formato compacto (YYYYMMDD) o ISO (YYYY-MM-DD)
    """
    if serie_fechas is None or serie_fechas.empty:
        return pd.Series(pd.NaT, index=serie_fechas.index if serie_fechas is not None else [], dtype='datetime64[ns]')
    
    s_raw = serie_fechas.astype(str).str.strip().str.replace(".0", "", regex=False)
    
    # 1. Probar explícitamente %d/%m/%Y (4 dígitos: junio a septiembre)
    dt1 = pd.to_datetime(s_raw, format="%d/%m/%Y", errors="coerce")
    
    # 2. Probar explícitamente %d/%m/%y (2 dígitos: octubre)
    dt2 = pd.to_datetime(s_raw, format="%d/%m/%y", errors="coerce")
    
    # 3. Formato compacto YYYYMMDD o ISO
    dt3 = pd.to_datetime(s_raw, format="%Y%m%d", errors="coerce")
    dt4 = pd.to_datetime(s_raw, format="%Y-%m-%d", errors="coerce")
    
    # 4. Formato serial numérico de Excel
    s_num = pd.to_numeric(s_raw.str.replace(",", "."), errors="coerce")
    mask_excel = s_num.notna() & (s_num > 30000) & (s_num < 70000)
    dt_ex = pd.Series(pd.NaT, index=serie_fechas.index, dtype='datetime64[ns]')
    if mask_excel.any():
        dt_ex[mask_excel] = pd.to_datetime(s_num[mask_excel], unit="D", origin="1899-12-30", errors="coerce")
        
    dt_final = dt1.fillna(dt2).fillna(dt3).fillna(dt4).fillna(dt_ex)
    
    # Respaldo por división de texto si aún quedara NaT
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

def procesar_maestro_articulos(carpeta="."):
    """Carga y procesa el catálogo maestro de artículos/SKUs."""
    archivos = glob.glob(os.path.join(carpeta, "*[Mm]aestro*.csv")) +                glob.glob(os.path.join(carpeta, "*[Aa]rticulo*.csv")) +                glob.glob(os.path.join(carpeta, "Datos_mensuales", "*[Mm]aestro*.csv"))
    
    if not archivos:
        print("⚠️ No se encontró archivo maestro de artículos específico. Se usarán datos presentes en rectificaciones.")
        return pd.DataFrame()
    
    archivo = archivos[0]
    print(f"📦 Procesando Maestro de Artículos: {archivo}")
    df_m = pd.read_csv(archivo, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    df_m.columns = df_m.columns.str.strip().str.upper()
    
    col_sku = next((c for c in df_m.columns if any(k in c for k in ["ARTICULO", "ARTÍCULO", "SKU", "COD_ART"])), None)
    col_desc = next((c for c in df_m.columns if any(k in c for k in ["DESCRIPCION", "DESCRIPCIÓN", "PRODUCTO", "DENOMINACION"])), None)
    col_fam = next((c for c in df_m.columns if any(k in c for k in ["FAMILIA", "SECTOR", "RUBRO"])), None)
    col_subfam = next((c for c in df_m.columns if any(k in c for k in ["SUBFAMILIA", "SUB_RUBRO", "CATEGORIA"])), None)
    col_uxb = next((c for c in df_m.columns if "UXB" in c or "UNID_BULTO" in c), None)
    col_bxm = next((c for c in df_m.columns if "BULFM" in c or "BXM" in c or "BULTO_MASTER" in c), None)

    res = pd.DataFrame()
    if col_sku:
        res["Artículo"] = df_m[col_sku].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
        if col_desc: res["Descripción"] = df_m[col_desc].apply(corregir_encoding_texto)
        if col_fam: res["Familia"] = df_m[col_fam].astype(str).str.strip()
        if col_subfam: res["Subfamilia"] = df_m[col_subfam].astype(str).str.strip()
        if col_uxb: res["UxB"] = pd.to_numeric(df_m[col_uxb].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
        if col_bxm: res["BULFM"] = pd.to_numeric(df_m[col_bxm].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
    
    return res.drop_duplicates(subset=["Artículo"])

def procesar_rectificaciones(carpeta=".", df_maestro=None):
    """Procesa el detalle de rectificaciones registradas."""
    archivos = glob.glob(os.path.join(carpeta, "*[Rr]ectif*.csv")) +                glob.glob(os.path.join(carpeta, "*[Dd]etalle*.csv")) +                glob.glob(os.path.join(carpeta, "Datos_mensuales", "*[Rr]ectif*.csv"))
    
    if not archivos:
        print("⚠️ No se encontraron archivos CSV de rectificaciones.")
        return pd.DataFrame()
    
    archivo = archivos[0]
    print(f"📋 Procesando Rectificaciones: {archivo}")
    df_r = pd.read_csv(archivo, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    df_r.columns = df_r.columns.str.strip()

    mapa = {}
    for c in df_r.columns:
        clow = c.lower()
        if "almac" in clow: mapa[c] = "Almacen"
        elif "tienda" in clow or "sucursal" in clow or "cod_suc_des" in clow: mapa[c] = "Tienda"
        elif "pedido" in clow: mapa[c] = "Pedido"
        elif "art" in clow or "sku" in clow: mapa[c] = "Artículo"
        elif "desc" in clow or "prod" in clow: mapa[c] = "Descripción"
        elif "motivo" in clow: mapa[c] = "Motivo"
        elif "proc" in clow: mapa[c] = "Procedencia"
        elif "estado" in clow: mapa[c] = "Estado"
        elif "rectif" in clow and "n" in clow: mapa[c] = "Nº Rectificación"
        elif "grab" in clow and "fech" in clow: mapa[c] = "Fecha de Grabación"
        elif "grab" in clow and ("unid" in clow or "cant" in clow): mapa[c] = "Unid/Kgs grabados"
        elif "abon" in clow and ("unid" in clow or "cant" in clow): mapa[c] = "Unid/Kgs abonados"
        elif any(k in clow for k in ["imp", "monto", "pvp"]): mapa[c] = "Monto_Rectif"

    df_r = df_r.rename(columns=mapa)

    if "Pedido" in df_r.columns:
        df_r["Pedido"] = df_r["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Tienda" in df_r.columns:
        df_r["Tienda"] = df_r["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Artículo" in df_r.columns:
        df_r["Artículo"] = df_r["Artículo"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Monto_Rectif" in df_r.columns:
        df_r["Monto_Rectif"] = pd.to_numeric(df_r["Monto_Rectif"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    # Normalizar Fecha de Grabación
    if "Fecha de Grabación" in df_r.columns:
        dt_g = normalizar_fechas_serie(df_r["Fecha de Grabación"])
        df_r["Fecha de Grabación"] = dt_g.dt.strftime("%d/%m/%Y").fillna(df_r["Fecha de Grabación"])
        df_r["Mes"] = dt_g.dt.month.fillna(0).astype(int)

    # Incorporar maestro si existe
    if df_maestro is not None and not df_maestro.empty and "Artículo" in df_r.columns:
        df_r = df_r.merge(df_maestro, on="Artículo", how="left", suffixes=("", "_m"))
        for col in ["Descripción", "Familia", "Subfamilia", "UxB", "BULFM"]:
            if f"{col}_m" in df_r.columns:
                df_r[col] = df_r[col].fillna(df_r[f"{col}_m"])
                df_r.drop(columns=[f"{col}_m"], inplace=True)

    # Cálculo de unidades y flags master
    if "Unid/Kgs grabados" in df_r.columns:
        df_r["Unidades_Num"] = pd.to_numeric(df_r["Unid/Kgs grabados"].astype(str).str.replace(",", "."), errors="coerce").fillna(1.0)
    else:
        df_r["Unidades_Num"] = 1.0

    df_r["UxB"] = pd.to_numeric(df_r.get("UxB", 1.0), errors="coerce").fillna(1.0)
    df_r["BULFM"] = pd.to_numeric(df_r.get("BULFM", 1.0), errors="coerce").fillna(1.0)
    df_r["UxM"] = df_r["UxB"] * df_r["BULFM"]
    df_r["Es_Master"] = np.where(df_r["BULFM"] > 1.0, "Sí", "No")

    df_r.to_parquet("Tablero_Rectificaciones_Detalle.parquet", index=False)
    print(f"✅ Guardado Tablero_Rectificaciones_Detalle.parquet ({len(df_r):,} registros)")
    return df_r

def procesar_pedidos_sla(carpeta=".", df_rect=None):
    """Genera la base consolidada de Pedidos y Puntuación SLA."""
    archivos = glob.glob(os.path.join(carpeta, "*[Ss][Ll][Aa]*.csv")) +                glob.glob(os.path.join(carpeta, "*[Pp]edidos*.csv")) +                glob.glob(os.path.join(carpeta, "Datos_mensuales", "*[Pp]edidos*.csv"))
    
    if not archivos:
        print("⚠️ No se encontraron archivos de pedidos SLA.")
        return pd.DataFrame()
    
    archivo = archivos[0]
    print(f"📊 Procesando Pedidos SLA: {archivo}")
    df_p = pd.read_csv(archivo, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    df_p.columns = df_p.columns.str.strip()

    mapa = {}
    for c in df_p.columns:
        clow = c.lower()
        if "pedido" in clow: mapa[c] = "Pedido"
        elif "tienda" in clow or "sucursal" in clow: mapa[c] = "Tienda"
        elif "almac" in clow: mapa[c] = "Almacen"
        elif "fech" in clow: mapa[c] = "Fecha_DT"
        elif "gest" in clow or "zona" in clow: mapa[c] = "Gestion"
        elif "resp" in clow or "superv" in clow or "franqui" in clow: mapa[c] = "Responsable_Tienda"
        elif "casuistica" in clow or "casuística" in clow: mapa[c] = "Casuistica"
        elif "puntos" in clow: mapa[c] = "Puntos_Obtenidos"

    df_p = df_p.rename(columns=mapa)
    if "Pedido" in df_p.columns:
        df_p["Pedido"] = df_p["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Tienda" in df_p.columns:
        df_p["Tienda"] = df_p["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Puntos_Obtenidos" in df_p.columns:
        df_p["Puntos_Obtenidos"] = pd.to_numeric(df_p["Puntos_Obtenidos"].astype(str).str.replace(",", "."), errors="coerce").fillna(10.0)
    else:
        df_p["Puntos_Obtenidos"] = 10.0

    if "Casuistica" not in df_p.columns:
        df_p["Casuistica"] = "Pedido Perfecto"

    if "Fecha_DT" in df_p.columns:
        dt = normalizar_fechas_serie(df_p["Fecha_DT"])
        df_p["Mes"] = dt.dt.month.fillna(0).astype(int)
        df_p["Año"] = dt.dt.year.fillna(2026).astype(int)

    df_p.to_parquet("Tablero_SLA_Pedidos.parquet", index=False)
    print(f"✅ Guardado Tablero_SLA_Pedidos.parquet ({len(df_p):,} pedidos)")
    return df_p

def procesar_anulaciones(carpeta="."):
    """Genera la base de causas de anulación y aprobación del portal con fechas y mes precalculados."""
    archivos = glob.glob(os.path.join(carpeta, "*[Aa]nula*.csv")) +                glob.glob(os.path.join(carpeta, "*[Cc]ausa*.csv")) +                glob.glob(os.path.join(carpeta, "Datos_mensuales", "*[Cc]ausa*.csv"))
    
    if not archivos:
        print("⚠️ No se encontraron archivos de anulaciones/causas.")
        return pd.DataFrame()
    
    archivo = archivos[0]
    print(f"❌ Procesando Anulaciones/Causas Portal: {archivo}")
    df_a = pd.read_csv(archivo, sep=None, engine="python", encoding="latin1", dtype=str, on_bad_lines="skip")
    df_a.columns = df_a.columns.str.strip()

    mapa = {}
    for c in df_a.columns:
        clow = c.lower()
        if "almac" in clow: mapa[c] = "Almacen"
        elif "tienda" in clow or "sucursal" in clow: mapa[c] = "Tienda"
        elif "pedido" in clow: mapa[c] = "Pedido"
        elif "nota" in clow or "nro" in clow: mapa[c] = "Nota_Nro"
        elif "fech" in clow and "modif" not in clow: mapa[c] = "Fecha"
        elif "fch. modif" in clow or "fecha modif" in clow: mapa[c] = "Fecha_Modif"
        elif "tipo" in clow: mapa[c] = "Tipo"
        elif "cnt" in clow or "blt" in clow: mapa[c] = "Cant_Blt"
        elif "imp" in clow or "monto" in clow: mapa[c] = "Monto"
        elif "motivo" in clow or "causa" in clow: mapa[c] = "Causa_Anulacion"
        elif "estado" in clow: mapa[c] = "Estado"

    df_a = df_a.rename(columns=mapa)
    if "Pedido" in df_a.columns:
        df_a["Pedido"] = df_a["Pedido"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Tienda" in df_a.columns:
        df_a["Tienda"] = df_a["Tienda"].astype(str).str.strip().str.replace(".0", "", regex=False).str.lstrip("0")
    if "Monto" in df_a.columns:
        df_a["Monto"] = pd.to_numeric(df_a["Monto"].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)

    # ⚡ NORMALIZACIÓN ROBUSTA DE FECHA (Acepta '19/10/26' de 2 dígitos, '1/6/2026' de 4 dígitos, Excel y YYYYMMDD)
    col_fec_origen = "Fecha" if "Fecha" in df_a.columns else ("Fecha_Modif" if "Fecha_Modif" in df_a.columns else None)
    if col_fec_origen:
        dt_parsed = normalizar_fechas_serie(df_a[col_fec_origen])
        df_a["Mes_Num"] = dt_parsed.dt.month.fillna(0).astype(int)
        df_a["Año"] = dt_parsed.dt.year.fillna(2026).astype(int)
        mapa_meses = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                      7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
        df_a["Nombre_Mes"] = df_a["Mes_Num"].map(mapa_meses).fillna("Sin Mes")
        df_a["Fecha"] = dt_parsed.dt.strftime("%d/%m/%Y").fillna(df_a[col_fec_origen])

    df_a.to_parquet("Tablero_Anulaciones_Detalle.parquet", index=False)
    print(f"✅ Guardado Tablero_Anulaciones_Detalle.parquet ({len(df_a):,} registros con mes normalizado)")
    return df_a

def auditar_todos_los_parquets():
    """Realiza un diagnóstico completo de todos los archivos Parquet en el directorio."""
    print("\n" + "=" * 70)
    print("📊 ANÁLISIS DE INTEGRIDAD DE TODOS LOS PARQUETS")
    print("=" * 70)
    
    parquets = [
        ("1. Pedidos SLA", "Tablero_SLA_Pedidos.parquet"),
        ("2. Rectificaciones Detalle", "Tablero_Rectificaciones_Detalle.parquet"),
        ("3. Anulaciones Detalle", "Tablero_Anulaciones_Detalle.parquet")
    ]
    
    mapa_meses = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                  7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
                  0: "⚠️ Sin Mes"}

    for nombre, arch in parquets:
        print(f"\n🔍 [{nombre}] Archivo: {arch}")
        if not os.path.exists(arch):
            print(f"   ❌ No existe en disco.")
            continue
        
        df_p = pd.read_parquet(arch)
        peso_mb = os.path.getsize(arch) / (1024 * 1024)
        print(f"   • Filas: {len(df_p):,} | Columnas: {len(df_p.columns)} | Peso: {peso_mb:.2f} MB")
        print(f"   • Columnas: {list(df_p.columns)}")
        
        col_m = "Mes" if "Mes" in df_p.columns else ("Mes_Num" if "Mes_Num" in df_p.columns else None)
        if col_m:
            meses_conteo = df_p[col_m].value_counts().rename(index=mapa_meses)
            print("   • Distribución de registros por Mes:")
            for m_nom, cant in meses_conteo.items():
                print(f"       - {m_nom}: {cant:,} registros")
        else:
            print("   • No contiene columna de mes numérico directo.")

    print("\n" + "=" * 70)
    print("✨ DIAGNÓSTICO DE PARQUETS FINALIZADO")
    print("=" * 70)

if __name__ == "__main__":
    print("🚀 Iniciando pipeline ETL de procesamiento de datos...")
    df_maestro = procesar_maestro_articulos()
    df_rect = procesar_rectificaciones(df_maestro=df_maestro)
    df_sla = procesar_pedidos_sla(df_rect=df_rect)
    df_anul = procesar_anulaciones()
    print("✨ Pipeline ETL completado exitosamente.")
    
    auditar_todos_los_parquets()
