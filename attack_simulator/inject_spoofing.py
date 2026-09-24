"""Injects three synthetic GPS/ADS-B spoofing attacks as CONTINUATIONS of
real decoded aircraft trajectories from data/real_tracks.csv.

No public archive of confirmed real spoofing incidents with raw ADS-B logs
exists to evaluate against, so -- exactly like academic GNSS-spoofing
detection papers do -- this project uses real background traffic with
clearly-labeled injected attacks to measure detection performance. The
underlying flight data (position, altitude, timing) is 100% real, decoded
from real Mode-S transmissions; only the attack continuations below are
synthetic.

Usage:
    python inject_spoofing.py
"""
import csv
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REAL_TRACKS_PATH = os.path.join(DATA_DIR, "real_tracks.csv")
OUT_PATH = os.path.join(DATA_DIR, "tracks_with_attacks.csv")


def load_position_reports():
    by_icao = {}
    with open(REAL_TRACKS_PATH, newline="") as f:
        for row in csv.DictReader(f):
            if row["lat"] and row["lon"] and row["altitude_ft"]:
                by_icao.setdefault(row["icao24"], []).append({
                    "icao24": row["icao24"],
                    "timestamp": float(row["timestamp"]),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "altitude_ft": float(row["altitude_ft"]),
                })
    for icao in by_icao:
        by_icao[icao].sort(key=lambda r: r["timestamp"])
    return by_icao


def make_teleport_attack(last_report):
    """A rogue transmitter (or a rebroadcast of a captured signal from a
    distant location) claims the aircraft is 500km away -- the classic
    GNSS-spoofing "teleport" signature. Broadcast twice in a row (a real
    spoofer transmits continuously, not once), which is also what lets the
    detector's confirmation logic tell this apart from a single noisy
    CPR-decoding fix on genuine traffic."""
    return [
        {**last_report, "timestamp": last_report["timestamp"] + 2,
         "lat": last_report["lat"] + 4.5, "label": "spoof_teleport"},
        {**last_report, "timestamp": last_report["timestamp"] + 3,
         "lat": last_report["lat"] + 4.6, "label": "spoof_teleport"},
    ]


def make_impossible_climb_attack(last_report):
    """Forged altitude jumps far beyond any real aircraft's climb
    performance, sustained over consecutive reports."""
    return [
        {**last_report, "timestamp": last_report["timestamp"] + 1,
         "altitude_ft": last_report["altitude_ft"] + 20000, "label": "spoof_impossible_climb"},
        {**last_report, "timestamp": last_report["timestamp"] + 2,
         "altitude_ft": last_report["altitude_ft"] + 21000, "label": "spoof_impossible_climb"},
    ]


def make_altitude_envelope_attack(last_report):
    """A forged altitude outside the physically possible envelope for
    powered flight entirely -- e.g. a corrupted/malicious payload rather
    than a plausible-looking lie."""
    return [
        {**last_report, "timestamp": last_report["timestamp"] + 1,
         "altitude_ft": 62000, "label": "spoof_altitude_envelope"},
        {**last_report, "timestamp": last_report["timestamp"] + 2,
         "altitude_ft": 62500, "label": "spoof_altitude_envelope"},
    ]


def main():
    by_icao = load_position_reports()
    all_rows = []

    for icao, reports in by_icao.items():
        for r in reports:
            all_rows.append({**r, "label": "real"})

        last = reports[-1]
        all_rows.extend(make_teleport_attack(last))
        all_rows.extend(make_impossible_climb_attack(last))
        all_rows.extend(make_altitude_envelope_attack(last))

    all_rows.sort(key=lambda r: (r["icao24"], r["timestamp"]))

    fieldnames = ["icao24", "timestamp", "lat", "lon", "altitude_ft", "label"]
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    n_attacks = sum(1 for r in all_rows if r["label"] != "real")
    print(f"Wrote {len(all_rows)} reports ({n_attacks} injected attacks across "
          f"{len(by_icao)} real aircraft) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
