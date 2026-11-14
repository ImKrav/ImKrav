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
    ("Código", ["js", "ts", "go", "python"]),
    ("Frameworks", ["nextjs", "angular", "nestjs", "fastapi"]),
    ("Datos", ["postgres", "mysql", "mongodb"]),
    ("Infraestructura y herramientas", ["git", "jenkins", "docker", "dokploy", "aws", "azure", "gcp", "heroku", "vercel"]),
]
MONTHS = "ene feb mar abr may jun jul ago sep oct nov dic".split()

THEMES = {
    "dark": dict(bg="#0f1318", edge="#1e252e", ink="#e8ecf0", muted="#8c96a2", faint="#262d36", tile="#141a21", bar="#4b5562", accent="#f2b13c"),
    "light": dict(bg="#f7f8fa", edge="#e1e5ea", ink="#12161b", muted="#5d6773", faint="#dce1e6", tile="#ffffff", bar="#a3acb6", accent="#c47f00"),
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
      contributionsCollection{totalCommitContributions totalPullRequestReviewContributions}
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
        "reviews": u["contributionsCollection"]["totalPullRequestReviewContributions"],
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
    return {"commits": 642, "prs": 38, "reviews": 12, "issues": 17, "stars": 24, "repos": 21, "followers": 15, "since": 2023, "days": days,
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
    local = HERE / "icons" / f"{name}.svg"  # iconos que skillicons.dev no tiene, en su mismo estilo de baldosa
    if local.exists():
        svg = local.read_text().strip()
        return svg.replace('fill="#242938"', 'fill="#F4F2ED"').replace('fill="#FFFFFF"', 'fill="#242938"') if theme == "light" else svg
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

    # Actividad: el mapa del año. Lo revela un barrido; los días de la racha actual van en el color de acento.
    tw, top = W - 2 * M, 352
    gx, pitch, cell = M + 30, (tw - 30) / 53, 11
    by_date = dict(year)
    mx = max(by_date.values(), default=0) or 1
    streak_days, day = set(), today - dt.timedelta(1 if by_date.get(today.isoformat(), 0) == 0 else 0)
    while len(streak_days) < cur:
        streak_days.add(day.isoformat())
        day -= dt.timedelta(1)
    start = today - dt.timedelta(52 * 7 + (today.weekday() + 1) % 7)  # domingo, 53 columnas, como GitHub
    cells, months, last_month = [], [], None
    for col in range(53):
        first = start + dt.timedelta(col * 7)
        if first.month != last_month and col < 51:
            if last_month is not None or first.day <= 7:
                months.append(f'<text x="{gx + col * pitch:.1f}" y="{top - 10}" class="mono">{MONTHS[first.month - 1]}</text>')
            last_month = first.month
        for row in range(7):
            day = first + dt.timedelta(row)
            if day > today:
                break
            c = by_date.get(day.isoformat(), 0)
            cls = "acc" if day.isoformat() in streak_days else ("bar" if c else "zero")
            op = f' fill-opacity="{.3 + .7 * math.sqrt(c / mx):.2f}"' if c and cls == "bar" else ""
            cells.append(f'<rect class="{cls}" x="{gx + col * pitch:.1f}" y="{top + row * pitch:.1f}" width="{cell}" height="{cell}" rx="2"{op}/>')
    gh = 7 * pitch
    out.append(f'''
<text x="{M}" y="{top - 36}" class="mono">Actividad, últimos 12 meses</text>
<text x="{W - M}" y="{top - 36}" class="mono ink" text-anchor="end">{fmt(year_total)} contribuciones</text>
{"".join(months)}
{"".join(f'<text x="{M}" y="{top + r * pitch + 9:.1f}" class="mono small">{lab}</text>' for r, lab in ((1, "lun"), (3, "mié"), (5, "vie")))}
<clipPath id="sweep"><rect class="sweep" x="{gx - 2}" y="{top - 2}" width="{tw - 28}" height="{gh + 4}"/></clipPath>
<g clip-path="url(#sweep)">{"".join(cells)}</g>
<rect class="head" x="{gx - 2}" y="{top - 6}" width="1.5" height="{gh + 10}"/>''')

    # Estadísticas: commits del año con su gráfica mensual, y el resto en una cuadrícula de 3×2
    y, gap, bh = 512, 12, 180
    out.append(f'<text x="{M}" y="{y - 14}" class="mono">Estadísticas</text>')
    bw = 284
    months_back = [((today.month - 1 - k) % 12 + 1, today.year - (k >= today.month)) for k in range(11, -1, -1)]  # (mes, año), del más viejo al actual
    per_month = [sum(c for dd, c in year if dd[:7] == f"{yy}-{mm:02d}") for mm, yy in months_back]
    pm_max = max(per_month) or 1
    cx0, cw, chart_top, chart_base = M + 18, (bw - 36) / 12, y + 98, y + bh - 26
    cols = []
    for i, ((mm, _), v) in enumerate(zip(months_back, per_month)):
        h = max(2, (chart_base - chart_top) * v / pm_max)
        cols.append(f'<rect class="{"acc" if i == 11 else "bar"} col" style="animation-delay:{2.1 + i * .05:.2f}s" x="{cx0 + i * cw + 2:.1f}" y="{chart_base - h:.1f}" width="{cw - 5:.1f}" height="{h:.1f}" rx="2"/>'
                    f'<text x="{cx0 + i * cw + cw / 2 - 1.5:.1f}" y="{chart_base + 14}" text-anchor="middle" class="mono small">{MONTHS[mm - 1][0]}</text>')
    out.append(f'''<rect x="{M}" y="{y}" width="{bw}" height="{bh}" rx="12" class="tile"/>
<text x="{M + 18}" y="{y + 28}" class="mono">Commits en {today.year}</text>
<text x="{M + bw - 18}" y="{y + 76}" class="mono small" text-anchor="end">contribuciones por mes</text>
<text x="{M + 16}" y="{y + 76}" class="big xl">{fmt(d["commits"])}</text>
{"".join(cols)}''')
    sx0 = M + bw + gap
    sw, sh = (tw - bw - gap - 2 * gap) / 3, (bh - gap) / 2
    small = [("Pull requests", d["prs"]), ("Issues", d["issues"]), ("Revisiones", d["reviews"]),
             ("Repositorios", d["repos"]), ("Estrellas", d["stars"]), ("Seguidores", d["followers"])]
    for i, (label, val) in enumerate(small):
        x, ty = sx0 + (i % 3) * (sw + gap), y + (i // 3) * (sh + gap)
        out.append(f'<rect x="{x:.1f}" y="{ty:.1f}" width="{sw:.1f}" height="{sh:.1f}" rx="12" class="tile"/>'
                   f'<text x="{x + 16:.1f}" y="{ty + 26:.1f}" class="mono">{label}</text>'
                   f'<text x="{x + 15:.1f}" y="{ty + 68:.1f}" class="big">{fmt(val)}</text>')

    # Racha: anillo (actual frente a la más larga) y los totales al lado
    y = 752
    r, rcx, rcy = 46, M + 50, y + 74
    circ = 2 * math.pi * r
    pct = cur / best if best else 0
    out.append(f'''
<text x="{M}" y="{y}" class="mono">Racha</text>
<circle cx="{rcx}" cy="{rcy}" r="{r}" fill="none" class="track" stroke-width="6"/>
<circle class="ring" cx="{rcx}" cy="{rcy}" r="{r}" fill="none" stroke-width="6" stroke-linecap="round"
  stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ * (1 - pct):.1f}" style="--c:{circ:.1f}px" transform="rotate(-90 {rcx} {rcy})"/>
<text x="{rcx}" y="{rcy + 8}" text-anchor="middle" class="big">{cur}</text>
<text x="{rcx}" y="{rcy + 26}" text-anchor="middle" class="mono small">{plural(cur, "día", "días")}</text>
<text x="{M + 122}" y="{rcy - 14}" class="mono">más larga</text>
<text x="{M + 122}" y="{rcy + 6}" class="body"><tspan class="num">{best}</tspan> {plural(best, "día", "días")} seguidos</text>
<text x="{M + 122}" y="{rcy + 34}" class="mono">desde {d["since"]}</text>
<text x="{M + 122}" y="{rcy + 54}" class="body"><tspan class="num">{fmt(sum(c for _, c in days))}</tspan> contribuciones</text>''')

    # Lenguajes: una barra por lenguaje, con su color real
    lx = M + 420
    lw = W - M - lx
    langs = sorted(d["langs"].items(), key=lambda kv: -kv[1][0])[:6]
    lsum = sum(v[0] for _, v in langs) or 1
    out.append(f'<text x="{lx}" y="{y}" class="mono">Lenguajes en repositorios públicos</text>')
    for i, (name, (size, color)) in enumerate(langs):
        p, ry = size / lsum, y + 26 + i * 25
        out.append(f'<text x="{lx}" y="{ry}" class="mono ink">{escape(name)}</text>'
                   f'<text x="{W - M}" y="{ry}" class="mono" text-anchor="end">{p * 100:.1f}%</text>'
                   f'<rect x="{lx}" y="{ry + 6}" width="{lw}" height="4" rx="2" class="zero"/>'
                   f'<rect class="seg" style="animation-delay:{2.7 + i * .08:.2f}s" x="{lx}" y="{ry + 6}" width="{max(lw * p, 4):.1f}" height="4" rx="2" fill="{color}"/>')

    # Stack: iconos reales, sin animación; el hueco entre iconos se calcula para llegar justo al margen derecho
    y, size, group_gap, n, x = 960, 30, 26, 0, M
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
  .bar{{fill:{t["bar"]}}} .zero{{fill:{t["faint"]}}} .acc,.head{{fill:{t["accent"]}}}
  .track{{stroke:{t["faint"]}}} .ring{{stroke:{t["accent"]};animation:ring 1.6s cubic-bezier(.16,1,.3,1) 2.6s both}}
  .big{{font:800 30px Bric,'Segoe UI',system-ui,sans-serif;fill:{t["ink"]}}} .small{{font-size:9px}} .xl{{font-size:44px}}
  .tile{{fill:{t["tile"]};stroke:{t["edge"]}}}
  .col{{transform-box:fill-box;transform-origin:bottom;animation:grow .9s cubic-bezier(.16,1,.3,1) both}}
  .up{{animation:up .9s cubic-bezier(.16,1,.3,1) both}}
  .fade{{animation:fade .8s ease-out both}}
  .sweep{{transform-box:fill-box;transform-origin:left;animation:sweep 1.8s cubic-bezier(.65,0,.35,1) .85s both}}
  .head{{opacity:0;animation:head 1.8s cubic-bezier(.65,0,.35,1) .85s both}}
  .seg{{transform-box:fill-box;transform-origin:left;animation:sweep 1s cubic-bezier(.16,1,.3,1) both}}
  @keyframes up{{from{{transform:translateY(72px)}}}}
  @keyframes fade{{from{{opacity:0}}}}
  @keyframes ring{{from{{stroke-dashoffset:var(--c)}}}}
  @keyframes sweep{{from{{transform:scaleX(0)}}}}
  @keyframes grow{{from{{transform:scaleY(0)}}}}
  @keyframes head{{0%{{opacity:1;transform:translateX(0)}}92%{{opacity:1}}100%{{opacity:0;transform:translateX({tw - 28}px)}}}}
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
