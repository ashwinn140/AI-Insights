# Shared NG-Dashboard login: integration contract (not yet activated)

## Verified current behavior
NG-Dashboard's `app/auth.py` supports email links, 6-digit codes, passwords,
12-hour sessions, role/company/LOB permissions. Its `app/server.py` sets an
HTTP-only `ng_session` cookie scoped to the dashboard's host and uses a
server-side sessions table. AI Insights cannot read that table (correctly denied).

## Safe integration
Implement an explicit, narrowly scoped, signed one-time SSO handoff:
1. User signs in to NG-Dashboard normally.
2. User clicks 'Open AI Insights' from NG-Dashboard (authenticated action).
3. Dashboard creates a single-use, short-lived, audience-bound authorization
   code and stores its hash with expiry and authorized company/LOB scope.
4. AI Insights backend exchanges the code server-to-server over HTTPS,
   authenticating its service identity. Dashboard validates and atomically
   consumes the code, then returns active identity, role and authorized scopes.
5. AI Insights issues its own HTTP-only Secure SameSite=Lax session and
   rechecks authorization on every data endpoint.
6. Disabled users and changed permissions must be invalidated promptly
   (short cache TTL, revocation or periodic verification).
7. Both services must reject missing scopes and prevent cross-company leakage.

## Security gates
- Do not share ng_session cookies, SECRET_KEY, passwords, or login tokens.
- Never embed identity claims in an unsigned browser redirect.
- Codes must be one-time, expire within 60 seconds, be audience-bound,
  use an unpredictable value, and never appear in application logs.
- Rate-limit handoffs and exchanges; require service authentication.
- Prevent open redirects: allowlist AI Insights callback URL.
- Do not enable data endpoints before authorization, CSRF and tests.
- No finance/profit access, no direct source table privileges.
- The current NG-Dashboard must remain unchanged until its small SSO bridge
  is reviewed and tested separately before production rollout.

## Current blocker
The existing dashboard exposes no verified cross-service identity handoff.
An isolated AI Insights service cannot securely infer an NG-Dashboard login
from its cookie or its restricted PostgreSQL account.
