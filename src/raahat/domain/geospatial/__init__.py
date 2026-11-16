"""Geospatial value objects."""
from .landmark import BoundingBox, Landmark, LandmarkCandidate
from .location_hypothesis import LocationHypothesis

__all__ = ["BoundingBox", "Landmark", "LandmarkCandidate", "LocationHypothesis"]
