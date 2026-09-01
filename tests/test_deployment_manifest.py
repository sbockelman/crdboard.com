from pathlib import Path


def test_kubernetes_deployment_manifest_defines_main_and_table_services():
    manifest = (Path(__file__).resolve().parents[1] / "deployment.yml").read_text()

    assert manifest.count("kind: Deployment") == 2
    assert manifest.count("kind: Service") == 2
    assert manifest.count("kind: PersistentVolumeClaim") == 2
    assert "name: main-app" in manifest
    assert "name: table-server-1" in manifest
    assert "image: crdboard-main:latest" in manifest
    assert "image: crdboard-table-server:latest" in manifest
    assert "secretKeyRef:" in manifest
    assert "name: crdboard-secrets" in manifest
    assert "name: CRDBOARD_TABLE_SERVER_PUBLIC_HOST" in manifest
    assert "value: 127.0.0.1" in manifest
    assert "name: CRDBOARD_TABLE_ID" in manifest
    assert 'value: "1"' in manifest
    assert "port: 5000" in manifest
    assert "port: 7001" in manifest
    assert "targetPort: 7000" in manifest
