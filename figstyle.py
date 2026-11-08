"""Figure style matching Auro's front end (task T32): the values are copied from web/public/styles.css (light theme),
the reference named in CLAUDE.md, so the figures sit beside the extension and the account site as one design.

A white card (#ffffff) with ink #17171c text, muted #6a6a75 labels and #e5e4e0 lines; the system sans-serif face
(Segoe UI on Windows, as the front end's font stack resolves there); data series in the ring colours #7c5cff, #3ec9ff,
#ff6ad5, then muted grey; green #16a34a, amber #d97706 and red #dc2626 are kept for good, caution and over-budget
states only; solid bars with rounded corners; no grid lines; frameless legends. Same names as the parts of TeXFormat
the scripts used (CYCLE, fontsize, fontsizeSmall, fontsizeTiny, bar), so a script switches with one import.

    import figstyle as fs
    fs.use()                       # once, before any figure is made
    fs.bar(ax, x, heights, fs.CYCLE[0], label="...")
    fs.save(fig, Path("Figures/x/name"))   # name.pdf and name.svg
"""
from pathlib import Path

BG, CARD, INK, MUTED, LINE = "#f7f7f5", "#ffffff", "#17171c", "#6a6a75", "#e5e4e0"  # styles.css :root
ACCENT, GOOD, WARN, BAD = "#6d4aff", "#16a34a", "#d97706", "#dc2626"
C1, C2, C3 = "#7c5cff", "#3ec9ff", "#ff6ad5"  # the ring gradient
CYCLE = [C1, C2, C3, MUTED]
FONTS = ["Segoe UI", "Roboto", "Helvetica Neue", "Arial", "DejaVu Sans"]  # styles.css font stack, as installed fonts
fontsize, fontsizeSmall, fontsizeTiny = 15, 14, 12


def use():
    """Apply the style to Matplotlib's rcParams (no LaTeX: text in the front end's sans-serif)."""
    import matplotlib as mpl
    mpl.rcParams.update({
        "text.usetex": False, "font.family": "sans-serif", "font.sans-serif": FONTS, "font.size": fontsize,
        "mathtext.fontset": "custom", "mathtext.rm": FONTS[0], "mathtext.it": FONTS[0], "mathtext.bf": FONTS[0],
        "text.color": INK, "axes.labelcolor": MUTED, "axes.titlecolor": INK, "axes.titleweight": "semibold",
        "axes.titlesize": fontsize + 1, "axes.titlelocation": "left", "axes.titlepad": 12,
        "axes.labelsize": fontsizeSmall, "axes.edgecolor": LINE, "axes.linewidth": 1.0,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
        "axes.prop_cycle": mpl.cycler(color=CYCLE), "axes.facecolor": CARD,
        "figure.facecolor": CARD, "savefig.facecolor": CARD, "figure.dpi": 100,
        "xtick.color": LINE, "ytick.color": LINE, "xtick.labelcolor": MUTED, "ytick.labelcolor": MUTED,
        "xtick.labelsize": fontsizeSmall, "ytick.labelsize": fontsizeSmall,
        "xtick.major.size": 4, "ytick.major.size": 4,
        "legend.frameon": False, "legend.fontsize": fontsizeSmall, "legend.labelcolor": INK,
        "lines.linewidth": 2.2, "lines.solid_capstyle": "round", "errorbar.capsize": 3,
        "svg.fonttype": "path", "pdf.fonttype": 42,  # SVG text as outlines for Illustrator; embedded fonts in PDF
    })


SOURCE = "Synthetic data for 100 example customers, generated from ONS and FCA statistics. Not real customers."


def headline(fig, title, subtitle=None, source=SOURCE):
    """Marketing layout: a bold headline and a muted subtitle top left, a small source line bottom left."""
    fig.subplots_adjust(top=0.80 if subtitle else 0.86, bottom=0.16)
    fig.text(0.01, 0.97, title, ha="left", va="top", fontsize=22, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, 0.895, subtitle, ha="left", va="top", fontsize=14, color=MUTED)
    if source:
        fig.text(0.01, 0.015, source, ha="left", va="bottom", fontsize=10.5, color=MUTED)


def clean(ax, grid="y"):
    """Light dashboard axes: faint guide lines behind the data, no left spine, no tick marks."""
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0, pad=6)
    if grid:
        ax.grid(axis=grid, color=LINE, linewidth=1)
        ax.set_axisbelow(True)


def gbp(ax, axis="y", decimals=0):
    """Pound amounts on an axis: £1,250."""
    from matplotlib.ticker import FuncFormatter
    f = FuncFormatter(lambda v, _: f"{'-' if v < 0 else ''}£{abs(v):,.{decimals}f}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def tint(color, alpha):
    """The colour mixed with white (a solid lighter shade, so bars stay opaque)."""
    from matplotlib.colors import to_rgb
    return tuple(1 - alpha * (1 - c) for c in to_rgb(color))


def bar(ax, x, height, color, width=0.8, gap=0.12, **kw):
    """Solid bars with rounded corners and a gap between neighbours. ponytail: corners are rounded by a round-joined
    outline in the bar's own colour (radius about 1.5 pt), not a true rounded rectangle; upgrade with FancyBboxPatch."""
    kw.setdefault("error_kw", {})
    kw["error_kw"] = {"ecolor": INK, "elinewidth": 1.2, "capthick": 1.2} | kw["error_kw"]
    return ax.bar(x, height, width=width * (1 - gap), color=color, edgecolor=color, linewidth=3, joinstyle="round", **kw)


def save(fig, stem):
    """stem.pdf and stem.svg with no creation dates (reruns give the same SVG)."""
    import matplotlib.pyplot as plt
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg"):
        fig.savefig(stem.with_suffix(f".{ext}"), bbox_inches="tight",
                    metadata={"pdf": {"CreationDate": None}, "svg": {"Date": None}}[ext])
    plt.close(fig)


def sha():
    """Short hash of this file, for figure provenance."""
    import hashlib
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
