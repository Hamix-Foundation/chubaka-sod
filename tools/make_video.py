import argparse
import os
import struct
import subprocess
import sys

MAGIC = b"LYV1"


def split_jpegs(blob):
    marks = []
    i = blob.find(b"\xff\xd8")
    while i != -1:
        marks.append(i)
        i = blob.find(b"\xff\xd8", i + 2)
    marks.append(len(blob))
    return [blob[marks[k]:marks[k + 1]] for k in range(len(marks) - 1)]


def frame_times(src):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0", src],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    times = []
    for t in out:
        try:
            times.append(float(t.split(",")[0]))
        except ValueError:
            pass
    return times


def has_audio(src):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", src],
        capture_output=True, text=True,
    ).stdout
    return "audio" in out


def convert(src, dst, quality=8, max_width=0):
    scale = ["-vf", f"scale='min({max_width},iw)':-2"] if max_width else []
    jpgs = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", src, "-an", *scale, "-c:v", "mjpeg", "-q:v", str(quality), "-pix_fmt", "yuvj420p", "-fps_mode", "passthrough", "-f", "image2pipe", "-"],
        check=True, capture_output=True,
    ).stdout
    frames = split_jpegs(jpgs)
    times = frame_times(src)
    n = min(len(frames), len(times)) if times else len(frames)
    frames = frames[:n]
    if times:
        base = times[0]
        times = [max(0.0, t - base) for t in times[:n]]
    else:
        times = [k / 25.0 for k in range(n)]
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", dst if False else src],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    w, h = (int(v) for v in probe.split("x"))
    if max_width and w > max_width:
        h = int(round(h * max_width / w / 2.0)) * 2
        w = max_width
    span = times[-1] if n > 1 else 1.0
    fps = (n - 1) / span if n > 1 and span > 0 else 25.0
    header = MAGIC + struct.pack("<IIIfI", w, h, n, fps, 0)
    offset = len(header) + n * 16
    table = bytearray()
    for f, t in zip(frames, times):
        table += struct.pack("<QII", offset, len(f), int(round(t * 1000)))
        offset += len(f)
    with open(dst, "wb") as fh:
        fh.write(header)
        fh.write(table)
        for f in frames:
            fh.write(f)
    if has_audio(src):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-c:a", "libvorbis", "-q:a", "4", os.path.splitext(dst)[0] + ".ogg"],
            check=True,
        )
    return w, h, n, fps


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert a video into the Lysyk .lyv format")
    ap.add_argument("source")
    ap.add_argument("output")
    ap.add_argument("--quality", type=int, default=8)
    ap.add_argument("--max-width", type=int, default=0)
    a = ap.parse_args(argv)
    w, h, n, fps = convert(a.source, a.output, a.quality, a.max_width)
    print(f"{a.output}: {w}x{h}, {n} frames, {fps:.2f} fps, {os.path.getsize(a.output) / 1e6:.1f} MB")


if __name__ == "__main__":
    sys.exit(main())
