import hashlib
import hmac
import json
import os

MAGIC = b"LSV1"


def _keystream(key, nonce, n):
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hashlib.sha256(key + nonce + counter.to_bytes(8, "little")).digest()
        counter += 1
    return bytes(out[:n])


class SaveFile:
    def __init__(self, path, password):
        self.path = path
        self.key = hashlib.sha256(password.encode("utf-8")).digest()

    def exists(self):
        return os.path.isfile(self.path)

    def write(self, data):
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(16)
        body = bytes(a ^ b for a, b in zip(raw, _keystream(self.key, nonce, len(raw))))
        tag = hmac.new(self.key, nonce + body, hashlib.sha256).digest()
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(MAGIC + nonce + tag + body)
        os.replace(tmp, self.path)

    def read(self, default=None):
        try:
            with open(self.path, "rb") as f:
                blob = f.read()
            if blob[:4] != MAGIC or len(blob) < 52:
                return default
            nonce, tag, body = blob[4:20], blob[20:52], blob[52:]
            if not hmac.compare_digest(tag, hmac.new(self.key, nonce + body, hashlib.sha256).digest()):
                return default
            raw = bytes(a ^ b for a, b in zip(body, _keystream(self.key, nonce, len(body))))
            return json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            return default

    def delete(self):
        try:
            os.remove(self.path)
        except OSError:
            pass
