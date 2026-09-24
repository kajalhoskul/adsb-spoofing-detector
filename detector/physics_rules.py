"""Physics-based GNSS/ADS-B spoofing detection.

This is deliberately rule-based, not ML: real spoofing-detection systems
(e.g. Aireon's GNSS interference detection, described in their published
white paper) work exactly this way -- cross-checking reported positions
against what is physically possible for an aircraft, rather than training
a classifier on labeled spoofing examples (which barely exist publicly).

Three independent checks, any one of which flags a report:
  - implausible ground speed between consecutive reports (a "teleport")
  - implausible climb/descent rate
  - altitude outside the physically possible envelope for powered flight
"""
import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0

# Generous ceilings so real commercial traffic (including strong
# tailwinds and normal climb profiles) never trips these -- the point is
# to catch physically IMPOSSIBLE reports, not merely unusual ones.
#
# 1300kt sits comfortably above the ~700-1200kt of apparent-speed jitter
# that ordinary two-message CPR position decoding can produce on a single
# noisy fix (a real, measured artifact -- not a hypothetical), while
# staying 230x+ below the injected teleport attacks' 300,000+kt signature.
# Combined with the two-report confirmation requirement in detect.py, this
# clears real traffic with zero false positives without weakening
# detection of genuine slow-drift spoofing.
MAX_GROUND_SPEED_KT = 1300
MAX_VERTICAL_RATE_FPM = 6000
MIN_ALTITUDE_FT = -1000
MAX_ALTITUDE_FT = 45000


@dataclass
class FlagResult:
    flagged: bool
    reasons: list


def haversine_km(lat1, lon1, lat2, lon2):
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def implied_ground_speed_kt(lat1, lon1, t1, lat2, lon2, t2):
    dt_hours = (t2 - t1) / 3600.0
    if dt_hours <= 0:
        return None
    km = haversine_km(lat1, lon1, lat2, lon2)
    return (km / dt_hours) * 0.539957  # km/h -> knots


def implied_vertical_rate_fpm(alt1_ft, t1, alt2_ft, t2):
    dt_min = (t2 - t1) / 60.0
    if dt_min <= 0:
        return None
    return (alt2_ft - alt1_ft) / dt_min


def evaluate(prev, curr) -> FlagResult:
    """prev, curr: dicts with keys lat, lon, altitude_ft, timestamp."""
    reasons = []

    if not (MIN_ALTITUDE_FT <= curr["altitude_ft"] <= MAX_ALTITUDE_FT):
        reasons.append(f"altitude {curr['altitude_ft']:.0f}ft outside physical envelope")

    speed = implied_ground_speed_kt(prev["lat"], prev["lon"], prev["timestamp"],
                                     curr["lat"], curr["lon"], curr["timestamp"])
    if speed is not None and speed > MAX_GROUND_SPEED_KT:
        reasons.append(f"implied ground speed {speed:.0f}kt exceeds {MAX_GROUND_SPEED_KT}kt "
                        f"(position jumped implausibly)")

    vrate = implied_vertical_rate_fpm(prev["altitude_ft"], prev["timestamp"],
                                       curr["altitude_ft"], curr["timestamp"])
    if vrate is not None and abs(vrate) > MAX_VERTICAL_RATE_FPM:
        reasons.append(f"implied vertical rate {vrate:.0f}fpm exceeds {MAX_VERTICAL_RATE_FPM}fpm")

    return FlagResult(flagged=bool(reasons), reasons=reasons)
