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


class ProfileKind(str, Enum):
    DEVELOPING_SESSION = "developing_session"
    FINAL_SESSION = "final_session"
    ROLLING_30M = "rolling_30m"
    ROLLING_60M = "rolling_60m"
    ROLLING_120M = "rolling_120m"


class AuctionLocationState(str, Enum):
    INSIDE_VALUE = "inside_value"
    ABOVE_VALUE = "above_value"
    BELOW_VALUE = "below_value"
    NO_REFERENCE = "no_reference"


class IAEGapDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class IAEGapState(str, Enum):
    OPEN = "open"
    TESTED = "tested"
    ABSORBED = "absorbed"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class CandidateEventType(str, Enum):
    VALUE_EXIT_UP = "value_exit_up"
    VALUE_EXIT_DOWN = "value_exit_down"
    VALUE_REENTRY_FROM_ABOVE = "value_reentry_from_above"
    VALUE_REENTRY_FROM_BELOW = "value_reentry_from_below"
    POC_MIGRATION_ABOVE_PRIOR_VAH = "poc_migration_above_prior_vah"
    POC_MIGRATION_BELOW_PRIOR_VAL = "poc_migration_below_prior_val"
    IAE_RETEST_BULL = "iae_retest_bull"
    IAE_RETEST_BEAR = "iae_retest_bear"


__all__ = (
    "AssetClassGroup",
    "AuctionLocationState",
    "CandidateEventType",
    "DataQualityStatus",
    "DatasetCertificationStatus",
    "ExperimentDecision",
    "IAEGapDirection",
    "IAEGapState",
    "ProfileKind",
    "ResearchEnvironment",
    "RollState",
    "SessionType",
)
