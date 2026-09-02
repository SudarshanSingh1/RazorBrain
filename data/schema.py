"""
Canonical transaction data contract for RazorBrain.

This module defines the authoritative schema for a single transaction record
flowing through the risk pipeline.  All upstream producers (synthetic generator,
future ingest adapters) and downstream consumers (feature engineering, risk
engine) must conform to this schema.

LEAKAGE RULE
------------
`is_fraud` is the supervised learning TARGET and must NEVER be used as an
input feature during model training or inference.  It must be separated from
features (X) before any model receives data.

MISSING DATA
------------
Optional fields accept ``None`` to represent information that is genuinely
unavailable at evaluation time (e.g. ip_address for card-present terminals).
Downstream imputation / confidence-reduction logic is handled by the feature
engineering layer — NOT here.  This layer only validates that present values
satisfy their stated constraints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, ClassVar, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PaymentMethod(str, Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"
    CRYPTO = "crypto"


# ---------------------------------------------------------------------------
# Main schema
# ---------------------------------------------------------------------------


class Transaction(BaseModel):
    """
    Canonical representation of a single transaction entering the risk pipeline.

    Fields are grouped by their role:
    - Identifiers    : immutable entity references
    - Core fields    : fundamental transaction attributes
    - Historical     : aggregate signals computed BEFORE this transaction
                       using only prior data (no leakage)
    - Derived flags  : binary signals contextual to this transaction
    - Target         : supervised learning label (MUST NOT be a model feature)
    """

    # ------------------------------------------------------------------
    # Identifiers
    # ------------------------------------------------------------------

    transaction_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this transaction.",
    )
    customer_id: str = Field(
        ...,
        min_length=1,
        description="Identifier for the customer initiating the transaction.",
    )
    merchant_id: str = Field(
        ...,
        min_length=1,
        description="Identifier for the merchant receiving the transaction.",
    )
    device_id: str = Field(
        ...,
        min_length=1,
        description="Identifier for the device used to initiate the transaction.",
    )
    ip_address: Optional[str] = Field(
        default=None,
        description=(
            "IP address associated with the transaction. "
            "May be None for card-present or otherwise unavailable contexts."
        ),
    )

    # ------------------------------------------------------------------
    # Core transaction attributes
    # ------------------------------------------------------------------

    timestamp: datetime = Field(
        ...,
        description="UTC timestamp of the transaction (timezone-aware).",
    )
    amount: Annotated[float, Field(ge=0.0)] = Field(
        ...,
        description="Transaction amount in the account's base currency. Must be >= 0.",
    )
    payment_method: PaymentMethod = Field(
        ...,
        description="Payment instrument used for this transaction.",
    )
    location: Optional[str] = Field(
        default=None,
        description=(
            "Coarse location label (e.g. city or country code). "
            "None when location information is unavailable."
        ),
    )

    # ------------------------------------------------------------------
    # Historical / pre-computed signals
    # (must represent information available BEFORE this transaction)
    # ------------------------------------------------------------------

    customer_account_age_days: Annotated[int, Field(ge=0)] = Field(
        ...,
        description=(
            "Age of the customer account in days at transaction time. "
            "A value of 0 indicates a new account."
        ),
    )
    previous_transaction_count: Annotated[int, Field(ge=0)] = Field(
        ...,
        description=(
            "Total number of transactions the customer completed BEFORE "
            "this transaction.  Does NOT include the current transaction."
        ),
    )
    previous_fraud_count: Annotated[int, Field(ge=0)] = Field(
        ...,
        description=(
            "Number of previously confirmed fraudulent transactions attributed "
            "to this customer.  Does NOT include the current transaction."
        ),
    )
    failed_attempt_count_24h: Annotated[int, Field(ge=0)] = Field(
        ...,
        description=(
            "Number of failed payment attempts by this customer in the 24 hours "
            "PRECEDING this transaction."
        ),
    )
    txns_last_5min: Annotated[int, Field(ge=0)] = Field(
        ...,
        description=(
            "Number of transactions the customer initiated in the 5 minutes "
            "immediately preceding this transaction (velocity signal)."
        ),
    )
    txns_last_1h: Annotated[int, Field(ge=0)] = Field(
        ...,
        description=(
            "Number of transactions the customer initiated in the 1 hour "
            "immediately preceding this transaction."
        ),
    )
    txns_last_24h: Annotated[int, Field(ge=0)] = Field(
        ...,
        description=(
            "Number of transactions the customer initiated in the 24 hours "
            "immediately preceding this transaction."
        ),
    )
    avg_customer_amount: Annotated[float, Field(ge=0.0)] = Field(
        ...,
        description=(
            "Average transaction amount for this customer computed over all "
            "PRIOR transactions.  Zero for new customers with no history."
        ),
    )
    amount_deviation: Annotated[float, Field(ge=0.0)] = Field(
        ...,
        description=(
            "Absolute deviation of `amount` from `avg_customer_amount`. "
            "Zero when there is no prior history."
        ),
    )
    merchant_fraud_rate: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        ...,
        description=(
            "Estimated historical fraud rate for this merchant, in [0, 1]. "
            "Computed from transactions PRIOR to the current one to avoid leakage."
        ),
    )

    # ------------------------------------------------------------------
    # Derived contextual flags (no leakage: evaluated at scoring time)
    # ------------------------------------------------------------------

    new_device_flag: bool = Field(
        ...,
        description=(
            "True if this device_id has not been previously observed for this "
            "customer."
        ),
    )
    new_location_flag: bool = Field(
        ...,
        description=(
            "True if this location has not been previously observed for this "
            "customer."
        ),
    )

    # ------------------------------------------------------------------
    # TARGET — MUST NOT be used as a model input feature
    # ------------------------------------------------------------------

    is_fraud: bool = Field(
        ...,
        description=(
            "Supervised learning target.  True if the transaction is confirmed "
            "fraudulent.  THIS FIELD MUST NEVER BE PASSED AS A MODEL FEATURE."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("ip_address", "location", mode="before")
    @classmethod
    def coerce_nan_to_none(cls, v: object) -> object:
        """
        Pandas represents missing Optional[str] values as float NaN in a
        mixed-type column.  Coerce these to None so Pydantic validates
        correctly when rows are loaded back from a DataFrame via .to_dict().
        """
        import math

        if isinstance(v, float) and math.isnan(v):
            return None
        return v

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "Transaction timestamp must be timezone-aware (tzinfo required). "
                "Use datetime.now(timezone.utc) or an equivalent."
            )
        return v

    @model_validator(mode="after")
    def amount_deviation_consistent(self) -> "Transaction":
        """
        Soft guard: amount_deviation should approximate abs(amount - avg).
        Allows a tolerance of ±1.0 to accommodate rounding in the generator.
        For new customers (avg = 0), any non-negative deviation is acceptable.
        """
        if self.avg_customer_amount > 0:
            expected = abs(self.amount - self.avg_customer_amount)
            if abs(self.amount_deviation - expected) > 1.0:
                raise ValueError(
                    f"amount_deviation ({self.amount_deviation:.2f}) is inconsistent "
                    f"with |amount - avg_customer_amount| ({expected:.2f}). "
                    "Ensure deviation is computed correctly."
                )
        return self

    # ------------------------------------------------------------------
    # Feature / target separation helpers
    # ------------------------------------------------------------------

    # Columns that must NEVER be used as model input features.
    _NON_FEATURE_COLUMNS: ClassVar[tuple[str, ...]] = ("is_fraud", "transaction_id")

    @classmethod
    def feature_columns(cls) -> list[str]:
        """
        Return the list of field names that are safe to use as model features.

        Excludes: is_fraud (target), transaction_id (identifier with no
        predictive signal).  customer_id / merchant_id / device_id are
        identifiers; include only if the model explicitly handles them
        (e.g. frequency-encoded).  They are excluded here for safety.
        """
        identifier_cols = {"transaction_id", "customer_id", "merchant_id", "device_id"}
        excluded = set(cls._NON_FEATURE_COLUMNS) | identifier_cols
        return [f for f in cls.model_fields if f not in excluded]

    @classmethod
    def target_column(cls) -> str:
        """Return the name of the supervised learning target column."""
        return "is_fraud"
