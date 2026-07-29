# Codebase Indexer Webhook — Ops Notes

## Public endpoint

The Hermes VM exposes a **single public HTTPS path** for GitHub webhook
deliveries. No other Hermes service (gateway, Open WebUI, MCP) rides this
public endpoint. All other services remain Tailscale-internal per **IDX-4**.

| Property | Value |
|---|---|
| Path | `POST /webhook/github` |
| Port | `8080` (configurable via `webhook_port`) |
| Exposure | Tailscale Funnel (or reverse proxy) |

## GitHub webhook configuration

1. Go to your repository → Settings → Webhooks → Add webhook.
2. Payload URL: `https://<funnel-hostname>/webhook/github`
3. Content type: `application/json`
4. Secret: See below.
5. Events: Select **"Just the push event"** (or "Send me everything").
6. Active: ✅

## Webhook secret

Generate a secure random secret:

```bash
openssl rand -hex 32
```

Set it in the config file at `/home/ubuntu/.hermes/indexer/config.json`:

```json
{ "webhook_secret": "<hex-secret>" }
```

Restart the webhook service:

```bash
sudo systemctl restart hermes-indexer-webhook
```

**Rotation:** Every 6 months, or immediately if the secret is suspected
compromised. Update both the Hermes config and GitHub webhook settings
within the same maintenance window (the old HMAC will be rejected for
deliveries in flight — GitHub retries for up to 30 days with backoff).

## HMAC validation

The handler requires `X-Hub-Signature-256` in the request header. It
computes `sha256 HMAC` of the raw request body using the configured
secret and compares via constant-time `hmac.compare_digest`.

- Missing or malformed signature → **401** (rejected).
- Valid signature → proceed to allowlist check.
- Non-allowlisted repo → **200** ACK but no index write.

## Rate limiting

Rate limiting applies per client IP on the public webhook path:

| Config key | Default | Notes |
|---|---|---|
| `webhook_rate_limit` | 60 | Requests per minute per key |

Exceeded requests return **429 Too Many Requests** with no processing.

## Delivery contract

GitHub expects a 2XX response within 10 seconds. The handler:

1. Rate-limit check (fast fail)
2. HMAC validation (fast fail)
3. Parse payload
4. Allowlist check
5. Dedup check (5-minute window per `repo/ref/after` key)
6. Execute sync (synchronous in v0; production should enqueue)

Because the sync can take longer than 10 seconds for large repos, a
production deployment should use a background job queue with immediate
ACK and separate worker. The v0 implementation performs a synchronous
sync; for small repos this still fits the window.

## ACL — only allowlisted repos are indexed

The handler checks the push payload's `repository.full_name` against the
configured allowlist. Repos not on the allowlist are acknowledged (200)
but produce no catalog or knowledge rows.

## Service management

```bash
# Start / stop / restart
sudo systemctl start hermes-indexer-webhook
sudo systemctl stop hermes-indexer-webhook
sudo systemctl restart hermes-indexer-webhook

# View logs
journalctl -u hermes-indexer-webhook -n 100 -f

# Enable on boot
sudo systemctl enable hermes-indexer-webhook
```

## Reconcile timer

An hourly reconcile checks for missed webhooks, force-pushes, and drift:

```bash
sudo systemctl start hermes-indexer-reconcile.timer
sudo systemctl enable hermes-indexer-reconcile.timer
```

## Tailscape / Funnel setup

The webhook endpoint is the **only** public surface. Use Tailscale Funnel
(or a standard reverse proxy) to expose port 8080:

```bash
# Install and configure funnel for the webhook path
# See Tailscale Funnel documentation
tailscale funnel 8080
```

Or use a reverse proxy (nginx / Caddy) in front of the service.

## Monitoring

Check webhook service health:

```bash
curl -X POST http://127.0.0.1:8080/webhook/github \
     -H "Content-Type: application/json" \
     -d '{}'
```

Check recent webhook deliveries in GitHub UI:
Settings → Webhooks → [your webhook] → Recent Deliveries.
