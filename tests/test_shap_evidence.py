"""
Tests for obsolete shap_evidence generator.
model/shap_evidence.py was removed during the cleanup pass (replaced by model/explanation.py).
All tests in this file are skipped.
"""
import pytest

pytestmark = pytest.mark.skip(reason="model/shap_evidence.py removed; superseded by model/explanation.py.")

# Stub the deleted module so the import below doesn't crash collection
try:
    from model.shap_evidence import generate_shap_evidence, ShapExplanationError  # noqa: F401
except ModuleNotFoundError:
    generate_shap_evidence = None  # type: ignore[assignment]
    ShapExplanationError = Exception  # type: ignore[assignment, misc]


@pytest.fixture(scope="module")
def model_components():
    pass


def test_shap_evidence_removed():
    pytest.skip("model/shap_evidence.py removed.")
