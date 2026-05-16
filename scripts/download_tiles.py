"""
download_tiles.py
Descarga tiles de mapas para una bounding box y rango de zoom dados.
Guarda en la misma estructura que TilesDark: {output_dir}/{zoom}/{x}/{y}.png

Uso rápido desde terminal:
    python download_tiles.py

O importado desde TD Textport:
    import importlib, sys
    sys.path.insert(0, project.folder + '/scripts')
    import download_tiles
    importlib.reload(download_tiles)
    download_tiles.download(
        bbox=(33.0, 124.5, 38.6, 130.0),
        zoom_range=(5, 8),
        source='carto_dark',
        output_dir=project.folder + '/TilesLight'
    )

Fuentes disponibles (source=):
    'carto_dark'    — CartoDB Dark (sin API key, igual a TilesDark actual)       ✓ bulk OK
    'carto_dark_nl' — CartoDB Dark SIN etiquetas (sin API key)                   ✓ bulk OK
    'carto_light'   — CartoDB Light minimalista (sin API key)                   ✓ bulk OK
    'carto_light_nl'— CartoDB Light SIN etiquetas (sin API key)                  ✓ bulk OK
    'carto_voyager' — CartoDB Voyager colorido (sin API key)                    ✓ bulk OK
    'carto_voyager_nl'—CartoDB Voyager SIN etiquetas (sin API key)              ✓ bulk OK
    'esri_satellite'— Esri World Imagery satélite (sin API key)                ✓ bulk OK
    'stadia_dark'   — Stadia Alidade Smooth Dark (requiere API key gratuita)   ✓ bulk OK
    'stadia_light'  — Stadia Alidade Smooth Light (requiere API key gratuita)  ✓ bulk OK
    'stadia_sat'    — Stadia Alidade Satellite (requiere API key gratuita)      ✓ bulk OK
    'stadia_outdoors'—Stadia Outdoors/terreno (requiere API key gratuita)       ✓ bulk OK
    'stadia_osm'    — Stadia OSM Bright (requiere API key gratuita)            ✓ bulk OK
    'stamen_toner'  — Stamen Toner B&N alto contraste (requiere API key)       ✓ bulk OK
    'stamen_terrain'— Stamen Terrain con relieve (requiere API key)            ✓ bulk OK
    'stamen_wc'     — Stamen Watercolor artistico (requiere API key)           ✓ bulk OK
    'mapbox_dark'   — Mapbox Dark v10 256px (requiere Mapbox access_token)     ✓ bulk OK
    'mapbox_light'  — Mapbox Light v10 256px (requiere Mapbox access_token)    ✓ bulk OK
    'mapbox_streets'— Mapbox Streets v12 256px (requiere Mapbox access_token)  ✓ bulk OK
    'mapbox_sat'    — Mapbox Satellite 256px (requiere Mapbox access_token)    ✓ bulk OK
    'mapbox_outdoors'—Mapbox Outdoors v12 256px (requiere Mapbox access_token) ✓ bulk OK
    'osm'           — OSM estándar — BLOQUEADO para descarga masiva (ToS)      ✗ NO usar
    URL custom      — cualquier URL con {z}/{x}/{y}, ej: 'https://mi.servidor/{z}/{x}/{y}.png'

Nota: Stadia NO tiene variantes nolabels en raster. Para mapas sin etiquetas usa carto_*_nl.

Nota Mapbox: pasar la access_token via api_key=. Ejemplo:
    download_tiles.download(source='mapbox_dark', api_key='pk.eyJ1...', output_dir=...)
"""

import math
import os
import time
import urllib.request
import urllib.error

# ------------------------------------------------------------------
# Fuentes de tiles
# ------------------------------------------------------------------

