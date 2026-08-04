from pathlib import Path

import pytest

from scripts import wp19_publication_web_only as contract


ROOT = Path(__file__).resolve().parents[1]


def test_publication_web_only_contract_is_staging_only_and_valid():
    data = contract.load_contract()
    contract.validate_contract(data)
    contract.validate_repository(data)
    contract.validate_dispatch_boundary()
    assert data["target"] == "staging"
    assert data["status"] == "READY_FOR_DEPLOY_AUTHORIZATION"


def test_publication_web_only_contract_rejects_production_target():
    data = contract.load_contract()
    data["target"] = "production"
    with pytest.raises(contract.ContractError, match="staging-only"):
        contract.validate_contract(data)


def test_publication_web_only_workflow_never_targets_production():
    workflow = (ROOT / ".github/workflows/wp19-publication-web-only.yml").read_text()
    assert "https://staging-vnext.muchenai.com" in workflow
    assert "journey.muchenai.com" not in workflow
    assert "/srv/journey-next-production" not in workflow
    assert "terraform apply" not in workflow
    assert "alembic" not in workflow
    assert "seed" not in workflow.lower()
    assert "WP19_PUBLICATION_SSH_INGRESS=CLOSED" in workflow
