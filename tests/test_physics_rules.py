"""Unit tests for the physics rules in detector/physics_rules.py.

Each rule is tested just inside and just outside its limit, so a change to
a threshold or a unit conversion shows up as a failing test.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from detector.physics_rules import (  # noqa: E402
    EARTH_RADIUS_KM,
    MAX_ALTITUDE_FT,
    MAX_GROUND_SPEED_KT,
    MAX_VERTICAL_RATE_FPM,
    MIN_ALTITUDE_FT,
    evaluate,
    haversine_km,
    implied_ground_speed_kt,
    implied_vertical_rate_fpm,
)

KM_PER_KT_HOUR = 1 / 0.539957  # 1 knot = 1.852 km/h


def report(lat=52.0, lon=4.0, altitude_ft=35000, timestamp=0.0):
    return {"lat": lat, "lon": lon, "altitude_ft": altitude_ft, "timestamp": timestamp}


def report_after(prev, speed_kt, seconds, altitude_ft=None):
    """A report due north of `prev`, reached by flying at `speed_kt`."""
    km = speed_kt * KM_PER_KT_HOUR * seconds / 3600.0
    dlat = math.degrees(km / EARTH_RADIUS_KM)
    return report(
        lat=prev["lat"] + dlat,
        lon=prev["lon"],
        altitude_ft=prev["altitude_ft"] if altitude_ft is None else altitude_ft,
        timestamp=prev["timestamp"] + seconds,
    )


# --- helpers ---------------------------------------------------------------

def test_haversine_one_degree_of_latitude():
    # One degree along a meridian is 2*pi*R/360, about 111.19 km.
    assert haversine_km(0, 0, 1, 0) == pytest.approx(2 * math.pi * EARTH_RADIUS_KM / 360)


def test_haversine_same_point_is_zero():
    assert haversine_km(52.3, 4.8, 52.3, 4.8) == 0


def test_ground_speed_matches_constructed_track():
    prev = report()
    curr = report_after(prev, speed_kt=450, seconds=60)
    speed = implied_ground_speed_kt(prev["lat"], prev["lon"], prev["timestamp"],
                                    curr["lat"], curr["lon"], curr["timestamp"])
    assert speed == pytest.approx(450, rel=1e-3)


@pytest.mark.parametrize("dt", [0, -5])
def test_ground_speed_undefined_without_forward_time(dt):
    assert implied_ground_speed_kt(52, 4, 100, 53, 4, 100 + dt) is None


@pytest.mark.parametrize("dt", [0, -5])
def test_vertical_rate_undefined_without_forward_time(dt):
    assert implied_vertical_rate_fpm(30000, 100, 31000, 100 + dt) is None


def test_vertical_rate_sign_follows_direction():
    assert implied_vertical_rate_fpm(30000, 0, 31000, 60) == pytest.approx(1000)
    assert implied_vertical_rate_fpm(31000, 0, 30000, 60) == pytest.approx(-1000)


# --- ground speed rule -----------------------------------------------------

def test_normal_cruise_is_not_flagged():
    prev = report()
    result = evaluate(prev, report_after(prev, speed_kt=480, seconds=10))
    assert not result.flagged
    assert result.reasons == []


def test_speed_just_below_limit_is_not_flagged():
    prev = report()
    assert not evaluate(prev, report_after(prev, MAX_GROUND_SPEED_KT - 5, seconds=10)).flagged


def test_speed_just_above_limit_is_flagged():
    prev = report()
    result = evaluate(prev, report_after(prev, MAX_GROUND_SPEED_KT + 5, seconds=10))
    assert result.flagged
    assert any("ground speed" in r for r in result.reasons)


def test_teleport_attack_is_flagged():
    # The injected attacks jump positions at 300,000+ kt.
    prev = report()
    result = evaluate(prev, report_after(prev, speed_kt=300_000, seconds=1))
    assert result.flagged
    assert any("ground speed" in r for r in result.reasons)


def test_identical_timestamps_do_not_crash_or_flag_speed():
    prev = report(timestamp=100)
    curr = report(lat=53.0, timestamp=100)
    assert evaluate(prev, curr).reasons == []


# --- vertical rate rule ----------------------------------------------------

def test_climb_just_below_limit_is_not_flagged():
    prev = report(altitude_ft=10000)
    curr = report(altitude_ft=10000 + MAX_VERTICAL_RATE_FPM - 100, timestamp=60)
    assert not evaluate(prev, curr).flagged


def test_climb_above_limit_is_flagged():
    prev = report(altitude_ft=10000)
    curr = report(altitude_ft=10000 + MAX_VERTICAL_RATE_FPM + 100, timestamp=60)
    result = evaluate(prev, curr)
    assert result.flagged
    assert any("vertical rate" in r for r in result.reasons)


def test_descent_above_limit_is_flagged():
    prev = report(altitude_ft=30000)
    curr = report(altitude_ft=30000 - MAX_VERTICAL_RATE_FPM - 100, timestamp=60)
    result = evaluate(prev, curr)
    assert result.flagged
    assert any("vertical rate" in r for r in result.reasons)


# --- altitude envelope rule ------------------------------------------------

@pytest.mark.parametrize("altitude", [MIN_ALTITUDE_FT, 0, MAX_ALTITUDE_FT])
def test_altitudes_inside_envelope_are_not_flagged(altitude):
    # Large time gap so the jump to `altitude` stays within the vertical-rate limit.
    prev = report(altitude_ft=altitude)
    curr = report(altitude_ft=altitude, timestamp=60)
    assert not evaluate(prev, curr).flagged


@pytest.mark.parametrize("altitude", [MIN_ALTITUDE_FT - 1, MAX_ALTITUDE_FT + 1])
def test_altitudes_outside_envelope_are_flagged(altitude):
    prev = report(altitude_ft=altitude)
    curr = report(altitude_ft=altitude, timestamp=60)
    result = evaluate(prev, curr)
    assert result.flagged
    assert any("altitude" in r and "envelope" in r for r in result.reasons)


# --- combined --------------------------------------------------------------

def test_multiple_violations_report_every_reason():
    prev = report(altitude_ft=30000)
    curr = report_after(prev, speed_kt=300_000, seconds=1, altitude_ft=60000)
    result = evaluate(prev, curr)
    assert result.flagged
    assert len(result.reasons) == 3
