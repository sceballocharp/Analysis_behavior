"""Configurable port-to-port connections for the existing canvas rectangles."""
import math
from matplotlib.colors import is_color_like
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from matplotlib.path import Path


def draw_connections(ax, preferences):
    # Redrawing must not accumulate lines or accidentally treat ports as buttons.
    for artist in list(ax.patches):
        if artist.get_gid() == '_canvas_connection':
            artist.remove()
    config = preferences.get('canvas_connections', {})
    if not isinstance(config, dict) or not config.get('enabled', True):
        return
    # Keep legacy flat edges readable; grouped lists mirror the GUI's tabs.
    legacy_edges = config.get('edges', [])
    edges = list(legacy_edges) if isinstance(legacy_edges, list) else []
    tabs = config.get('tabs', {})
    if isinstance(tabs, dict):
        for subtabs in tabs.values():
            if not isinstance(subtabs, dict):
                continue
            for connections in subtabs.values():
                if isinstance(connections, list):
                    edges.extend(connections)
    buttons = {patch.get_gid(): patch for patch in ax.patches
               if isinstance(patch, Rectangle) and patch.get_gid()}
    ports = set()

    def number(value, default, minimum=0):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= minimum:
            return value
        return default

    def port(button, side):
        x, y = button.get_xy()
        w, h = button.get_width(), button.get_height()
        return {'left': (x, y+h/2), 'right': (x+w, y+h/2),
                'top': (x+w/2, y), 'bottom': (x+w/2, y+h)}[side]

    for edge in edges:
        if not isinstance(edge, dict) or not edge.get('enabled', True):
            continue
        source = buttons.get(edge.get('from'))
        target = buttons.get(edge.get('to'))
        if source is None or target is None or source is target:
            continue
        sx, sy = source.get_xy(); tx, ty = target.get_xy()
        if abs(tx-sx) >= abs(ty-sy):
            auto_from, auto_to = ('right', 'left') if tx >= sx else ('left', 'right')
        else:
            auto_from, auto_to = ('bottom', 'top') if ty >= sy else ('top', 'bottom')
        start_side = edge.get('from_port', auto_from)
        end_side = edge.get('to_port', auto_to)
        if start_side not in ('left', 'right', 'top', 'bottom'):
            start_side = auto_from
        if end_side not in ('left', 'right', 'top', 'bottom'):
            end_side = auto_to
        start, end = port(source, start_side), port(target, end_side)
        offsets = {'left': (-1, 0), 'right': (1, 0), 'top': (0, -1), 'bottom': (0, 1)}
        gap = number(edge.get('port_offset_px', config.get('port_offset_px')), 10)
        dx, dy = offsets[start_side]; ex, ey = offsets[end_side]
        a = (start[0]+dx*gap, start[1]+dy*gap)
        b = (end[0]+ex*gap, end[1]+ey*gap)
        waypoints = edge.get('via')
        if isinstance(waypoints, list) and all(isinstance(p, list) and len(p)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in p) for p in waypoints):
            middle = [tuple(p) for p in waypoints]
        elif start_side in ('left', 'right') and end_side in ('left', 'right'):
            mid = (a[0]+b[0])/2
            middle = [(mid,a[1]), (mid,b[1])]
        else:
            mid = (a[1]+b[1])/2
            middle = [(a[0],mid), (b[0],mid)]
        points = [start,a,*middle,b,end]
        color = edge.get('color', config.get('color', '#8A9BAE'))
        if not is_color_like(color):
            color = '#8A9BAE'
        width = number(edge.get('width', config.get('width')), 1.4, .1)
        transform = source.get_data_transform()
        line = FancyArrowPatch(path=Path(points, [Path.MOVETO]+[Path.LINETO]*(len(points)-1)),
                               arrowstyle='-|>' if edge.get('arrow', config.get('arrow', True)) else '-',
                               mutation_scale=9, linewidth=width, color=color,
                               transform=transform, zorder=.5, picker=False)
        line.set_gid('_canvas_connection')
        ax.add_patch(line)
        if config.get('show_ports', True):
            for button, side, point in ((source,start_side,start),(target,end_side,end)):
                identity = (button.get_gid(),side)
                if identity in ports:
                    continue
                ports.add(identity)
                dot=Circle(point,radius=number(config.get('port_radius_px'),3),
                           facecolor=config.get('port_color',color) if is_color_like(config.get('port_color',color)) else color,
                           edgecolor='white',linewidth=.6,transform=transform,zorder=2,picker=False)
                dot.set_gid('_canvas_connection')
                ax.add_patch(dot)
