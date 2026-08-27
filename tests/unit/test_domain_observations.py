from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from fx_cpm.domain import (
    DomainValidationError,
    Frequency,
    ImputationMetadata,
    MissingStatus,
    Observation,
    ProvenanceType,
    RevisionStatus,
    SourceAuthority,
    SourceType,
    TransformationStep,
)


def observation(**overrides: object) -> Observation:
    values: dict[str, object] = {
        "feature_id": "reserves_usd",
        "country_id": "X",
        "currency_id": "XCU",
        "value": 10.0,
        "unit": "USD million",
        "frequency": Frequency.MONTHLY,
        "period_start": date(2020, 1, 1),
        "period_end": date(2020, 1, 31),
        "release_date": date(2020, 2, 15),
        "retrieval_date": date(2020, 2, 15),
        "vintage": "2020-02-15",
        "source_name": "Example central bank",
        "source_url": "https://example.test/series",
        "source_type": SourceType.CENTRAL_BANK,
        "license": "open",
        "base_quality": 0.9,
        "revision_status": RevisionStatus.FIRST_RELEASE,
        "provenance_type": ProvenanceType.TRUE_VINTAGE,
        "status": MissingStatus.AVAILABLE,
        "provider": "Example provider",
        "source_authority": SourceAuthority.PRIMARY,
    }
    values.update(overrides)
    return Observation(**values)  # type: ignore[arg-type]


def test_observation_is_frozen_and_zero_is_a_valid_observation() -> None:
    item = observation(value=0.0)
    assert item.value == 0.0
    with pytest.raises(FrozenInstanceError):
        item.value = 1.0  # type: ignore[misc]


def test_missing_is_never_encoded_as_economic_zero() -> None:
    missing = observation(value=None, status=MissingStatus.MISSING)
    assert missing.value is None
    assert not missing.is_usable()
    with pytest.raises(DomainValidationError, match="missing is not zero"):
        observation(value=0.0, status=MissingStatus.MISSING)
    with pytest.raises(DomainValidationError, match="require a value"):
        observation(value=None, status=MissingStatus.AVAILABLE)


def test_imputation_retains_original_missingness_and_uncertainty() -> None:
    imputation = ImputationMetadata(
        method="training-window median",
        original_status=MissingStatus.MISSING,
        uncertainty=2.5,
        training_end_date=date(2019, 12, 31),
    )
    item = observation(
        value=8.0,
        provenance_type=ProvenanceType.IMPUTED,
        imputation=imputation,
    )
    assert item.was_imputed
    assert item.original_missing_status is MissingStatus.MISSING


def test_derived_observation_requires_traceable_lineage() -> None:
    with pytest.raises(DomainValidationError, match="transformation lineage"):
        observation(provenance_type=ProvenanceType.DERIVED)
    step = TransformationStep("ratio", ("reserves:2020-01", "imports:2020-01"))
    item = observation(
        feature_id="reserves_to_imports",
        provenance_type=ProvenanceType.DERIVED,
        transformation_lineage=(step,),
    )
    assert item.transformation_lineage[0].operation == "ratio"


def test_observation_dates_and_quality_are_validated() -> None:
    with pytest.raises(DomainValidationError, match="period_end"):
        observation(period_end=date(2019, 12, 31))
    with pytest.raises(DomainValidationError, match="retrieval_date"):
        observation(retrieval_date=date(2020, 2, 1))
    with pytest.raises(DomainValidationError, match="base_quality"):
        observation(base_quality=1.1)

