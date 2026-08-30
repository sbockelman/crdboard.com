# crdboard.com

MVP scaffold for a multiplayer interactive table game board.

## What is implemented

- Main Flask app for:
  - user register/login/logout
  - table creation/listing
  - invite creation and acceptance
  - table-server assignment/routing and signed table access tokens
- Table-server Flask + Socket.IO service for:
  - server-authoritative object operations
  - websocket state sync + broadcast
  - reconnect sync with snapshot + missed events
  - presence tracking
- Per-table SQLite state:
  - object state (`print_object`, `move`, `rotate`, `flip`, `set_z`, `stack`, `edit`)
  - immutable operation/event history
  - periodic snapshots for recovery
- Browser UI baseline:
  - print card-like objects
  - drag to move
  - rotate, flip, bring-to-front, stack
  - presence display

## Local development

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run main app:

```bash
python app.py
```

3. Run table-server for table `1` in a second terminal:

```bash
CRDBOARD_TABLE_ID=1 python table_server_app.py
```

4. Open `http://localhost:5000`.

If using Docker Compose, set `CRDBOARD_SECRET_KEY` and `CRDBOARD_TABLE_ACCESS_SECRET` in your shell or `.env` file before `docker compose up`. `CRDBOARD_TABLE_SERVER_HOST` is for internal routing/orchestration and `CRDBOARD_TABLE_SERVER_PUBLIC_HOST` is the client-facing host used in browser connection URLs.

## Architecture notes

- Main app persists auth/table/invite/membership metadata in `data/main.sqlite`.
- Table-servers persist table object state in `data/tables/table_<table_id>.sqlite`.
- Each printed object becomes a unique object instance with an immutable source reference (`sourceType` + `sourceId`) and independent editable state (`editPayload`, metadata, transforms).
- Conflict handling is last-write-wins with server-side global event ordering.

## Containerization

- `Dockerfile.main` builds the main app image.
- `Dockerfile.table-server` builds the table-server image.
- `docker-compose.yml` provides local orchestration with one main app and one example table-server.
- `deployment.yml` provides a Kubernetes deployment with one main app service and one example table-server service for table `1`.
- `.github/workflows/k3d-deploy.yml` deploys `deployment.yml` into k3d and smoke-tests it for pull requests targeting `main`.

### Kubernetes

1. Build the images:

```bash
docker build -f Dockerfile.main -t crdboard-main:latest .
docker build -f Dockerfile.table-server -t crdboard-table-server:latest .
```

2. Apply the manifest:

```bash
kubectl create secret generic crdboard-secrets \
  --from-literal=CRDBOARD_SECRET_KEY=replace-me \
  --from-literal=CRDBOARD_TABLE_ACCESS_SECRET=replace-me-too
kubectl apply -f deployment.yml
```

3. For local access, forward both services:

```bash
kubectl port-forward svc/main-app 5000:5000
kubectl port-forward svc/table-server-1 7001:7001
```

The manifest expects an existing `crdboard-secrets` Kubernetes secret. It sets `CRDBOARD_TABLE_SERVER_PUBLIC_HOST` to `127.0.0.1` so the browser can connect to the example table-server while those port-forwards are active.
