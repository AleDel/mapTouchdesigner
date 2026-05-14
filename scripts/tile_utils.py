"""
tile_utils.py
Funciones puras de conversión geográfica OSM para el sistema de mapa de tiles.
Sin referencias a op() — usable desde cualquier contexto Python.
Migrado y refactorizado desde el módulo computaGrid del Mapa original.
"""
import math
import os


TILE_SIZE = 512  # Tamaño de tile en píxeles (Mapbox @2x)


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

def latLonToScreenXY(location, center, screen_wh, zoom):
    """
    Convierte (lat, lon) a coordenadas de píxel en pantalla.
    location : (lat, lon)
    center   : (centerLat, centerLon) — centro actual del mapa
    screen_wh: (width, height) en píxeles
    zoom     : nivel de zoom (puede ser float)
    Devuelve (x_px, y_px).
    """
    scale = math.pow(2.0, zoom)
    cx = screen_wh[0] / 2.0
    cy = screen_wh[1] / 2.0
    tile_center = lngLatToTileIndex(center[0], center[1])
    tile_loc = lngLatToTileIndex(location[0], location[1])
    dx = tile_loc[0] - tile_center[0]
    dy = tile_loc[1] - tile_center[1]
    s = TILE_SIZE * scale
    return (cx + dx * s, cy + dy * s)


def screenXYToLatLon(pos_screen, center, screen_wh, zoom):
    """
    Convierte una posición de píxel en pantalla a (lat, lon).
    pos_screen: (x_px, y_px)
    center    : (centerLat, centerLon)
    screen_wh : (width, height)
    zoom      : nivel de zoom (puede ser float)
    """
    scale = math.pow(2.0, zoom)
    cx = screen_wh[0] / 2.0
    cy = screen_wh[1] / 2.0
    tile_center = lngLatToTileIndex(center[0], center[1])
    dx = cx - pos_screen[0]
    dy = cy - pos_screen[1]
    tx = tile_center[0] - (dx / TILE_SIZE) / scale
    ty = tile_center[1] - (dy / TILE_SIZE) / scale
    return tileIndexToLngLat(tx, ty)


def drag(dx_px, dy_px, center, zoom):
    """
    Calcula el nuevo center (lat, lon) tras arrastrar el mapa dx_px, dy_px píxeles.
    dx_px, dy_px: desplazamiento en píxeles (positivo = mover mapa a la derecha/abajo)
    center      : (centerLat, centerLon) actual
    zoom        : nivel de zoom (puede ser float)
    """
    scale = math.pow(2.0, zoom)
    tile_center = lngLatToTileIndex(center[0], center[1])
    new_tx = tile_center[0] - (dx_px / TILE_SIZE) / scale
    new_ty = tile_center[1] - (dy_px / TILE_SIZE) / scale
    return tileIndexToLngLat(new_tx, new_ty)


# ---------------------------------------------------------------------------
# Cálculo de la grilla de tiles visibles
# ---------------------------------------------------------------------------

def computeVisibleTileGrid(center_lat, center_lon, zoom_float, screen_w, screen_h, tiles_dir):
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
    fixed_zoom = int(math.floor(zoom_float))
    scale = math.pow(2.0, zoom_float)
    fixed_pow_zoom = math.pow(2.0, fixed_zoom)
    scale_value = math.pow(2.0, zoom_float % 1.0)
    tile_size_scaled = TILE_SIZE * scale_value

    norm = lngLatToTileIndex(center_lat, center_lon)
    center_tile_x = math.floor(norm[0] * fixed_pow_zoom)
    center_tile_y = math.floor(norm[1] * fixed_pow_zoom)

    num_tiles_x = math.ceil(screen_w / TILE_SIZE / 2.0) + 1
    num_tiles_y = math.ceil(screen_h / TILE_SIZE / 2.0) + 1
    num_grids = int(math.pow(2.0, fixed_zoom))

    # Tamaño 3D de cada tile (espacio normalizado TD: pantalla = 1 unidad de ancho)
    tile_3d_size = tile_size_scaled / screen_w

    # Centro del tile central en espacio 3D
    ttl_x = norm[0] * TILE_SIZE * scale
    ttl_y = norm[1] * TILE_SIZE * scale
    center_tile_pixel_x = (center_tile_x + 0.5) * tile_size_scaled
    center_tile_pixel_y = (center_tile_y + 0.5) * tile_size_scaled

    tiles = []
    tile_id = 0
    for ix in range(int(center_tile_x - num_tiles_x), int(center_tile_x + num_tiles_x) + 1):
        if ix < 0 or ix >= num_grids:
            continue
        for iy in range(int(center_tile_y - num_tiles_y), int(center_tile_y + num_tiles_y) + 1):
            if iy < 0 or iy >= num_grids:
                continue
            file_path = os.path.join(tiles_dir, str(fixed_zoom), str(ix), str(iy) + '.png')
            file_path = file_path.replace('\\', '/')
            if not os.path.exists(file_path):
                continue

            # Offset 3D: posición del tile respecto al centro de pantalla
            tile_px_x = (ix + 0.5) * tile_size_scaled
            tile_px_y = (iy + 0.5) * tile_size_scaled
            # Diferencia respecto al centro del mapa en píxeles
            diff_x = tile_px_x - ttl_x
            diff_y = tile_px_y - ttl_y
            # Convertir a espacio TD ([-0.5, 0.5] para el ancho de pantalla)
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
            tile_id += 1

    return tiles


def tileGridToDAT(tiles, dat_op):
    """
    Escribe la lista de tiles devuelta por computeVisibleTileGrid en un tableDAT de TD.
    dat_op : referencia al operador tableDAT
    """
    dat_op.clear()
    dat_op.appendRow(['id', 'ox', 'oy', 'tamx', 'tamy', 'tilex', 'tiley', 'zoom', 'filePath'])
    for t in tiles:
        dat_op.appendRow([
            t['id'], t['ox'], t['oy'], t['tamx'], t['tamy'],
            t['tilex'], t['tiley'], t['zoom'], t['filePath']
        ])
