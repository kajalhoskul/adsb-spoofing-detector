"""Streaming spoofing detector: evaluates each incoming report against the
last TRUSTED (non-flagged, confirmed) report for that aircraft.

Two design choices, both matching how a real production system would
behave, not just what makes the demo numbers look good:

1. A flagged report never becomes the new reference frame -- otherwise a
   single accepted spoof would silently reset what "normal" looks like
   for every report after it.

2. An anomaly must be CONFIRMED on two consecutive reports against the
   same reference before it's raised as a detection. A single flagged
   report is held, not alerted on. This exists because real ADS-B
   position decoding (CPR) has genuine per-fix jitter -- an early version
   of this detector, using a single-sample threshold, had an 11% false
   positive rate on entirely real traffic, all clustered in the 700-1200kt
   range versus the injected attacks' 300,000+kt, i.e. real decoding noise,
   not real anomalies. Requiring confirmation eliminates that without
   loosening the physical thresholds (which would weaken the detector
   against genuine slow-drift attacks).

Usage:
    python detect.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from detector.physics_rules import evaluate

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
IN_PATH = os.path.join(DATA_DIR, "tracks_with_attacks.csv")
OUT_PATH = os.path.join(DATA_DIR, "detection_results.csv")


def main():
    with open(IN_PATH, newline="") as f:
        rows = list(csv.DictReader(f))

    last_trusted = {}
    pending = {}  # icao -> reasons from the previous (unconfirmed) flag
    results = []

    for row in rows:
        icao = row["icao24"]
        curr = {
            "lat": float(row["lat"]), "lon": float(row["lon"]),
            "altitude_ft": float(row["altitude_ft"]), "timestamp": float(row["timestamp"]),
        }

        prev = last_trusted.get(icao)
        if prev is None:
            flagged_now, reasons = False, []
        else:
            result = evaluate(prev, curr)
            flagged_now, reasons = result.flagged, result.reasons

        confirmed = flagged_now and icao in pending

        if flagged_now:
            pending[icao] = reasons
        else:
            last_trusted[icao] = curr
            pending.pop(icao, None)

        results.append({
            **row,
            "flagged": confirmed,
            "reasons": "; ".join(reasons) if flagged_now else "",
            "status": "confirmed" if confirmed else ("pending" if flagged_now else "clean"),
        })

    fieldnames = ["icao24", "timestamp", "lat", "lon", "altitude_ft", "label", "flagged", "reasons", "status"]
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    real_flagged = sum(1 for r in results if r["label"] == "real" and r["flagged"])
    real_total = sum(1 for r in results if r["label"] == "real")
    print(f"Real reports: {real_total}  |  false positives (confirmed): {real_flagged}")
    print()

    # Group by attack episode (icao, label) -- an episode counts as caught
    # if ANY of its messages reached confirmed status.
    episodes = {}
    for r in results:
        if r["label"] == "real":
            continue
        key = (r["icao24"], r["label"])
        episodes.setdefault(key, []).append(r)

    caught = 0
    for (icao, label), episode_rows in episodes.items():
        was_caught = any(r["flagged"] for r in episode_rows)
        caught += was_caught
        status = "CAUGHT" if was_caught else "MISSED"
        reasons = next((r["reasons"] for r in episode_rows if r["reasons"]), "(never flagged)")
        print(f"  [{status}] {icao} {label}: {reasons}")

    print(f"\n{caught}/{len(episodes)} attack episodes caught, "
          f"{real_flagged} false positives out of {real_total} real reports.")
    print(f"Wrote -> {OUT_PATH}")


if __name__ == "__main__":
    main()
