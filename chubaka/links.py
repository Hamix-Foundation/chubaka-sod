import os
import webbrowser


def open_url(url):
    if not url:
        return
    if "LYSYK_ROOT" in os.environ or ("ANDROID_ROOT" in os.environ and "ANDROID_DATA" in os.environ):
        try:
            from lysyk.engine._native import android_open_url
            android_open_url(url)
            return
        except Exception:
            pass
    webbrowser.open(url, new=2)
