# parexec_filtros.py
# ParameterExecuteDAT para el container Mapa2.
# onValueChange se dispara solo al cambiar un custom par — sin polling.
# onPulse se dispara al pulsar los botones de Acciones.

import math

_MES_CODES = ['01', '02', '03', '04', '05', '06']

# Guardia para evitar loop: _syncCustomPars escribe en Centerlat/Centerlon/Zoomfloat,
# lo que volvería a disparar onValueChange. Se activa antes de escribir y se desactiva después.
_syncing = False


def _ext():
    return op('/project1/Mapa2').ext.MapaExt


def _cookDots():
    # No usar force=True desde dentro de un cook callback: genera dependency loop.
    # glsl_dots se recookea solo al cambiar sus inputs/uniforms; no hace falta forzar.
    pass


def _filterAndRefresh(mes_idx, fecha):
    mes = _MES_CODES[mes_idx] if 0 <= mes_idx < len(_MES_CODES) else '01'
    _ext().filterData(mes, fecha.strip())
    _cookDots()


def onValueChange(par, prev):
    global _syncing
    if _syncing:
        return

    name = par.name

    # --- Navegación manual por slider ---
    # Se difiere 1 frame igual que Tileset: escribir en table_tilelist / uniforms
    # desde dentro del cook de parexec dispara otro cook (dependency loop).
    if name == 'Centerlat':
        ext = _ext()
        ext.centerLat = float(par.val)
        run("op('/project1/Mapa2').ext.MapaExt.updateTileGrid()", delayFrames=1)

    elif name == 'Centerlon':
        ext = _ext()
        ext.centerLon = float(par.val)
        run("op('/project1/Mapa2').ext.MapaExt.updateTileGrid()", delayFrames=1)

    elif name == 'Zoomfloat':
        ext = _ext()
        ext.zoomFloat = float(par.val)
        ext.zoom      = int(math.floor(ext.zoomFloat))
        run("op('/project1/Mapa2').ext.MapaExt.updateTileGrid()", delayFrames=1)

    # --- Filtros ---
    elif name == 'Mes':
        fecha = str(op('/project1/Mapa2').par.Fecha.val)
        _filterAndRefresh(int(par.menuIndex), fecha)

    elif name == 'Fecha':
        idx = int(op('/project1/Mapa2').par.Mes.menuIndex)
        _filterAndRefresh(idx, str(par.val))

    # --- Visualizacion ---
    elif name == 'Tileset':
        # Diferir 1 frame para evitar cook loop: _reconnectTileArray crea/destruye
        # ops moviefileinTOP mientras el cook del parexec sigue activo.
        run("op('/project1/Mapa2').ext.MapaExt.updateTileGrid()", delayFrames=1)

    elif name == 'Mapstate':
        # Escrito desde fuera (instalación): sincronizar estado interno sin loop
        ext = _ext()
        ext.mapState = str(par.val)
        ext._writeStateDAT()
        _cookDots()

    elif name in ('Autodeselect', 'Deselectdelay', 'Infofadein', 'Infofadeout'):
        # Cambios en config de animación: solo forzar redraw
        _cookDots()

    elif name in ('Screenw', 'Screenh'):
        ext = _ext()
        mapa = op('/project1/Mapa2')
        ext.screenW = float(mapa.par.Screenw.val)
        ext.screenH = float(mapa.par.Screenh.val)
        glsl = op('/project1/Mapa2/tiles/glsl_tiles_array')
        if glsl is not None:
            glsl.par.resolutionw = int(ext.screenW)
            glsl.par.resolutionh = int(ext.screenH)
        ext.updateTileGrid()

    elif name in ('Dotradius', 'Dotradiussel'):
        _ext()._updateDotsUniforms()
        _cookDots()

    elif name in ('Dotcolr', 'Dotcolg', 'Dotcolb', 'Dotcola',
                  'Dotselr', 'Dotselg', 'Dotselb', 'Dotsela'):
        _ext()._updateDotsUniforms()
        _cookDots()

    elif name == 'Showdots':
        show = bool(par.val)
        gd = op('/project1/Mapa2/tiles/glsl_dots')
        if gd is not None:
            gd.bypass = not show
        gs = op('/project1/Mapa2/render/geo_stations')
        if gs is not None:
            gs.par.render = show

    elif name == 'Showinfo':
        # Bypasear el Over TOP que compone el panel UI sobre el mapa
        over_ui = op('/project1/Mapa2/tiles/over_ui')
        if over_ui is not None:
            over_ui.bypass = not bool(par.val)

    elif name in ('Infopx', 'Infopy'):
        # Mover el Container COMP ui directamente
        ui_comp = op('/project1/Mapa2/ui')
        mapa2 = op('/project1/Mapa2')
        if ui_comp is not None and mapa2 is not None:
            ui_comp.par.x = mapa2.par.Infopx.val
            ui_comp.par.y = mapa2.par.Infopy.val


def onPulse(par):
    name = par.name

    if name == 'Recargardatos':
        _ext().recargarDatos()

    elif name == 'Reiniciarmapa':
        _ext().reiniciarMapa()

    elif name == 'Deselectnow':
        _ext().deselectStation()
