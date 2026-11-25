"""Build the hand-drawn architecture diagram.

Outputs (in docs/engagement/):
  architecture.excalidraw   open at excalidraw.com (File > Open) to edit
  architecture-sketch.html  open in a browser
Usage: python3 docs/engagement/diagram/build.py

PNG (from the project root):
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
    --force-device-scale-factor=2 --virtual-time-budget=8000 --window-size=1232,800 \
    --screenshot="$PWD/docs/engagement/architecture-sketch.png" "file://$PWD/docs/engagement/architecture-sketch.html"
"""

import json
import random
from pathlib import Path

OUT = Path(__file__).parent.parent

YELLOW, BLUE, GREEN, RED, NOTE = "#ffec99", "#a5d8ff", "#b2f2bb", "#ffc9c9", "#fff3bf"

TITLE = "YK Finance voice agent: architecture v1"

ZONES = [  # x, y, w, h, label
    (20, 80, 1160, 130, "OUTSIDE SYSTEMS"),
    (20, 240, 1160, 170, "OUR PROCESSES · stateless"),
    (20, 450, 1160, 290, "STATE · must survive"),
]

ZONE_LABEL_X = [14, 250, 390]  # offsets that keep zone labels clear of arrows

BOXES = [  # id, x, y, w, h, fill, title, subtitle
    ("loan", 40, 115, 230, 70, YELLOW, "Lender's loan system", "system of record"),
    ("borrower", 330, 115, 170, 70, YELLOW, "Borrower", "on the phone"),
    ("tel", 560, 115, 260, 70, YELLOW, "Telephony provider", "Twilio (demo) · Exotel/Plivo (India)"),
    ("ai", 890, 115, 270, 70, YELLOW, "STT · LLM · TTS", "Deepgram · OpenAI · Cartesia + backups"),
    ("api", 40, 280, 230, 96, BLUE, "API", "webhooks · ops dashboard"),
    ("wf", 360, 280, 280, 96, BLUE, "Workflow workers", "Temporal · schedule · dial · retry"),
    ("voice", 720, 280, 300, 96, BLUE, "Voice workers", "Pipecat · STT → LLM → TTS + tools"),
    ("temporal", 420, 490, 220, 76, GREEN, "Temporal", "timers · workflow progress"),
    ("object", 780, 490, 200, 76, GREEN, "Object storage", "call recordings"),
    ("pg", 40, 640, 1120, 80, GREEN, "Postgres",
     "cases · attempts · promises · outbox   |   compliance schema: stop flags · contact rules · decisions"),
]

BADGES = [  # x, y, w, h, text (compliance runs inside these processes)
    (375, 362, 140, 30, "compliance lib"),
    (740, 362, 140, 30, "compliance lib"),
]

NOTE_BOX = (1040, 485, 125, 110, "Rules live in code.\nThe LLM only\nproposes.")

ARROWS = [  # points, label, label (x, y), align, both ends
    ([(155, 185), (155, 278)], "EMI failed / paid", (165, 210), "start", False),
    ([(500, 150), (558, 150)], "call", (529, 140), "middle", True),
    ([(590, 185), (590, 225), (240, 225), (240, 278)], "call events", (420, 218), "middle", False),
    ([(620, 278), (620, 187)], "dial", (610, 262), "end", False),
    ([(760, 187), (760, 278)], "call audio", (770, 236), "start", True),
    ([(980, 278), (980, 187)], "audio ↔ text", (990, 236), "start", True),
    ([(120, 376), (120, 638)], "events", (130, 430), "start", False),
    ([(220, 376), (220, 528), (418, 528)], "start workflows", (318, 520), "middle", False),
    ([(560, 378), (560, 488)], "tasks · results", (570, 438), "start", True),
    ([(395, 394), (395, 638)], "case state", (405, 610), "start", False),
    ([(900, 394), (900, 488)], "recordings", (910, 438), "start", False),
    ([(1005, 378), (1005, 638)], "promises · stop flags", (995, 610), "end", False),
]

