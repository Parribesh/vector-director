"""Beats from audio (librosa) or MIDI -> keyframe times."""

from __future__ import annotations

from pathlib import Path


def beats_from_audio(path: Path) -> list[float]:
    raise NotImplementedError


def beats_from_midi(path: Path) -> list[float]:
    raise NotImplementedError


def snap_to_beats(spec, beats: list[float]):
    """Move keyframes onto the nearest beat."""
    raise NotImplementedError
