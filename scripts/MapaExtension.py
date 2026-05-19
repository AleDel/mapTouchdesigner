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
_TILES_BASE   = project.folder + '/tiles'           # carpeta contenedora de todos los tilesets
_TILES_DIR    = project.folder + '/tiles/TilesDark'  # fallback si no hay par Tileset

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
            # Leer de custom pars si ya existen (reinit)
            _p = owner_op.par
            if hasattr(_p, 'Screenw'): self.screenW = float(_p.Screenw.val)
            if hasattr(_p, 'Screenh'): self.screenH = float(_p.Screenh.val)

            # --- Filtro activo ---
            self.currentMes   = '01'
            self.currentFecha = ''       # vacío = sin filtro de fecha

            # --- Selección ---
            self.selectedStation = None  # dict con keys: area, estacion, lat, lon, data
            self.hoverLat = 0.0
            self.hoverLon = 0.0

            # --- Máquina de estados ---
            # usable: interactivo normal  |  selected: estación seleccionada
            # waiting: esperando animación externa  |  animating: animando
            # locked: completamente bloqueado (instalación en control)
            self.mapState        = 'usable'
            self._selectionTime  = None   # absTime.seconds al seleccionar (para fade)
            self._deselect_token = 0      # incrementa c/selección → cancela run() previos

            # --- Datos en memoria ---
            self._water_rows    = []     # lista de dicts (datos CSV completos)
            self._water_headers = []     # lista de nombres de columnas
            self._stations      = []     # lista de dicts: area, estacion, lat, lon
            self._filtered_rows = []     # filas del día activo con coords adjuntas

            self._lastTileCount     = 0   # tiles reales (con archivo) en la grilla anterior
            self._lastTileFiles     = []   # file paths de los tiles reales
            self._lastTilePositions = []   # posiciones (tilex, tiley) de tiles reales
            self._lastGridAll       = 0    # grid_w * grid_h (todos los slots, incluyendo gaps)
            self._lastTilesDir      = ''   # directorio de tiles activo en la última grilla
            self._xMinAll           = 0    # tilex mínimo del grid completo (incluyendo gaps)
            self._yMinAll           = 0    # tiley mínimo del grid completo
            self._gridWAll          = 1    # grid_w completo
            self._gridHAll          = 1    # grid_h completo
            self._tileFileSize      = tile_utils.TILE_SIZE  # ancho real del PNG del tileset activo

            self._loadStations()
            self._loadWaterCSV()

            # Primer cálculo de tiles y datos
            self.updateTileGrid()
            self.filterData(self.currentMes, self.currentFecha)

            # Poblar menú Tileset con las carpetas Tiles* disponibles
            self._updateTilesetPar()

            # Crear pars de control visual de dots si no existen
            self._ensureDotsControlPars()

            # Crear página Control (máquina de estados + animación) si no existe
            self._ensureControlPars()

            print('[MapaExt] Extension inicializada. Estaciones:', len(self._stations),
                  '| Filas CSV:', len(self._water_rows))

            owner_op.store('ext_init_ok', 'OK estaciones={} rows={}'.format(
                len(self._stations), len(self._water_rows)))
            
            self.reiniciarMapa()

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
        self._updateDotsTable()

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
    # Tilesets disponibles
    # ------------------------------------------------------------------

    def _availableTilesets(self):
        """Devuelve lista de carpetas Tiles* encontradas en tiles/, ordenadas."""
        try:
            dirs = sorted([
                d for d in os.listdir(_TILES_BASE)
                if d.startswith('Tiles') and os.path.isdir(os.path.join(_TILES_BASE, d))
            ])
            return dirs if dirs else ['TilesDark']
        except Exception as e:
            print('[MapaExt] Error escaneando tilesets:', e)
            return ['TilesDark']

    def _ensureDotsControlPars(self):
        """Crea los pars de control visual de dots en Visualizacion si no existen."""
        try:
            page = None
            for pg in self._owner.customPages:
                if pg.name == 'Visualizacion':
                    page = pg
                    break
            if page is None:
                return
            if not hasattr(self._owner.par, 'Dotradius'):
                p = page.appendInt('Dotradius', label='Radio dots')[0]
                p.default = 9
                p.min = 1
                p.max = 50
                p.val = 9
                p.normMin = 1
                p.normMax = 30
            if not hasattr(self._owner.par, 'Dotradiussel'):
                p = page.appendInt('Dotradiussel', label='Radio seleccionado')[0]
                p.default = 13
                p.min = 1
                p.max = 60
                p.val = 13
                p.normMin = 1
                p.normMax = 40
            # Color del dot normal (RGBA 0..1)
            for name, label, dv in [
                    ('Dotcolr', 'Dot R', 1.0), ('Dotcolg', 'Dot G', 1.0),
                    ('Dotcolb', 'Dot B', 0.2), ('Dotcola', 'Dot A', 1.0)]:
                if not hasattr(self._owner.par, name):
                    p = page.appendFloat(name, label=label)[0]
                    p.default = dv; p.min = 0.0; p.max = 1.0; p.val = dv
            # Color del dot seleccionado (RGBA 0..1)
            for name, label, dv in [
                    ('Dotselr', 'Sel R', 1.0), ('Dotselg', 'Sel G', 0.4),
                    ('Dotselb', 'Sel B', 0.0), ('Dotsela', 'Sel A', 1.0)]:
                if not hasattr(self._owner.par, name):
                    p = page.appendFloat(name, label=label)[0]
                    p.default = dv; p.min = 0.0; p.max = 1.0; p.val = dv
            if not hasattr(self._owner.par, 'Infopx'):
                p = page.appendInt('Infopx', label='Info panel X offset')[0]
                p.default = 0; p.min = -960; p.max = 960
                p.normMin = -640; p.normMax = 640; p.val = 0
            if not hasattr(self._owner.par, 'Infopy'):
                p = page.appendInt('Infopy', label='Info panel Y offset')[0]
                p.default = 0; p.min = -540; p.max = 540
                p.normMin = -360; p.normMax = 360; p.val = 0
            if not hasattr(self._owner.par, 'Screenw'):
                p = page.appendInt('Screenw', label='Resolución ancho')[0]
                p.default = 1280; p.min = 320; p.max = 3840
                p.normMin = 640; p.normMax = 1920; p.val = int(self.screenW)
            if not hasattr(self._owner.par, 'Screenh'):
                p = page.appendInt('Screenh', label='Resolución alto')[0]
                p.default = 720; p.min = 240; p.max = 2160
                p.normMin = 360; p.normMax = 1080; p.val = int(self.screenH)
        except Exception as e:
            print('[MapaExt] Error creando pars dots:', e)

    def _ensureControlPars(self):
        """Crea la página Control con pars de estado y animación si no existen."""
        try:
            page = None
            for pg in self._owner.customPages:
                if pg.name == 'Control':
                    page = pg
                    break
            if page is None:
                page = self._owner.appendCustomPage('Control')
            p = self._owner.par
            if not hasattr(p, 'Mapstate'):
                par = page.appendMenu('Mapstate', label='Estado del mapa')[0]
                states = ['usable', 'selected', 'waiting', 'animating', 'locked']
                par.menuNames  = states
                par.menuLabels = ['Usable', 'Seleccionado', 'Waiting', 'Animating', 'Locked']
                par.val = 'usable'
            if not hasattr(p, 'Autodeselect'):
                par = page.appendToggle('Autodeselect', label='Auto-deselect')[0]
                par.default = True; par.val = True
            if not hasattr(p, 'Deselectdelay'):
                par = page.appendFloat('Deselectdelay', label='Tiempo visible (seg)')[0]
                par.default = 8.0; par.min = 0.5; par.max = 120.0
                par.normMin = 0.5; par.normMax = 30.0; par.val = 8.0
            if not hasattr(p, 'Infofadein'):
                par = page.appendFloat('Infofadein', label='Fade-in (seg)')[0]
                par.default = 0.5; par.min = 0.0; par.max = 10.0
                par.normMin = 0.0; par.normMax = 5.0; par.val = 0.5
            if not hasattr(p, 'Infofadeout'):
                par = page.appendFloat('Infofadeout', label='Fade-out (seg)')[0]
                par.default = 0.5; par.min = 0.0; par.max = 10.0
                par.normMin = 0.0; par.normMax = 5.0; par.val = 0.5
            if not hasattr(p, 'Infoalpha'):
                par = page.appendFloat('Infoalpha', label='Alpha info (auto)')[0]
                par.default = 0.0; par.min = 0.0; par.max = 1.0; par.val = 0.0
            if not hasattr(p, 'Deselectnow'):
                page.appendPulse('Deselectnow', label='Deselect ahora')
        except Exception as e:
            print('[MapaExt] Error creando pars Control:', e)

    # ------------------------------------------------------------------
    # Máquina de estados
    # ------------------------------------------------------------------

    def _setState(self, state):
        """Actualiza mapState y escribe en par.Mapstate (con guardia anti-loop)."""
        self.mapState = state
        try:
            pe = self._owner.op('parexec_filtros')
            if pe is not None:
                pe.module._syncing = True
            self._owner.par.Mapstate = state
        except Exception as e:
            print('[MapaExt] Error escribiendo Mapstate par:', e)
        finally:
            try:
                if pe is not None:
                    pe.module._syncing = False
            except:
                pass

    def selectStation(self, station):
        """
        Selecciona una estación: inicia fade-in, programa auto-deselect.
        station: dict con keys area, estacion, lat, lon, data.
        """
        self.selectedStation = station
        self._selectionTime  = absTime.seconds
        self._deselect_token += 1
        self._setState('selected')
        self._writeSelectionInfo()
        self._writeStateDAT()
        self._scheduleAutoDeselect(self._deselect_token)
        self._updateDotsTable()
        print('[MapaExt] Seleccionada:', station['estacion'] if station else '?')

    def deselectStation(self):
        """Deselecciona la estación activa y vuelve al estado usable."""
        self.selectedStation = None
        self._selectionTime  = None
        self._setState('usable')
        self._writeSelectionInfo()
        self._writeStateDAT()
        self._syncCustomPars()
        self._updateDotsTable()
        print('[MapaExt] Estación deseleccionada')

    def _scheduleAutoDeselect(self, token):
        """Programa deselect automático. token evita que runs previos actúen."""
        try:
            if not bool(self._owner.par.Autodeselect.val):
                return
            fade_in  = max(0.0, float(self._owner.par.Infofadein.val))
            delay    = max(0.0, float(self._owner.par.Deselectdelay.val))
            fade_out = max(0.0, float(self._owner.par.Infofadeout.val))
            total    = fade_in + delay + fade_out
            run(
                "op('{}').ext.MapaExt._autoDeselect({})" .format(self._owner.path, token),
                delaySeconds=max(0.1, total)
            )
        except Exception as e:
            print('[MapaExt] Error programando auto-deselect:', e)

    def _autoDeselect(self, token):
        """Callback del run() de auto-deselect. Solo actúa si el token coincide."""
        if token == self._deselect_token:
            self.deselectStation()

    def getInfoAlpha(self):
        """
        Devuelve el alpha (0-1) para el panel de información según el tiempo transcurrido.
        Llamar desde script_dots.cook() cada frame para animar fade-in / fade-out.
        Timeline:
          0 → fade_in : fade-in (0→1)
          fade_in → fade_in+delay : visible (1)
          fade_in+delay → total : fade-out (1→0)
        """
        if self._selectionTime is None:
            return 0.0
        elapsed = absTime.seconds - self._selectionTime
        try:
            fade_in  = max(0.001, float(self._owner.par.Infofadein.val))
            delay    = max(0.0,   float(self._owner.par.Deselectdelay.val))
            fade_out = max(0.001, float(self._owner.par.Infofadeout.val))
            auto     = bool(self._owner.par.Autodeselect.val)
        except:
            return 1.0
        if elapsed < fade_in:
            return elapsed / fade_in
        if not auto:
            return 1.0
        if elapsed < fade_in + delay:
            return 1.0
        t_out = elapsed - fade_in - delay
        if t_out < fade_out:
            return max(0.0, 1.0 - t_out / fade_out)
        return 0.0

    def _writeStateDAT(self):
        """Escribe estado completo del mapa en data/table_mapstate (key-value)."""
        try:
            dat = self._owner.op('data/table_mapstate')
            if dat is None:
                return
            dat.clear()
            dat.appendRow(['key', 'value'])
            sel = self.selectedStation or {}
            for k, v in [
                ('state',    self.mapState),
                ('area',     sel.get('area', '')),
                ('estacion', sel.get('estacion', '')),
                ('lat',      str(sel.get('lat', ''))),
                ('lon',      str(sel.get('lon', ''))),
                ('info_alpha', '{:.3f}'.format(self.getInfoAlpha())),
                ('mes',      self.currentMes),
                ('fecha',    self.currentFecha),
                ('info',     self.selectedInfo),
            ]:
                dat.appendRow([k, v])
        except Exception as e:
            print('[MapaExt] Error escribiendo table_mapstate:', e)

    def _updateTilesetPar(self):
        """Actualiza el menú del par Tileset con las carpetas Tiles* actuales."""
        try:
            p = self._owner.par
            if not hasattr(p, 'Tileset'):
                return
            tilesets = self._availableTilesets()
            p.Tileset.menuLabels = tilesets
            p.Tileset.menuNames  = tilesets
            # Si el valor actual no está en la lista, forzar el primero
            if str(p.Tileset.val) not in tilesets and tilesets:
                p.Tileset.val = tilesets[0]
            print('[MapaExt] Tilesets disponibles:', tilesets)
        except Exception as e:
            print('[MapaExt] Error actualizando par Tileset:', e)

    @property
    def tilesDir(self):
        """Ruta a la carpeta de tiles activa (lee par Tileset si existe)."""
        try:
            p = self._owner.par
            if hasattr(p, 'Tileset'):
                folder = str(p.Tileset.val).strip()
                if folder:
                    return _TILES_BASE + '/' + folder
        except Exception:
            pass
        return _TILES_DIR

    # ------------------------------------------------------------------
    # Grilla de tiles
    # ------------------------------------------------------------------

    def updateTileGrid(self):
        """
        Calcula los tiles visibles y escribe tiles/table_tilelist.
        tiles incluye TODAS las posiciones del grid (con gaps filePath='').
        La tabla solo contiene tiles reales, con id=posición row-major.
        """
        tiles = tile_utils.computeVisibleTileGrid(
            self.centerLat, self.centerLon,
            self.zoomFloat,
            self.screenW, self.screenH,
            self.tilesDir,
            tile_size=getattr(self, '_tileFileSize', tile_utils.TILE_SIZE)
        )

        # Métricas del grid completo (incluyendo gaps) para cachesize del tex3d
        if tiles:
            xs = [t['tilex'] for t in tiles]
            ys = [t['tiley'] for t in tiles]
            self._xMinAll  = min(xs)
            self._yMinAll  = min(ys)
            self._gridWAll = max(xs) - self._xMinAll + 1
            self._gridHAll = max(ys) - self._yMinAll + 1
            self._lastGridAll = self._gridWAll * self._gridHAll
        else:
            self._xMinAll  = 0
            self._yMinAll  = 0
            self._gridWAll = 1
            self._gridHAll = 1
            self._lastGridAll = 0

        # Tamaño real del tile desde disco (soporta PNG y JPEG)
        real_files = [t['filePath'] for t in tiles if t.get('filePath')]
        if real_files:
            _w, _h = tile_utils.readImageSize(real_files[0])
            if _w > 0:
                self._tileFileSize = _w

        try:
            dat = self._owner.op('tiles/table_tilelist')
            if dat is not None:
                tile_utils.tileGridToDAT(tiles, dat)  # solo escribe tiles reales
        except Exception as e:
            print('[MapaExt] Error escribiendo table_tilelist:', e)

        real_tiles = [t for t in tiles if t['filePath']]

        # El replicator1 escucha table_tilelist y gestiona los ops tile_N
        # (creación, archivo, cableado del switch) via onReplicate callbacks.
        # Esta extensión solo actualiza uniforms y dots.
        self._updateGLSLUniforms()
        self._updateDotsTable()
        self._updateDotsUniforms()

        print('[MapaExt] updateTileGrid zoom={} -> {}/{} slots ({}x{})'.format(
            int(self.zoomFloat), len(real_tiles), self._lastGridAll,
            max((t['tilex'] for t in tiles), default=0) - min((t['tilex'] for t in tiles), default=0) + 1,
            max((t['tiley'] for t in tiles), default=0) - min((t['tiley'] for t in tiles), default=0) + 1,
        ))
        return tiles

    # ------------------------------------------------------------------
    # Atlas GLSL: metadata + uniforms
    # ------------------------------------------------------------------

    def _atlasMetaForZoom(self, zoom):
        """
        Carga y devuelve el JSON de metadatos del atlas para el zoom dado.
        Devuelve None si el atlas no ha sido generado aún.
        """
        import json as _json
        json_path = os.path.join(self.tilesDir, 'atlas_z{}.json'.format(zoom))
        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    return _json.load(f)
            except Exception as e:
                print('[MapaExt] Error leyendo atlas metadata:', e)
        return None

    def _atlasPathForZoom(self, zoom):
        """Devuelve la ruta del atlas PNG para el zoom dado, o None si no existe."""
        path = os.path.join(self.tilesDir, 'atlas_z{}.png'.format(zoom))
        return path if os.path.exists(path) else None

    def _prefillTex3d(self, tex3d, sw, n_all):
        """
        Configura el tex3d y programa un prefill diferido.
        - Mantiene active=True y la expresión frame-based en el switch para que
          el tex3d pueda capturar cada capa mientras los moviefileinTOP cargan.
        - Después de n_all+5 frames (tiempo suficiente para carga desde disco),
          ejecuta el prefill real, limpia la expresión del switch y congela el tex3d.
        NOTA: sw.par.index.val = N no limpia la expresión en TD; hay que borrar
        sw.par.index.expr explícitamente antes de asignar el valor constante.
        """
        tex3d.par.cachesize = n_all
        tex3d.par.active    = True          # activo para que el prefill funcione
        sw.par.index.expr   = 'me.time.frame-1'  # ciclar a través de todas las capas

        # Diferir el prefill para dar tiempo a que moviefileinTOP cargue desde disco
        delay = max(8, n_all + 5)
        run(
            "t=op('{}'); s=op('{}')\n"
            "t.par.prefillpulse.pulse()\n"
            "s.par.index.expr=''\n"
            "s.par.index.val=0\n"
            "t.par.active=False\n".format(tex3d.path, sw.path),
            delayFrames=delay
        )

    def _reconnectTileArray(self):
        """
        Crea los tile ops (moviefileinTOP) directamente desde table_tilelist, sin replicador.
        - Destruye ops anteriores (tile_N con digits).
        - Crea nuevos ops para cada fila real de la tabla.
        - Cablea el switch COMPACTO: solo tiles reales, ordenados por row_major_id.
          No hay gap fillers — el shader usa uIds para mapear posición → capa.
        - Actualiza cachesize = n_real tiles y hace prefill del tex3d.
        """
        try:
            tiles_comp = self._owner.op('tiles')
            tex3d = tiles_comp.op('tiles_tex3d1')
            sw    = tiles_comp.op('switch_tiles')
            dat   = tiles_comp.op('table_tilelist')
            if tex3d is None or sw is None or dat is None:
                return

            # 1) Destruir tile ops anteriores
            for o in list(tiles_comp.children):
                if o.digits is not None and o.name.startswith('tile_'):
                    o.destroy()

            # 2) Recoger filas y ordenar por id (row_major_id ascendente)
            rows = []
            for r in range(1, dat.numRows):
                try:
                    rows.append((int(dat[r, 'id']), str(dat[r, 'filePath'])))
                except Exception:
                    continue
            rows.sort(key=lambda x: x[0])

            # 3) Crear tile ops en ese orden
            for tid, filepath in rows:
                new_op = tiles_comp.create(moviefileinTOP, 'tile_{}'.format(tid))
                new_op.par.file = filepath

            # 4) Cablear switch COMPACTO: solo los tiles reales, sin gap fillers
            inputs_list = [tiles_comp.op('tile_{}'.format(tid)) for tid, _ in rows]
            inputs_list = [o for o in inputs_list if o is not None]
            sw.setInputs(inputs_list)

            # 5) cachesize = tiles reales (no grid completo) + prefill
            n_real = len(inputs_list)
            self._prefillTex3d(tex3d, sw, n_real)
            print('[MapaExt] _reconnectTileArray: {} tiles reales (compacto, grid total {})'.format(
                n_real, self._lastGridAll))
        except Exception as e:
            print('[MapaExt] Error _reconnectTileArray:', e)

    def _updateTileFiles(self):
        """
        Actualiza par.file de cada tile op leyendo desde table_tilelist (ya actualizada).
        Llamado cuando las posiciones del grid no cambiaron pero sí los archivos.
        """
        try:
            tiles_comp = self._owner.op('tiles')
            tex3d = tiles_comp.op('tiles_tex3d1')
            sw    = tiles_comp.op('switch_tiles')
            dat   = tiles_comp.op('table_tilelist')
            if tex3d is None or sw is None or dat is None:
                return
            # El id en la tabla ES el nombre del op (row-major, 1-indexed)
            for r in range(1, dat.numRows):
                row_id   = int(dat[r, 'id'])
                tile_op  = tiles_comp.op('tile_{}'.format(row_id))
                if tile_op is not None:
                    tile_op.par.file = str(dat[r, 'filePath'])
            self._prefillTex3d(tex3d, sw, self._lastTileCount)  # compacto: n_real
            print('[MapaExt] _updateTileFiles: {} tiles actualizados'.format(dat.numRows - 1))
        except Exception as e:
            print('[MapaExt] Error _updateTileFiles:', e)

    def _updateDotsTable(self):
        """
        Escribe en tiles/table_dots las posiciones en pantalla (UV 0..1) de cada
        estación del período filtrado. Cada fila: sx, sy, selected, quality.
        Llamado desde updateTileGrid(), filterData(), selectStation(), deselectStation().
        """
        try:
            dat = self._owner.op('tiles/table_dots')
            if dat is None:
                return
            dat.clear()
            dat.appendRow(['sx', 'sy', 'selected', 'quality'])

            if not self._filtered_rows:
                return

            int_zoom     = int(self.zoomFloat)
            fixed_pow    = math.pow(2.0, int_zoom)
            scale_value  = math.pow(2.0, self.zoomFloat - int_zoom)
            base_size    = getattr(self, '_tileFileSize', tile_utils.TILE_SIZE)
            tile_size_px = base_size * scale_value

            norm_c = tile_utils.lngLatToTileIndex(self.centerLat, self.centerLon)
            cx = norm_c[0] * fixed_pow
            cy = norm_c[1] * fixed_pow

            sel_area = self.selectedStation['area']     if self.selectedStation else None
            sel_name = self.selectedStation['estacion'] if self.selectedStation else None

            seen = set()
            for entry in self._filtered_rows:
                lat = entry['lat'];  lon = entry['lon']
                if lat is None or lon is None:
                    continue
                key = (entry['area'], entry['estacion'])
                if key in seen:
                    continue
                seen.add(key)

                norm = tile_utils.lngLatToTileIndex(lat, lon)
                tx = norm[0] * fixed_pow
                ty = norm[1] * fixed_pow

                # Offset en píxeles desde el centro de la pantalla
                dpx =  (tx - cx) * tile_size_px
                dpy = -(ty - cy) * tile_size_px   # TD UV Y: 0=abajo, 1=arriba → invertir

                sx = 0.5 + dpx / self.screenW
                sy = 0.5 + dpy / self.screenH

                # Descartar puntos muy fuera de pantalla (margen 20%)
                if sx < -0.2 or sx > 1.2 or sy < -0.2 or sy > 1.2:
                    continue

                is_sel = 1.0 if (entry['area'] == sel_area and
                                  entry['estacion'] == sel_name) else 0.0
                dat.appendRow([round(sx, 6), round(sy, 6), is_sel, 1.0])

        except Exception as e:
            print('[MapaExt] Error _updateDotsTable:', e)

    def _updateDotsUniforms(self):
        """
        Actualiza los uniforms del GLSL TOP tiles/glsl_dots:
        - uDotParams (vec0): screenW, screenH, radius(px), dotCount
        - uDotParamsSel (vec1): radiusSel
        - uDotColor (vec2): RGBA color normal
        - uDotColorSel (vec3): RGBA color seleccionado
        """
        try:
            glsl = self._owner.op('tiles/glsl_dots')
            if glsl is None:
                return

            p = self._owner.par
            radius     = float(p.Dotradius.val)    if hasattr(p, 'Dotradius')    else 9.0
            radius_sel = float(p.Dotradiussel.val) if hasattr(p, 'Dotradiussel') else 13.0

            dat = self._owner.op('tiles/table_dots')
            n   = (dat.numRows - 1) if dat is not None else 0

            glsl.par.vec0name   = 'uDotParams'
            glsl.par.vec0valuex = self.screenW
            glsl.par.vec0valuey = self.screenH
            glsl.par.vec0valuez = radius
            glsl.par.vec0valuew = float(n)

            glsl.par.vec1name   = 'uDotParamsSel'
            glsl.par.vec1valuex = radius_sel

            glsl.par.vec2name   = 'uDotColor'
            glsl.par.vec2valuex = float(p.Dotcolr.val) if hasattr(p, 'Dotcolr') else 1.0
            glsl.par.vec2valuey = float(p.Dotcolg.val) if hasattr(p, 'Dotcolg') else 1.0
            glsl.par.vec2valuez = float(p.Dotcolb.val) if hasattr(p, 'Dotcolb') else 0.2
            glsl.par.vec2valuew = float(p.Dotcola.val) if hasattr(p, 'Dotcola') else 1.0

            glsl.par.vec3name   = 'uDotColorSel'
            glsl.par.vec3valuex = float(p.Dotselr.val) if hasattr(p, 'Dotselr') else 1.0
            glsl.par.vec3valuey = float(p.Dotselg.val) if hasattr(p, 'Dotselg') else 0.4
            glsl.par.vec3valuez = float(p.Dotselb.val) if hasattr(p, 'Dotselb') else 0.0
            glsl.par.vec3valuew = float(p.Dotsela.val) if hasattr(p, 'Dotsela') else 1.0

        except Exception as e:
            print('[MapaExt] Error _updateDotsUniforms:', e)

    def _updateGLSLUniforms(self):
        """
        Actualiza los uniforms del GLSL TOP tiles/glsl_tiles para el
        Texture 2D Array. Lee el grid actual desde table_tilelist y
        detecta el tile_size real desde tile_1.width.
        Se llama automáticamente desde updateTileGrid() en cada pan/zoom.
        """
        try:
            glsl = self._owner.op('tiles/glsl_tiles_array')
            if glsl is None:
                return

            int_zoom    = int(self.zoomFloat)
            scale_value = math.pow(2.0, self.zoomFloat - int_zoom)

            # Tamaño real del tile (leído desde disco en updateTileGrid)
            base_tile_size = getattr(self, '_tileFileSize', tile_utils.TILE_SIZE)
            tile_size_px = base_tile_size * scale_value

            # Centro en espacio tile (coordenadas float del zoom entero)
            norm      = tile_utils.lngLatToTileIndex(self.centerLat, self.centerLon)
            fixed_pow = math.pow(2.0, int_zoom)
            cx = norm[0] * fixed_pow
            cy = norm[1] * fixed_pow

            # Grid info del grid completo (incluyendo gaps en bordes)
            # Usar bounds guardados por updateTileGrid para coincidir con los layer indices
            x_min  = self._xMinAll
            y_min  = self._yMinAll
            grid_w = self._gridWAll
            grid_h = self._gridHAll

            # Set uniforms via página "Vectors" del GLSL TOP
            glsl.par.vec0name   = 'uCenterTile'
            glsl.par.vec0valuex = cx
            glsl.par.vec0valuey = cy
            glsl.par.vec1name   = 'uAtlas'
            glsl.par.vec1valuex = float(x_min)
            glsl.par.vec1valuey = float(y_min)
            glsl.par.vec1valuez = float(grid_w)
            glsl.par.vec1valuew = float(grid_h)
            glsl.par.vec2name   = 'uScreen'
            glsl.par.vec2valuex = self.screenW
            glsl.par.vec2valuey = self.screenH
            glsl.par.vec3name   = 'uTileSize'
            glsl.par.vec3valuex = tile_size_px

            # --- Uniforms compactos: uTileCount + uIds0..uIds8 ---
            # Leer IDs de tiles reales, mismo orden que setInputs en _reconnectTileArray
            dat = self._owner.op('tiles/table_tilelist')
            tile_ids = []
            if dat is not None:
                id_rows = []
                for r in range(1, dat.numRows):
                    try:
                        id_rows.append(int(dat[r, 'id']))
                    except:
                        pass
                id_rows.sort()
                tile_ids = id_rows
            n_real = len(tile_ids)

            # uTileCount en vec3.y
            glsl.par.vec3valuey = float(n_real)

            # Expandir secuencia: necesitamos vec0..vec12 (13 total)
            if glsl.par.vec.val < 13:
                glsl.par.vec = 13

            # Empaquetar IDs en vec4..vec12 (9 vec4, 36 slots)
            tile_ids_padded = tile_ids + [0] * (36 - len(tile_ids))
            for vi in range(9):   # vec4..vec12
                ids = tile_ids_padded[vi * 4 : vi * 4 + 4]
                vn  = 'vec{}'.format(vi + 4)
                getattr(glsl.par, vn + 'name').val   = 'uIds{}'.format(vi)
                getattr(glsl.par, vn + 'valuex').val = float(ids[0])
                getattr(glsl.par, vn + 'valuey').val = float(ids[1])
                getattr(glsl.par, vn + 'valuez').val = float(ids[2])
                getattr(glsl.par, vn + 'valuew').val = float(ids[3])

        except Exception as e:
            print('[MapaExt] Error _updateGLSLUniforms:', e)

    # ------------------------------------------------------------------
    # Interacción: pan, zoom, click, hover
    # ------------------------------------------------------------------

    def onDrag(self, u, v):
        """
        Llamar desde un chopexec cuando cambia el valor de drag (u, v en píxeles).
        Actualiza el centro del mapa y regenera la grilla de tiles.
        """
        new_center = tile_utils.drag(u, v, (self.centerLat, self.centerLon), self.zoomFloat,
                                      tile_size=getattr(self, '_tileFileSize', tile_utils.TILE_SIZE))
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
        Ignorado si el mapa está en estado waiting / animating / locked.
        """
        if self.mapState in ('waiting', 'animating', 'locked'):
            return
        x_px = (x_norm + 0.5) * self.screenW
        y_px = self.screenH - (y_norm + 0.5) * self.screenH
        lat_lon = tile_utils.screenXYToLatLon(
            [x_px, y_px],
            (self.centerLat, self.centerLon),
            (self.screenW, self.screenH),
            self.zoomFloat,
            tile_size=getattr(self, '_tileFileSize', tile_utils.TILE_SIZE)
        )
        station = self._findNearestStation(lat_lon[0], lat_lon[1])
        if station:
            self.selectStation(station)
        else:
            self.deselectStation()
        self._syncCustomPars()

    def _writeSelectionInfo(self):
        """
        Escribe el texto formateado de la estación seleccionada en data/text_selectedinfo.
        El Text TOP de la UI lee ese DAT para mostrar el panel de información.
        """
        try:
            dat = self._owner.op('data/text_selectedinfo')
            if dat is not None:
                dat.text = self.selectedInfo
        except Exception as e:
            print('[MapaExt] Error escribiendo text_selectedinfo:', e)

    def onHoverScreen(self, x_norm, y_norm):
        """Actualiza hoverLat/Lon desde posición de cursor normalizada."""
        x_px = (x_norm + 0.5) * self.screenW
        y_px = self.screenH - (y_norm + 0.5) * self.screenH
        lat_lon = tile_utils.screenXYToLatLon(
            [x_px, y_px],
            (self.centerLat, self.centerLon),
            (self.screenW, self.screenH),
            self.zoomFloat,
            tile_size=getattr(self, '_tileFileSize', tile_utils.TILE_SIZE)
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
            self.zoomFloat,
            tile_size=getattr(self, '_tileFileSize', tile_utils.TILE_SIZE)
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
            # Activar guardia en parexec para evitar loop de onValueChange
            pe = self._owner.op('parexec_filtros')
            if pe is not None:
                pe.module._syncing = True
            else:
                print('[MapaExt] WARN: parexec_filtros no encontrado, _syncing inactivo')
            p = self._owner.par
            if hasattr(p, 'Centerlat'):  p.Centerlat  = self.centerLat
            if hasattr(p, 'Centerlon'):  p.Centerlon  = self.centerLon
            if hasattr(p, 'Zoom'):       p.Zoom       = self.zoom
            if hasattr(p, 'Zoomfloat'): p.Zoomfloat  = self.zoomFloat
            if hasattr(p, 'Selectedstation'):
                p.Selectedstation = (self.selectedStation or {}).get('estacion', '')
            if hasattr(p, 'Currentmes'):   p.Currentmes   = self.currentMes
            if hasattr(p, 'Currentfecha'): p.Currentfecha = self.currentFecha
            if hasattr(p, 'Mapstate'):     p.Mapstate     = self.mapState
            if hasattr(p, 'Infoalpha'):    p.Infoalpha    = self.getInfoAlpha()
        except Exception as e:
            print('[MapaExt] Error sync pars:', e)
        finally:
            try:
                if pe is not None:
                    pe.module._syncing = False
            except:
                pass

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
            #'Lat: {:.4f}  Lon: {:.4f}'.format(s['lat'], s['lon']),
        ]
        # Añadir parámetros de calidad con valor (no vacíos)
        quality_cols = [
            ('BOD',   15),  # 생물화학적산소요구량(BOD)
            ('COD',   22),  # 화학적산소요구량(COD)
            ('pH',    50),  # 수소이온농도(pH)
            ('DO',    31),  # 용존산소(DO)
            ('T-N',   58),  # 총질소(T-N)
            ('T-P',   60),  # 총인(T-P)
            ('TOC',   59),  # 총유기탄소(TOC)
            ('SS',    54),  # 부유물질(SS)
            ('EC',    34),  # 전기전도도(EC)
            ('Temp',  57),  # 수온
        ]
        for label, idx in quality_cols:
            if idx < len(data) and data[idx].strip() not in ('', '정량한계미만'):
                lines.append('{}: {}'.format(label, data[idx].strip()))
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Acciones públicas (llamables desde textport o scripts TD)
    # Par.Recargardatos y par.Reiniciarmapa las invocan
    # ------------------------------------------------------------------

    def recargarDatos(self):
        """Recarga estaciones y CSV desde disco y re-filtra con el mes activo."""
        self._loadStations()
        self._loadWaterCSV()
        self.filterData(self.currentMes, self.currentFecha)
        self.updateTileGrid()
        print('[MapaExt] Datos recargados. Filas CSV:', len(self._water_rows))

    def reiniciarMapa(self):
        """Resetea el mapa al centro y zoom por defecto."""
        self.centerLat = 36.5
        self.centerLon = 127.5
        self.zoomFloat = 6.6
        self.zoom      = 6
        self._syncCustomPars()
        self.updateTileGrid()
        print('[MapaExt] Mapa reiniciado al centro por defecto.')
