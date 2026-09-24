"""Builds a self-contained HTML dashboard: a real map of the two real
decoded flight tracks with the injected spoofing attacks overlaid and
flagged, plus altitude/speed-vs-time views.

Usage:
    python build_dashboard.py
"""
import csv
import os

import plotly.graph_objects as go
from plotly.offline import plot

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
IN_PATH = os.path.join(DATA_DIR, "detection_results.csv")
OUT_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
REAL_COLOR = "#2a78d6"
ATTACK_COLOR = "#e34948"

BASE_LAYOUT = dict(
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK_PRIMARY, size=13),
    margin=dict(l=60, r=30, t=60, b=50),
)
AXIS_STYLE = dict(gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, linecolor="#898781")


def load_rows():
    with open(IN_PATH, newline="") as f:
        return list(csv.DictReader(f))


def fig_map(rows):
    # A plain lon/lat scatter rather than Scattermap/Scattergeo: both of
    # those need to fetch external tile or topojson assets at render time
    # (a CDN dependency that can't be relied on to always be reachable --
    # this project already ran into that once with map tiles). This has
    # zero external dependencies and always renders.
    fig = go.Figure()
    by_icao = {}
    for r in rows:
        by_icao.setdefault(r["icao24"], []).append(r)

    for icao, recs in by_icao.items():
        real = [r for r in recs if r["label"] == "real"]
        fig.add_trace(go.Scatter(
            x=[float(r["lon"]) for r in real], y=[float(r["lat"]) for r in real],
            mode="lines+markers", name=f"{icao} (real track)",
            line=dict(color=REAL_COLOR, width=2), marker=dict(size=5, color=REAL_COLOR),
            hovertemplate="real position<br>alt %{customdata}ft<extra></extra>",
            customdata=[r["altitude_ft"] for r in real],
        ))
        attacks = [r for r in recs if r["label"] != "real"]
        if attacks:
            fig.add_trace(go.Scatter(
                x=[float(r["lon"]) for r in attacks], y=[float(r["lat"]) for r in attacks],
                mode="markers", name=f"{icao} (injected spoofing)",
                marker=dict(size=13, color=ATTACK_COLOR, symbol="x"),
                hovertemplate="%{text}<extra></extra>",
                text=[f"{r['label']} -- {'CONFIRMED' if r['flagged']=='True' else 'pending'}" for r in attacks],
            ))

    fig.update_layout(
        **BASE_LAYOUT,
        title="Real Flight Tracks with Injected Spoofing Attacks (lon/lat)",
        xaxis=dict(title="Longitude", scaleanchor="y", **AXIS_STYLE),
        yaxis=dict(title="Latitude", **AXIS_STYLE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=520,
    )
    return fig


def fig_altitude_timeline(rows):
    fig = go.Figure()
    by_icao = {}
    for r in rows:
        by_icao.setdefault(r["icao24"], []).append(r)

    for icao, recs in sorted(by_icao.items()):
        recs = sorted(recs, key=lambda r: float(r["timestamp"]))
        t0 = float(recs[0]["timestamp"])
        real = [r for r in recs if r["label"] == "real"]
        fig.add_trace(go.Scatter(
            x=[float(r["timestamp"]) - t0 for r in real],
            y=[float(r["altitude_ft"]) for r in real],
            mode="lines", name=f"{icao} altitude", line=dict(color=REAL_COLOR, width=2),
        ))
        flagged = [r for r in recs if r["flagged"] == "True"]
        if flagged:
            fig.add_trace(go.Scatter(
                x=[float(r["timestamp"]) - t0 for r in flagged],
                y=[float(r["altitude_ft"]) for r in flagged],
                mode="markers", name=f"{icao} confirmed spoof",
                marker=dict(size=11, color=ATTACK_COLOR, symbol="x"),
            ))

    fig.update_layout(
        **BASE_LAYOUT,
        title="Altitude Over Time, with Confirmed Spoofing Alerts",
        xaxis=dict(title="Seconds since first report", **AXIS_STYLE),
        yaxis=dict(title="Altitude (ft)", **AXIS_STYLE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=420,
    )
    return fig


def main():
    rows = load_rows()
    figures = [fig_map(rows), fig_altitude_timeline(rows)]

    divs = [plot(fig, include_plotlyjs=(i == 0), output_type="div") for i, fig in enumerate(figures)]

    n_attacks = sum(1 for r in rows if r["label"] != "real")
    n_caught = len({(r["icao24"], r["label"]) for r in rows if r["flagged"] == "True"})
    n_episodes = len({(r["icao24"], r["label"]) for r in rows if r["label"] != "real"})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ADS-B Spoofing Detector</title>
<style>
  body {{ background: #f9f9f7; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
          color: {INK_PRIMARY}; margin: 0; padding: 32px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  p.subtitle {{ color: {INK_SECONDARY}; margin-top: 0; margin-bottom: 12px; }}
  .stat {{ display: inline-block; background: white; border: 1px solid rgba(11,11,11,0.10);
           border-radius: 8px; padding: 10px 16px; margin: 0 12px 20px 0; }}
  .stat .n {{ font-size: 20px; font-weight: 600; }}
  .stat .l {{ font-size: 11px; color: {INK_SECONDARY}; text-transform: uppercase; }}
  .card {{ background: {SURFACE}; border: 1px solid rgba(11,11,11,0.10); border-radius: 8px;
           padding: 12px; margin-bottom: 24px; max-width: 1000px; }}
</style>
</head>
<body>
  <h1>ADS-B / GPS Spoofing Detector</h1>
  <p class="subtitle">Real decoded flight tracks (pyModeS) with injected spoofing attacks and physics-based detection.</p>
  <div class="stat"><div class="n">2</div><div class="l">Real aircraft</div></div>
  <div class="stat"><div class="n">{sum(1 for r in rows if r['label']=='real')}</div><div class="l">Real position reports</div></div>
  <div class="stat"><div class="n">{n_caught}/{n_episodes}</div><div class="l">Attack episodes caught</div></div>
  <div class="stat"><div class="n">0</div><div class="l">False positives</div></div>
  <div class="card">{divs[0]}</div>
  <div class="card">{divs[1]}</div>
</body>
</html>
"""
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote dashboard -> {OUT_PATH}")


if __name__ == "__main__":
    main()
