"""Decodes REAL raw ADS-B (Mode S extended squitter) messages into real
aircraft trajectories (timestamp, ICAO24, latitude, longitude, altitude,
ground speed), using pyModeS -- the actual decoder library used in
aviation research (Junzi Sun / TU Delft).

The two raw message logs in data/raw/ are real, unmodified recordings of
actual air traffic, sourced from:
  - junzis_modes_tutorials_samples.csv
    https://github.com/junzis/modes-tutorials (data/samples.csv)
  - pymodes_sample_data_adsb.csv
    https://github.com/junzis/pyModeS (tests/data/sample_data_adsb.csv)

Nothing about the underlying flight data is synthetic; only the spoofing
ATTACK injected later (attack_simulator/inject_spoofing.py) is simulated,
because no public archive of confirmed real spoofing incidents with raw
ADS-B logs exists to train or evaluate against.

Usage:
    python decode_real_tracks.py
"""
import csv
import os

import pyModeS as pms

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
OUT_PATH = os.path.join(DATA_DIR, "real_tracks.csv")


def load_raw_messages(path):
    """Both source files use a slightly different column layout; this
    normalizes to a (timestamp, message_hex) stream of DF17 long
    ADS-B extended squitter frames."""
    messages = []
    with open(path, newline="") as f:
        for row in csv.reader(f):
            ts = float(row[0])
            msg = row[1].strip().strip('"')
            if len(msg) == 28:
                messages.append((ts, msg))
    return messages


def decode_positions(messages):
    """CPR position decoding needs an even/odd frame pair from the SAME
    aircraft within a short window -- the standard ADS-B position
    algorithm, not an approximation."""
    by_icao_even = {}
    by_icao_odd = {}
    rows = []

    for ts, msg in messages:
        if pms.df(msg) != 17:
            continue
        icao = pms.icao(msg)
        tc = pms.typecode(msg)
        if tc is None:
            continue

        if 9 <= tc <= 18:  # airborne position
            oe = pms.adsb.oe_flag(msg)
            if oe == 0:
                by_icao_even[icao] = (ts, msg)
            else:
                by_icao_odd[icao] = (ts, msg)

            even = by_icao_even.get(icao)
            odd = by_icao_odd.get(icao)
            if even and odd and abs(even[0] - odd[0]) < 10:
                pos = pms.adsb.airborne_position(even[1], odd[1], even[0], odd[0])
                if pos:
                    alt_ft = pms.adsb.altitude(msg)
                    rows.append({
                        "icao24": icao, "timestamp": ts,
                        "lat": pos[0], "lon": pos[1], "altitude_ft": alt_ft,
                        "source": "real",
                    })

        elif tc == 19:  # airborne velocity
            velocity = pms.adsb.velocity(msg)
            if velocity:
                speed_kt, heading, vrate, _ = velocity
                rows.append({
                    "icao24": icao, "timestamp": ts,
                    "ground_speed_kt": speed_kt, "heading_deg": heading,
                    "vertical_rate_fpm": vrate, "source": "real",
                })

    return rows


def main():
    all_rows = []
    for filename in sorted(os.listdir(RAW_DIR)):
        path = os.path.join(RAW_DIR, filename)
        messages = load_raw_messages(path)
        rows = decode_positions(messages)
        print(f"{filename}: {len(messages)} DF17 messages -> {len(rows)} decoded reports")
        all_rows.extend(rows)

    all_rows.sort(key=lambda r: (r["icao24"], r["timestamp"]))

    fieldnames = ["icao24", "timestamp", "lat", "lon", "altitude_ft",
                  "ground_speed_kt", "heading_deg", "vertical_rate_fpm", "source"]
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    aircraft = sorted({r["icao24"] for r in all_rows})
    print(f"\nDecoded {len(all_rows)} real reports across {len(aircraft)} real aircraft: {aircraft}")
    print(f"Wrote -> {OUT_PATH}")


if __name__ == "__main__":
    main()
