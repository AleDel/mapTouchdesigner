# panelexec_nav.py
# Navegación del mapa: drag, zoom, click mediante el panel del container Mapa2.
#
# Panel values del containerCOMP:
#   lselect  — botón izquierdo presionado (1) / suelto (0)
#   u, v     — posición normalizada del ratón (u=0 izq, v=0 abajo)
#   wheel    — delta de rueda del ratón (resetea a 0 después de cada tick)
#
# Convención de tile_utils.drag(dx_px, dy_px):
#   dx_px > 0 = ratón fue a la derecha  → mapa se desplaza al oeste
#   dy_px > 0 = ratón fue ABAJO (screen Y = 0 arriba) → mapa se desplaza al norte
#   Como el panel de TD tiene v=0 abajo, hay que negar el eje Y: dy_px = -dv * H

from typing import Any

W_DEFAULT = 1280
H_DEFAULT = 720
CLICK_PX  = 5    # píxeles máximos de movimiento para considerar un click


def _dims():
    """Dimensiones actuales del container en píxeles."""
    c = op('/project1/Mapa2')
    return (c.width or W_DEFAULT), (c.height or H_DEFAULT)

_dragging = False
_last_u   = None   # u propio (no usar prev de TD: puede ser stale tras click)
_last_v   = None   # v propio
_start_u  = None   # posición de inicio del press (para detectar click)
_start_v  = None


def _ext():
    return op('/project1/Mapa2').ext.MapaExt


def onOffToOn(panelValue: PanelValue):
    """Inicio de press izquierdo."""
    global _dragging, _last_u, _last_v, _start_u, _start_v
    if panelValue.name == 'lselect':
        panel     = op('/project1/Mapa2').panel
        _dragging = True
        _last_u   = float(panel.u)
        _last_v   = float(panel.v)
        _start_u  = _last_u
        _start_v  = _last_v


def whileOn(panelValue: PanelValue):
    return


def onOnToOff(panelValue: PanelValue):
    """Fin de press — click o fin de drag."""
    global _dragging, _last_u, _last_v, _start_u, _start_v
    if panelValue.name == 'lselect':
        if _start_u is not None:
            panel = op('/project1/Mapa2').panel
            W, H  = _dims()
            du = abs(float(panel.u) - _start_u) * W
            dv = abs(float(panel.v) - _start_v) * H
            if du < CLICK_PX and dv < CLICK_PX:
                u = float(panel.u)
                v = float(panel.v)
                _ext().onClickScreen(u - 0.5, v - 0.5)
        _dragging = False
        _last_u   = None
        _last_v   = None
        _start_u  = None
        _start_v  = None


def whileOff(panelValue: PanelValue):
    return


def onValueChange(panelValue: PanelValue, prev: Any):
    """Movimiento del ratón (drag) y rueda (zoom)."""
    name = panelValue.name

    if name == 'wheel':
        val = float(panelValue.val)
        # Ignorar el reset a 0 que llega después de cada tick
        if abs(val) > 0.001:
            _ext().onZoom(val * 0.3)

    elif name in ('u', 'v') and _dragging:
        # Manejar movimiento en cualquier dirección: u y v disparan onValueChange
        # por separado. Ambos leen del panel para que el segundo disparo compute
        # delta=0 (los valores ya fueron actualizados por el primero).
        global _last_u, _last_v
        panel   = op('/project1/Mapa2').panel
        curr_u  = float(panel.u)
        curr_v  = float(panel.v)
        du      = curr_u - (_last_u if _last_u is not None else curr_u)
        dv      = curr_v - (_last_v if _last_v is not None else curr_v)
        _last_u = curr_u
        _last_v = curr_v

        W, H  = _dims()
        dx_px = du * W
        dy_px = dv * H

        if abs(dx_px) > 0.1 or abs(dy_px) > 0.1:
            # Negar dy: TD panel v=0 abajo, tile_utils espera screen Y (0=arriba)
            _ext().onDrag(dx_px, -dy_px)
