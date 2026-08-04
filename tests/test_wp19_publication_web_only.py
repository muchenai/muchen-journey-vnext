import pytest

from scripts import wp19_publication_web_only as contract


def test_publication_web_only_contract_is_staging_only_and_valid(monkeypatch):
    data = contract.load_contract()
    contract.validate_contract(data)
    sources = {
        ("diff", "--name-only"): "",
        ("show",): (
            "export type PublishFormalJourneyActionState = SubmissionActionState\n"
            "return submissionError(error)\n"
            'apiRequest("/api/v1/ops/formal-journeys/publish"\n'
            "useActionState(\npublishFormalJourney\nstate.requestId\n发布受控内测 V1\n"
        ),
    }

    def fake_git(*args: str) -> str:
        if args[0] == "diff":
            return sources[("diff", "--name-only")]
        if args[0] == "show":
            return sources[("show",)]
        return ""

    monkeypatch.setattr(contract, "git", fake_git)
    contract.validate_repository(data)
    assert data["target"] == "staging"
    assert data["status"] == "READY_FOR_DEPLOY_AUTHORIZATION"


def test_publication_web_only_contract_rejects_production_target():
    data = contract.load_contract()
    data["target"] = "production"
    with pytest.raises(contract.ContractError, match="staging-only"):
        contract.validate_contract(data)


def test_publication_web_only_workflow_never_targets_production():
    workflow = """
workflow_dispatch:
DEPLOY_12BC627_PUBLICATION_WEB_ONLY_STAGING
WP19_PUBLICATION_SSH_INGRESS=CLOSED
deploy/production/web_only.sh
https://staging-vnext.muchenai.com
database:"UNCHANGED"
business_facts:"UNCHANGED"
"""
    contract.validate_dispatch_boundary(
        workflow=workflow,
        deploy_script="WP16_EXPECTED_HOME_MARKER",
    )


def test_publication_web_only_workflow_rejects_production():
    with pytest.raises(contract.ContractError, match="staging Web-only"):
        contract.validate_dispatch_boundary(
            workflow="journey.muchenai.com",
            deploy_script="WP16_EXPECTED_HOME_MARKER",
        )
