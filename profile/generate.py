#!/usr/bin/env python3
"""Genera profile/profile.svg: el perfil completo como un único SVG animado.

Uso:
  GH_TOKEN=... USERNAME=ImKrav python3 profile/generate.py   # datos reales (CI)
  python3 profile/generate.py --sample                      # datos de ejemplo (vista previa local)
"""
import datetime as dt, json, os, random, re, sys, urllib.request
from html import escape
from pathlib import Path

OUT = Path(__file__).with_name("profile.svg")

# ── Contenido personal ──────────────────────────────────────────────────────
NAME = "Alejandro Bermúdez Bedoya"
ROLE = "Estudiante de Ingeniería de Sistemas"
CHIPS = ["Arquitectura de Software", "DevOps", "Apps escalables"]
STACK = [
    ("Lenguajes", ["js", "ts", "python"]),
    ("Frameworks", ["react", "nextjs", "tailwind", "nestjs", "express"]),
    ("Bases de datos", ["postgres", "mysql", "mongodb"]),
    ("Herramientas", ["git", "github", "nodejs", "docker", "kubernetes", "aws", "azure", "heroku", "vercel", "supabase"]),
]
MONTHS = "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split()

# ── Datos de GitHub ─────────────────────────────────────────────────────────
def gql(query, variables, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-svg"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch(login, token):
    u = gql("""query($login:String!){user(login:$login){
      createdAt followers{totalCount}
      pullRequests{totalCount} issues{totalCount}
      repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,first:100){totalCount nodes{
        stargazerCount languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}
      contributionsCollection{totalCommitContributions}
    }}""", {"login": login}, token)["user"]

    # Calendario año por año desde la creación de la cuenta → totales y rachas históricas.
    first, now = int(u["createdAt"][:4]), dt.datetime.now(dt.timezone.utc)
    parts = [
        f'y{y}:contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{min(dt.datetime(y, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now).strftime("%Y-%m-%dT%H:%M:%SZ")}")'
        "{contributionCalendar{weeks{contributionDays{date contributionCount}}}}"
        for y in range(first, now.year + 1)
    ]
    years = gql(f"query($login:String!){{user(login:$login){{{' '.join(parts)}}}}}", {"login": login}, token)["user"]
    days = sorted(
        (d["date"], d["contributionCount"])
        for y in years.values() for w in y["contributionCalendar"]["weeks"] for d in w["contributionDays"]
    )
    langs = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or "#8b949e"])[0] += e["size"]
    return {
        "commits": u["contributionsCollection"]["totalCommitContributions"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        "repos": u["repositories"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "since": first,
        "days": days,
        "langs": langs,
    }


def sample():
    rnd, today = random.Random(7), dt.date.today()
    days = [((today - dt.timedelta(d)).isoformat(), rnd.choice([0, 0, 1, 2, 3, 5, 8, 12])) for d in range(730, -1, -1)]
    days[-6:] = [(d, c or 2) for d, c in days[-6:]]
    return {"commits": 642, "prs": 38, "issues": 17, "stars": 24, "repos": 21, "followers": 15, "since": 2023, "days": days,
            "langs": {"TypeScript": [52000, "#3178c6"], "JavaScript": [31000, "#f1e05a"], "Python": [18000, "#3572A5"],
                      "CSS": [9000, "#663399"], "HTML": [6000, "#e34c26"], "Dockerfile": [1500, "#384d54"]}}


def streaks(days):
    """days: [(fecha, cantidad)] ordenado. Devuelve (actual, más larga). Hoy en 0 no rompe la racha."""
    longest = run = 0
    for _, c in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    counts = [c for _, c in days]
    if counts and counts[-1] == 0:
        counts.pop()
    current = 0
    for c in reversed(counts):
        if not c:
            break
        current += 1
    return current, longest


def icon(name, x, y, size, uid):
    """Incrusta un icono de skillicons.dev como <svg> anidado (GitHub no carga recursos externos)."""
    req = urllib.request.Request(f"https://skillicons.dev/icons?i={name}", headers={"User-Agent": "Mozilla/5.0 profile-svg"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    inner = raw[raw.index("<svg", 10): raw.rindex("</g>")].strip()
    inner = re.sub(r'id="([^"]+)"', rf'id="{uid}\1"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", rf"url(#{uid}\1)", inner)
    inner = re.sub(r'href="#([^"]+)"', rf'href="#{uid}\1"', inner)
    inner = re.sub(r'\s(width|height)="256"', "", inner, count=2)
    return inner.replace("<svg", f'<svg x="{x}" y="{y}" width="{size}" height="{size}"', 1)


# ── Render ──────────────────────────────────────────────────────────────────
W, PAD = 880, 32
MONO = "'JetBrains Mono','Fira Code','SF Mono',Consolas,'Liberation Mono',monospace"
SANS = "'Segoe UI',Inter,system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif"
LEVELS = ["#161e2e", "#123a63", "#1b5fae", "#3b82f6", "#7dd3fc"]
fmt = lambda n: f"{n:,}".replace(",", ".")


def anim(cls, delay, body):
    return f'<g class="{cls}" style="animation-delay:{delay:.2f}s">{body}</g>'


def heading(y, text, delay, right="", line_end=W - PAD):
    return anim("fade", delay,
        f'<text x="{PAD}" y="{y}" class="mono h">// {escape(text)}</text>'
        f'<line x1="{PAD + 30 + len(text) * 7.8:.0f}" y1="{y - 4}" x2="{line_end}" y2="{y - 4}" stroke="#1f2a3d"/>{right}')


def panel(x, y, w, h):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#0f1524" stroke="#1f2a3d"/>'


def render(d, fetch_icon=icon):
    days = d["days"]
    cur, best = streaks(days)
    total = sum(c for _, c in days)
    year_days = days[-371:]
    year_total = sum(c for _, c in year_days)
    today = dt.date.fromisoformat(days[-1][0]) if days else dt.date.today()
    out = []

    # Hero ─ ventana de terminal
    prompt = "whoami"
    pw = len(prompt) * 9.6
    out.append(f'''
<g class="fade" style="animation-delay:.05s">
  <circle cx="{PAD + 8}" cy="30" r="6" fill="#ff5f57"/><circle cx="{PAD + 28}" cy="30" r="6" fill="#febc2e"/><circle cx="{PAD + 48}" cy="30" r="6" fill="#28c840"/>
  <text x="{W / 2}" y="34" text-anchor="middle" class="mono dim" font-size="12">imkrav@github: ~</text>
  <line x1="0" y1="54" x2="{W}" y2="54" stroke="#1f2a3d"/>
</g>
<text x="{PAD + 8}" y="96" class="mono" font-size="16"><tspan fill="#22d3ee">❯</tspan><tspan fill="#64748b"> ~ </tspan></text>
<clipPath id="typeClip"><rect class="type" x="{PAD + 52}" y="80" width="{pw}" height="22"/></clipPath>
<text x="{PAD + 52}" y="96" class="mono" font-size="16" fill="#e2e8f0" clip-path="url(#typeClip)">{prompt}</text>
<rect class="cursor" x="{PAD + 54 + pw}" y="82" width="9" height="18" fill="#22d3ee"/>
{anim("rise", 1.25, f'<text x="{PAD + 8}" y="150" font-family="{SANS}" font-size="40" font-weight="800" fill="url(#grad)">{escape(NAME)}</text>')}
{anim("rise", 1.45, f'<text x="{PAD + 8}" y="184" class="mono" font-size="16" fill="#94a3b8">{escape(ROLE)}</text>')}''')
    x = PAD + 8
    for i, c in enumerate(CHIPS):
        w = len(c) * 7.2 + 26
        out.append(anim("rise", 1.65 + i * 0.12,
            f'<rect x="{x}" y="204" width="{w}" height="26" rx="13" fill="#3b82f61a" stroke="#3b82f655"/>'
            f'<text x="{x + w / 2}" y="221" text-anchor="middle" class="mono" font-size="12" fill="#93c5fd">{escape(c)}</text>'))
        x += w + 10
    # Decoración: órbitas
    cx, cy = W - PAD - 80, 142
    out.append(anim("zoom", 0.6, f'''
  <circle cx="{cx}" cy="{cy}" r="74" fill="url(#glow)"/>
  <g class="spin"><circle cx="{cx}" cy="{cy}" r="66" fill="none" stroke="#3b82f6" stroke-opacity=".55" stroke-dasharray="4 10"/><circle cx="{cx + 66}" cy="{cy}" r="4" fill="#22d3ee"/></g>
  <g class="spin rev"><circle cx="{cx}" cy="{cy}" r="46" fill="none" stroke="#a78bfa" stroke-opacity=".6" stroke-dasharray="30 12"/><circle cx="{cx}" cy="{cy - 46}" r="3.5" fill="#a78bfa"/></g>
  <circle cx="{cx}" cy="{cy}" r="28" fill="#0f1524" stroke="#1f2a3d"/>
  <text x="{cx}" y="{cy + 6}" text-anchor="middle" class="mono" font-size="17" font-weight="700" fill="#22d3ee">&lt;/&gt;</text>'''))

    # Estadísticas
    y0 = 284
    out.append(heading(y0, "estadísticas", 2.0))
    cards = [(f"Commits {today.year}", d["commits"], "#3b82f6"), ("Pull Requests", d["prs"], "#a78bfa"),
             ("Issues", d["issues"], "#22d3ee"), ("Estrellas", d["stars"], "#f59e0b"),
             ("Repositorios", d["repos"], "#34d399"), ("Seguidores", d["followers"], "#f472b6")]
    cw = (W - 2 * PAD - 5 * 12) / 6
    for i, (label, val, color) in enumerate(cards):
        x = PAD + i * (cw + 12)
        out.append(anim("rise", 2.1 + i * 0.09,
            panel(x, y0 + 16, cw, 84) +
            f'<rect x="{x + 16}" y="{y0 + 16}" width="{cw - 32}" height="2" rx="1" fill="{color}"/>'
            f'<text x="{x + cw / 2}" y="{y0 + 62}" text-anchor="middle" font-family="{SANS}" font-size="26" font-weight="700" fill="#f1f5f9">{fmt(val)}</text>'
            f'<text x="{x + cw / 2}" y="{y0 + 84}" text-anchor="middle" class="mono dim" font-size="11">{escape(label)}</text>'))

    # Racha + lenguajes
    y1 = 420
    lx, lw = PAD, 392
    out.append(heading(y1, "racha", 2.6, line_end=lx + lw))
    out.append(anim("rise", 2.7, panel(lx, y1 + 16, lw, 184)))
    r, rcx, rcy = 44, lx + lw / 2, y1 + 98
    circ = 2 * 3.14159 * r
    pct = cur / best if best else 0
    out.append(anim("fade", 2.8, f'''
  <circle cx="{rcx}" cy="{rcy}" r="{r}" fill="none" stroke="#1f2a3d" stroke-width="8"/>
  <circle class="ring" cx="{rcx}" cy="{rcy}" r="{r}" fill="none" stroke="url(#grad)" stroke-width="8" stroke-linecap="round"
    stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ * (1 - pct):.1f}" style="--c:{circ:.1f}px" transform="rotate(-90 {rcx} {rcy})"/>
  <text x="{rcx}" y="{rcy + 10}" text-anchor="middle" font-family="{SANS}" font-size="28" font-weight="800" fill="#f1f5f9">{cur}</text>
  <text x="{rcx}" y="{rcy + 72}" text-anchor="middle" class="mono" font-size="12" fill="#22d3ee">Racha actual</text>'''))
    for i, (val, label, sub) in enumerate([(fmt(total), "Contribuciones", f"desde {d['since']}"), (fmt(best), "Racha más larga", "días seguidos")]):
        sx = lx + (68 if i == 0 else lw - 68)
        out.append(anim("rise", 2.95 + i * 0.1,
            f'<text x="{sx}" y="{y1 + 104}" text-anchor="middle" font-family="{SANS}" font-size="24" font-weight="700" fill="#f1f5f9">{val}</text>'
            f'<text x="{sx}" y="{y1 + 128}" text-anchor="middle" class="mono" font-size="11" fill="#cbd5e1">{label}</text>'
            f'<text x="{sx}" y="{y1 + 146}" text-anchor="middle" class="mono dim" font-size="10">{sub}</text>'))

    gx, gw = PAD + lw + 16, W - 2 * PAD - lw - 16
    out.append(anim("fade", 2.6, f'<text x="{gx}" y="{y1}" class="mono h">// lenguajes</text>'
                                 f'<line x1="{gx + 120}" y1="{y1 - 4}" x2="{W - PAD}" y2="{y1 - 4}" stroke="#1f2a3d"/>'))
    out.append(anim("rise", 2.75, panel(gx, y1 + 16, gw, 184)))
    langs = sorted(d["langs"].items(), key=lambda kv: -kv[1][0])[:6]
    lsum = sum(v[0] for _, v in langs) or 1
    for i, (name, (size, color)) in enumerate(langs):
        p, ry = size / lsum * 100, y1 + 44 + i * 27
        out.append(anim("fade", 2.9 + i * 0.08,
            f'<text x="{gx + 20}" y="{ry}" class="mono" font-size="12" fill="#cbd5e1">{escape(name)}</text>'
            f'<text x="{gx + gw - 20}" y="{ry}" text-anchor="end" class="mono dim" font-size="11">{p:.1f}%</text>'
            f'<rect x="{gx + 20}" y="{ry + 6}" width="{gw - 40}" height="6" rx="3" fill="#1a2233"/>'
            f'<rect class="bar" style="animation-delay:{3.0 + i * 0.08:.2f}s" x="{gx + 20}" y="{ry + 6}" width="{max((gw - 40) * p / 100, 6):.1f}" height="6" rx="3" fill="{color}"/>'))

    # Mapa de contribuciones
    y2 = 660
    cell, gap = 11, 3
    legend_x = W - PAD - 5 * (cell + gap) - 30
    legend = (f'<text x="{legend_x - 8}" y="{y2}" text-anchor="end" class="mono dim" font-size="10">Menos</text>' +
              "".join(f'<rect x="{legend_x + i * (cell + gap)}" y="{y2 - 10}" width="{cell}" height="{cell}" rx="2" fill="{c}"/>' for i, c in enumerate(LEVELS)) +
              f'<text x="{legend_x + 5 * (cell + gap) + 4}" y="{y2}" class="mono dim" font-size="10">Más</text>')
    out.append(heading(y2, f"actividad · {fmt(year_total)} contribuciones en el último año", 3.3, legend, legend_x - 56))
    out.append(anim("fade", 3.35, panel(PAD, y2 + 16, W - 2 * PAD, 150)))
    start = today - dt.timedelta(52 * 7 + (today.weekday() + 1) % 7)  # domingo, 53 columnas, como GitHub
    by_date = dict(year_days)
    mx = max(by_date.values(), default=0) or 1
    hx, hy = PAD + 54, y2 + 52
    for wd, lab in ((1, "Lun"), (3, "Mié"), (5, "Vie")):
        out.append(anim("fade", 3.4, f'<text x="{hx - 10}" y="{hy + wd * (cell + gap) + 9}" text-anchor="end" class="mono dim" font-size="9">{lab}</text>'))
    last_month = None
    for col in range(53):
        cells = []
        for row in range(7):
            day = start + dt.timedelta(col * 7 + row)
            if day > today:
                break
            c = by_date.get(day.isoformat(), 0)
            lvl = 0 if not c else min(4, 1 + int(4 * c / (mx + 1)))
            cells.append(f'<rect x="{hx + col * (cell + gap)}" y="{hy + row * (cell + gap)}" width="{cell}" height="{cell}" rx="2" fill="{LEVELS[lvl]}"/>')
        top = start + dt.timedelta(col * 7)
        if top.month != last_month and col < 51:
            if last_month is not None or top.day <= 7:
                cells.append(f'<text x="{hx + col * (cell + gap)}" y="{hy - 9}" class="mono dim" font-size="9">{MONTHS[top.month - 1]}</text>')
            last_month = top.month
        out.append(anim("pop", 3.45 + col * 0.018, "".join(cells)))

    # Stack
    y3 = 856
    out.append(heading(y3, "stack & herramientas", 4.3))
    out.append(anim("fade", 4.35, panel(PAD, y3 + 16, W - 2 * PAD, 4 * 50 + 22)))
    n = 0
    for i, (cat, icons) in enumerate(STACK):
        ry = y3 + 38 + i * 50
        out.append(anim("fade", 4.4 + i * 0.1, f'<text x="{PAD + 22}" y="{ry + 24}" class="mono" font-size="12" fill="#94a3b8">{cat}</text>'))
        for j, name in enumerate(icons):
            out.append(anim("pop", 4.5 + n * 0.045, fetch_icon(name, PAD + 170 + j * 50, ry, 38, f"i{n}_")))
            n += 1

    # Footer
    y4 = y3 + 4 * 50 + 74
    msg = f" actualizado {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC · auto-generado con GitHub Actions"
    out.append(anim("fade", 5.4,
        f'<text x="{PAD + 8}" y="{y4}" class="mono" font-size="12"><tspan fill="#22d3ee">❯</tspan><tspan fill="#64748b">{msg}</tspan></text>'
        f'<rect class="blink" x="{PAD + 8 + (len(msg) + 2) * 7.2:.0f}" y="{y4 - 11}" width="7" height="14" fill="#22d3ee"/>'))
    H = y4 + 28

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">{escape(NAME)} · GitHub</title>
<desc id="d">{escape(ROLE)}. {fmt(total)} contribuciones, racha actual de {cur} días, {d["repos"]} repositorios públicos.</desc>
<defs>
  <linearGradient id="grad" x1="0" y1="0" x2="1" y2="0" spreadMethod="reflect">
    <stop offset="0" stop-color="#3b82f6"/><stop offset=".5" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/>
    <animateTransform attributeName="gradientTransform" type="translate" values="0 0;1 0;0 0" dur="8s" repeatCount="indefinite"/>
  </linearGradient>
  <radialGradient id="glow"><stop offset="0" stop-color="#3b82f6" stop-opacity=".35"/><stop offset="1" stop-color="#3b82f6" stop-opacity="0"/></radialGradient>
  <radialGradient id="orbA"><stop offset="0" stop-color="#2563eb" stop-opacity=".22"/><stop offset="1" stop-color="#2563eb" stop-opacity="0"/></radialGradient>
  <radialGradient id="orbB"><stop offset="0" stop-color="#7c3aed" stop-opacity=".16"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
  <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#ffffff" stroke-opacity=".035"/></pattern>
  <clipPath id="frame"><rect width="{W}" height="{H}" rx="16"/></clipPath>
</defs>
<style>
  .mono{{font-family:{MONO}}} .dim{{fill:#64748b}} .h{{font-size:13px;fill:#22d3ee;letter-spacing:.5px}}
  .fade,.rise,.pop,.zoom{{animation-duration:.7s;animation-timing-function:cubic-bezier(.2,.75,.25,1);animation-fill-mode:both}}
  .fade{{animation-name:fade}} .rise{{animation-name:rise}} .pop{{animation-name:pop;animation-duration:.5s}} .zoom{{animation-name:zoom;animation-duration:1.1s}}
  .pop,.zoom,.spin{{transform-box:fill-box;transform-origin:center}}
  .bar,.type{{transform-box:fill-box;transform-origin:left center}}
  .type{{animation:type .7s steps(6) .45s both}}
  .cursor{{animation:slide .7s steps(6) .45s both,blink 1s step-end 1.15s infinite}}
  .blink{{animation:blink 1s step-end infinite}}
  .bar{{animation:grow 1.1s cubic-bezier(.2,.75,.25,1) both}}
  .ring{{animation:ring 1.6s cubic-bezier(.2,.75,.25,1) 2.9s both}}
  .spin{{animation:spin 24s linear infinite}} .rev{{animation-direction:reverse;animation-duration:16s}}
  .orb{{animation:float 12s ease-in-out infinite alternate}} .orb2{{animation-duration:15s;animation-delay:-5s}}
  @keyframes fade{{from{{opacity:0}}}}
  @keyframes rise{{from{{opacity:0;transform:translateY(14px)}}}}
  @keyframes pop{{from{{opacity:0;transform:scale(.3)}}}}
  @keyframes zoom{{from{{opacity:0;transform:scale(.6) rotate(-30deg)}}}}
  @keyframes type{{from{{transform:scaleX(0)}}}}
  @keyframes slide{{from{{transform:translateX(-{pw:.1f}px)}}}}
  @keyframes grow{{from{{transform:scaleX(0)}}}}
  @keyframes ring{{from{{stroke-dashoffset:var(--c)}}}}
  @keyframes blink{{50%{{opacity:0}}}}
  @keyframes spin{{to{{transform:rotate(360deg)}}}}
  @keyframes float{{to{{transform:translate(60px,40px)}}}}
  @media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<g clip-path="url(#frame)">
  <rect width="{W}" height="{H}" fill="#0a0e17"/>
  <rect width="{W}" height="{H}" fill="url(#grid)"/>
  <circle class="orb" cx="140" cy="120" r="320" fill="url(#orbA)"/>
  <circle class="orb orb2" cx="{W - 120}" cy="{H - 260}" r="360" fill="url(#orbB)"/>
  {"".join(out)}
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="#1f2a3d"/>
</svg>
'''


def selfcheck():
    assert streaks([("a", 1), ("b", 2), ("c", 0), ("d", 3), ("e", 1)]) == (2, 2)
    assert streaks([("a", 1), ("b", 1), ("c", 1), ("d", 0)]) == (3, 3)  # hoy en 0 no rompe la racha
    assert streaks([("a", 1), ("b", 0), ("c", 0)]) == (0, 1)
    assert streaks([]) == (0, 0)


if __name__ == "__main__":
    selfcheck()
    if "--sample" in sys.argv:
        data = sample()
    else:
        token = os.environ.get("GH_TOKEN") or sys.exit("Falta GH_TOKEN")
        data = fetch(os.environ.get("USERNAME", "ImKrav"), token)
    OUT.write_text(render(data), encoding="utf-8")
    print(f"✔ {OUT}")
