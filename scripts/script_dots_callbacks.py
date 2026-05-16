# script_dots_callbacks.py
# Renderiza los dots de estaciones usando tiles/ramp1 como textura.
# Cada dot es un stamp del ramp1 redimensionado al tamanio del dot.
# El dot seleccionado se renderiza mas grande y con borde blanco.

def cook(scriptOp):
    import numpy as np
    import cv2

    W, H = 1280, 720

    # --- Base: leer tiles desde input ---
    if scriptOp.inputs:
        raw = scriptOp.inputs[0].numpyArray()
        canvas = raw.copy() if (raw is not None and raw.shape == (H, W, 4)) else np.zeros((H, W, 4), dtype=np.float32)
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

    # --- Animación: obtener alpha del panel de info y programar siguiente cook ---
    mapa2 = op('/project1/Mapa2')
    try:
        info_alpha = ext.getInfoAlpha()
        # Publicar alpha para que otros nodos lo puedan cablear
        if hasattr(mapa2.par, 'Infoalpha'):
            mapa2.par.Infoalpha = info_alpha
        # Seguir cocinando cada frame mientras la animación esté activa
        if ext._selectionTime is not None:
            run("op('/project1/Mapa2/tiles/script_dots').cook(force=True)", delayFrames=1)
    except Exception:
        info_alpha = 1.0 if sel else 0.0

    # --- Cargar textura del ramp1 (float32 RGBA, row0=bottom en TD) ---
    ramp_top = op('/project1/Mapa2/tiles/ramp1')
    ramp_tex = None
    if ramp_top is not None:
        ramp_tex = ramp_top.numpyArray()   # shape (H_r, W_r, 4), float32, row0=bottom

    # --- Funcion para hacer stamp de la textura en el canvas ---
    def stamp_dot(canvas_u8, cx, cy, radius, selected=False):
        d = radius * 2
        if ramp_tex is not None:
            # Redimensionar ramp al diametro del dot
            # ramp row0=bottom (coords TD) -> flipear para que row0=top (cv2)
            tex = ramp_tex[::-1, :, :].copy()
            tex_u8 = (tex * 255).astype(np.uint8)
            tex_rsz = cv2.resize(tex_u8, (d, d), interpolation=cv2.INTER_LINEAR)
            # Crear mascara circular para recortar el ramp
            mask = np.zeros((d, d), dtype=np.uint8)
            cv2.circle(mask, (radius, radius), radius, 255, -1)
            tex_rsz[:, :, 3] = np.minimum(tex_rsz[:, :, 3], mask)
        else:
            # Fallback: circulo solido azul
            tex_rsz = np.zeros((d, d, 4), dtype=np.uint8)
            cv2.circle(tex_rsz, (radius, radius), radius, (50, 50, 220, 255), -1)

        # Calcular region de destino en canvas (con clipping)
        x0 = cx - radius;  y0 = cy - radius
        x1 = x0 + d;       y1 = y0 + d
        tx0 = max(0, -x0); ty0 = max(0, -y0)
        cx0 = max(0, x0);  cy0 = max(0, y0)
        cx1 = min(W, x1);  cy1 = min(H, y1)
        tx1 = tx0 + (cx1 - cx0)
        ty1 = ty0 + (cy1 - cy0)
        if cx1 <= cx0 or cy1 <= cy0:
            return

        # Compositar Over (alpha blending)
        src  = tex_rsz[ty0:ty1, tx0:tx1].astype(np.float32) / 255.0
        dst  = canvas_u8[cy0:cy1, cx0:cx1].astype(np.float32) / 255.0
        a    = src[:, :, 3:4]
        blended = src[:, :, :3] * a + dst[:, :, :3] * (1.0 - a)
        out_a = a + dst[:, :, 3:4] * (1.0 - a)
        result = np.concatenate([blended, out_a], axis=2)
        canvas_u8[cy0:cy1, cx0:cx1] = (result * 255).astype(np.uint8)

        # Borde blanco en seleccionada
        if selected:
            cv2.circle(canvas_u8, (cx, cy), radius, (255, 255, 255, 255), 2)

    # --- Dibujar dots ---
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
            cx_dot = int(round(px))
            cy_dot = H - int(round(py_screen))
            if cx_dot < 0 or cx_dot >= W or cy_dot < 0 or cy_dot >= H:
                continue
            is_sel = bool(sel_key and (area, estac) == sel_key)
            try:
                mapa2 = op('/project1/Mapa2')
                base_r = int(mapa2.par.Dotradius.val)
                sel_r  = int(mapa2.par.Dotradiussel.val)
            except Exception:
                base_r = 9
                sel_r  = 13
            radius = sel_r if is_sel else base_r
            stamp_dot(ov, cx_dot, cy_dot, radius, selected=is_sel)
        except Exception as e:
            print('[script_dots] dot', i, e)

    scriptOp.copyNumpyArray(ov.astype('float32') / 255.0)
