"""
Run once to generate the PNG icons for the Lens extension.
Uses only Python stdlib — no external dependencies needed.

Usage:
    python create_icons.py
"""
import struct, zlib, os, math

def make_png(size, color_bg=(79,70,229), color_ring=(129,140,248)):
    """Create a lens icon PNG using pure Python."""
    w, h = size, size
    cx, cy = w / 2, h / 2
    r_outer = w * 0.38
    r_inner = w * 0.18
    line_w  = max(1, w * 0.09)

    def pixel(x, y):
        dx, dy = x - cx, y - cy
        dist = math.sqrt(dx*dx + dy*dy)
        # Ring
        if r_outer - line_w <= dist <= r_outer:
            return color_ring + (255,)
        # Inner fill
        if dist <= r_inner:
            return color_bg + (200,)
        # Handle line (bottom-right)
        hx1, hy1 = cx + r_outer * 0.7, cy + r_outer * 0.7
        hx2, hy2 = cx + r_outer * 1.35, cy + r_outer * 1.35
        # Distance from point to line segment
        llen = math.sqrt((hx2-hx1)**2 + (hy2-hy1)**2)
        t = max(0, min(1, ((x-hx1)*(hx2-hx1) + (y-hy1)*(hy2-hy1)) / (llen*llen)))
        nearest_x = hx1 + t*(hx2-hx1)
        nearest_y = hy1 + t*(hy2-hy1)
        d_line = math.sqrt((x-nearest_x)**2 + (y-nearest_y)**2)
        if d_line <= line_w * 0.6:
            return color_ring + (255,)
        return (15, 15, 26, 255)

    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter none
        for x in range(w):
            r, g, b, a = pixel(x, y)
            raw += bytes([r, g, b, a])

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)  # RGBA
    idat = zlib.compress(bytes(raw))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', idat)
            + chunk(b'IEND', b''))

os.makedirs(os.path.dirname(__file__) or '.', exist_ok=True)

for size in [16, 48, 128]:
    data = make_png(size)
    path = os.path.join(os.path.dirname(__file__), f'icon{size}.png')
    with open(path, 'wb') as f:
        f.write(data)
    print(f'Created {path} ({len(data)} bytes)')

print('Done. Icons created.')
