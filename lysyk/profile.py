PROFILES = {
    "potato": {"detail": -2, "shadow_quality": 0, "shadow_range": 4.0, "particles": 0, "render_scale": 0.25, "ambient_scale": 0.32, "sun_scale": 0.35, "exposure": 0.72, "shadow_strength": 0.4, "tube_intensity": 0.0, "tube_radius": 3.2, "fill_intensity": 0.0, "fog_density": 0.0, "fog_scatter": 0.0, "fps": 30, "grain": 0.0, "scanlines": 0.0},
    "low": {"detail": 0, "shadow_quality": 0, "shadow_range": 6.0, "particles": 0, "render_scale": 0.5, "ambient_scale": 0.55, "sun_scale": 0.6, "exposure": 0.88, "shadow_strength": 0.6, "tube_intensity": 0.38, "tube_radius": 3.8, "fill_intensity": 0.0, "fog_density": 0.004, "fog_scatter": 0.2, "fps": 30, "grain": 0.0, "scanlines": 0.0},
    "medium": {"detail": 1, "shadow_quality": 1, "shadow_range": 8.0, "particles": 24, "render_scale": 0.72, "ambient_scale": 0.78, "sun_scale": 0.82, "exposure": 0.98, "shadow_strength": 0.72, "tube_intensity": 0.62, "tube_radius": 4.5, "fill_intensity": 0.12, "fog_density": 0.01, "fog_scatter": 0.55, "fps": 60, "grain": 0.04, "scanlines": 0.0},
    "high": {"detail": 2, "shadow_quality": 2, "shadow_range": 9.0, "particles": 48, "render_scale": 0.88, "ambient_scale": 1.0, "sun_scale": 1.05, "exposure": 1.06, "shadow_strength": 0.86, "tube_intensity": 0.95, "tube_radius": 5.6, "fill_intensity": 0.22, "fog_density": 0.016, "fog_scatter": 0.82, "fps": 0, "grain": 0.045, "scanlines": 0.04},
    "ultra": {"detail": 3, "shadow_quality": 3, "shadow_range": 10.0, "particles": 96, "render_scale": 1.0, "ambient_scale": 1.28, "sun_scale": 1.3, "exposure": 1.16, "shadow_strength": 0.98, "tube_intensity": 1.5, "tube_radius": 7.0, "fill_intensity": 0.36, "fog_density": 0.025, "fog_scatter": 1.0, "fps": 30, "grain": 0.065, "scanlines": 0.05},
}


def resolve(name, is_mobile):
    if name in PROFILES:
        return name
    return "low" if is_mobile else "medium"


def quality_profile(name, is_mobile=False):
    profile = dict(PROFILES[resolve(name, is_mobile)])
    if is_mobile and name == "ultra":
        profile["shadow_quality"] = 2
        profile["particles"] = 48
    return profile


def frame_limit(name, is_mobile, configured=0):
    if configured > 0:
        return configured
    if is_mobile:
        return PROFILES[resolve(name, True)]["fps"]
    return 60 if name == "auto" else 0
