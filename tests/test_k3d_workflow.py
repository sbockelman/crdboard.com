from pathlib import Path


def test_k3d_workflow_runs_for_pull_requests_to_main_and_deploys_manifest():
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "k3d-deploy.yml"
    ).read_text()

    assert "pull_request:" in workflow
    assert "branches:" in workflow
    assert "- main" in workflow
    assert "- synchronize" in workflow
    assert "k3d cluster create crdboard-ci --wait" in workflow
    assert "k3d image import crdboard-main:latest --cluster crdboard-ci" in workflow
    assert "k3d image import crdboard-table-server:latest --cluster crdboard-ci" in workflow
    assert "set -euo pipefail" in workflow
    assert 'CRDBOARD_SECRET_KEY="$(openssl rand -hex 32)"' in workflow
    assert 'CRDBOARD_TABLE_ACCESS_SECRET="$(openssl rand -hex 32)"' in workflow
    assert "kubectl apply -f deployment.yml" in workflow
    assert "kubectl rollout status deployment/main-app --timeout=180s" in workflow
    assert "kubectl rollout status deployment/table-server-1 --timeout=180s" in workflow
    assert "kubectl port-forward svc/main-app 5000:5000" in workflow
    assert "kubectl port-forward svc/table-server-1 7001:7001" in workflow
    assert "--retry-all-errors" in workflow
    assert "http://127.0.0.1:7001/health" in workflow
    assert 'CI_PASSWORD="$(openssl rand -hex 16)"' in workflow
    assert 'TABLE_ID="$(python - <<' in workflow
    assert "-c cookies.txt" in workflow
    assert 'http://127.0.0.1:5000/api/tables/${TABLE_ID}/connect' in workflow
    assert 'assert connect["serverStatus"] in {"assigned", "running"}' in workflow
    assert 'assert connect["socketUrl"] == "http://127.0.0.1:7001"' in workflow
