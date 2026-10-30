"""Shared contracts. Milestones depend on core; core depends on no milestone."""

from vector_director.core.spec import AnimationSpec, Keyframe, SceneObject, Track
from vector_director.core.types import Frames, GenerationResult, Hit, Sample, Scores

__all__ = [
    "AnimationSpec",
    "Frames",
    "GenerationResult",
    "Hit",
    "Keyframe",
    "Sample",
    "SceneObject",
    "Scores",
    "Track",
]
