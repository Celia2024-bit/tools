"""
Build the five figures for the LinkedIn post (see AI.md / site/ai-story.html).

Figures 1-4 are rendered from the site's own stylesheet through headless Chrome,
so they cannot drift from the real pages' look. Figure 5 is composed from frames
of the four demo recordings in site/images/.

Run from anywhere:   python site/images/post/build.py

Output: site/images/post/fig1..fig5 *.png  (2x device scale, trimmed to content)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent          # site/images/post
SITE = HERE.parent.parent                      # site/
IMAGES = SITE / "images"
TMP = Path(tempfile.gettempdir()) / "tsfigs"
TMP.mkdir(exist_ok=True)

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
SCALE = 2                                      # device pixel ratio for crisp output
BG = (11, 14, 20)                              # --bg #0b0e14

# --------------------------------------------------------------------------- #
# HTML rendering helpers
# --------------------------------------------------------------------------- #

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<link rel="stylesheet" href="../../assets/style.css">
<style>
  /* Flat background so the screenshot can be trimmed to the content box. */
  html, body {{ background: #0b0e14 !important; margin: 0; padding: 0; }}
  body::before, body::after {{ display: none !important; }}
  .figbox {{ width: {width}px; padding: 28px; }}
  .figbox > :last-child {{ margin-bottom: 0 !important; }}
</style></head>
<body{body_attr}><div class="figbox">{content}</div></body></html>
"""


def render(name: str, content: str, width: int, height: int = 2400,
           body_attr: str = "") -> Path:
    """Render an HTML fragment with the site stylesheet, trimmed to its content."""
    html = TMP / f"{name}.html"
    # The temp file lives two levels under site/ so the stylesheet path resolves.
    target = IMAGES / "post" / f".{name}.tmp.html"
    target.write_text(
        PAGE.format(width=width, content=content, body_attr=body_attr),
        encoding="utf-8",
    )
    shot = TMP / f"{name}.png"
    subprocess.run([
        str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--force-device-scale-factor={SCALE}",
        f"--window-size={width + 80},{height}",
        f"--screenshot={shot}", target.as_uri(),
    ], check=True, capture_output=True)
    target.unlink(missing_ok=True)
    html.unlink(missing_ok=True)

    out = HERE / f"{name}.png"
    trim(shot, out, margin=24 * SCALE)
    print(f"  {out.name:<34} {Image.open(out).size}")
    return out


def trim(src: Path, dst: Path, margin: int = 0, tol: int = 8) -> None:
    """Crop the flat background border away, then add a uniform margin back."""
    im = Image.open(src).convert("RGB")
    px = im.load()
    w, h = im.size
    bg = px[1, 1]

    def differs(x, y):
        p = px[x, y]
        return (abs(p[0] - bg[0]) > tol or abs(p[1] - bg[1]) > tol
                or abs(p[2] - bg[2]) > tol)

    left, right, top, bottom = w, 0, h, 0
    for y in range(h):
        for x in range(w):
            if differs(x, y):
                left = min(left, x); right = max(right, x)
                top = min(top, y); bottom = max(bottom, y)
    if right < left:                            # nothing drawn
        im.save(dst); return

    box = (max(0, left - margin), max(0, top - margin),
           min(w, right + 1 + margin), min(h, bottom + 1 + margin))
    canvas = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), bg)
    canvas.paste(im.crop(box), (0, 0))
    canvas.save(dst)


def section_of(page: str, start: str, end: str) -> str:
    """Lift a markup block straight out of a real page, so figures match it."""
    text = (SITE / page).read_text(encoding="utf-8")
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


# --------------------------------------------------------------------------- #
# Figure 1 — the four-card overview grid, as on index.html
# --------------------------------------------------------------------------- #

def fig1():
    cards = section_of("index.html", '<section class="cards">', "</section>") + "</section>"
    # Cards are links on the real page; in a figure they must not look clickable.
    cards = cards.replace("<a class=\"card\"", "<div class=\"card\"").replace("</a>", "</div>")
    return render("fig1-four-tools", cards, width=760)


# --------------------------------------------------------------------------- #
# Figure 2 — what you used to write by hand
# --------------------------------------------------------------------------- #

def fig2():
    shell = section_of("aspect-injector.html",
                       '<div class="code">\n      <div class="code-head"><span class="dot"></span>shell',
                       "<h2 id=\"config\">")
    cfg = section_of("aspect-injector.html",
                     '<div class="code">\n      <div class="code-head"><span class="dot"></span>config.json',
                     '<h3 id="fields">')
    # Drop the log block that sits between them on the real page.
    shell = shell.split('<div class="code-head"><span class="dot"></span>log')[0]
    if not shell.rstrip().endswith("</div>"):
        shell = shell.rstrip().rsplit("<div class=\"code\">", 1)[0]
    return render("fig2-by-hand", shell + cfg, width=820,
                  body_attr=' data-tool="aspect"')


# --------------------------------------------------------------------------- #
# Figure 3 — by hand vs. one sentence (the centrepiece)
# --------------------------------------------------------------------------- #

def fig3():
    split = section_of("ai-assistant.html", '<div class="split">', '<h2 id="why">')
    split = split.rstrip()
    return render("fig3-before-after", split, width=1040)


