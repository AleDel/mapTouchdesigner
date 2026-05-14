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

    scriptOp.copyNumpyArray(canvas)
