# script_dots_callbacks.py
# Cook del scriptTOP de puntos de estaciones.
# Lee el mapa de tiles desde scriptOp.inputs[0] como base.
# Dibuja los puntos de estaciones encima.
# Bypasear este operador oculta la capa de puntos (igual que Google Maps).

def cook(scriptOp):
    import numpy as np
    import cv2

    W, H = 1280, 720

    # Base: leer tiles desde el input, o negro si no hay input
    if scriptOp.inputs:
        raw = scriptOp.inputs[0].numpyArray()
        if raw is not None and raw.shape == (H, W, 4):
            canvas = raw.copy()
        else:
            canvas = np.zeros((H, W, 4), dtype=np.float32)
    else:
        canvas = np.zeros((H, W, 4), dtype=np.float32)

    coords = op('/project1/Mapa2/data/table_coords')
    if coords is None or coords.numRows < 2:
        scriptOp.copyNumpyArray(canvas)
        return

    try:
        ext     = op('/project1/Mapa2').ext.MapaExt
        sel     = ext.selectedStation
        sel_key = (sel['area'], sel['estacion']) if sel else None
    except Exception:
        ext     = None
        sel_key = None

    if ext is None:
        scriptOp.copyNumpyArray(canvas)
        return

    # Trabajar en uint8 para cv2.circle
    ov = (canvas * 255).astype(np.uint8)

    for i in range(1, coords.numRows):
        try:
            lat   = float(str(coords[i, 'lat']))
            lon   = float(str(coords[i, 'lon']))
            area  = str(coords[i, 'area'])
            estac = str(coords[i, 'estacion'])
        except Exception:
            continue
        try:
            px, py_screen = ext.latLonToScreenXY(lat, lon)
            # py_screen: 0=arriba en pantalla
            # numpy row0=bottom en TD => cy_dot = H - py_screen
            cx_dot = int(round(px))
            cy_dot = H - int(round(py_screen))
            if cx_dot < 0 or cx_dot >= W or cy_dot < 0 or cy_dot >= H:
                continue
            if sel_key and (area, estac) == sel_key:
                color_bgra = (30, 220, 255, 255)   # amarillo (BGRA)
                radius     = 9
            else:
                color_bgra = (50, 50, 220, 255)    # rojo (BGRA)
                radius     = 5
            cv2.circle(ov, (cx_dot, cy_dot), radius, color_bgra, -1)
            cv2.circle(ov, (cx_dot, cy_dot), radius, (255, 255, 255, 255), 1)
        except Exception as e:
            print('[script_dots] dot', i, e)

    scriptOp.copyNumpyArray(ov.astype('float32') / 255.0)
