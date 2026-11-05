import os
import webbrowser


def open_url(url):
    if not url:
        return
    if "ANDROID_ROOT" in os.environ:
        try:
            from jnius import autoclass
            ActivityThread = autoclass("android.app.ActivityThread")
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            app = ActivityThread.currentApplication()
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            app.startActivity(intent)
            return
        except Exception:
            pass
    webbrowser.open(url, new=2)
