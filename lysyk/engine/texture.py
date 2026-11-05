from lysyk.engine._native import Texture

FIT_STRETCH = "stretch"
FIT_CONTAIN = "contain"
FIT_COVER = "cover"


def fit_rect(src_w, src_h, x, y, w, h, fit=FIT_CONTAIN):
    if fit == FIT_STRETCH or src_w <= 0 or src_h <= 0:
        return x, y, w, h, (0.0, 0.0, 1.0, 1.0)
    sx, sy = w / src_w, h / src_h
    if fit == FIT_COVER:
        k = max(sx, sy)
        vw, vh = w / (src_w * k), h / (src_h * k)
        u0, v0 = (1.0 - vw) / 2.0, (1.0 - vh) / 2.0
        return x, y, w, h, (u0, v0, u0 + vw, v0 + vh)
    k = min(sx, sy)
    dw, dh = src_w * k, src_h * k
    return x + (w - dw) / 2.0, y + (h - dh) / 2.0, dw, dh, (0.0, 0.0, 1.0, 1.0)


def draw_image(canvas, tex, x, y, w, h, fit=FIT_STRETCH, tint=None):
    dx, dy, dw, dh, uv = fit_rect(tex.width, tex.height, x, y, w, h, fit)
    canvas.image(tex, dx, dy, dw, dh, tint, uv)


__all__ = ["Texture", "fit_rect", "draw_image", "FIT_STRETCH", "FIT_CONTAIN", "FIT_COVER"]
