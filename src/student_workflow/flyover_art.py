"""Local artwork and decorative flight-map markup. No student data is cached."""

import base64
import math
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / 'app/assets/flyover'


@lru_cache(maxsize=6)
def asset_data(name: str) -> str:
    return 'data:image/png;base64,' + base64.b64encode((ASSETS / name).read_bytes()).decode()


def logo() -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1888 832" role="img" aria-label="Flyover"><rect width="1888" height="832" fill="#E6CCBE"/><image href="{asset_data("logo-peach.png")}" width="1888" height="832"/></svg>'


def banner() -> str:
    return '<div class="flyover-slides" aria-hidden="true">' + ''.join(
        f'<div class="flyover-slide slide-{index}" style="background-image:url({asset_data(name)})">'
        f'<span>{label}</span></div>' for index, (name, label) in enumerate([
            ('tokyo.png', 'Shibuya, Tokyo'), ('san-francisco.png', 'San Francisco Bay'),
            ('las-vegas.png', 'Las Vegas, Nevada'),
        ])
    ) + '</div>'


def flight_map(pieces: float, animate: bool = True, previous: float = 0) -> str:
    land = '''<path d="M60 70L105 36 184 26 230 43 270 35 302 65 267 86 242 92 220 121
      180 113 158 145 122 126 102 99 64 97Z M190 153L230 152 254 185 250 208 223 251
      207 237 198 203 180 177Z M370 32L415 19 442 38 418 68 386 66Z
      M500 81L527 48 566 45 595 70 614 82 594 102 557 104 540 124 510 115Z
      M534 127L572 116 607 141 619 171 598 203 571 230 550 219 535 184 510 158Z
      M601 58L665 36 726 40 773 24 850 42 898 53 950 44 1022 66 1061 88 1025 114
      985 113 945 136 917 116 883 149 851 136 832 163 813 144 780 139 755 107
      718 113 688 97 657 107 622 92Z M737 126L765 134 778 160 759 181 747 165Z
      M851 171L872 182 881 204 861 199Z M887 211L937 189 988 196 1005 229
      971 250 918 244 892 232Z M1032 230L1048 243 1040 256 1022 252Z"/>
      <path d="M206 100 Q470 0 820 105 Q970 150 956 223" fill="none" stroke="#777DA7"
        stroke-width="2.5" stroke-dasharray="7 9"/>
      <circle cx="206" cy="100" r="7"/><circle cx="820" cy="105" r="7"/>
      <circle cx="956" cy="223" r="7"/>'''
    clips = [
        'M0 0H400V95C430 75 442 105 426 117C415 126 405 121 400 119V280H0Z',
        'M400 0H800V174C830 154 841 185 826 197C815 206 805 201 800 199V280H400V119C405 121 415 126 426 117C442 105 430 75 400 95Z',
        'M800 0H1200V280H800V199C805 201 815 206 826 197C841 185 830 154 800 174Z',
    ]
    groups = []
    for index in range(3):
        fraction = max(0, min(1, pieces - index))
        before = max(0, min(1, previous - index))
        # Clip the visible portion within each interlocking puzzle silhouette.
        right = 100 - ((index * 400 + fraction * 440) / 1200 * 100)
        old_right = 100 - ((index * 400 + before * 440) / 1200 * 100)
        moving = animate and fraction > before
        shape = f'<path d="{clips[index]}" fill="#E5EDDF" stroke="#629677" stroke-width="2"/>{land}'
        groups.append(f'<g clip-path="url(#piece-{index})" opacity=".10">{shape}</g>')
        if fraction:
            groups.append(f'<g clip-path="url(#piece-{index})"><g class="reveal-{index}" '
                          f'style="clip-path:inset(0 {right}% 0 0);opacity:.68;'
                          f'animation:{"reveal" + str(index) + " .9s ease-out both" if moving else "none"}">{shape}</g></g>')
        groups.append(f'<style>@keyframes reveal{index}{{from{{clip-path:inset(0 {old_right}% 0 0)}}'
                      f'to{{clip-path:inset(0 {right}% 0 0)}}}}</style>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 280" fill="#629677">
      <style>@media(prefers-reduced-motion:reduce){{g{{animation:none!important}}}}</style>
      <defs>{"".join(f'<clipPath id="piece-{i}"><path d="{path}"/></clipPath>' for i, path in enumerate(clips))}</defs>
      {"".join(groups)}</svg>'''
    encoded = base64.b64encode(svg.encode()).decode()
    return f'<div class="flight-map" style="background-image:url(data:image/svg+xml;base64,{encoded})" aria-hidden="true"></div>'


# ---- Low-poly airplane for the scroll-over scene (flat facets, Flyover palette) ----

_INK = '#28323C'
_SAGE = '#629677'


def _mix(a: str, b: str, t: float) -> str:
    one = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    two = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(x + (y - x) * t):02X}' for x, y in zip(one, two, strict=True))


def _poly(points, fill: str) -> str:
    return '<polygon points="' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in points) + f'" fill="{fill}"/>'


def _ring(cx: float, cy: float, r: float, n: int, rot: float = 0) -> list[tuple[float, float]]:
    return [(cx + r * math.sin(math.radians(rot + 360 * k / n)),
             cy - r * math.cos(math.radians(rot + 360 * k / n))) for k in range(n + 1)]


def _nearest(table, angle: float) -> str:
    return min(table, key=lambda item: abs(((angle - item[0] + 180) % 360) - 180))[1]


_BODY = [(15, '#F6F5FB'), (45, '#E8E9F3'), (75, '#D5D8EA'), (105, '#C2C6E0'), (135, '#6FA283'),
         (165, '#5C9070'), (195, '#4F8062'), (225, '#5E9172'), (255, '#CBCEE4'), (285, '#DEE0EF'),
         (315, '#EDEEF7'), (345, '#FBFBFE')]
_NACELLE = [(18, '#F4F4FA'), (54, '#E4E6F2'), (90, '#CBCEE4'), (126, '#B3B8D6'), (162, '#A2A8CB'),
            (198, '#9AA0C5'), (234, '#B8BDD9'), (270, '#D2D5E8'), (306, '#E6E8F3'), (342, '#F7F7FC')]


def _facets(cx, cy, r, n, colour, rot=0) -> str:
    v = _ring(cx, cy, r, n, rot)
    return ''.join(_poly([(cx, cy), v[k], v[k + 1]], colour((rot + 360 * (k + .5) / n) % 360))
                   for k in range(n))


def _wing(shade: float) -> str:
    def s(colour: str) -> str:
        return _mix(colour, _INK, shade)
    return (_poly([(230, 252), (50, 226), (46, 240), (230, 282)], s('#DADCEC'))
            + _poly([(230, 252), (50, 226), (62, 232), (230, 264)], s('#F0F0F8'))
            + _poly([(230, 282), (46, 240), (52, 246), (230, 290)], s('#A9AECB'))
            + _poly([(50, 226), (40, 198), (60, 224)], s('#8A90B8')))


def _engine(cx: float, cy: float, shade: float) -> str:
    def s(colour: str) -> str:
        return _mix(colour, _INK, shade)
    out = _poly([(cx - 8, cy - 40), (cx + 8, cy - 40), (cx + 12, cy - 22), (cx - 12, cy - 22)], s('#C6CAE0'))
    out += _facets(cx, cy, 42, 10, lambda a: s(_nearest(_NACELLE, a)))
    out += _poly(_ring(cx, cy, 34, 10)[:-1], s(_SAGE)) + _poly(_ring(cx, cy, 29, 10)[:-1], _INK)
    blades = _ring(cx, cy, 29, 10)
    out += ''.join(_poly([(cx, cy), blades[k], blades[k + 1]], '#3B4856' if k % 2 else '#222B34')
                   for k in range(10))
    return out + _poly(_ring(cx, cy, 7, 6)[:-1], '#D7D9EA')


@lru_cache(maxsize=1)
def plane_svg() -> str:
    """A front-on jet; its windshield sits at 37.6% of the height, the zoom's anchor."""
    parts = [
        _poly([(291, 58), (309, 58), (314, 142), (286, 142)], '#C9CCE3'),
        _poly([(291, 58), (300, 58), (300, 142), (286, 142)], '#E6E7F2'),
        _poly([(291, 58), (309, 58), (310, 74), (290, 74)], _SAGE),
        f'<g>{_wing(0)}</g>', f'<g transform="translate(600,0) scale(-1,1)">{_wing(.12)}</g>',
        _engine(158, 276, 0), _engine(442, 276, .1),
        _facets(300, 215, 80, 12, lambda a: _nearest(_BODY, a)),
        _facets(300, 226, 38, 6, lambda a: _mix(_nearest(_BODY, a), '#FFFFFF', .35), rot=30),
        _poly([(258, 152), (342, 152), (334, 184), (266, 184)], _INK),
        _poly([(262, 156), (286, 156), (270, 178)], '#5B6B7C'),
        _poly([(298, 156), (318, 156), (306, 178)], '#3B4856'),
        _poly([(298, 152), (302, 152), (302, 184), (298, 184)], '#E8E9F3'),
    ]
    for x in (262, 338):
        parts += [f'<rect x="{x - 2.5}" y="285" width="5" height="48" fill="{_INK}"/>',
                  f'<rect x="{x - 12}" y="326" width="9" height="26" rx="3" fill="{_INK}"/>',
                  f'<rect x="{x + 3}" y="326" width="9" height="26" rx="3" fill="{_INK}"/>']
    parts += [f'<rect x="297.5" y="296" width="5" height="40" fill="{_INK}"/>',
              f'<rect x="289" y="330" width="9" height="22" rx="3" fill="{_INK}"/>',
              f'<rect x="302" y="330" width="9" height="22" rx="3" fill="{_INK}"/>']
    return ('<svg viewBox="0 40 600 340" xmlns="http://www.w3.org/2000/svg">'
            + ''.join(parts) + '</svg>')


_CLOUD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 80">'
          '<polygon points="8,72 10,52 40,42 60,22 92,14 120,26 142,18 170,32 192,52 194,72" fill="#fff"/>'
          '<polygon points="8,72 10,60 194,60 194,72" fill="#E4E5F1"/></svg>')


def _svg_src(svg: str) -> str:
    # st.html strips inline <svg>, so the art travels as an image data URL.
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


def flight_scene(static: bool) -> str:
    """Scroll-over scene. CSS scroll timelines drive it; no script is needed."""
    cloud = _svg_src(_CLOUD)
    clouds = ''.join(f'<img class="fly-cloud fly-cloud-{n}" src="{cloud}" alt="">' for n in range(5))
    return (
        f'<div class="fly-runway{" is-static" if static else ""}"><div class="fly-stage">'
        f'<div class="fly-sky">{clouds}'
        '<p class="fly-msg">You’re ready to go. <span>Let’s get your professional up to speed.</span></p>'
        f'<div class="fly-plane"><div class="fly-plane-inner"><img src="{_svg_src(plane_svg())}" '
        'alt="A low-poly airplane flying toward you"></div></div>'
        '<div class="fly-hint">Scroll to fly</div></div>'
        '<div class="fly-reveal"><div class="fly-reveal-inner" id="airshow">'
        '<h2>Meet <span>Airshow</span>, your AI assistant.</h2>'
        '<p>Tell Airshow what you want to get done and who you’re seeing. It drafts a handoff '
        'you can share and the questions worth asking.</p></div></div>'
        '</div></div>'
    )
