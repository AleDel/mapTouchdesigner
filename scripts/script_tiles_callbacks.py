# script_tiles_callbacks.py
# Cook del scriptTOP de tiles:
# 1. Composita tiles de mapa desde disco con cv2.
# 2. Dibuja dots de estaciones sobre el mapa (overlay con numpy/cv2).
# ox/oy/tamx en table_tilelist son coordenadas normalizadas:
#   cx_px = ox * W + W/2,   cy_px = H/2 - oy * W

def cook(scriptOp):
    import numpy as np
    import cv2

    tlist  = op('/project1/Mapa2/tiles/table_tilelist')
    coords = op('/project1/Mapa2/data/table_coords')
    W, H = 1280, 720
    canvas = np.zeros((H, W, 4), dtype=np.float32)

    # --- 1. Compositar tiles ---
    if tlist is not None and tlist.numRows >= 2:
        for i in range(1, tlist.numRows):
            try:
                ax        = float(str(tlist[i, 'ox']))
                ay        = float(str(tlist[i, 'oy']))
                atx       = float(str(tlist[i, 'tamx']))
                file_path = str(tlist[i, 'filePath'])
                img_bgr = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
                if img_bgr is None:
                    continue
                if img_bgr.ndim == 2:
                    img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGRA)
                elif img_bgr.shape[2] == 3:
                    img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
                img_rgba = img_bgr[:, :, [2, 1, 0, 3]].astype(np.float32) / 255.0
                # cv2.imread: row 0 = top del PNG
                # TD copyNumpyArray: row 0 = bottom de la imagen
                # → hay que invertir Y para que el contenido aparezca correcto
                img_rgba = img_rgba[::-1, :, :]
                w_px = int(round(atx * W))
                h_px = w_px
                if w_px < 1:
                    continue
                if w_px != img_rgba.shape[1]:
                    img_rgba = cv2.resize(img_rgba, (w_px, h_px), interpolation=cv2.INTER_LINEAR)
                cx_px = ax * W + W / 2.0
                cy_px = H / 2.0 - ay * W
                sx0 = int(cx_px - w_px / 2.0)
                sy0 = int(cy_px - h_px / 2.0)
                td_y1 = H - sy0
                td_y0 = td_y1 - h_px
                cx0 = max(0, sx0);   cx1 = min(W, sx0 + w_px)
                cy0 = max(0, td_y0); cy1 = min(H, td_y1)
                if cx1 <= cx0 or cy1 <= cy0:
                    continue
                px0 = cx0 - sx0;   px1 = px0 + (cx1 - cx0)
                py0 = cy0 - td_y0; py1 = py0 + (cy1 - cy0)
                py1 = min(py1, img_rgba.shape[0])
                px1 = min(px1, img_rgba.shape[1])
                cy1 = cy0 + (py1 - py0)
                cx1 = cx0 + (px1 - px0)
                if cy1 <= cy0 or cx1 <= cx0:
                    continue
                canvas[cy0:cy1, cx0:cx1] = img_rgba[py0:py1, px0:px1]
            except Exception as e:
                print('[script_tiles] tile', i, e)

    # --- 2. Overlay de estaciones ---
    if coords is not None and coords.numRows >= 2:
        try:
            ext     = op('/project1/Mapa2').ext.MapaExt
            sel     = ext.selectedStation
            sel_key = (sel['area'], sel['estacion']) if sel else None
        except Exception:
            ext     = None
            sel_key = None

        # Trabajar en uint8 para cv2.circle
        ov = (canvas * 255).astype('uint8')

        for i in range(1, coords.numRows):
            try:
                lat   = float(str(coords[i, 'lat']))
                lon   = float(str(coords[i, 'lon']))
                area  = str(coords[i, 'area'])
                estac = str(coords[i, 'estacion'])
            except Exception:
                continue
            if ext is None:
                continue
            try:
                px, py_screen = ext.latLonToScreenXY(lat, lon)
                # py_screen: 0=arriba, crece hacia abajo (coords pantalla)
                # numpy row 0 = bottom en TD → invertir Y
                cx_dot = int(round(px))
                cy_dot = H - int(round(py_screen))
                if cx_dot < 0 or cx_dot >= W or cy_dot < 0 or cy_dot >= H:
                    continue
                if sel_key and (area, estac) == sel_key:
                    color_bgr = (30, 220, 255)  # amarillo (BGR)
                    radius    = 9
                else:
                    color_bgr = (50, 50, 220)   # rojo (BGR)
                    radius    = 5
                cv2.circle(ov, (cx_dot, cy_dot), radius, color_bgr + (255,), -1)
                cv2.circle(ov, (cx_dot, cy_dot), radius, (255, 255, 255, 255), 1)
            except Exception as e:
                print('[script_tiles] dot', i, e)

        canvas = ov.astype('float32') / 255.0

    scriptOp.copyNumpyArray(canvas)
