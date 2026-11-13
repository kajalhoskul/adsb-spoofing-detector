"""Tests for the two-report confirmation rule in detector/detect.py.

A single anomalous report is held as "pending", and only a second one in a
row is raised as "confirmed". This is what took the false-positive rate on
real traffic from 11% to 0, so these tests pin the behaviour down.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from detector.detect import ConfirmationTracker  # noqa: E402

ICAO = "406B90"


def report(t, lat=52.0, altitude_ft=35000):
    return {"lat": lat, "lon": 4.0, "altitude_ft": altitude_ft, "timestamp": float(t)}


def normal(t):
    """A plausible cruise track: about 480 kt due north, 1 s between reports."""
    return report(t, lat=52.0 + t * 0.00222)


def spoofed(t):
    """An impossible jump far off the normal track (a teleport)."""
    return report(t, lat=60.0)


def test_first_report_is_always_clean():
    # With no reference yet there is nothing to compare against.
    tracker = ConfirmationTracker()
    assert tracker.process(ICAO, spoofed(0)) == ("clean", [])


def test_normal_track_stays_clean():
    tracker = ConfirmationTracker()
    statuses = [tracker.process(ICAO, normal(t))[0] for t in range(10)]
    assert statuses == ["clean"] * 10


def test_single_anomaly_is_held_as_pending():
    tracker = ConfirmationTracker()
    tracker.process(ICAO, normal(0))
    status, reasons = tracker.process(ICAO, spoofed(1))
    assert status == "pending"
    assert reasons  # the reasons are reported even while held


def test_two_anomalies_in_a_row_are_confirmed():
    tracker = ConfirmationTracker()
    tracker.process(ICAO, normal(0))
    tracker.process(ICAO, spoofed(1))
    status, reasons = tracker.process(ICAO, spoofed(2))
    assert status == "confirmed"
    assert any("ground speed" in r for r in reasons)


def test_one_off_jitter_resets_after_a_clean_report():
    # anomaly, clean, anomaly: never two in a row, so never confirmed.
    tracker = ConfirmationTracker()
    tracker.process(ICAO, normal(0))
    assert tracker.process(ICAO, spoofed(1))[0] == "pending"
    assert tracker.process(ICAO, normal(2))[0] == "clean"
    assert tracker.process(ICAO, spoofed(3))[0] == "pending"


def test_flagged_report_never_becomes_the_reference():
    # If a spoofed report replaced the reference, the next spoofed report
    # (at the same fake position) would look normal and the attack would
    # slip through.
    tracker = ConfirmationTracker()
    tracker.process(ICAO, normal(0))
    tracker.process(ICAO, spoofed(1))
    assert tracker.last_trusted[ICAO] == normal(0)
    assert tracker.process(ICAO, spoofed(2))[0] == "confirmed"


def test_sustained_attack_stays_confirmed():
    tracker = ConfirmationTracker()
    tracker.process(ICAO, normal(0))
    statuses = [tracker.process(ICAO, spoofed(t))[0] for t in range(1, 6)]
    assert statuses == ["pending"] + ["confirmed"] * 4


def test_aircraft_are_tracked_independently():
    tracker = ConfirmationTracker()
    tracker.process("AAAAAA", normal(0))
    tracker.process("BBBBBB", normal(0))
    tracker.process("AAAAAA", spoofed(1))  # A is now pending
    # B's first anomaly must not be confirmed by A's pending state.
    assert tracker.process("BBBBBB", spoofed(1))[0] == "pending"
