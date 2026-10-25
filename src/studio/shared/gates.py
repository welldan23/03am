"""Gate persetujuan manusia. Dipakai bersama oleh `episodes` dan `approvals`."""

from enum import StrEnum


class Gate(StrEnum):
    TOPIC = "G0"
    EDITORIAL = "G1"
    COST = "G2"
    FINAL = "G3"
