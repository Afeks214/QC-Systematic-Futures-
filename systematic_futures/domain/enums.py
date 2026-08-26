from __future__ import annotations

from enum import Enum


class AssetClassGroup(str, Enum):
    EQUITY_INDEX = "equity_index"
    RATES = "rates"
    FX = "fx"


class DatasetCertificationStatus(str, Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    CERTIFIED_CONTEXT = "certified_context"
    CERTIFIED_SIGNAL = "certified_signal"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class DataQualityStatus(str, Enum):
    VALID = "valid"
    PARTIAL = "partial"
    STALE = "stale"
    WITHHELD = "withheld"
    REJECTED = "rejected"


class RollState(str, Enum):
    NORMAL = "normal"
    PRE_ROLL = "pre_roll"
    ROLL_TRANSITION = "roll_transition"
    POST_ROLL = "post_roll"
    BLACKOUT = "blackout"


class SessionType(str, Enum):
    ETH = "eth"
    RTH = "rth"
    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"
    US_CASH_HOURS = "us_cash_hours"
    MAINTENANCE = "maintenance"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class ResearchEnvironment(str, Enum):
    LOCAL = "local"
    QC_RESEARCH = "qc_research"
    QC_BACKTEST = "qc_backtest"


class ExperimentDecision(str, Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    RETEST = "retest"
    KILL = "kill"


__all__ = (
    "AssetClassGroup",
    "DataQualityStatus",
    "DatasetCertificationStatus",
    "ExperimentDecision",
    "ResearchEnvironment",
    "RollState",
    "SessionType",
)
