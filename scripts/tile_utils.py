"""
tile_utils.py
Funciones puras de conversión geográfica OSM para el sistema de mapa de tiles.
Sin referencias a op() — usable desde cualquier contexto Python.
Migrado y refactorizado desde el módulo computaGrid del Mapa original.
"""
import math
import os
import struct


TILE_SIZE = 512  # Tamaño de tile en píxeles (Mapbox @2x)


# ---------------------------------------------------------------------------
# Lectura de dimensiones de imagen (PNG y JPEG)
# ---------------------------------------------------------------------------

def readImageSize(filepath):
    """
    Devuelve (width, height) leyendo la cabecera de un PNG o JPEG.
    Retorna (0, 0) si el formato no es reconocido o hay error.
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(24)
            # PNG: signature \x89PNG\r\n\x1a\n  → width en bytes 16-19 (big-endian)
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                w = struct.unpack('>I', header[16:20])[0]
                h = struct.unpack('>I', header[20:24])[0]
                return w, h
            # JPEG: SOI = \xff\xd8, luego buscar marcador SOF
            elif header[:2] == b'\xff\xd8':
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xff:
                        break
                    m = marker[1]
                    # SOF0..SOF3, SOF5..SOF7, SOF9..SOF11, SOF13..SOF15
                    if m in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
                             0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                        f.read(3)  # length(2) + precision(1)
                        h = struct.unpack('>H', f.read(2))[0]
                        w = struct.unpack('>H', f.read(2))[0]
                        return w, h
                    else:
                        seg_len = struct.unpack('>H', f.read(2))[0]
                        f.seek(seg_len - 2, 1)
    except Exception:
        pass
    return 0, 0


# ---------------------------------------------------------------------------
# Conversiones lat/lon ↔ tile index normalizado [0, 1]
# ---------------------------------------------------------------------------

def lngLatToTileIndex(lat, lon):
    """Convierte lat/lon a tile index normalizado [0,1] × [0,1]."""
    x = (lon + 180.0) / 360.0
    sin_lat = math.sin(lat * math.pi / 180.0)
    y = 0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4.0 * math.pi)
    return (x, y)


def tileIndexToLngLat(x, y):
    """Convierte tile index normalizado [0,1] × [0,1] a (lat, lon)."""
    xx = x - 0.5
    yy = 0.5 - y
    lat = 90.0 - 360.0 * math.atan(math.exp(-yy * 2.0 * math.pi)) / math.pi
    lon = 360.0 * xx
    return (lat, lon)


def deg2tileXY(lat, lon, zoom):
    """Devuelve el índice de tile (tx, ty) entero para un zoom dado."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    tx = int((lon + 180.0) / 360.0 * n)
    ty = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (tx, ty)


# ---------------------------------------------------------------------------
# Conversiones pantalla ↔ lat/lon
# ---------------------------------------------------------------------------

def latLonToScreenXY(location, center, screen_wh, zoom, tile_size=None):
    """
    Convierte (lat, lon) a coordenadas de píxel en pantalla.
    location : (lat, lon)
    center   : (centerLat, centerLon) — centro actual del mapa
    screen_wh: (width, height) en píxeles
    zoom     : nivel de zoom (puede ser float)
    tile_size: tamaño real del tile en píxeles (default: TILE_SIZE)
    Devuelve (x_px, y_px).
    """
    _ts = tile_size if tile_size is not None else TILE_SIZE
    scale = math.pow(2.0, zoom)
    cx = screen_wh[0] / 2.0
    cy = screen_wh[1] / 2.0
    tile_center = lngLatToTileIndex(center[0], center[1])
    tile_loc = lngLatToTileIndex(location[0], location[1])
    dx = tile_loc[0] - tile_center[0]
    dy = tile_loc[1] - tile_center[1]
    s = _ts * scale
    return (cx + dx * s, cy + dy * s)


def screenXYToLatLon(pos_screen, center, screen_wh, zoom, tile_size=None):
    """
    Convierte una posición de píxel en pantalla a (lat, lon).
    pos_screen: (x_px, y_px)
    center    : (centerLat, centerLon)
    screen_wh : (width, height)
    zoom      : nivel de zoom (puede ser float)
    tile_size : tamaño real del tile en píxeles (default: TILE_SIZE)
    """
    _ts = tile_size if tile_size is not None else TILE_SIZE
    scale = math.pow(2.0, zoom)
    cx = screen_wh[0] / 2.0
    cy = screen_wh[1] / 2.0
    tile_center = lngLatToTileIndex(center[0], center[1])
    dx = cx - pos_screen[0]
    dy = cy - pos_screen[1]
    tx = tile_center[0] - (dx / _ts) / scale
    ty = tile_center[1] - (dy / _ts) / scale
    return tileIndexToLngLat(tx, ty)


def drag(dx_px, dy_px, center, zoom, tile_size=None):
    """
    Calcula el nuevo center (lat, lon) tras arrastrar el mapa dx_px, dy_px píxeles.
    dx_px, dy_px: desplazamiento en píxeles (positivo = mover mapa a la derecha/abajo)
    center      : (centerLat, centerLon) actual
    zoom        : nivel de zoom (puede ser float)
    tile_size   : tamaño real del tile en píxeles (default: TILE_SIZE)
    """
    _ts = tile_size if tile_size is not None else TILE_SIZE
    scale = math.pow(2.0, zoom)
    tile_center = lngLatToTileIndex(center[0], center[1])
    new_tx = tile_center[0] - (dx_px / _ts) / scale
    new_ty = tile_center[1] - (dy_px / _ts) / scale
    return tileIndexToLngLat(new_tx, new_ty)