SOURCES = {
    # OSM estándar: PROHIBIDO para descarga masiva por sus ToS.
    # El servidor bloquea las peticiones y devuelve una imagen de error.
    # Usa cualquiera de las fuentes CARTO o Stadia en su lugar.
    # Ref: https://operations.osmfoundation.org/policies/tiles/
    'osm': {
        'url':    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        'ext':    'png',
        'note':   'BLOQUEADO PARA DESCARGA MASIVA — viola ToS de OSM. Usa carto_* o stadia_* en su lugar.',
        'blocked': True,
    },
    'carto_dark': {
        'url':    'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'ext':    'png',
        'note':   'CartoDB Dark - gratis, sin API key',
    },
    'carto_dark_nl': {
        'url':    'https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png',
        'ext':    'png',
        'note':   'CartoDB Dark SIN etiquetas - gratis, sin API key',
    },
    'carto_light': {
        'url':    'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
        'ext':    'png',
        'note':   'CartoDB Light - gratis, sin API key',
    },
    'carto_light_nl': {
        'url':    'https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png',
        'ext':    'png',
        'note':   'CartoDB Light SIN etiquetas - gratis, sin API key',
    },
    'carto_voyager': {
        'url':    'https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
        'ext':    'png',
        'note':   'CartoDB Voyager (colorido) - gratis, sin API key',
    },
    'carto_voyager_nl': {
        'url':    'https://a.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png',
        'ext':    'png',
        'note':   'CartoDB Voyager SIN etiquetas - gratis, sin API key',
    },
    'esri_satellite': {
        # OJO: Esri usa {z}/{y}/{x} (y antes que x)
        'url':    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        'ext':    'jpg',
        'note':   'Esri World Imagery (satélite) - gratis, sin API key',
        'swap_xy': True,   # Esri invierte y/x en la URL
    },
    'stadia_dark': {
        'url':        'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stadia Dark - requiere API key gratuita (https://client.stadiamaps.com/)',
        'auth_param': 'api_key',
    },
    'stadia_light': {
        'url':        'https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stadia Light - requiere API key gratuita (https://client.stadiamaps.com/)',
        'auth_param': 'api_key',
    },
    'stadia_sat': {
        'url':        'https://tiles.stadiamaps.com/tiles/alidade_satellite/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stadia Satellite (imagenes aereas + etiquetas) - requiere API key gratuita',
        'auth_param': 'api_key',
    },
    'stadia_outdoors': {
        'url':        'https://tiles.stadiamaps.com/tiles/outdoors/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stadia Outdoors (terreno, rutas) - requiere API key gratuita',
        'auth_param': 'api_key',
    },
    'stadia_osm': {
        'url':        'https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stadia OSM Bright - requiere API key gratuita',
        'auth_param': 'api_key',
    },
    'stamen_toner': {
        'url':        'https://tiles.stadiamaps.com/tiles/stamen_toner/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stamen Toner (B&N alto contraste) - requiere API key gratuita',
        'auth_param': 'api_key',
    },
    'stamen_terrain': {
        'url':        'https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stamen Terrain (relieve y vegetacion) - requiere API key gratuita',
        'auth_param': 'api_key',
    },
    'stamen_wc': {
        'url':        'https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.png',
        'ext':        'png',
        'note':       'Stamen Watercolor (estilo artistico acuarela) - requiere API key gratuita',
        'auth_param': 'api_key',
    },
    # --- Mapbox (requiere access_token de https://account.mapbox.com) ---
    # URL formato: /styles/v1/{user}/{style}/tiles/256/{z}/{x}/{y}?access_token=...
    # Los tiles de 512px (tileSize=512&zoomOffset=-1) también funcionan pero
    # rompen el sistema de grid actual que espera 256px.
    'mapbox_dark': {
        'url':        'https://api.mapbox.com/styles/v1/mapbox/dark-v10/tiles/256/{z}/{x}/{y}',
        'ext':        'png',
        'note':       'Mapbox Dark v10 (256px) - requiere access_token de mapbox.com',
        'auth_param': 'access_token',
    },
    'mapbox_light': {
        'url':        'https://api.mapbox.com/styles/v1/mapbox/light-v10/tiles/256/{z}/{x}/{y}',
        'ext':        'png',
        'note':       'Mapbox Light v10 (256px) - requiere access_token de mapbox.com',
        'auth_param': 'access_token',
    },
    'mapbox_streets': {
        'url':        'https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/256/{z}/{x}/{y}',
        'ext':        'png',
        'note':       'Mapbox Streets v12 (256px) - requiere access_token de mapbox.com',
        'auth_param': 'access_token',
    },
    'mapbox_sat': {
        'url':        'https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/256/{z}/{x}/{y}',
        'ext':        'png',
        'note':       'Mapbox Satellite v9 (256px) - requiere access_token de mapbox.com',
        'auth_param': 'access_token',
    },
    'mapbox_outdoors': {
        'url':        'https://api.mapbox.com/styles/v1/mapbox/outdoors-v12/tiles/256/{z}/{x}/{y}',
        'ext':        'png',
        'note':       'Mapbox Outdoors v12 (256px) - requiere access_token de mapbox.com',
        'auth_param': 'access_token',
    },
}

