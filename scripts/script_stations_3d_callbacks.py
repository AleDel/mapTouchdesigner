"""
script_stations_3d_callbacks.py
Cook script para el scriptSOP 'script_stations' dentro de geo_stations.

Genera una nube de puntos 3D sobre el plano del mapa (z = 0.001 + quality * Zheight3d),
con colores por parámetro de calidad del agua (BOD, COD, DO, pH, etc.).

Arquitectura de datos:
  table_coords   → lat/lon por estación (unique per station)
  table_filtered → filas de datos con columnas Lat, Lon, y parámetros de calidad
  tiles/table_dots → sx, sy (UV pantalla) ya computados por MapaExt

El plano del mapa (geo1/rectangle1) tiene:
  sizex = 1.0    → X en [-0.5, 0.5]
  sizey = 0.5625 → Y en [-0.28125, 0.28125]

Referenciado desde: /project1/Mapa2/render/geo_stations/script_stations
"""

import sys
import math

# Columnas de tabla_filtered indexadas por nombre de parámetro
PARAM_COL = {
    'BOD': 15,   # 생물화학적산소요구량(BOD)
    'COD': 22,   # 화학적산소요구량(COD)
    'DO':  31,   # 용존산소(DO)
    'pH':  50,   # 수소이온농도(pH)
    'TN':  58,   # 총질소(T-N)
    'TP':  60,   # 총인(T-P)
    'TOC': 59,   # 총유기탄소(TOC)
    'SS':  54,   # 부유물질(SS)
}

# Para pH el rango normal es ~6.5–8.5: valores extremos → peor calidad
# Para DO: mayor valor = mejor calidad (invertir la escala de color)
INVERT_SCALE = {'DO', 'pH'}  # para estas, mayor valor = menor preocupación


def _quality_color(q_norm):
    """
    Mapea q_norm [0,1] a color RGB:
      0.0 → azul brillante (excelente)
      0.5 → amarillo (moderado)
      1.0 → rojo fuerte (crítico)
    """
    if q_norm < 0.5:
        t = q_norm * 2.0
        r = t
        g = 0.5 + t * 0.5
        b = 1.0 - t
    else:
        t = (q_norm - 0.5) * 2.0
        r = 1.0
        g = 1.0 - t
        b = 0.0
    return (r, g, b, 1.0)


