"""
MapaExtension.py
Extension principal para el container Mapa2 en TouchDesigner.

Centraliza todo el estado del mapa, las conversiones geográficas OSM,
el filtrado del CSV de calidad de agua y la generación de la grilla de tiles.

Uso en TD:
    - El container Mapa2 declara: extension1 = op('ext').module
    - Acceso desde cualquier op: op('/project1/Mapa2').ext.MapaExt
"""

import csv
import math
import os
import sys

# Rutas derivadas de project.folder — portátil entre máquinas
# project es la variable global de TD (td.project), siempre disponible en contexto TD
_PROJECT_DIR  = project.folder
_SCRIPTS_DIR  = project.folder + '/scripts'
_CSV_WATER    = project.folder + '/water2022.csv'
_CSV_STATIONS = project.folder + '/scripts/estaciones_coords.csv'
_TILES_DIR    = project.folder + '/TilesDark'

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import tile_utils


class MapaExt:
    """Extension principal del container Mapa2."""

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------

    def __init__(self, owner_op):
        try:
            self._owner = owner_op

            # --- Estado de navegación ---
            self.centerLat  = 36.5
            self.centerLon  = 127.5
            self.zoomFloat  = 6.6
            self.zoom       = 6          # zoom entero (nivel de tile)
            self.screenW    = 1280.0
            self.screenH    = 720.0

            # --- Filtro activo ---
            self.currentMes   = '01'
            self.currentFecha = ''       # vacío = sin filtro de fecha

            # --- Selección ---
            self.selectedStation = None  # dict con keys: area, estacion, lat, lon, data
            self.hoverLat = 0.0
            self.hoverLon = 0.0

            # --- Datos en memoria ---
            self._water_rows    = []     # lista de dicts (datos CSV completos)
            self._water_headers = []     # lista de nombres de columnas
            self._stations      = []     # lista de dicts: area, estacion, lat, lon
            self._filtered_rows = []     # filas del día activo con coords adjuntas

            self._loadStations()
            self._loadWaterCSV()

            # Primer cálculo de tiles y datos
            self.updateTileGrid()
            self.filterData(self.currentMes, self.currentFecha)

            print('[MapaExt] Extension inicializada. Estaciones:', len(self._stations),
                  '| Filas CSV:', len(self._water_rows))

            owner_op.store('ext_init_ok', 'OK estaciones={} rows={}'.format(
                len(self._stations), len(self._water_rows)))

        except Exception as _init_err:
            import traceback
            _tb = traceback.format_exc()
            print('[MapaExt] ERROR en __init__:', _tb)
            try:
                owner_op.store('ext_init_error', _tb)
            except:
                pass
            raise

    # ------------------------------------------------------------------
    # Carga de datos
    # ------------------------------------------------------------------

    def _loadStations(self):
        """Carga estaciones_coords.csv en self._stations."""
        self._stations = []
        try:
            with open(_CSV_STATIONS, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._stations.append({
                        'area':     row['area'].strip(),
                        'estacion': row['estacion'].strip(),
                        'lat':      float(row['lat']) if row['lat'] not in ('', 'None') else None,
                        'lon':      float(row['lon']) if row['lon'] not in ('', 'None') else None,
                    })
        except Exception as e:
            print('[MapaExt] Error cargando estaciones_coords.csv:', e)

    def _loadWaterCSV(self):
        """Carga water2022.csv en memoria como lista de dicts."""
        self._water_rows    = []
        self._water_headers = []
        try:
            with open(_CSV_WATER, encoding='utf-8') as f:
                reader = csv.reader(f)
                raw_headers = next(reader)
                self._water_headers = [h.strip() for h in raw_headers]
                for row in reader:
                    if len(row) < 8:
                        continue
                    self._water_rows.append(row)
        except Exception as e:
            print('[MapaExt] Error cargando water2022.csv:', e)

    # ------------------------------------------------------------------
    # Filtrado de datos
    # ------------------------------------------------------------------

    def filterData(self, mes, fecha=''):
        """
        Filtra los datos del CSV por mes (str '01'–'06') y opcionalmente por fecha ('2022.05.03').
        Adjunta las coordenadas lat/lon de la estación a cada fila.
        Escribe el resultado en los DATs data/table_filtered y data/table_coords.
        """
        self.currentMes   = str(mes).zfill(2)
        self.currentFecha = fecha.strip()

        # --- Filtrar filas ---
        COL_MES   = 2   # ' 월'
        COL_FECHA = 4   # ' 채수 일자'
        COL_AREA  = 6   # ' 중권역명' (mid-basin — coincide con allregions col 0)
        COL_ESTAC = 7   # ' 측정소 명'

        filtered = []
        for row in self._water_rows:
            if row[COL_MES].strip() != self.currentMes:
                continue
            if self.currentFecha and row[COL_FECHA].strip() != self.currentFecha:
                continue
            filtered.append(row)

        # --- Adjuntar coords por estación ---
        # Construir lookup: (area, estacion) -> (lat, lon)
        station_lookup = {}
        for s in self._stations:
            key = (s['area'], s['estacion'])
            station_lookup[key] = (s['lat'], s['lon'])

        self._filtered_rows = []
        for row in filtered:
            area   = row[COL_AREA].strip()
            estac  = row[COL_ESTAC].strip()
            coords = station_lookup.get((area, estac), (None, None))
            self._filtered_rows.append({
                'row':    row,
                'area':   area,
                'estacion': estac,
                'lat':    coords[0],
                'lon':    coords[1],
            })

        # --- Escribir en DATs de TouchDesigner ---
        self._writeFilteredDAT()
        self._writeCoordsDAT()

        print('[MapaExt] filterData mes={} fecha={} -> {} filas'.format(
            self.currentMes, self.currentFecha or '*', len(self._filtered_rows)))

    def _writeFilteredDAT(self):
        """Escribe los datos filtrados en data/table_filtered."""
        try:
            dat = self._owner.op('data/table_filtered')
            if dat is None:
                return
            dat.clear()
            dat.appendRow(self._water_headers + ['Lat', 'Lon'])
            for entry in self._filtered_rows:
                lat = entry['lat'] if entry['lat'] is not None else ''
                lon = entry['lon'] if entry['lon'] is not None else ''
                dat.appendRow(entry['row'] + [lat, lon])
        except Exception as e:
            print('[MapaExt] Error escribiendo table_filtered:', e)

    def _writeCoordsDAT(self):
        """
        Escribe en data/table_coords una fila por estación única del período filtrado,
        con columnas: area, estacion, lat, lon.
        """
        try:
            dat = self._owner.op('data/table_coords')
            if dat is None:
                return
            dat.clear()
            dat.appendRow(['area', 'estacion', 'lat', 'lon'])
            seen = set()
            for entry in self._filtered_rows:
                key = (entry['area'], entry['estacion'])
                if key in seen or entry['lat'] is None:
                    continue
                seen.add(key)
                dat.appendRow([entry['area'], entry['estacion'],
                                entry['lat'], entry['lon']])
        except Exception as e:
            print('[MapaExt] Error escribiendo table_coords:', e)

    # ------------------------------------------------------------------
    # Grilla de tiles
    # ------------------------------------------------------------------

    def updateTileGrid(self):
        """
        Calcula los tiles visibles y escribe tiles/table_tilelist en TD.
        Solo incluye tiles que existen en TilesDark/.
        """
        tiles = tile_utils.computeVisibleTileGrid(
            self.centerLat, self.centerLon,
            self.zoomFloat,
            self.screenW, self.screenH,
            _TILES_DIR
        )
        try:
            dat = self._owner.op('tiles/table_tilelist')
            if dat is not None:
                tile_utils.tileGridToDAT(tiles, dat)
        except Exception as e:
            print('[MapaExt] Error escribiendo table_tilelist:', e)

        # Forzar recook del scriptTOP de tiles
        try:
            script_tiles = self._owner.op('tiles/script_tiles')
            if script_tiles is not None:
                script_tiles.cook(force=True)
        except Exception as e:
            print('[MapaExt] Error forzando cook de script_tiles:', e)

        print('[MapaExt] updateTileGrid zoom={} -> {} tiles'.format(
            int(self.zoomFloat), len(tiles)))
        return tiles

    # ------------------------------------------------------------------
    # Interacción: pan, zoom, click, hover
    # ------------------------------------------------------------------

    def onDrag(self, u, v):
        """
        Llamar desde un chopexec cuando cambia el valor de drag (u, v en píxeles).
        Actualiza el centro del mapa y regenera la grilla de tiles.
        """
        new_center = tile_utils.drag(u, v, (self.centerLat, self.centerLon), self.zoomFloat)
        self.centerLat = new_center[0]
        self.centerLon = new_center[1]
        self._syncCustomPars()
        self.updateTileGrid()

    def onZoom(self, delta):
        """
        Aplica un delta de zoom (positivo = acercar, negativo = alejar).
        delta es un float (ej. 0.1 por tick de rueda).
        """
        zoom_min = 5.0
        zoom_max = 8.0
        self.zoomFloat = max(zoom_min, min(zoom_max, self.zoomFloat + delta))
        self.zoom = int(math.floor(self.zoomFloat))
        self._syncCustomPars()
        self.updateTileGrid()

    def onClickScreen(self, x_norm, y_norm):
        """
        Procesa un click en pantalla. x_norm, y_norm son coordenadas normalizadas
        de renderpick [-0.5, 0.5].
        Convierte a lat/lon, busca la estación más cercana y actualiza selectedStation.
        """
        x_px = (x_norm + 0.5) * self.screenW
        y_px = self.screenH - (y_norm + 0.5) * self.screenH
        lat_lon = tile_utils.screenXYToLatLon(
            [x_px, y_px],
            (self.centerLat, self.centerLon),
            (self.screenW, self.screenH),
            self.zoomFloat
        )
        self.selectedStation = self._findNearestStation(lat_lon[0], lat_lon[1])
        self._syncCustomPars()
        if self.selectedStation:
            print('[MapaExt] Estación seleccionada:', self.selectedStation['estacion'])

    def onHoverScreen(self, x_norm, y_norm):
        """Actualiza hoverLat/Lon desde posición de cursor normalizada."""
        x_px = (x_norm + 0.5) * self.screenW
        y_px = self.screenH - (y_norm + 0.5) * self.screenH
        lat_lon = tile_utils.screenXYToLatLon(
            [x_px, y_px],
            (self.centerLat, self.centerLon),
            (self.screenW, self.screenH),
            self.zoomFloat
        )
        self.hoverLat = lat_lon[0]
        self.hoverLon = lat_lon[1]

    # ------------------------------------------------------------------
    # Utilidades de conversión expuestas para expresiones TD
    # ------------------------------------------------------------------

    def latLonToScreenXY(self, lat, lon):
        """Convierte (lat, lon) a (x_px, y_px) en pantalla. Para usar en expresiones TD."""
        return tile_utils.latLonToScreenXY(
            (lat, lon),
            (self.centerLat, self.centerLon),
            (self.screenW, self.screenH),
            self.zoomFloat
        )

    def getStationScreenXY(self, area, estacion):
        """Devuelve (x_px, y_px) de una estación por nombre. Útil para instanciación."""
        for s in self._stations:
            if s['area'] == area and s['estacion'] == estacion:
                if s['lat'] is not None:
                    return self.latLonToScreenXY(s['lat'], s['lon'])
        return (self.screenW / 2.0, self.screenH / 2.0)

    def getAvailableDates(self, mes=None):
        """Devuelve lista de fechas únicas disponibles, opcionalmente filtradas por mes."""
        m = str(mes).zfill(2) if mes else None
        dates = set()
        for row in self._water_rows:
            if m and row[2].strip() != m:
                continue
            dates.add(row[4].strip())
        return sorted(dates)

    def getAvailableMonths(self):
        """Devuelve lista de meses disponibles en el CSV."""
        return sorted(set(row[2].strip() for row in self._water_rows))

    # ------------------------------------------------------------------
    # Sincronización con Custom Parameters de Mapa2
    # ------------------------------------------------------------------

    def _syncCustomPars(self):
        """Actualiza los Custom Parameters del container con el estado actual."""
        try:
            p = self._owner.par
            if hasattr(p, 'Centerlat'):  p.Centerlat  = self.centerLat
            if hasattr(p, 'Centerlon'):  p.Centerlon  = self.centerLon
            if hasattr(p, 'Zoom'):       p.Zoom       = self.zoom
            if hasattr(p, 'Zoomfloat'): p.Zoomfloat  = self.zoomFloat
            if self.selectedStation and hasattr(p, 'Selectedstation'):
                p.Selectedstation = self.selectedStation.get('estacion', '')
        except Exception as e:
            print('[MapaExt] Error sync pars:', e)

    # ------------------------------------------------------------------
    # Búsqueda de estación más cercana
    # ------------------------------------------------------------------

    def _findNearestStation(self, lat, lon, max_dist_deg=0.5):
        """
        Busca la estación más cercana a (lat, lon) entre las estaciones del período filtrado.
        max_dist_deg: distancia máxima en grados para considerar un hit.
        Devuelve dict con keys area, estacion, lat, lon, data (primera fila) o None.
        """
        best = None
        best_dist = max_dist_deg ** 2

        seen = set()
        for entry in self._filtered_rows:
            if entry['lat'] is None:
                continue
            key = (entry['area'], entry['estacion'])
            if key in seen:
                continue
            seen.add(key)
            dlat = entry['lat'] - lat
            dlon = entry['lon'] - lon
            dist2 = dlat * dlat + dlon * dlon
            if dist2 < best_dist:
                best_dist = dist2
                best = {
                    'area':     entry['area'],
                    'estacion': entry['estacion'],
                    'lat':      entry['lat'],
                    'lon':      entry['lon'],
                    'data':     entry['row'],
                }
        return best

    # ------------------------------------------------------------------
    # Acceso público a datos filtrados (para expresiones TD o scripts)
    # ------------------------------------------------------------------

    @property
    def filteredCount(self):
        return len(self._filtered_rows)

    @property
    def selectedInfo(self):
        """Devuelve string con info de la estación seleccionada para la UI."""
        if not self.selectedStation:
            return ''
        s = self.selectedStation
        headers = self._water_headers
        data    = s.get('data', [])
        lines   = [
            s['estacion'],
            s['area'],
            'Lat: {:.4f}  Lon: {:.4f}'.format(s['lat'], s['lon']),
        ]
        # Añadir parámetros de calidad con valor (no vacíos)
        quality_cols = [
            ('BOD',   15),  # 생물화학적산소요구량
            ('COD',   22),  # 화학적산소요구량
            ('pH',    49),  # 수소이온농도
            ('DO',    31),  # 용존산소
            ('T-N',   57),  # 총질소
            ('T-P',   59),  # 총인
            ('TOC',   58),  # 총유기탄소
            ('SS',    53),  # 부유물질
            ('EC',    34),  # 전기전도도
        ]
        for label, idx in quality_cols:
            if idx < len(data) and data[idx].strip() not in ('', '정량한계미만'):
                lines.append('{}: {}'.format(label, data[idx].strip()))
        return '\n'.join(lines)
