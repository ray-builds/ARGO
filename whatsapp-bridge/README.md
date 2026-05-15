# ARGO WhatsApp Bridge (Section 5 Option B)

This service uses `whatsapp-web.js` to ingest WhatsApp messages and forward them to:

- `POST /api/whatsapp/incoming`

## Environment

- `ARGO_BACKEND_URL` (default `http://app:8000`)
- `BRIDGE_SECRET` (must match `WHATSAPP_BRIDGE_SECRET` in ARGO)
- `BRIDGE_PORT` (default `3001`)
- `BRIDGE_MAX_HISTORY` (default `500`)
- `BRIDGE_ALLOWED_GROUP_IDS` (comma-separated group IDs, e.g. `1203...@g.us`)
- `BRIDGE_ALLOWED_GROUP_NAMES` (comma-separated group names, fallback filter)

## Restrict To One Trade Group

Set one of these in `.env`:

- Preferred: `BRIDGE_ALLOWED_GROUP_IDS=1203xxxxxxxx@g.us`
- Or by name: `BRIDGE_ALLOWED_GROUP_NAMES=ARP Trading`

When either allowlist is set, the bridge forwards messages only from matching groups.
Direct messages are ignored.

## Local run (without Docker)

```bash
cd whatsapp-bridge
npm install
npm start
```

Scan the printed QR code once to authenticate.

Then list available groups and copy the exact trade-group ID:

```bash
curl http://localhost:3001/groups
```