# ------------------------------------------------------------------
# Conversión lat/lon -> tile XY (estándar OSM/Web Mercator)
# ------------------------------------------------------------------

def _lat_lon_to_tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    x = max(0, min(n - 1, x))
    y = max(0, min(n - 1, y))
    return x, y

def _bbox_to_tile_range(lat_min, lon_min, lat_max, lon_max, zoom):
    """Devuelve (x_min, x_max, y_min, y_max) de tiles que cubren la bbox."""
    x0, y0 = _lat_lon_to_tile(lat_max, lon_min, zoom)  # lat_max -> y_min
    x1, y1 = _lat_lon_to_tile(lat_min, lon_max, zoom)  # lat_min -> y_max
    return x0, x1, y0, y1

# ------------------------------------------------------------------
# Función principal
# ------------------------------------------------------------------

def download(
    bbox=(33.0, 124.5, 38.6, 130.0),
    zoom_range=(5, 8),
    source='carto_dark',
    output_dir=None,
    api_key=None,
    delay=0.15,
    skip_existing=True,
    dry_run=False,
):
    """
    Descarga tiles para la bounding box y zoom dados.

    Args:
        bbox         : (lat_min, lon_min, lat_max, lon_max)
        zoom_range   : (zoom_min, zoom_max) ambos inclusive
        source       : clave de SOURCES o URL custom con {z}/{x}/{y}
        output_dir   : carpeta raíz de destino (se crea si no existe)
        api_key      : API key opcional (para Stadia, Mapbox, etc.)
        delay        : segundos entre requests (respetar servidores)
        skip_existing: si True, salta tiles ya descargados
        dry_run      : si True, solo cuenta tiles sin descargar
    """
    # Resolver fuente
    if source in SOURCES:
        cfg      = SOURCES[source]
        # Detener si la fuente está marcada como bloqueada
        if cfg.get('blocked'):
            print('[tiles] ERROR: La fuente "{}" está bloqueada para descarga masiva.'.format(source))
            print('[tiles]', cfg['note'])
            print('[tiles] Usa: carto_dark, carto_light, carto_voyager, esri_satellite o stadia_*')
            return
        url_tmpl = cfg['url']
        ext      = cfg['ext']
        swap_xy    = cfg.get('swap_xy', False)
        auth_param = cfg.get('auth_param', 'api_key')
        print('[tiles] Fuente:', source, '—', cfg['note'])
    else:
        url_tmpl   = source   # URL custom directa
        ext        = 'png'
        swap_xy    = False
        auth_param = 'api_key'
        print('[tiles] Fuente custom:', url_tmpl)

    if output_dir is None:
        raise ValueError('Debes indicar output_dir')

    lat_min, lon_min, lat_max, lon_max = bbox
    z_min, z_max = zoom_range

    # Contar total de tiles
    total = 0
    for z in range(z_min, z_max + 1):
        x0, x1, y0, y1 = _bbox_to_tile_range(lat_min, lon_min, lat_max, lon_max, z)
        total += (x1 - x0 + 1) * (y1 - y0 + 1)

    print('[tiles] Bbox: lat {}-{} lon {}-{}'.format(lat_min, lat_max, lon_min, lon_max))
    print('[tiles] Zoom {}-{} | Total estimado: {} tiles'.format(z_min, z_max, total))
    print('[tiles] Destino:', output_dir)

    if dry_run:
        print('[tiles] dry_run=True — nada descargado.')
        return

    headers = {
        'User-Agent': 'TileDownloader/1.0 (TouchDesigner project; educational use)',
    }

    downloaded = 0
    skipped    = 0
    errors     = 0

    for z in range(z_min, z_max + 1):
        x0, x1, y0, y1 = _bbox_to_tile_range(lat_min, lon_min, lat_max, lon_max, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                # Ruta de destino
                out_path = os.path.join(output_dir, str(z), str(x), '{}.{}'.format(y, ext))

                if skip_existing and os.path.exists(out_path):
                    skipped += 1
                    continue

                # Construir URL
                if swap_xy:
                    url = url_tmpl.format(z=z, x=x, y=y)  # Esri ya usa {y} antes que {x} en la plantilla
                else:
                    url = url_tmpl.format(z=z, x=x, y=y)

                if api_key:
                    sep = '&' if '?' in url else '?'
                    url = '{}{}{}={}'.format(url, sep, auth_param, api_key)

                # Crear carpeta
                os.makedirs(os.path.dirname(out_path), exist_ok=True)

                # Descargar
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = resp.read()
                    with open(out_path, 'wb') as f:
                        f.write(data)
                    downloaded += 1
                    if downloaded % 50 == 0:
                        print('[tiles] {} / {} descargados ({} saltados, {} errores)'.format(
                            downloaded, total - skipped, skipped, errors))
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        pass  # Tile no existe (normal en bordes de bbox)
                    else:
                        errors += 1
                        print('[tiles] HTTP {} para z={} x={} y={}: {}'.format(e.code, z, x, y, url))
                except Exception as e:
                    errors += 1
                    print('[tiles] Error z={} x={} y={}: {}'.format(z, x, y, e))

                time.sleep(delay)

    print('[tiles] Descarga completada: {} nuevos, {} saltados, {} errores'.format(
        downloaded, skipped, errors))


# ------------------------------------------------------------------
# Ejecución directa (python download_tiles.py)
# ------------------------------------------------------------------

if __name__ == '__main__':
    import os as _os

    # Detectar carpeta del script como raíz del proyecto
    _script_dir  = _os.path.dirname(_os.path.abspath(__file__))
    _project_dir = _os.path.dirname(_script_dir)   # carpeta que contiene /scripts/

    # Cargar .env del proyecto si existe (sin dependencias externas)
    _env_file = _os.path.join(_project_dir, '.env')
    if _os.path.exists(_env_file):
        with open(_env_file) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _v = _line.split('=', 1)
                    _os.environ.setdefault(_k.strip(), _v.strip())

    # --- CONFIGURAR AQUÍ ---
    BBOX       = (33.0, 124.5, 38.6, 130.0)   # Corea del Sur
    ZOOM_RANGE = (5, 8)
    SOURCE     = 'stamen_wc'               # ver SOURCES arriba
    OUTPUT_DIR = _os.path.join(_project_dir, 'tiles', 'TilesWaterColor')
    API_KEY    = _os.environ.get('STADIA_API_KEY') or _os.environ.get('MAPBOX_TOKEN')
    DELAY      = 0.15                          # segundos entre requests
    DRY_RUN    = False                          # cambiar a False para descargar de verdad
    # -----------------------

    # Primero hacer un dry_run para ver cuántos tiles son
    download(
        bbox=BBOX,
        zoom_range=ZOOM_RANGE,
        source=SOURCE,
        output_dir=OUTPUT_DIR,
        api_key=API_KEY,
        delay=DELAY,
        skip_existing=True,
        dry_run=DRY_RUN,
    )
