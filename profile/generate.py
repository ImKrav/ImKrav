#!/usr/bin/env python3
"""Genera profile/profile-dark.svg y profile/profile-light.svg: el perfil completo como SVG animado.

Uso:
  GH_TOKEN=... USERNAME=ImKrav python3 profile/generate.py   # datos reales (CI)
  python3 profile/generate.py --sample                      # datos de ejemplo (vista previa local)
"""
import base64, datetime as dt, functools, json, math, os, random, re, sys, urllib.request
from html import escape
from pathlib import Path

HERE = Path(__file__).parent

# ── Contenido personal ──────────────────────────────────────────────────────
NAME = ("Alejandro", "Bermúdez Bedoya")
INTRO = ("Estudio Ingeniería de Sistemas. Me interesa cómo se diseña el software por dentro",
         "y cómo llega a producción: arquitectura, contenedores, pipelines y nube.")
STACK = [  # (grupo, iconos de skillicons.dev), en una sola fila de margen a margen
    ("Código", ["js", "ts", "python"]),
    ("Frameworks", ["react", "nextjs", "tailwind", "nestjs", "express"]),
    ("Datos", ["postgres", "mysql", "mongodb"]),
    ("Infraestructura y herramientas", ["git", "github", "nodejs", "docker", "kubernetes", "aws", "azure", "heroku", "vercel", "supabase"]),
]
MONTHS = "ene feb mar abr may jun jul ago sep oct nov dic".split()

THEMES = {
    "dark": dict(bg="#0f1318", edge="#1e252e", ink="#e8ecf0", muted="#8c96a2", faint="#262d36", bar="#4b5562", accent="#f2b13c"),
    "light": dict(bg="#f7f8fa", edge="#e1e5ea", ink="#12161b", muted="#5d6773", faint="#dce1e6", bar="#a3acb6", accent="#c47f00"),
}


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


