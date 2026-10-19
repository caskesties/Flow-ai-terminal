# Massive private bridge — experimental
Reads Massive real-time trades and BBO quotes and infers trade side by quote touch (fallback: tick rule).
Never call this an exchange-provided aggressor flag. Tick rule is less reliable.
The Flow front end consumes normalized JSON only. A local backend listens on 127.0.0.1:8765, and needs a **private TLS WSS reverse proxy**.
Environment: MASSIVE_API_KEY (GitHub secret alone does not deploy this server), FLOW_BRIDGE_TOKEN (strong random secret), MASSIVE_SYMBOLS (comma-separated **dated and verified** contracts like GCZ6), FLOW_BRIDGE_PORT.
Install with `pip install -r backend/requirements.txt`. Start from backend directory with `python massive_bridge.py`.
Configure the browser with `wss://your-private-server/market`, an access token, and the dated contract. Keep the secret out of repo, browser URLs and logs. Restrict origin, protect with additional reverse-proxy access controls and rotate tokens.
**Not deployed.** No 24/7 service or frontend live streaming until a host and TLS proxy are configured and real-time integration tests pass.
The quote feed is BBO only, not Level 2. No identification of institutions; classify only where quote is recent or tick rule is usable. During reconnection the backend closes clients to avoid stale signals.
**Current limitation:** guard against rolled/wrong instruments requires human-confirmed symbol in MASSIVE_SYMBOLS. Automated contract selection/liquidity verification is NOT active.
**Security:** because browser-token authentication alone is not origin protection, deploy only on a private host behind authenticated access and strict Origin restriction. Do not share tokens publicly.
**Validation:** `cd backend && python -m unittest test_flow_classifier.py`.