W, H = 1200, 760


# ---------- Excalidraw file ----------

def base(kind, x, y, w, h, **extra):
    seed = random.randint(1, 2**31)
    el = {
        "id": f"{kind}-{seed}", "type": kind, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
        "fillStyle": "hachure", "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1,
        "opacity": 100, "groupIds": [], "frameId": None, "roundness": None, "seed": seed,
        "version": 1, "versionNonce": seed, "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
    }
    el.update(extra)
    return el


def text_el(x, y, text, size=18, align="left", container=None, color="#1e1e1e"):
    lines = text.split("\n")
    w = max(len(line) for line in lines) * size * 0.55
    h = len(lines) * size * 1.25
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    return base("text", x, y, w, h, text=text, originalText=text, fontSize=size, fontFamily=1,
                textAlign=align, verticalAlign="middle" if container else "top",
                containerId=container, lineHeight=1.25, strokeColor=color, autoResize=True)


def excalidraw():
    els = [text_el(40, 25, TITLE, size=28)]
    for x, y, w, h, label in ZONES:
        els.append(base("rectangle", x, y, w, h, strokeStyle="dashed", strokeColor="#868e96",
                        strokeWidth=1, roundness={"type": 3}))
        els.append(text_el(x + ZONE_LABEL_X[ZONES.index((x, y, w, h, label))], y + 8, label, size=14, color="#868e96"))
    for _, x, y, w, h, fill, title, sub in BOXES:
        box = base("rectangle", x, y, w, h, backgroundColor=fill, roundness={"type": 3})
        t = text_el(x + w / 2, y + h / 2 - 22, f"{title}\n{sub}", size=16, align="center",
                    container=box["id"])
        box["boundElements"] = [{"type": "text", "id": t["id"]}]
        els += [box, t]
    for x, y, w, h, label in BADGES:
        b = base("rectangle", x, y, w, h, backgroundColor=RED, fillStyle="solid", roundness={"type": 3})
        t = text_el(x + w / 2, y + 4, label, size=14, align="center", container=b["id"])
        b["boundElements"] = [{"type": "text", "id": t["id"]}]
        els += [b, t]
    x, y, w, h, label = NOTE_BOX
    n = base("rectangle", x, y, w, h, backgroundColor=NOTE, fillStyle="solid", strokeColor="#f08c00")
    t = text_el(x + w / 2, y + 20, label, size=16, align="center", container=n["id"])
    n["boundElements"] = [{"type": "text", "id": t["id"]}]
    els += [n, t]
    for pts, label, (lx, ly), align, both in ARROWS:
        x0, y0 = pts[0]
        rel = [[px - x0, py - y0] for px, py in pts]
        xs, ys = [p[0] for p in rel], [p[1] for p in rel]
        els.append(base("arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys), points=rel,
                        startArrowhead="arrow" if both else None, endArrowhead="arrow",
                        startBinding=None, endBinding=None, lastCommittedPoint=None, elbowed=False))
        els.append(text_el(lx, ly - 14, label, size=14,
                           align={"start": "left", "middle": "center", "end": "right"}[align]))
    return {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}