@functools.cache
def icon_svg(name, theme):
    req = urllib.request.Request(f"https://skillicons.dev/icons?i={name}&theme={theme}", headers={"User-Agent": "Mozilla/5.0 profile-svg"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    return raw[raw.index("<svg", 10): raw.rindex("</g>")].strip()


def icon(name, theme, x, y, size, uid):
    """Incrusta un icono de skillicons.dev como <svg> anidado (GitHub no carga recursos externos)."""
    inner = icon_svg(name, theme)
    inner = re.sub(r'id="([^"]+)"', rf'id="{uid}\1"', inner)
    inner = re.sub(r"url\(#([^)]+)\)", rf"url(#{uid}\1)", inner)
    inner = re.sub(r'href="#([^"]+)"', rf'href="#{uid}\1"', inner)
    inner = re.sub(r'\s(width|height)="256"', "", inner, count=2)
    return inner.replace("<svg", f'<svg x="{x}" y="{y}" width="{size}" height="{size}"', 1)


@functools.cache
def font_css():
    face = lambda fam, file, wt: (f"@font-face{{font-family:'{fam}';font-weight:{wt};src:url(data:font/woff2;base64,"
                                  f"{base64.b64encode((HERE / 'fonts' / file).read_bytes()).decode()}) format('woff2')}}")
    return face("Bric", "bric-400.woff2", 400) + face("Bric", "bric-800.woff2", 800) + face("Martian", "martian-400.woff2", 400)


# ── Render ──────────────────────────────────────────────────────────────────
W, M = 880, 48
fmt = lambda n: f"{n:,}".replace(",", ".")
plural = lambda n, one, many: f"{one if n == 1 else many}"


def render(d, theme="dark", get_icon=icon):
    t = THEMES[theme]
    days = d["days"]
    cur, best = streaks(days)
    today = dt.date.fromisoformat(days[-1][0]) if days else dt.date.today()
    year = days[-365:]
    year_total = sum(c for _, c in year)
    out = []
    b = lambda n: f'<tspan class="num">{fmt(n)}</tspan>'  # cifra resaltada dentro de una frase

    # Cabecera: meta, nombre, presentación
    out.append(f'''
<text x="{M}" y="52" class="mono">@ImKrav</text>
<text x="{W - M}" y="52" class="mono" text-anchor="end">actualizado {today.day} {MONTHS[today.month - 1]} {today.year}</text>
<clipPath id="n1"><rect x="0" y="72" width="{W}" height="72"/></clipPath>
<clipPath id="n2"><rect x="0" y="144" width="{W}" height="64"/></clipPath>
<g clip-path="url(#n1)"><text x="{M - 4}" y="128" class="name up" style="animation-delay:.1s">{escape(NAME[0])}</text></g>
<g clip-path="url(#n2)"><text x="{M - 4}" y="192" class="name up" style="animation-delay:.22s">{escape(NAME[1])}</text></g>
<g class="fade" style="animation-delay:.6s">
  <text x="{M}" y="238" class="body">{escape(INTRO[0])}</text>
  <text x="{M}" y="264" class="body">{escape(INTRO[1])}</text>
</g>''')

    # Firma: la traza del año, un día por barra. La racha actual va en el color de acento.
    top, base, tw = 340, 450, W - 2 * M
    pitch = tw / 365
    mx = max((c for _, c in year), default=0) or 1
    streak_from = len(year) - cur - (1 if year and year[-1][1] == 0 else 0)
    bars = []
    for i, (date, c) in enumerate(year):
        h = 2 if not c else max(4, math.sqrt(c / mx) * (base - top))
        cls = "acc" if c and i >= streak_from else ("bar" if c else "zero")
        bars.append(f'<rect class="{cls}" x="{M + i * pitch:.2f}" y="{base - h:.1f}" width="{pitch * .62:.2f}" height="{h:.1f}"/>')
    months = []
    for i, (date, _) in enumerate(year):
        day = dt.date.fromisoformat(date)
        if day.day == 1 and i < len(year) - 12:
            months.append(f'<text x="{M + i * pitch:.1f}" y="{base + 22}" class="mono">{MONTHS[day.month - 1]}</text>')
    out.append(f'''
<text x="{M}" y="{top - 18}" class="mono">Contribuciones, últimos 12 meses</text>
<text x="{W - M}" y="{top - 18}" class="mono ink" text-anchor="end">{fmt(year_total)} en total · racha actual <tspan class="acc-t">{cur} {plural(cur, "día", "días")}</tspan></text>
<clipPath id="sweep"><rect class="sweep" x="{M}" y="{top - 4}" width="{tw}" height="{base - top + 8}"/></clipPath>
<g clip-path="url(#sweep)">{"".join(bars)}</g>
<rect class="head" x="{M}" y="{top - 6}" width="1.5" height="{base - top + 10}"/>
<rect x="{M}" y="{base + 1}" width="{tw}" height="1" class="rule"/>
{"".join(months)}''')

    # Los números, dichos en una frase
    y = 524
    lines = [
        f'Este año: {b(d["commits"])} commits. En total, {b(d["prs"])} pull requests y {b(d["issues"])} issues.',
        f'Racha actual de {b(cur)} {plural(cur, "día", "días")}; la más larga, {b(best)}. Contribuyendo desde {d["since"]}.',
        f'{b(d["repos"])} {plural(d["repos"], "repositorio público", "repositorios públicos")}, '
        f'{b(d["stars"])} {plural(d["stars"], "estrella", "estrellas")} y {b(d["followers"])} {plural(d["followers"], "seguidor", "seguidores")}.',
    ]
    out += [f'<text x="{M}" y="{y + i * 32}" class="say">{s}</text>' for i, s in enumerate(lines)]

    # Lenguajes: una barra segmentada con sus colores reales
    y = 640
    langs = sorted(d["langs"].items(), key=lambda kv: -kv[1][0])[:6]
    lsum = sum(v[0] for _, v in langs) or 1
    segs, legend, x = [], [], M
    for i, (name, (size, color)) in enumerate(langs):
        w = tw * size / lsum
        segs.append(f'<rect class="seg" style="animation-delay:{2.5 + i * .09:.2f}s" x="{x:.1f}" y="{y + 14}" width="{max(w - 2, 1):.1f}" height="8" fill="{color}"/>')
        legend.append(f'<tspan fill="{color}" font-weight="800">— </tspan><tspan class="ink-t">{escape(name)}</tspan> {size / lsum * 100:.0f}%{"   " if i < len(langs) - 1 else ""}')
        x += w
    out.append(f'<text x="{M}" y="{y}" class="mono">Lenguajes en repositorios públicos</text>'
               f'<clipPath id="lbar"><rect x="{M}" y="{y + 14}" width="{tw}" height="8" rx="4"/></clipPath>'
               f'<g clip-path="url(#lbar)">{"".join(segs)}</g>'
               f'<text x="{M}" y="{y + 48}" class="mono" xml:space="preserve">{"".join(legend)}</text>')

    # Stack: iconos reales, sin animación; el hueco entre iconos se calcula para llegar justo al margen derecho
    y, size, group_gap, n, x = 746, 30, 26, 0, M
    count = sum(len(icons) for _, icons in STACK)
    gap = (tw - count * size - (len(STACK) - 1) * group_gap) / (count - len(STACK))
    for group, icons in STACK:
        out.append(f'<text x="{x:.1f}" y="{y}" class="mono">{escape(group)}</text>')
        for name in icons:
            out.append(get_icon(name, theme, round(x, 1), y + 12, size, f"i{n}_"))
            x += size + gap
            n += 1
        x += group_gap - gap
    H = y + 76

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">{escape(" ".join(NAME))}</title>
<desc id="d">{escape(" ".join(INTRO))} {fmt(year_total)} contribuciones en los últimos 12 meses, racha actual de {cur} días.</desc>
<style>
  {font_css()}
  text{{fill:{t["muted"]}}}
  .name{{font:800 64px Bric,'Segoe UI',system-ui,sans-serif;letter-spacing:-1.6px;fill:{t["ink"]}}}
  .body{{font:400 17px Bric,'Segoe UI',system-ui,sans-serif;fill:{t["muted"]}}}
  .say{{font:400 19px Bric,'Segoe UI',system-ui,sans-serif;fill:{t["muted"]}}}
  .num{{font-weight:800;fill:{t["ink"]}}}
  .mono{{font:400 11px Martian,ui-monospace,'SF Mono',Consolas,monospace;letter-spacing:.2px}}
  .ink,.ink-t{{fill:{t["ink"]}}} .acc-t{{fill:{t["accent"]}}}
  .bar{{fill:{t["bar"]}}} .zero,.rule{{fill:{t["faint"]}}} .acc,.head{{fill:{t["accent"]}}}
  .up{{animation:up .9s cubic-bezier(.16,1,.3,1) both}}
  .fade{{animation:fade .8s ease-out both}}
  .sweep{{transform-box:fill-box;transform-origin:left;animation:sweep 1.8s cubic-bezier(.65,0,.35,1) .85s both}}
  .head{{opacity:0;animation:head 1.8s cubic-bezier(.65,0,.35,1) .85s both}}
  .seg{{transform-box:fill-box;transform-origin:left;animation:sweep .7s cubic-bezier(.16,1,.3,1) both}}
  @keyframes up{{from{{transform:translateY(72px)}}}}
  @keyframes fade{{from{{opacity:0}}}}
  @keyframes sweep{{from{{transform:scaleX(0)}}}}
  @keyframes head{{0%{{opacity:1;transform:translateX(0)}}92%{{opacity:1}}100%{{opacity:0;transform:translateX({tw}px)}}}}
  @media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="{t["bg"]}" stroke="{t["edge"]}"/>
{"".join(out)}
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
    for theme in THEMES:
        path = HERE / f"profile-{theme}.svg"
        path.write_text(render(data, theme), encoding="utf-8")
        print(f"✔ {path}")
