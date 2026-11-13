# ADS-B / GPS Spoofing Detector

[![CI](https://github.com/kajalhoskul/adsb-spoofing-detector/actions/workflows/ci.yml/badge.svg)](https://github.com/kajalhoskul/adsb-spoofing-detector/actions/workflows/ci.yml)

A physics-based GNSS/ADS-B spoofing detector, built on **real decoded
aircraft trajectories** -- not synthetic data. GNSS spoofing in conflict
zones is a real, growing, and actively-researched aviation security
problem (Aireon and Stanford's GPS Lab have both published detection work
on exactly this). This project decodes real raw Mode-S signals from two
real aircraft using the actual decoder library aviation researchers use,
then demonstrates detection against injected (necessarily synthetic --
see below) spoofing attacks.

## Where the real data comes from

Two raw Mode-S/ADS-B message logs, real and unmodified:

- `data/raw/junzis_modes_tutorials_samples.csv` -- from
  [junzis/modes-tutorials](https://github.com/junzis/modes-tutorials)
  (`data/samples.csv`)
- `data/raw/pymodes_sample_data_adsb.csv` -- from
  [junzis/pyModeS](https://github.com/junzis/pyModeS)
  (`tests/data/sample_data_adsb.csv`)

Both are decoded with **pyModeS** (Junzi Sun / TU Delft's Mode-S decoder,
the real library used in academic ADS-B research) into 2,703 real
position/velocity reports across 2 real aircraft -- one climbing out of
the Amsterdam area toward Frankfurt, the other cruising near the
Netherlands/Germany border. `data_prep/decode_real_tracks.py` does the
actual CPR position decoding (the standard even/odd-frame ADS-B position
algorithm, not an approximation).

**What's synthetic:** only the spoofing attacks themselves. No public
archive of confirmed real spoofing incidents with raw ADS-B logs exists to
evaluate against, so -- the same way academic spoofing-detection papers
do it -- `attack_simulator/inject_spoofing.py` injects three attack types
as continuations of the real tracks, with ground-truth labels for
evaluating the detector.

## The detector

Rule-based, not ML -- this mirrors how real systems like Aireon's actually
work (cross-checking reported positions against what's physically
possible), not a classifier trained on scarce labeled spoofing examples.
Three checks in `detector/physics_rules.py`:

- **Ground speed**: implied speed between consecutive reports (haversine
  distance / time) exceeding 1,300kt
- **Vertical rate**: implied climb/descent exceeding 6,000ft/min
- **Altitude envelope**: outside -1,000ft to 45,000ft

Two design details that came from an actual development problem, not
guesswork:

1. **Confirmation requirement.** An anomaly must appear on two consecutive
   reports before being raised. A first version without this had an 11%
   false-positive rate on entirely real traffic -- all in the 700-1,200kt
   range, versus injected attacks' 300,000+kt. That's real CPR
   position-decoding jitter, not real anomalies. Confirmation eliminated
   it without loosening the physical thresholds. Final result: **0 false
   positives across 1,287 real reports, 6/6 injected attack episodes
   caught**, a 230x+ margin between the noise floor and real attacks.
2. **A flagged report never becomes the new reference frame** -- an
   accepted spoof must never get to redefine what "normal" looks like for
   subsequent reports.

## Running it

```bash
pip install -r requirements.txt
python data_prep/decode_real_tracks.py      # decode real Mode-S -> data/real_tracks.csv
python attack_simulator/inject_spoofing.py  # inject 3 attack types -> data/tracks_with_attacks.csv
python detector/detect.py                   # run the detector -> data/detection_results.csv
python dashboard/build_dashboard.py         # -> dashboard/dashboard.html
```

The dashboard shows both real flight paths with the injected attacks
plotted well off-track, and an altitude-vs-time view with confirmed
detections marked.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests in `tests/` check each physics rule just inside and just outside
its limit. GitHub Actions runs them on Python 3.11 to 3.13 for every push
and pull request.

## Project layout

```
data/raw/                 real raw Mode-S message logs (unmodified)
data_prep/
  decode_real_tracks.py    pyModeS CPR position/velocity decoding
attack_simulator/
  inject_spoofing.py        3 synthetic attacks appended to real tracks
detector/
  physics_rules.py           the plausibility checks
  detect.py                   streaming confirmation-based detector
dashboard/
  build_dashboard.py          Plotly dashboard (lon/lat scatter -- see below)
```

## A note on the map rendering

The dashboard's map is a plain longitude/latitude scatter plot, not a
tile-based map (`Scattermap`/`Scattergeo`). Both of those need to fetch
external tile or topojson assets from a CDN at render time; in a
network-restricted environment (this one included) that fetch silently
fails and the whole panel renders blank. A dependency-free scatter plot
always renders, in any environment.
