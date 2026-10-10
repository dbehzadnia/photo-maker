#!/usr/bin/env python3
"""Render drawings/<id>.svg -> output/<id>_<name_en>.png (1920x1080) with headless Chromium
(supports feTurbulence/feDisplacementMap). Usage: render.py --all | --only a,b [--sheet]"""
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).parent
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
REF_ORDER = [("east-azerbaijan", "Image.png"), ("tehran", "Image-1.png"), ("isfahan", "Image-2.png")]

def inline(svg):
    """Inject shared style/filters.svg <defs> (+ palette CSS) into a drawing's <!--@filters--> marker."""
    pal = json.loads((ROOT / "style/palette.json").read_text())
    css = ":root{" + ";".join(f"--{k}:{v}" for k, v in pal.items()) + "}" + "".join(
        f".f-{k}{{fill:var(--{k})}}.s-{k}{{stroke:var(--{k})}}" for k in pal)
    defs = (ROOT / "style/filters.svg").read_text().replace("/*@palette*/", css)
    defs = re.search(r"<defs>.*</defs>", defs, re.S).group(0)
    assert "<!--@filters-->" in svg, "drawing is missing <!--@filters-->"
    return svg.replace("<!--@filters-->", defs)

def render(p, fails):
    out = ROOT / "output" / f"{p['id']}_{re.sub(r'[^A-Za-z0-9]+', '_', p['name_en'])}"
    svg = inline((ROOT / "drawings" / f"{p['id']}.svg").read_text())
    out.with_suffix(".svg").write_text(svg)  # self-contained copy for the website
    with tempfile.TemporaryDirectory() as t:
        html = Path(t) / "p.html"
        html.write_text(f'<!doctype html><html><body style="margin:0;overflow:hidden;background:#F5F0E6">{svg}</body></html>')
        r = subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                            "--window-size=1920,1200", f"--screenshot={out.with_suffix('.png')}", f"file://{html}"],
                           capture_output=True, text=True, timeout=180)
    png = out.with_suffix(".png")
    ok = png.exists() and Image.open(png).size[0] == 1920
    if ok:  # headless window has ~100px of browser chrome: keep the top 1920x1080
        Image.open(png).crop((0, 0, 1920, 1080)).save(png)
    if not ok:
        fails.append(p["id"]); print("FAILED", p["id"], r.stderr[-400:], file=sys.stderr)
        if len(fails) >= 3: sys.exit("3 renders failed in a row, stopping")
    else:
        fails.clear(); print("ok", out.with_suffix(".png").name)

def sheet(provs):
    """References on top, renders below."""
    outs = {p["id"]: next((ROOT / "output").glob(f"{p['id']}_*.png"), None) for p in provs}
    done = [p for p in provs if outs[p["id"]]]
    if len(done) <= 3:
        cols, w = 3, 640
        refs = [Image.open(ROOT / "references" / f) for i, f in REF_ORDER if i in outs and outs[i]]
        done = [next(p for p in provs if p["id"] == i) for i, _ in REF_ORDER if outs.get(i)]
    else:
        cols, w = 6, 320
        refs = [Image.open(ROOT / "references" / f) for _, f in REF_ORDER]
    h = w * 9 // 16
    rows = [refs] + [[Image.open(outs[p["id"]]) for p in done[i:i + cols]] for i in range(0, len(done), cols)]
    sh = Image.new("RGB", (cols * w, len(rows) * h), "#F5F0E6")
    for y, row in enumerate(rows):
        for x, im in enumerate(row):
            sh.paste(im.convert("RGB").resize((w, h), Image.LANCZOS), (x * w, y * h))
    sh.save(ROOT / "output/contact_sheet.png"); print("ok contact_sheet.png")

if __name__ == "__main__":
    a = argparse.ArgumentParser(); g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true"); g.add_argument("--only")
    a.add_argument("--sheet", action="store_true", help="also build output/contact_sheet.png")
    a = a.parse_args()
    provs = json.loads((ROOT / "provinces.json").read_text())
    ids = {p["id"] for p in provs} if a.all else set(a.only.split(","))
    bad = ids - {p["id"] for p in provs}
    if bad: sys.exit(f"unknown ids: {bad}")
    fails = []
    for p in provs:
        if p["id"] in ids: render(p, fails)
    if a.sheet: sheet(provs)
