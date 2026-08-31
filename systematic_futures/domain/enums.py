from enum import Enum


class AssetClassGroup(str, Enum):
    EQUITY_INDEX = "equity_index"
    RATES = "rates"
    FX = "fx"


class RevisionMetadataPolicy(str, Enum):
    """Dataset-specific requirement for source revision identity."""

    NOT_APPLICABLE = "not_applicable"
    OPTIONAL = "optional"
    REQUIRED = "required"
    UNVERIFIED = "unverified"


class MarketCertificationStatus(str, Enum):
    """Certification state of one immutable Market Master record."""

    NOT_VERIFIED = "not_verified"
    CERTIFIED_CURRENT_LEAN_REFERENCE = "certified_current_lean_reference"


class EvidenceAvailability(str, Enum):
    """Whether a named roll input was actually present in the observation."""

    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"


class DataQualityStatus(str, Enum):
    VALID = "valid"
    PARTIAL = "partial"
    STALE = "stale"
    WITHHELD = "withheld"
    REJECTED = "rejected"


class MeasurementQualitySeverity(str, Enum):
    INFORMATIONAL = "informational"
    WARNING = "warning"
    BLOCKING = "blocking"


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


class AuctionPhase(str, Enum):
    """Economic phase of one actual-contract auction excursion."""

    NOT_READY = "not_ready"
    BALANCE = "balance"
    INITIATIVE = "initiative"
    ACCEPTED = "accepted"
    FAILED = "failed"
    PULLBACK = "pullback"
    ROTATION = "rotation"
    LIQUIDITY_VACUUM = "liquidity_vacuum"
    ROLL_TRANSITION = "roll_transition"


class AuctionTransitionType(str, Enum):
    """Legal state transition emitted by the ASR v2 state machine."""

    NONE = "none"
    SESSION_RESET = "session_reset"
    BALANCE_TO_INITIATIVE = "balance_to_initiative"
    INITIATIVE_TO_ACCEPTANCE = "initiative_to_acceptance"
    INITIATIVE_TO_FAILURE = "initiative_to_failure"
    INITIATIVE_EXPIRED = "initiative_expired"
    ACCEPTANCE_TO_PULLBACK = "acceptance_to_pullback"
    ROLL_TRANSITION = "roll_transition"


class BookType(str, Enum):
    CORE_THESIS = "core_thesis"
    TACTICAL_ALPHA = "tactical_alpha"
    HEDGE = "hedge"


class HorizonFamily(str, Enum):
    MICRO_EXECUTION = "micro_execution"
    INTRADAY = "intraday"
    SHORT_SWING = "short_swing"
    CORE = "core"
    HEDGE = "hedge"


class IAEGapDirection(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class IAEGapState(str, Enum):
    OPEN = "open"
    TESTED = "tested"
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
    "AuctionPhase",
    "AuctionTransitionType",
    "BookType",
    "CandidateEventType",
    "DataQualityStatus",
    "EvidenceAvailability",
    "HorizonFamily",
    "IAEGapDirection",
    "IAEGapState",
    "MarketCertificationStatus",
    "MeasurementQualitySeverity",
    "ProfileKind",
    "RevisionMetadataPolicy",
    "RollState",
    "SessionType",
)
