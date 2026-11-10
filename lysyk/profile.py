PROFILES = {
    "low": {"detail": 0, "shadow_quality": 0, "shadow_range": 6.0, "particles": 0, "msaa": False, "fps": 30, "grain": 0.0, "scanlines": 0.0},
    "medium": {"detail": 1, "shadow_quality": 1, "shadow_range": 8.0, "particles": 24, "msaa": False, "fps": 60, "grain": 0.04, "scanlines": 0.0},
    "high": {"detail": 2, "shadow_quality": 2, "shadow_range": 9.0, "particles": 48, "msaa": True, "fps": 0, "grain": 0.045, "scanlines": 0.04},
}


def resolve(name, is_mobile):
    if name in PROFILES:
        return name
    return "low" if is_mobile else "high"