# ---------------------------------------------------------------------------
# Cálculo de la grilla de tiles visibles
# ---------------------------------------------------------------------------

def computeVisibleTileGrid(center_lat, center_lon, zoom_float, screen_w, screen_h, tiles_dir, tile_size=None):
    """
    Calcula qué tiles son visibles en pantalla y cuáles existen en disco.

    Parámetros:
        center_lat, center_lon : centro del mapa en grados
        zoom_float             : zoom como float (ej. 6.6)
        screen_w, screen_h     : resolución de la pantalla en píxeles
        tiles_dir              : ruta raíz de la carpeta TilesDark (str)

    Devuelve lista de dicts:
        {id, tilex, tiley, zoom (int), ox, oy, tamx, tamy, filePath}
        ox/oy  : offset 3D del plano del tile en el espacio de TouchDesigner
        tamx/tamy : tamaño 3D del tile
    """
    _ts = tile_size if tile_size is not None else TILE_SIZE
    fixed_zoom = int(math.floor(zoom_float))
    scale = math.pow(2.0, zoom_float)
    fixed_pow_zoom = math.pow(2.0, fixed_zoom)
    scale_value = math.pow(2.0, zoom_float % 1.0)
    tile_size_scaled = _ts * scale_value

    norm = lngLatToTileIndex(center_lat, center_lon)
    center_tile_x = math.floor(norm[0] * fixed_pow_zoom)
    center_tile_y = math.floor(norm[1] * fixed_pow_zoom)

    num_tiles_x = math.ceil(screen_w / _ts / 2.0) + 1
    num_tiles_y = math.ceil(screen_h / _ts / 2.0) + 1
    num_grids = int(math.pow(2.0, fixed_zoom))

    # Tamaño 3D de cada tile (espacio normalizado TD: pantalla = 1 unidad de ancho)
    tile_3d_size = tile_size_scaled / screen_w

    # Centro del tile central en espacio 3D
    ttl_x = norm[0] * _ts * scale
    ttl_y = norm[1] * _ts * scale
    center_tile_pixel_x = (center_tile_x + 0.5) * tile_size_scaled
    center_tile_pixel_y = (center_tile_y + 0.5) * tile_size_scaled

    # Bounding box (clamped al rango válido)
    ix_min = max(0, int(center_tile_x - num_tiles_x))
    ix_max = min(num_grids - 1, int(center_tile_x + num_tiles_x))
    iy_min = max(0, int(center_tile_y - num_tiles_y))
    iy_max = min(num_grids - 1, int(center_tile_y + num_tiles_y))

    tiles = []
    # Row-major: iy (norte→sur) varía lento, ix (oeste→este) varía rápido.
    # Así el layer index del shader es: layer = (iy - iy_min)*grid_w + (ix - ix_min)
    # Las posiciones sin tile en disco se incluyen con filePath='' (layer negro).
    for iy in range(iy_min, iy_max + 1):
        for ix in range(ix_min, ix_max + 1):
            base_path = os.path.join(tiles_dir, str(fixed_zoom), str(ix), str(iy))
            file_path = ''
            for _ext in ('.png', '.jpg', '.jpeg'):
                _candidate = (base_path + _ext).replace('\\', '/')
                if os.path.exists(_candidate):
                    file_path = _candidate
                    break

            # Offset 3D: posición del tile respecto al centro de pantalla
            tile_px_x = (ix + 0.5) * tile_size_scaled
            tile_px_y = (iy + 0.5) * tile_size_scaled
            diff_x = tile_px_x - ttl_x
            diff_y = tile_px_y - ttl_y
            ox = diff_x / screen_w
            oy = -diff_y / screen_w  # invertir Y para TD (Y hacia arriba)

            tiles.append({
                'id': int(str(fixed_zoom) + str(ix).zfill(3) + str(iy).zfill(3)),
                'tilex': ix,
                'tiley': iy,
                'zoom': fixed_zoom,
                'ox': ox,
                'oy': oy,
                'tamx': tile_3d_size,
                'tamy': tile_3d_size,
                'filePath': file_path,
            })

    return tiles


def tileGridToDAT(tiles, dat_op):
    """
    Escribe en dat_op solo los tiles con filePath no vacío.
    tiles  : lista COMPLETA de computeVisibleTileGrid() (incluyendo gaps con filePath='').
    Columnas:
      id   - posición row-major 1-indexada (para uIds del GLSL)
      name - '{zoom}_{tilex}_{tiley}' (usado por el replicador para nombrar ops)
    dat_op : referencia al operador tableDAT
    """
    dat_op.clear()
    dat_op.appendRow(['id', 'name', 'ox', 'oy', 'tamx', 'tamy', 'tilex', 'tiley', 'zoom', 'filePath'])
    real_tiles = [t for t in tiles if t.get('filePath', '')]
    if not real_tiles:
        return
    # Usar el grid COMPLETO (con gaps) para calcular la posición row-major
    x_min = min(t['tilex'] for t in tiles)
    grid_w = max(t['tilex'] for t in tiles) - x_min + 1
    y_min = min(t['tiley'] for t in tiles)
    for t in real_tiles:
        ix = t['tilex'] - x_min
        iy = t['tiley'] - y_min
        row_major_id = iy * grid_w + ix + 1
        tname = '{}_{}_{}'.format(t['zoom'], t['tilex'], t['tiley'])
        dat_op.appendRow([
            row_major_id, tname, t['ox'], t['oy'], t['tamx'], t['tamy'],
            t['tilex'], t['tiley'], t['zoom'], t['filePath']
        ])
