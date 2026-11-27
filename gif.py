#!/usr/bin/env python3
"""Render an animated Agent Field Notes edition (issues/NNN-slug/spec.json) into a looping GIF.

  python3 gif.py issues/001-the-refresh-test            # -> dist/agent-field-notes-001.gif + cover.png + scene stills

The animation lives in template/anim.{html,css,js}; frames are captured one by one at fixed
instants (AFN.seek), so every render is identical. Encoding uses one global palette with ordered
dithering, which keeps static areas byte-identical between frames and the file under 8 MB.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "template" / "anim.html"
W, H = 1080, 1350
MAX_BYTES = 7_900_000  # LinkedIn images via Zernio: 8 MB
MAX_FRAMES = 250        # LinkedIn's image API limit for GIFs (the web UI allows 500)
# Tried in order until the file fits: (fps, colours, bayer scale)
ENCODINGS = [(12.5, 256, 3), (10, 256, 3), (10, 224, 4), (25 / 3, 224, 4), (25 / 3, 160, 5)]


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg  # pip wheel with a static ffmpeg, used on GitHub runners

    return imageio_ffmpeg.get_ffmpeg_exe()


def capture(spec, frames_dir, fps):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto(TEMPLATE.as_uri())
        info = page.evaluate("spec => AFN.build(spec)", spec)
        problems = page.evaluate("info => AFN.audit(info)", info)
        stills = {}
        for sc in info["scenes"]:
            page.evaluate(f"AFN.seek({sc['settled']})")
            stills[sc["id"]] = page.screenshot(clip={"x": 0, "y": 0, "width": W, "height": H})
        count = int(info["total"] / 1000 * fps)
        for i in range(count):
            page.evaluate(f"AFN.seek({i * 1000 / fps})")
            page.screenshot(path=str(frames_dir / f"f{i:04d}.png"), clip={"x": 0, "y": 0, "width": W, "height": H})
        browser.close()
    return info, problems, stills, count


def encode(frames_dir, out, fps, colors, bayer):
    """Identical consecutive frames become one frame with a longer delay (static holds cost nothing)."""
    runs, prev = [], None
    for f in sorted(frames_dir.glob("f*.png")):
        digest = hashlib.md5(f.read_bytes()).digest()
        if digest == prev:
            runs[-1][1] += 1
        else:
            runs.append([f.name, 1])
            prev = digest
    listing = frames_dir / "frames.txt"
    listing.write_text("".join(f"file '{name}'\nduration {k / fps:.4f}\n" for name, k in runs) + f"file '{runs[-1][0]}'\n")
    graph = (f"[0:v]split[a][b];[a]palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=0[p];"
             f"[b][p]paletteuse=dither=bayer:bayer_scale={bayer}:diff_mode=rectangle")
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-fps_mode", "vfr",
                    "-filter_complex", graph, "-loop", "0", str(out)], check=True)
    return out.stat().st_size, len(runs)


def render_gif(issue_dir):
    issue = pathlib.Path(issue_dir).resolve()
    spec = json.loads((issue / "spec.json").read_text())
    dist = issue / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"agent-field-notes-{int(spec['issue']):03d}.gif"
    report = {}
    with tempfile.TemporaryDirectory(prefix="afn-frames-") as tmp:
        frames = pathlib.Path(tmp)
        fps0 = ENCODINGS[0][0]
        info, problems, stills, count = capture(spec, frames, fps0)
        hard = [p for p in problems if not p.startswith("note:")]
        if hard:
            raise SystemExit("Layout problems:\n- " + "\n- ".join(hard))
        shutil.copy(frames / "f0000.png", dist / "cover.png")
        for sec in filter(None, os.environ.get("AFN_PEEK", "").split(",")):  # review stills, e.g. AFN_PEEK=1.4,16
            k = min(count - 1, int(float(sec) * fps0))
            shutil.copy(frames / f"f{k:04d}.png", dist / f"peek-{float(sec):05.1f}s.png")
        for i, (sid, png) in enumerate(stills.items(), 1):
            (dist / f"scene-{i}-{sid}.png").write_bytes(png)
        for fps, colors, bayer in ENCODINGS:
            if fps != fps0:  # fewer frames: drop the in-between ones
                step = fps0 / fps
                keep = sorted({int(round(k * step)) for k in range(int(count / step))})
                sub = frames / f"fps{round(fps, 2)}"
                sub.mkdir(exist_ok=True)
                for j, k in enumerate(keep):
                    shutil.copy(frames / f"f{k:04d}.png", sub / f"f{j:04d}.png")
                src = sub
            else:
                src = frames
            size, nframes = encode(src, out, fps, colors, bayer)
            report = {"gif": out.name, "bytes": size, "fps": round(fps, 2), "colors": colors, "bayer": bayer,
                      "frames": nframes, "seconds": round(info["total"] / 1000, 1),
                      "notes": [p for p in problems if p.startswith("note:")]}
            if size <= MAX_BYTES and nframes <= MAX_FRAMES:
                break
        else:
            raise SystemExit(f"GIF too heavy even at the smallest setting ({size / 1e6:.1f} MB, {nframes} frames); shorten the edition.")
    print(json.dumps(report))
    return report


if __name__ == "__main__":
    render_gif(sys.argv[1] if len(sys.argv) > 1 else "issues/001-the-refresh-test")