def cook(scriptOp):
    """
    Genera puntos 3D para cada estación de calidad de agua visible.
    """
    _scripts_dir = project.folder + '/scripts'
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    import tile_utils

    mapa2 = op('/project1/Mapa2')
    if mapa2 is None:
        return

    # --- Parámetros de vista ---
    center_lat = float(mapa2.par.Centerlat.val)
    center_lon = float(mapa2.par.Centerlon.val)
    zoom_float = float(mapa2.par.Zoomfloat.val)
    screen_w   = float(mapa2.par.Screenw.val)  if hasattr(mapa2.par, 'Screenw')  else 1280.0
    screen_h   = float(mapa2.par.Screenh.val)  if hasattr(mapa2.par, 'Screenh')  else 720.0

    # --- Parámetros Render3D ---
    z_height = float(mapa2.par.Zheight3d.val) if hasattr(mapa2.par, 'Zheight3d') else 0.08
    p_scale  = float(mapa2.par.Pscale3d.val)  if hasattr(mapa2.par, 'Pscale3d')  else 0.012
    param_key = str(mapa2.par.Param3d.val)    if hasattr(mapa2.par, 'Param3d')   else 'BOD'
    param_col = PARAM_COL.get(param_key, 15)

    # Mostrar u ocultar: si Show3d es False, limpiar y salir
    show3d = bool(mapa2.par.Show3d.val) if hasattr(mapa2.par, 'Show3d') else True
    scriptOp.clear()
    if not show3d:
        return

    # --- Cálculo de viewport ---
    int_zoom    = int(zoom_float)
    fixed_pow   = math.pow(2.0, int_zoom)
    scale_val   = math.pow(2.0, zoom_float - int_zoom)
    tile_px     = tile_utils.TILE_SIZE * scale_val

    norm_c = tile_utils.lngLatToTileIndex(center_lat, center_lon)
    cx = norm_c[0] * fixed_pow
    cy = norm_c[1] * fixed_pow

    # --- Dimensiones del plano del mapa (rectangle1 en geo1) ---
    PLANE_W = 1.0
    PLANE_H = 0.5625

    # --- Tablas de datos ---
    tc = op('/project1/Mapa2/data/table_coords')     # area, estacion, lat, lon
    tf = op('/project1/Mapa2/data/table_filtered')   # …, Lat (col63), Lon (col64)

    if tc is None or tc.numRows < 2:
        return

    # --- Estación seleccionada ---
    sel_area  = None
    sel_estac = None
    try:
        ext = mapa2.ext.MapaExt
        if ext.selectedStation:
            sel_area  = ext.selectedStation['area']
            sel_estac = ext.selectedStation['estacion']
    except Exception:
        pass

    # --- Lookup de calidad: max(param) por estación ---
    quality_raw = {}     # (area, estac) → float max
    if tf is not None and tf.numRows > 1:
        for r in range(1, tf.numRows):
            area  = tf[r, 6].val.strip()
            estac = tf[r, 7].val.strip()
            if param_col < tf.numCols:
                val_s = tf[r, param_col].val.strip()
                try:
                    val = float(val_s)
                    key = (area, estac)
                    if key not in quality_raw or val > quality_raw[key]:
                        quality_raw[key] = val
                except (ValueError, TypeError):
                    pass

    # Normalizar [0, 1] con min/max
    if quality_raw:
        vals  = list(quality_raw.values())
        q_min = min(vals)
        q_max = max(vals)
        q_range = max(q_max - q_min, 1e-9)
        quality_norm = {
            k: max(0.0, min(1.0, (v - q_min) / q_range))
            for k, v in quality_raw.items()
        }
        # Para DO/pH: invertir (mayor valor = mejor calidad → color azul)
        if param_key in INVERT_SCALE:
            quality_norm = {k: 1.0 - v for k, v in quality_norm.items()}
    else:
        quality_norm = {}

    # --- Crear atributos una sola vez antes del loop ---
    scriptOp.pointAttribs.create('Cd')
    scriptOp.pointAttribs.create('N')
    scriptOp.pointAttribs.create('pscale', p_scale)

    # --- Generar puntos 3D ---
    seen = set()
    for r in range(1, tc.numRows):
        area  = tc[r, 0].val.strip()
        estac = tc[r, 1].val.strip()
        lat_s = tc[r, 2].val.strip()
        lon_s = tc[r, 3].val.strip()
        if not lat_s or not lon_s:
            continue
        key = (area, estac)
        if key in seen:
            continue
        seen.add(key)

        try:
            lat = float(lat_s)
            lon = float(lon_s)
        except (ValueError, TypeError):
            continue

        # Convertir lat/lon a coordenadas de pantalla UV [0,1]
        norm  = tile_utils.lngLatToTileIndex(lat, lon)
        tx    = norm[0] * fixed_pow
        ty    = norm[1] * fixed_pow
        dpx   =  (tx - cx) * tile_px
        dpy   = -(ty - cy) * tile_px   # invertir Y (TD: 0=abajo, 1=arriba)
        sx    = 0.5 + dpx / screen_w
        sy    = 0.5 + dpy / screen_h

        # Descartar puntos fuera del margen visible
        if sx < -0.15 or sx > 1.15 or sy < -0.15 or sy > 1.15:
            continue

        # Convertir UV de pantalla → coordenadas 3D del plano
        px = (sx - 0.5) * PLANE_W
        py = (sy - 0.5) * PLANE_H

        # Z: altura proporcional a calidad (peor = más alto para visibilidad)
        q_norm = quality_norm.get(key, 0.0)
        pz     = 0.001 + q_norm * z_height

        # Color según calidad
        is_sel = (area == sel_area and estac == sel_estac)
        if is_sel:
            color = (1.0, 1.0, 1.0, 1.0)   # blanco para seleccionada
            size  = p_scale * 1.8
        else:
            color = _quality_color(q_norm)
            size  = p_scale

        pt = scriptOp.appendPoint()
        pt.P      = (px, py, pz)
        pt.Cd     = color
        pt.N      = (0.0, 0.0, 1.0)    # normal apuntando hacia la cámara
        pt.pscale = size
