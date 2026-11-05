import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "chubaka", "assets", "game", "textures")
Image.MAX_IMAGE_PIXELS = None
PREVIEW = 2400.0 / 1568.0


def photo(name):
    return Image.open(os.path.join(os.environ.get("PHOTOS", "photos"), f"IMG_{name}.jpeg"))


def pano_crop(name, x0, y0, x1, y1):
    im = photo(name)
    s = im.size[0] / 2400.0 * PREVIEW
    return im.crop((int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s)))


def arr(im):
    return np.asarray(im.convert("RGB"), dtype=np.float32)


def fit(a, size):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return arr(im.resize((size, size), Image.LANCZOS))


def tileable(a):
    h, w = a.shape[:2]
    wy = np.abs(np.linspace(-1.0, 1.0, h))[:, None, None]
    wx = np.abs(np.linspace(-1.0, 1.0, w))[None, :, None]
    mask = np.clip(np.maximum(wx, wy) * 1.1, 0.0, 1.0) ** 1.5
    shifted = np.roll(np.roll(a, h // 2, axis=0), w // 2, axis=1)
    return a * (1.0 - mask) + shifted * mask


def noise(rng, size, octaves=4, base=4):
    out = np.zeros((size, size), dtype=np.float32)
    amp = 1.0
    total = 0.0
    for o in range(octaves):
        n = base * (2 ** o)
        g = rng.random((n, n)).astype(np.float32)
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
        out += np.asarray(im, dtype=np.float32) / 255.0 * amp
        total += amp
        amp *= 0.5
    return out / total


def tint(base, n, strength):
    return base[None, None, :] * (1.0 + (n[..., None] - 0.5) * strength)


def mean_color(a):
    return a.reshape(-1, 3).mean(axis=0)


def save(name, a):
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(os.path.join(OUT, name + ".png"), optimize=True)


def stains(rng, size, strength):
    n = noise(rng, size, 5, 3)
    s = np.clip((n - 0.55) * 4.0, 0.0, 1.0)
    return 1.0 - s * strength


def plaster(rng, size, base, grime):
    n = noise(rng, size, 5, 6)
    fine = rng.random((size, size)).astype(np.float32)
    a = tint(np.array(base, dtype=np.float32), n, 0.16)
    a *= (1.0 + (fine[..., None] - 0.5) * 0.07)
    a *= stains(rng, size, grime)[..., None]
    return a


def make_plaster(rng):
    base = np.array([150, 204, 188], dtype=np.float32)
    a = plaster(rng, 256, base, 0.35)
    mold = np.clip((noise(rng, 256, 5, 4) - 0.62) * 5.0, 0.0, 1.0)[..., None]
    a = a * (1.0 - mold * 0.55) + np.array([52, 70, 58], dtype=np.float32) * mold * 0.55
    peel = np.clip((noise(rng, 256, 4, 5) - 0.7) * 8.0, 0.0, 1.0)[..., None]
    a = a * (1.0 - peel * 0.45) + np.array([138, 130, 108], dtype=np.float32) * peel * 0.45
    save("plaster", tileable(a))
    b = plaster(rng, 256, base * 0.7, 0.5)
    save("plaster_dark", tileable(b))


def make_wood(rng):
    ref = arr(pano_crop("1299", 10, 150, 320, 350))
    ref = ref[40:-10, 130:-80]
    a = fit(ref, 256)
    lum = a.mean(axis=2, keepdims=True)
    a = a * 0.7 + lum * 0.3
    save("wood_panel", tileable(a * 0.95))
    dark = a * np.array([0.62, 0.58, 0.55], dtype=np.float32)
    save("wood_dark", tileable(dark))


def make_parquet(rng):
    ref = arr(pano_crop("1300", 470, 255, 760, 365))
    base = mean_color(ref[20:-10])
    size = 512
    a = np.zeros((size, size, 3), dtype=np.float32)
    plank_w = size // 8
    for i in range(8):
        y0 = i * plank_w
        x = -int(rng.integers(0, size // 2))
        while x < size:
            length = int(rng.integers(size // 3, size // 2 + size // 6))
            tone = 0.72 + rng.random() * 0.5
            col = base * tone * np.array([1.0, 0.97 + rng.random() * 0.06, 0.95 + rng.random() * 0.08], dtype=np.float32)
            grain = noise(rng, size, 3, 24)[y0:y0 + plank_w, :]
            streak = np.repeat(rng.random((plank_w, 1)).astype(np.float32), size, axis=1) * 0.5 + grain * 0.5
            patch = col[None, None, :] * (0.88 + streak[..., None] * 0.28)
            xs = max(x, 0)
            xe = min(x + length, size)
            if xe > xs:
                a[y0:y0 + plank_w - 2, xs:xe] = patch[:plank_w - 2, xs:xe]
                a[y0 + plank_w - 2:y0 + plank_w, xs:xe] = col * 0.35
                a[y0:y0 + plank_w, xs:xs + 2] = col * 0.3
            x += length
    wear = stains(rng, size, 0.35)[..., None]
    a = a * wear
    save("parquet", tileable(a))


def make_door(rng):
    base = np.array([202, 200, 190], dtype=np.float32)
    size = 256
    n = noise(rng, size, 4, 6)
    a = tint(base, n, 0.14)
    a *= (1.0 + (rng.random((size, size, 1)).astype(np.float32) - 0.5) * 0.06)
    a *= stains(rng, size, 0.3)[..., None]
    for _ in range(14):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        l = int(rng.integers(12, 60))
        a[y:y + 2, x:x + l] *= 0.78
    save("door_paint", tileable(a))


def make_board(rng):
    ref = arr(pano_crop("1299", 360, 40, 440, 300))
    ref = ref[:int(ref.shape[0] * 0.6), :]
    base = mean_color(ref)
    base = np.clip(base * np.array([0.85, 1.05, 1.0], dtype=np.float32), 0, 255)
    size = 256
    n = noise(rng, size, 4, 5)
    a = tint(base, n, 0.2)
    dust = np.clip((noise(rng, size, 5, 8) - 0.5) * 2.2, 0.0, 1.0)[..., None]
    a = a * (1.0 - dust * 0.25) + np.array([120, 132, 124], dtype=np.float32) * dust * 0.25
    save("chalkboard", tileable(a))


def make_desk(rng):
    size = 256
    base = np.array([186, 160, 118], dtype=np.float32)
    n = noise(rng, size, 4, 8)
    a = tint(base, n, 0.12)
    a *= (1.0 + (rng.random((size, 1, 1)).astype(np.float32) - 0.5) * 0.06)
    a *= stains(rng, size, 0.25)[..., None]
    save("desk_top", tileable(a))
    metal = np.full((128, 128, 3), 30, dtype=np.float32) * (1.0 + (noise(rng, 128, 3, 8)[..., None] - 0.5) * 0.5)
    save("metal_black", tileable(metal))
    ply = np.array([160, 118, 72], dtype=np.float32)
    n2 = noise(rng, size, 4, 6)
    p = tint(ply, n2, 0.22) * stains(rng, size, 0.25)[..., None]
    save("plywood", tileable(p))
    wd = tint(np.array([92, 66, 44], dtype=np.float32), noise(rng, size, 4, 7), 0.25)
    save("wood_old", tileable(wd))


def make_cabinet(rng):
    size = 128
    red = np.array([150, 34, 44], dtype=np.float32)
    yellow = np.array([214, 172, 52], dtype=np.float32)
    for name, col in (("cabinet_red", red), ("cabinet_yellow", yellow)):
        a = tint(col, noise(rng, size, 4, 6), 0.18) * stains(rng, size, 0.3)[..., None]
        save(name, tileable(a))


def make_ceiling(rng):
    a = plaster(rng, 256, (176, 178, 170), 0.55)
    mold = np.clip((noise(rng, 256, 5, 3) - 0.6) * 5.0, 0.0, 1.0)[..., None]
    a = a * (1.0 - mold * 0.5) + np.array([64, 70, 58], dtype=np.float32) * mold * 0.5
    save("ceiling", tileable(a))


def make_corridor(rng):
    size = 256
    floor = np.full((size, size, 3), 52, dtype=np.float32)
    n = noise(rng, size, 4, 6)
    floor = floor * (0.8 + n[..., None] * 0.5)
    for _ in range(1400):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        c = float(rng.choice((24, 96, 130, 160)))
        floor[y:y + 2, x:x + 2] = c
    floor *= stains(rng, size, 0.25)[..., None]
    save("terrazzo", tileable(floor))
    green = plaster(rng, size, (118, 168, 134), 0.45)
    save("corridor_green", tileable(green))
    cream = plaster(rng, size, (190, 190, 166), 0.5)
    save("corridor_cream", tileable(cream))
    wooddoor = tint(np.array([120, 78, 46], dtype=np.float32), noise(rng, size, 4, 10), 0.3)
    save("corridor_wood", tileable(wooddoor))
    lamp = tint(np.array([226, 168, 104], dtype=np.float32), noise(rng, 64, 3, 4), 0.3)
    save("lamp_shade", lamp)


def make_curtain(rng):
    size = 128
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    lace = 0.5 + 0.5 * np.sin(xs * 0.5) * np.sin(ys * 0.5)
    base = np.array([196, 192, 182], dtype=np.float32)
    a = base[None, None, :] * (0.7 + 0.3 * lace[..., None])
    a *= stains(rng, size, 0.4)[..., None]
    save("lace", tileable(a))
    g = tint(np.array([128, 122, 112], dtype=np.float32), noise(rng, size, 3, 4), 0.2)
    folds = 0.82 + 0.18 * np.sin(xs * 0.35)
    save("curtain_grey", tileable(g * folds[..., None]))


def make_plastic(rng):
    size = 64
    a = np.full((size, size, 3), (176, 172, 160), dtype=np.float32) * (1.0 + (noise(rng, size, 3, 4)[..., None] - 0.5) * 0.15)
    save("plastic_white", tileable(a))
    r = np.full((size, size, 3), (160, 156, 148), dtype=np.float32) * (1.0 + (noise(rng, size, 3, 4)[..., None] - 0.5) * 0.2)
    save("radiator", tileable(r))


def make_misc(rng):
    size = 128
    save("paper", tileable(tint(np.array([196, 190, 172], dtype=np.float32), noise(rng, size, 3, 4), 0.15)))
    save("brick", tileable(tint(np.array([120, 74, 58], dtype=np.float32), noise(rng, size, 4, 8), 0.4)))
    save("rubble", tileable(tint(np.array([150, 144, 128], dtype=np.float32), noise(rng, size, 4, 8), 0.45)))
    save("cloth_dark", tileable(tint(np.array([38, 40, 44], dtype=np.float32), noise(rng, size, 3, 6), 0.35)))
    save("book_blue", tileable(tint(np.array([60, 100, 150], dtype=np.float32), noise(rng, size, 3, 4), 0.25)))
    save("leather", tileable(tint(np.array([32, 30, 32], dtype=np.float32), noise(rng, size, 3, 4), 0.2)))
    save("pumpkin", tileable(tint(np.array([214, 110, 30], dtype=np.float32), noise(rng, size, 3, 4), 0.25)))
    save("leaf_brown", tileable(tint(np.array([150, 82, 38], dtype=np.float32), noise(rng, size, 4, 8), 0.5)))
    save("glass", np.full((16, 16, 3), (150, 184, 196), dtype=np.float32))
    save("cardboard", tileable(tint(np.array([164, 128, 84], dtype=np.float32), noise(rng, size, 3, 5), 0.3)))


def make_yard(rng):
    size = 256
    grass = tint(np.array([96, 122, 58], dtype=np.float32), noise(rng, size, 5, 8), 0.55)
    dirt = np.clip((noise(rng, size, 4, 4) - 0.55) * 4.0, 0.0, 1.0)[..., None]
    grass = grass * (1.0 - dirt * 0.6) + np.array([112, 94, 66], dtype=np.float32) * dirt * 0.6
    save("grass", tileable(grass))
    n = noise(rng, size, 5, 10)[..., None]
    bush = np.array([176, 138, 44], dtype=np.float32) * (0.55 + n * 0.9)
    leaf = np.clip((noise(rng, size, 4, 6) - 0.5) * 3.0, 0.0, 1.0)[..., None]
    bush = bush * (1.0 - leaf * 0.5) + np.array([70, 88, 40], dtype=np.float32) * leaf * 0.5
    save("bush", tileable(bush))
    wall = tint(np.array([186, 170, 148], dtype=np.float32), noise(rng, size, 4, 6), 0.25) * stains(rng, size, 0.4)[..., None]
    save("yard_wall", tileable(wall))
    roof = tint(np.array([148, 64, 48], dtype=np.float32), noise(rng, size, 4, 12), 0.35)
    save("roof", tileable(roof))
    block = tint(np.array([150, 148, 140], dtype=np.float32), noise(rng, size, 4, 6), 0.22)
    save("concrete", tileable(block))
    bark = tint(np.array([58, 46, 38], dtype=np.float32), noise(rng, size, 4, 14), 0.5)
    save("bark", tileable(bark))
    gravel = tint(np.array([120, 112, 100], dtype=np.float32), noise(rng, size, 5, 14), 0.5)
    save("gravel", tileable(gravel))


def make_view(rng):
    from PIL import ImageDraw
    size = 256
    soil = tint(np.array([66, 52, 40], dtype=np.float32), noise(rng, size, 5, 8), 0.5)
    clods = np.clip((noise(rng, size, 4, 12) - 0.55) * 4.0, 0.0, 1.0)[..., None]
    soil = soil * (1.0 - clods * 0.35) + np.array([96, 82, 62], dtype=np.float32) * clods * 0.35
    save("soil", tileable(soil))
    wing = tint(np.array([166, 164, 156], dtype=np.float32), noise(rng, size, 4, 6), 0.2) * stains(rng, size, 0.45)[..., None]
    save("wing_wall", tileable(wing))
    stucco = tint(np.array([196, 182, 150], dtype=np.float32), noise(rng, size, 4, 6), 0.22)
    peel = np.clip((noise(rng, size, 4, 4) - 0.58) * 5.0, 0.0, 1.0)[..., None]
    stucco = stucco * (1.0 - peel * 0.7) + np.array([206, 128, 92], dtype=np.float32) * peel * 0.7
    save("stucco_peel", tileable(stucco * stains(rng, size, 0.3)[..., None]))
    ruin = tint(np.array([214, 168, 140], dtype=np.float32), noise(rng, size, 4, 6), 0.2) * stains(rng, size, 0.4)[..., None]
    img = Image.fromarray(np.clip(ruin, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for _ in range(26):
        x = int(rng.integers(0, size))
        y = int(rng.integers(120, size))
        col = [(60, 110, 200), (232, 140, 60), (230, 230, 240), (90, 60, 140)][int(rng.integers(0, 4))]
        for _ in range(int(rng.integers(3, 7))):
            nx = x + int(rng.integers(-14, 15))
            ny = y + int(rng.integers(-10, 11))
            d.line((x, y, nx, ny), fill=col, width=int(rng.integers(2, 5)))
            x, y = nx, ny
    save("graffiti", np.asarray(img, dtype=np.float32))
    panel = tint(np.array([204, 200, 188], dtype=np.float32), noise(rng, size, 4, 5), 0.14) * stains(rng, size, 0.3)[..., None]
    panel[::64, :] *= 0.8
    panel[:, ::64] *= 0.8
    save("panel_wall", tileable(panel))
    w, h = 192, 128
    sea = np.zeros((h, w, 3), dtype=np.float32)
    sea[:] = (78, 118, 170)
    sea *= (0.92 + noise(rng, w, 3, 6)[:h, :w, None] * 0.16)
    im = Image.fromarray(np.clip(sea, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    lands = [(18, 24, 70, 70), (60, 66, 92, 118), (96, 18, 160, 64), (110, 54, 150, 96), (150, 82, 178, 108), (6, 80, 40, 112)]
    cols = [(120, 168, 96), (206, 176, 86), (196, 128, 84), (150, 176, 100), (214, 196, 110), (176, 150, 110)]
    for (x0, y0, x1, y1), col in zip(lands, cols):
        d.ellipse((x0, y0, x1, y1), fill=col)
    save("worldmap", np.asarray(im, dtype=np.float32))
    pw, ph = 64, 96
    por = np.full((ph, pw, 3), (112, 70, 40), dtype=np.float32)
    im = Image.fromarray(por.astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.ellipse((20, 14, 44, 44), fill=(214, 170, 120))
    d.rectangle((8, 58, 56, 96), fill=(34, 26, 22))
    d.polygon([(24, 40), (40, 40), (46, 60), (18, 60)], fill=(30, 24, 20))
    d.rectangle((20, 8, 44, 20), fill=(48, 34, 26))
    save("portrait", np.asarray(im, dtype=np.float32))


def main():
    rng = np.random.default_rng(1307)
    for fn in (make_plaster, make_wood, make_parquet, make_door, make_board, make_desk, make_cabinet, make_ceiling, make_corridor, make_curtain, make_plastic, make_misc, make_yard):
        fn(rng)
    print(sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