# ---------- Hand-drawn HTML (rough.js) ----------

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YK Finance Architecture Sketch</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Kalam:wght@400;700&display=swap">
<style>
  body { margin: 0; background: #ffffff; color: #1e1e1e; }
  .wrap { overflow-x: auto; padding: 16px; }
  svg { display: block; width: 100%; min-width: 900px; max-width: 1400px; margin: 0 auto; height: auto;
        font-family: "Kalam", "Comic Sans MS", cursive; }
</style>
</head>
<body>
<div class="wrap"><svg id="d" viewBox="0 0 __W__ __H__" role="img"
  aria-label="Architecture: outside systems, three stateless process types with compliance inside, and the state stores."></svg></div>
<script src="https://cdn.jsdelivr.net/npm/roughjs@4.6.6/bundled/rough.js"></script>
<script>
const S = __SPEC__;
const svg = document.getElementById("d");
const rc = rough.svg(svg);
const NS = "http://www.w3.org/2000/svg";
let seed = 7;
const o = (extra) => Object.assign({ roughness: 1.1, bowing: 1, stroke: "#1e1e1e", strokeWidth: 1.6, seed: seed++ }, extra);

function text(x, y, str, size, opts = {}) {
  const t = document.createElementNS(NS, "text");
  t.setAttribute("x", x); t.setAttribute("y", y);
  t.setAttribute("font-size", size);
  t.setAttribute("text-anchor", opts.anchor || "start");
  t.setAttribute("fill", opts.color || "#1e1e1e");
  if (opts.bold) t.setAttribute("font-weight", "700");
  t.textContent = str;
  svg.appendChild(t);
}

text(40, 50, S.title, 30, { bold: true });

for (const [x, y, w, h, label] of S.zones) {
  svg.appendChild(rc.rectangle(x, y, w, h, o({ stroke: "#868e96", strokeWidth: 1.2, strokeLineDash: [8, 6], roughness: 0.8 })));
  text(x + S.zoneLabelX[S.zones.findIndex(z => z[1] === y)], y + 22, label, 14, { color: "#6c757d" });
}
for (const [id, x, y, w, h, fill, title, sub] of S.boxes) {
  svg.appendChild(rc.rectangle(x, y, w, h, o({ fill, fillStyle: "hachure", hachureGap: 7, fillWeight: 1.2 })));
  text(x + w / 2, y + h / 2 - 2, title, 19, { anchor: "middle", bold: true });
  text(x + w / 2, y + h / 2 + 20, sub, 14.5, { anchor: "middle", color: "#343a40" });
}
for (const [x, y, w, h, label] of S.badges) {
  svg.appendChild(rc.rectangle(x, y, w, h, o({ fill: "#ffc9c9", fillStyle: "solid", strokeWidth: 1.3 })));
  text(x + w / 2, y + 20, label, 14, { anchor: "middle" });
}
{
  const [x, y, w, h, label] = S.note;
  svg.appendChild(rc.rectangle(x, y, w, h, o({ fill: "#fff3bf", fillStyle: "solid", stroke: "#f08c00" })));
  label.split("\\n").forEach((line, i) => text(x + w / 2, y + 34 + i * 24, line, 16, { anchor: "middle" }));
}
function head(p, q) {
  const a = Math.atan2(q[1] - p[1], q[0] - p[0]), L = 12, s = 0.45;
  for (const d of [a + Math.PI - s, a + Math.PI + s])
    svg.appendChild(rc.line(q[0], q[1], q[0] + L * Math.cos(d), q[1] + L * Math.sin(d), o({ roughness: 0.6 })));
}
for (const [pts, label, [lx, ly], align, both] of S.arrows) {
  svg.appendChild(rc.linearPath(pts, o({ roughness: 0.9 })));
  head(pts[pts.length - 2], pts[pts.length - 1]);
  if (both) head(pts[1], pts[0]);
  text(lx, ly, label, 15, { anchor: align, color: "#1971c2" });
}
</script>
</body>
</html>
"""


def html():
    spec = {"zoneLabelX": ZONE_LABEL_X, "title": TITLE, "zones": ZONES, "boxes": BOXES, "badges": BADGES,
            "note": NOTE_BOX, "arrows": ARROWS}
    return (HTML.replace("__SPEC__", json.dumps(spec, ensure_ascii=False))
                .replace("__W__", str(W)).replace("__H__", str(H)))


if __name__ == "__main__":
    random.seed(42)
    (OUT / "architecture.excalidraw").write_text(json.dumps(excalidraw(), indent=1, ensure_ascii=False))
    (OUT / "architecture-sketch.html").write_text(html())
    print("wrote architecture.excalidraw and architecture-sketch.html")
