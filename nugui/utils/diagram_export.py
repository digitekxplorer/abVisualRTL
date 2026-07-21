"""FIX 5.1 (rev 2): pure-Pillow diagram renderer — no Ghostscript needed.

Draws the FSM from the data model (nodes + lines) directly with
ImageDraw, mirroring the canvas geometry math, then saves PNG or PDF.
"""
import math
from PIL import Image, ImageDraw, ImageFont

from nugui.utils.constants import BUBBLE_RADIUS

# Colors matched to the canvas
COL_STATE_FILL = "#e8f0fe"
COL_STATE_OUTLINE = "#1a56db"
COL_LINE = "#333333"
COL_TEXT = "#000000"
COL_DETAIL = "#0000ff"
COL_BG = "#ffffff"

SCALE = 3          # Supersample factor for crisp output
MARGIN = 40        # Logic-unit margin around the diagram


def _font(size):
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _quad_bezier(p0, cp, p1, steps=40):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt * mt * p0[0] + 2 * mt * t * cp[0] + t * t * p1[0]
        y = mt * mt * p0[1] + 2 * mt * t * cp[1] + t * t * p1[1]
        pts.append((x, y))
    return pts


def _cubic_bezier(p0, c1, c2, p1, steps=48):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt ** 3 * p0[0] + 3 * mt * mt * t * c1[0]
             + 3 * mt * t * t * c2[0] + t ** 3 * p1[0])
        y = (mt ** 3 * p0[1] + 3 * mt * mt * t * c1[1]
             + 3 * mt * t * t * c2[1] + t ** 3 * p1[1])
        pts.append((x, y))
    return pts


def _arrowhead(draw, tip, prev, size, color):
    """Filled triangle arrowhead at `tip`, pointing away from `prev`."""
    ang = math.atan2(tip[1] - prev[1], tip[0] - prev[0])
    spread = math.radians(25)
    a = (tip[0] - size * math.cos(ang - spread), tip[1] - size * math.sin(ang - spread))
    b = (tip[0] - size * math.cos(ang + spread), tip[1] - size * math.sin(ang + spread))
    draw.polygon([tip, a, b], fill=color)


def _arc_control_point(n1, n2, curvature):
    mid = ((n1[0] + n2[0]) / 2, (n1[1] + n2[1]) / 2)
    dx, dy = n2[0] - n1[0], n2[1] - n1[1]
    dist = math.hypot(dx, dy)
    if dist == 0:
        return mid
    return (mid[0] + (-dy / dist) * curvature, mid[1] + (dx / dist) * curvature)


def _edge_point(center, toward, r):
    dx, dy = toward[0] - center[0], toward[1] - center[1]
    dist = math.hypot(dx, dy)
    if dist == 0:
        return center
    return (center[0] + dx / dist * r, center[1] + dy / dist * r)


def render_diagram(nodes: dict, lines: list, show_details: bool = True) -> Image.Image:
    """Renders the FSM to a PIL Image (RGB, white background)."""
    if not nodes:
        raise ValueError("No states to export.")

    # Bounding box in logic coordinates (include loop extents roughly)
    xs = [n.x for n in nodes.values()]
    ys = [n.y for n in nodes.values()]
    pad = BUBBLE_RADIUS + 80 + MARGIN
    x0, y0 = min(xs) - pad, min(ys) - pad
    x1, y1 = max(xs) + pad, max(ys) + pad

    w = int((x1 - x0) * SCALE)
    h = int((y1 - y0) * SCALE)
    img = Image.new("RGB", (w, h), COL_BG)
    draw = ImageDraw.Draw(img)

    def T(x, y):  # logic -> image coords
        return ((x - x0) * SCALE, (y - y0) * SCALE)

    r = BUBBLE_RADIUS * SCALE
    lw = max(2, 2 * SCALE)
    font_name = _font(10 * SCALE)
    font_small = _font(8 * SCALE)
    arrow_size = 10 * SCALE

    # --- Transitions first (under the states' labels but arrows visible) ---
    for line in lines:
        n1 = nodes[line.start_state_id]
        n2 = nodes[line.end_state_id]

        if line.start_state_id == line.end_state_id:
            # Self-loop: cubic bezier, same geometry as the canvas
            c = T(n1.x, n1.y)
            ls = line.curvature * SCALE
            spread = math.radians(40)
            exit_a = line.loop_angle - spread
            entry_a = line.loop_angle + spread
            p0 = (c[0] + math.cos(exit_a) * r, c[1] + math.sin(exit_a) * r)
            p3 = (c[0] + math.cos(entry_a) * r, c[1] + math.sin(entry_a) * r)
            c1 = (c[0] + math.cos(exit_a) * (r + ls), c[1] + math.sin(exit_a) * (r + ls))
            c2 = (c[0] + math.cos(entry_a) * (r + ls), c[1] + math.sin(entry_a) * (r + ls))
            pts = _cubic_bezier(p0, c1, c2, p3)
            hx = c[0] + math.cos(line.loop_angle) * (r + ls)
            hy = c[1] + math.sin(line.loop_angle) * (r + ls)
        else:
            a, b = T(n1.x, n1.y), T(n2.x, n2.y)
            cp = _arc_control_point(a, b, line.curvature * SCALE)
            p0 = _edge_point(a, cp, r)
            p1 = _edge_point(b, cp, r)
            pts = _quad_bezier(p0, cp, p1)
            hx, hy = cp

        draw.line(pts, fill=COL_LINE, width=lw, joint="curve")
        _arrowhead(draw, pts[-1], pts[-3], arrow_size, COL_LINE)

        if show_details:
            label = f"[{line.condition}]"
            if line.action:
                label += f" / {line.action}"
            tx = hx + line.text_offset_x * SCALE
            ty = hy + line.text_offset_y * SCALE
            draw.text((tx, ty), label, fill=COL_DETAIL, font=font_small, anchor="mm")

    # --- States ---
    for node in nodes.values():
        cx, cy = T(node.x, node.y)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=COL_STATE_FILL, outline=COL_STATE_OUTLINE, width=lw)
        if node.is_reset_state:  # double circle marks the reset state
            r2 = r - 4 * SCALE
            draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
                         outline=COL_STATE_OUTLINE, width=max(1, SCALE))
        draw.text((cx + node.name_offset_x * SCALE, cy + node.name_offset_y * SCALE),
                  node.name, fill=COL_TEXT, font=font_name, anchor="mm")
        if show_details and node.actions:
            draw.text((cx + node.details_offset_x * SCALE, cy + node.details_offset_y * SCALE),
                      "\n".join(node.actions), fill=COL_DETAIL, font=font_small)

    return img


def export_diagram(file_path: str, nodes: dict, lines: list, show_details: bool = True):
    """Renders and saves as PNG or PDF based on the file extension."""
    img = render_diagram(nodes, lines, show_details)
    if file_path.lower().endswith(".pdf"):
        img.save(file_path, "PDF", resolution=72.0 * SCALE)
    else:
        img.save(file_path, "PNG")