# --------------------------------------------------------------------------- #
# Figure 4 — the two AI layers (hand-built, in the site's own styling)
# --------------------------------------------------------------------------- #

ARROW = ('<div style="text-align:center;color:var(--text-mute);font-size:20px;'
         'line-height:1;margin:10px 0">&#8595;</div>')


def box(title, body, color="var(--accent)", mono=False):
    font = "var(--mono)" if mono else "var(--sans)"
    return f"""
    <div style="border:1px solid var(--line);border-left:3px solid {color};
                border-radius:10px;background:var(--panel);padding:14px 18px">
      <div style="font-size:14.5px;font-weight:650;color:#fff;margin-bottom:4px">{title}</div>
      <div style="font-size:13px;color:var(--text-dim);font-family:{font};line-height:1.55">{body}</div>
    </div>"""


def fig4():
    content = f"""
    <div style="font-family:var(--sans)">
      {box("One sentence, in plain English",
           "&ldquo;Add trace and validate logging to every function under test/src, "
           "but skip AlphaEngine.cpp&rdquo;", "var(--text-mute)", mono=True)}
      {ARROW}
      {box("Layer 1 &middot; AI router &mdash; <em>which tool?</em>",
           "Picks one of a fixed set: state machine &middot; interface sync &middot; "
           "aspect injector &middot; performance monitor &middot; <b>out of scope</b>. "
           "An enum, not free text &mdash; anything it cannot map, it refuses.")}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px">
        <div style="text-align:center;color:var(--text-mute);font-size:12.5px;
                    font-family:var(--mono)">&#8595;&nbsp; a tool was matched</div>
        <div style="text-align:center;color:var(--amber);font-size:12.5px;
                    font-family:var(--mono)">&#8595;&nbsp; nothing matched</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px">
        {box("Layer 2 &middot; AI writes the intermediate file",
             "A Markdown transition table, a <code>config.json</code>, or the new header "
             "&mdash; in the exact format that tool already parses. Nothing else.")}
        {box("Refused &mdash; nothing ran",
             "No file generated, no file changed. It says why, and lists what it does automate.",
             "var(--amber)")}
      </div>
      {ARROW}
      {box("The deterministic pipeline does the actual work",
           "libclang for the AST &middot; Jinja2 for the code &middot; g++ to prove it builds. "
           "Unchanged from before the AI layer existed &mdash; the model never edits a line of C++.",
           "var(--green)")}
      {ARROW}
      {box("Back in the browser",
           "Every generated file, every edit as a unified diff, the Mermaid diagram &mdash; "
           "and one button to put the tree back.")}
      <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line-soft);
                  font-size:13px;color:var(--text-mute);text-align:center">
        Intent comes from the model &middot; correctness comes from the tools
      </div>
    </div>"""
    return render("fig4-two-layers", content, width=880)


# --------------------------------------------------------------------------- #
# Figure 5 — 2x2 grid of "the moment the result appears"
# --------------------------------------------------------------------------- #

# (video, timestamp in seconds, caption) — timestamps picked by reviewing a
# contact sheet of candidates; each one is the frame where the payoff is on screen.
FRAMES = [
    ("aspect_inject.mp4", 29.1, "Aspect Injector \u2014 13 files rewritten, +243 lines, every one a diff"),
    ("StateMachine.mp4", 38.1, "State Machine \u2014 spec, C++, Mermaid diagram, compiled and run"),
    ("interface_syn.mp4", 43.0, "Interface Sync \u2014 the interface change, propagated to every override"),
    ("Unsported_tool.mp4", 16.3, "Out of scope \u2014 nothing ran, and it says why"),
]


def font(size, bold=True):
    for name in (("seguisb.ttf", "segoeuib.ttf") if bold else ("segoeui.ttf",)):
        path = Path(r"C:\Windows\Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def fig5():
    cell_w = 1000
    pad, gap, cap_h = 26, 18, 44
    tiles = []
    for name, t, caption in FRAMES:
        raw = TMP / f"frame_{Path(name).stem}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}",
                        "-i", str(IMAGES / name), "-frames:v", "1", str(raw)],
                       check=True)
        im = Image.open(raw).convert("RGB")
        im = im.resize((cell_w, round(im.height * cell_w / im.width)), Image.LANCZOS)
        tiles.append((im, caption))

    cell_h = max(im.height for im, _ in tiles) + cap_h
    W = pad * 2 + cell_w * 2 + gap
    H = pad * 2 + cell_h * 2 + gap
    sheet = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(sheet)
    f = font(21)

    for i, (im, caption) in enumerate(tiles):
        x = pad + (i % 2) * (cell_w + gap)
        y = pad + (i // 2) * (cell_h + gap)
        draw.rounded_rectangle([x - 4, y - 4, x + cell_w + 3, y + cell_h + 3],
                               radius=10, outline=(35, 43, 61), width=2)
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + im.height + 13), caption, font=f, fill=(151, 161, 187))

    out = HERE / "fig5-results.png"
    sheet.save(out)
    print(f"  {out.name:<34} {sheet.size}")
    return out


# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    if not CHROME.exists():
        sys.exit(f"Chrome not found at {CHROME}")
    print("building figures into", HERE)
    fig1(); fig2(); fig3(); fig4(); fig5()
    print("done")
