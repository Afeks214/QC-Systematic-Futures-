"""Symbolic economic hypotheses and canonical candidate contracts."""

from systematic_futures.hypotheses.contracts import CandidateEvent, HypothesisTemplate
from systematic_futures.hypotheses.h2_h3 import (
    H2H3HypothesisEngine,
    H2_HYPOTHESIS_ID,
    H3_HYPOTHESIS_ID,
    build_h2_template,
    build_h3_template,
)

__all__ = (
    "CandidateEvent",
    "H2H3HypothesisEngine",
    "H2_HYPOTHESIS_ID",
    "H3_HYPOTHESIS_ID",
    "HypothesisTemplate",
    "build_h2_template",
    "build_h3_template",
)
