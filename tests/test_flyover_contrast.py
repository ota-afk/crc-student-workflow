"""Flyover's text and icon colours meet WCAG contrast, read straight from style.css.

Each check finds a rule's colour in the real stylesheet, resolves var(--…) from :root, blends
semi-transparent colours over what is behind them, and compares the WCAG ratio with the
minimum: 4.5:1 for normal text, 3:1 for icons and focus rings. Plan ticket A3.
"""

import re
from pathlib import Path

import pytest

_RAW = (Path(__file__).resolve().parents[1] / 'app/assets/flyover/style.css').read_text()
# Comments removed, so a comment above a rule is never read as part of its selector.
CSS = re.sub(r'/\*.*?\*/', '', _RAW, flags=re.DOTALL)
PAPER = (247, 244, 239)  # --flyover-paper, the page behind every semi-transparent layer


def _rule(selector: str) -> str:
    """The body of the first rule whose selector list contains exactly this selector."""
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', CSS):
        # Text before a ';' (like the @import line) is not part of the selector.
        if selector in (s.strip() for s in selectors.split(';')[-1].split(',')):
            return body
    raise AssertionError(f'no CSS rule for {selector!r}')  # fail loudly if a selector moves


def _value(selector: str, prop: str) -> str:
    match = re.search(rf'(?:^|;|\s){re.escape(prop)}\s*:\s*([^;!]+)', _rule(selector))
    assert match, f'{selector!r} has no {prop}'
    value = match.group(1).strip()
    if var := re.fullmatch(r'var\((--[\w-]+)\)', value):
        value = re.search(rf'{var.group(1)}\s*:\s*([^;]+);', _rule(':root')).group(1).strip()
    return value


def _rgb(value: str, behind: tuple[int, int, int] = PAPER) -> tuple[int, ...]:
    """#rrggbb or rgba(r,g,b,a); an alpha colour is blended over `behind`."""
    if value.startswith('#'):
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    *channels, alpha = (float(x) for x in re.findall(r'[\d.]+', value))
    return tuple(round(c * alpha + b * (1 - alpha)) for c, b in zip(channels, behind))


def _ratio(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    def luminance(color):
        linear = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
                  for v in (c / 255 for c in color)]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


HEADER = '.st-key-flyover_header'
QUOTE = '.fly-quote'

# (what, foreground selector, property, background selector or None for the step card, minimum)
CHECKS = [
    ('AI button text', '.st-key-flyover_ai button', 'color', HEADER, 4.5),
    ('settings icon', '.st-key-flyover_settings button [data-testid="stIconMaterial"]', 'color',
     HEADER, 3),
    ('header focus ring', '.st-key-flyover_header button:focus-visible', 'outline-color',
     HEADER, 3),
    ('Next button label', '.st-key-flyover_next button', 'color',
     '.st-key-flyover_next button', 4.5),
    ('quote footer', '.fly-quote footer', 'color', QUOTE, 4.5),
    ('step label', '.gate-step', 'color', None, 4.5),
    ('checklist note', '.fly-note', 'color', '.fly-note', 4.5),
    ('demo notice', '.fly-demo-notice', 'color', '.fly-demo-notice', 4.5),
    ('handoff demo line', '.fly-doc .fly-doc-scenario', 'color',
     '.fly-doc .fly-doc-scenario', 4.5),
]


@pytest.mark.parametrize(('what', 'fg', 'prop', 'bg', 'minimum'), CHECKS,
                         ids=[check[0] for check in CHECKS])
def test_colour_pair_meets_wcag_minimum(what, fg, prop, bg, minimum):
    background = (_rgb(_value('.st-key-flyover_gate', 'background')) if bg is None
                  else _rgb(_value(bg, 'background')))
    assert _ratio(_rgb(_value(fg, prop), background), background) >= minimum, what


def test_ai_launcher_hover_ring_meets_wcag_minimum():
    # The logo launcher shows a ring on hover instead of a fill: a UI boundary, so 3:1.
    hover = '.st-key-flyover_ai button:hover'
    ring = _value(hover, 'outline').split()[-1]  # "2.5px solid var(--flyover-ink)"
    ring = re.search(rf'{ring[4:-1]}\s*:\s*([^;]+);', _rule(':root')).group(1).strip()
    header = _rgb(_value(HEADER, 'background'))
    assert _ratio(_rgb(ring), header) >= 3


@pytest.mark.parametrize('selector', ['.stApp h1', '.st-key-flyover_workflow h3'])
def test_headings_meet_the_normal_text_minimum(selector):
    # Deep sage, 6.2:1 on the page: readable at any size, not only because headings are large.
    assert _ratio(_rgb(_value(selector, 'color')), PAPER) >= 4.5


def test_no_text_is_smaller_than_12_5_pixels():
    # 0.78rem = 12.5px at the browser default. font-size:0 (hidden labels) has no unit.
    rem = [float(v) for v in re.findall(r'font-size:\s*([\d.]+)rem', CSS)]
    px = [float(v) for v in re.findall(r'font-size:\s*([\d.]+)px', CSS)]
    assert rem and min(rem) >= 0.78, sorted(rem)[:3]
    assert not px or min(px) >= 12.5, sorted(px)[:3]
