# Local Auth Proxy (OpenResty)

The auth-test Docker profile includes an [OpenResty](https://openresty.org/) reverse proxy (`auth0-proxy`) that sits between the browser and [localauth0](https://github.com/primait/localauth0). This doc explains why it exists and how to troubleshoot it.

## Why a proxy?

The Auth0 SPA SDK makes cross-origin XHR requests (token exchange, userinfo) from the frontend origin (`http://localhost:3000`) to the OIDC provider. localauth0 doesn't set CORS headers, so the browser blocks these requests.

In production, Auth0 lives on a separate origin from the frontend and handles CORS itself. The proxy mirrors this architecture locally: the frontend talks to `localhost:3100` (the proxy), which forwards to `localauth0:3000` inside the Docker network.

```
Browser
  ├─ localhost:3000  ──►  Frontend (nginx, serves SPA)
  ├─ localhost:3100  ──►  Auth0 Proxy (OpenResty)  ──►  localauth0:3000 (Docker internal)
  └─ localhost:8000  ──►  API (FastAPI)
                            └─ JWKS validation via http://localauth0:3000/.well-known/jwks.json
```

## Why OpenResty instead of plain nginx?

Plain nginx handles CORS fine, but localauth0 has a second limitation: it doesn't propagate the OIDC **nonce** from `/authorize` into the ID token.

The OIDC spec says the nonce is sent in the `/authorize` redirect and returned in the ID token. localauth0 ignores it there — but *will* include a nonce if the `/oauth/token` request body contains a `nonce` field. The Auth0 SPA SDK (correctly) only sends nonce on `/authorize`, not in the token request.

The proxy uses Lua (`access_by_lua_block`) to bridge this gap:

1. On `GET /authorize?nonce=xxx` — captures the nonce into a shared memory dict
2. On `POST /oauth/token` — appends `&nonce=xxx` to the request body before forwarding

This requires OpenResty (nginx + LuaJIT). See `dev/localauth0-proxy.conf` for the full config.

## localauth0 limitations & workarounds

| Limitation | Workaround | Details |
|---|---|---|
| No CORS headers | Proxy adds `Access-Control-Allow-*` | Standard nginx `add_header` directives |
| No nonce propagation | Lua captures from `/authorize`, injects into `/oauth/token` | `lua_shared_dict` with 5-min TTL |
| Hardcoded `client_id` | Use literal string `"client_id"` | localauth0 [hardcodes](https://github.com/primait/localauth0/blob/master/src/lib.rs) `CLIENT_ID_VALUE = "client_id"` — not configurable via TOML |
| No `/v2/logout` endpoint | `LogoutButton` uses SDK's `openUrl` option | Navigates directly to `window.location.origin` after clearing local session |
| ServiceWorker on `:3100` | Clear manually if it causes issues | localauth0 registers a SW that can cache responses on the proxy's origin |

## Starting the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile auth-test up --build
```

The `auth0-proxy` service waits for localauth0's healthcheck before starting. The healthcheck is configured with `start_period: 10s` and `start_interval: 1s`, so the proxy should be ready within ~15 seconds of localauth0 starting.

## Troubleshooting

### CORS errors on `/oauth/token`

The browser blocks the token exchange response. Check:

1. Is `auth0-proxy` running? `curl -s http://localhost:3100/.well-known/openid-configuration | head -1`
2. Open browser DevTools → Network tab → look at the failed request's response headers. You should see `Access-Control-Allow-Origin: http://localhost:3000`.
3. If headers are missing, the request may not be hitting the proxy (check the URL is `localhost:3100`, not `localhost:3000`).

### "Nonce (nonce) claim must be a string present in the ID token"

The proxy didn't inject the nonce into the token request. Check:

1. Was `/authorize` routed through the proxy (`localhost:3100`)? The nonce is captured from this request.
2. Check proxy logs: `docker compose logs auth0-proxy`. Look for the `GET /authorize` and `POST /oauth/token` entries.
3. If the proxy was restarted between `/authorize` and `/oauth/token`, the nonce is lost (stored in memory). Retry the login.

### 401 on token exchange (`"access_denied"`)

localauth0 rejected the token request. The most common cause:

- **Wrong `client_id`**: localauth0 expects the literal string `"client_id"`. Check `VITE_AUTH0_CLIENT_ID=client_id` in `.env`. Any other value (e.g., `local-test-client`) will fail.

### Logout stuck at `localhost:3100/v2/logout`

localauth0 doesn't implement Auth0's `/v2/logout` endpoint. The `LogoutButton` uses the SDK's `openUrl` option to bypass this, but if you see this URL:

1. localauth0's **ServiceWorker** may be intercepting the navigation. Open DevTools → Application → Service Workers → Unregister any SW on `localhost:3100`.
2. Hard-refresh (`Ctrl+Shift+R`) or clear site data for `localhost:3100`.

### Slow proxy startup

The proxy depends on localauth0 being healthy. If localauth0 takes a long time:

1. Check localauth0 logs: `docker compose logs localauth0`
2. The healthcheck runs `/localauth0 healthcheck` every 1s during the start period (10s). After that, it falls back to 30s intervals.
