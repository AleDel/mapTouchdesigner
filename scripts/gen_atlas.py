"""
gen_atlas.py
Genera un atlas PNG por nivel de zoom a partir de los tiles descargados.

Ejecutar UNA VEZ desde terminal (o desde TD con execScript):
    python scripts/gen_atlas.py
    python scripts/gen_atlas.py --tileset TilesDark --zoom 8

Salida por cada zoom encontrado:
    tiles/<Tileset>/atlas_z<zoom>.png   ← imagen RGBA con todos los tiles en grilla
    tiles/<Tileset>/atlas_z<zoom>.json  ← metadatos de la grilla (x_min, y_min, etc.)

La grilla del atlas sigue la convención:
    - Columna 0 = tilex mínimo (más al oeste)
    - Fila 0 del PNG = tiley mínimo (más al norte)
    - Fila N del PNG = tiley máximo (más al sur)

TouchDesigner carga las imágenes PNG con fila 0 en la parte inferior de la textura
(v=0), por eso el shader invierte la coordenada V.
"""

import os
import sys
import json
import struct

import numpy as np
import cv2


TILE_SIZE = 512   # tamaño nativo de los tiles (Mapbox @2x)


def _read_png_size(path):
    """Lee el ancho/alto de un PNG sin cargar la imagen completa."""
    with open(path, 'rb') as f:
        f.read(8)                          # firma PNG
        f.read(4)                          # longitud del chunk IHDR
        f.read(4)                          # 'IHDR'
        w = struct.unpack('>I', f.read(4))[0]
        h = struct.unpack('>I', f.read(4))[0]
    return w, h


def generate_atlas(tiles_base, zoom, tile_size=TILE_SIZE):
    """
    Genera atlas_z<zoom>.png y atlas_z<zoom>.json dentro de tiles_base.

    Parámetros:
        tiles_base : carpeta raíz del tileset, ej. 'C:/DEA/map2/tiles/TilesDark'
        zoom       : nivel de zoom entero
        tile_size  : tamaño de cada tile en el atlas (512 para Mapbox @2x)

    Devuelve dict con metadatos o None si no hay tiles.
    """
    zoom_dir = os.path.join(tiles_base, str(zoom))
    if not os.path.isdir(zoom_dir):
        print(f'  [zoom {zoom}] No existe directorio: {zoom_dir}')
        return None

    # ── Escanear todos los tiles (tilex/tiley) disponibles ──────────────
    entries = []
    for x_name in sorted(os.listdir(zoom_dir)):
        x_dir = os.path.join(zoom_dir, x_name)
        if not os.path.isdir(x_dir):
            continue
        try:
            tx = int(x_name)
        except ValueError:
            continue
        for fname in os.listdir(x_dir):
            if not fname.endswith('.png'):
                continue
            try:
                ty = int(os.path.splitext(fname)[0])
            except ValueError:
                continue
            entries.append((tx, ty, os.path.join(x_dir, fname)))

    if not entries:
        print(f'  [zoom {zoom}] Sin tiles PNG en {zoom_dir}')
        return None

    x_vals = sorted(set(e[0] for e in entries))
    y_vals = sorted(set(e[1] for e in entries))
    x_min, x_max = min(x_vals), max(x_vals)
    y_min, y_max = min(y_vals), max(y_vals)
    grid_w = x_max - x_min + 1
    grid_h = y_max - y_min + 1

    atlas_w = grid_w * tile_size
    atlas_h = grid_h * tile_size

    print(f'  [zoom {zoom}] grilla {grid_w}×{grid_h}  '
          f'(x {x_min}–{x_max}, y {y_min}–{y_max})  '
          f'atlas {atlas_w}×{atlas_h}px  '
          f'{len(entries)} tiles')

    # ── Montar atlas en numpy (RGBA, uint8) ─────────────────────────────
    # Fila 0 del array = fila 0 del PNG = tiley mínimo (norte)
    atlas = np.zeros((atlas_h, atlas_w, 4), dtype=np.uint8)

    loaded = 0
    for tx, ty, path in entries:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f'    WARN: no se pudo leer {path}')
            continue

        # Normalizar a BGRA
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

        # Redimensionar si es necesario
        if img.shape[0] != tile_size or img.shape[1] != tile_size:
            img = cv2.resize(img, (tile_size, tile_size), interpolation=cv2.INTER_LINEAR)

        # BGR→RGB para guardar como RGBA en el atlas
        img_rgba = img[:, :, [2, 1, 0, 3]]

        col = tx - x_min
        row = ty - y_min
        y0 = row * tile_size
        x0 = col * tile_size
        atlas[y0:y0 + tile_size, x0:x0 + tile_size] = img_rgba
        loaded += 1

    print(f'  [zoom {zoom}] {loaded}/{len(entries)} tiles cargados')

    # ── Guardar atlas PNG (cv2 necesita BGRA) ───────────────────────────
    out_png = os.path.join(tiles_base, f'atlas_z{zoom}.png')
    cv2.imwrite(out_png, atlas[:, :, [2, 1, 0, 3]])
    print(f'  [zoom {zoom}] ✓ {out_png}')

    # ── Guardar metadatos JSON ───────────────────────────────────────────
    meta = {
        'zoom':     zoom,
        'x_min':    x_min,
        'y_min':    y_min,
        'x_max':    x_max,
        'y_max':    y_max,
        'grid_w':   grid_w,
        'grid_h':   grid_h,
        'tile_size': tile_size,
        'atlas_w':  atlas_w,
        'atlas_h':  atlas_h,
        'count':    loaded,
    }
    out_json = os.path.join(tiles_base, f'atlas_z{zoom}.json')
    with open(out_json, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f'  [zoom {zoom}] ✓ {out_json}')

    return meta


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Detectar directorio raíz del proyecto
    script_dir    = os.path.dirname(os.path.abspath(__file__))
    project_dir   = os.path.dirname(script_dir)
    tiles_base_root = os.path.join(project_dir, 'tiles')

    # Argumentos opcionales: --tileset  --zoom
    args = sys.argv[1:]

    if '--tileset' in args:
        i = args.index('--tileset')
        tilesets = [args[i + 1]]
    else:
        tilesets = sorted([
            d for d in os.listdir(tiles_base_root)
            if d.startswith('Tiles') and
            os.path.isdir(os.path.join(tiles_base_root, d))
        ])

    if '--zoom' in args:
        i = args.index('--zoom')
        zooms = [int(args[i + 1])]
    else:
        zooms = [5, 6, 7, 8]

    print(f'Generando atlas en: {tiles_base_root}')
    print(f'Tilesets: {tilesets}')
    print(f'Zooms: {zooms}\n')

    for ts in tilesets:
        ts_path = os.path.join(tiles_base_root, ts)
        print(f'[{ts}]')
        for z in zooms:
            generate_atlas(ts_path, z, tile_size=TILE_SIZE)
        print()
