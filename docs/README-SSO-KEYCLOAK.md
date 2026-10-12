# 🧠 LEO BOT — SSO Integration (Keycloak + Redis Sessions)

This document describes the **Single Sign-On (SSO)** implementation for **LEO BOT Admin Portal**, using **Keycloak** as the identity provider and **Redis** as the session manager.

It is designed for both **development** (with HTTPS verification disabled) and **production** (secure with verified SSL).

---

## 🚀 Overview

The LEO BOT Admin panel uses **Keycloak OpenID Connect** for user authentication.

After login:

* Tokens are fetched from Keycloak
* User info is retrieved via `/userinfo`
* A short-lived Redis session is created and used for subsequent requests

This avoids passing JWTs to the front-end directly, while keeping SSO behavior consistent across environments.

---

## 🧩 Architecture

```
[ User Browser ]
       │
       ▼
[ FastAPI Router: /_leoai/sso/login ]
       │
       ▼
[ Keycloak Login Page (OIDC) ]
       │
       ▼
[ FastAPI Callback: /_leoai/sso/callback ]
       │
       ├─> Exchange auth code → access_token
       ├─> Fetch user info via /userinfo
       ├─> Create Redis session (sid:uuid)
       └─> Redirect → /admin?sid=<session_id>
```

Redis stores the following payload for each session:

```json
{
  "user": {
    "preferred_username": "john.doe",
    "email": "john@example.com",
    "name": "John Doe"
  },
  "token": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 300
  },
  "timestamp": 1731204510
}
```

TTL: **1 hour**, auto-expiring via Redis `setex`.

---

## ⚙️ Environment Configuration

Set the following variables in your `.env` or deployment environment:

```bash
# In dev, disable HTTPS certificate verification
PYTHONHTTPSVERIFY=0

# --- Keycloak ---
KEYCLOAK_URL=https://leoid.example.com
KEYCLOAK_REALM=master
KEYCLOAK_CLIENT_ID=leobot
KEYCLOAK_CLIENT_SECRET=YOUR_SECRET_CODE
KEYCLOAK_CALLBACK_URL=https://leobot.example.com/_leoai/sso/callback
KEYCLOAK_ENABLED=true
KEYCLOAK_VERIFY_SSL=false
```

For production, ensure:

* `KEYCLOAK_VERIFY_SSL=true`
* A valid TLS certificate on both Keycloak and LEO BOT domain.

---

## 🧱 Core Code Structure

### File: `leobot_admin_router.py`

The router defines all SSO routes and session management logic.

#### 1. Initialization

* Loads Keycloak environment config
* Verifies presence of `client_secret`
* Disables SSL warnings if running in DEV
* Initializes `FastAPIKeycloak` instance (confidential client)

#### 2. Redis Session Helpers

```python
create_redis_session(user_info, token) -> str
get_session_from_redis(session_id) -> dict | None
```

Sessions are stored with a unique ID (`sid:<uuid>`) and a 1-hour TTL.

#### 3. User Info

User info is fetched via:

```python
GET {KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/userinfo
```

using `httpx.AsyncClient`, with debug logs for network troubleshooting.

#### 4. SSO Routes

| Route                  | Purpose                                                           |
| ---------------------- | ----------------------------------------------------------------- |
| `/_leoai/sso/login`    | Redirects user to Keycloak login page                             |
| `/_leoai/sso/callback` | Handles Keycloak callback, exchanges token, creates Redis session |
| `/_leoai/sso/logout`   | Clears Redis + global logout from Keycloak                        |
| `/admin`               | Protected route requiring valid Redis session                     |
| `/_leoai/sso/me`       | Returns user info from Redis session                              |
| `/_leoai/sso/error`    | Friendly SSO error handler                                        |

---

## 🧠 How Authentication Works

1. User hits `/admin`
2. If no `sid`, redirect → `/login`
3. User authenticates via Keycloak → redirect back with `code` and `session_state`
4. FastAPI exchanges code for access token
5. Fetch user profile → save to Redis
6. Redirect → `/admin?sid=<session_id>`
7. Subsequent API requests include:

   * `?sid=<session_id>` query param **or**
   * `Authorization: Bearer <session_id>` header

---

## 🧰 Redis Session Management

### Key Format

```
sid:{UUIDv7}
```

### TTL

```
3600 seconds (1 hour)
```

### Example Command

```bash
redis-cli keys "sid:*"
redis-cli get sid:2b2d8f3e-...
```

### Expired Sessions

Automatically cleared by Redis.
Requests using an expired SID will redirect to the login page.

---

## 🔐 Logout Flow

Global logout from both systems:

1. Delete local Redis session
2. Redirect user to Keycloak’s standard logout endpoint:

```
/realms/{realm}/protocol/openid-connect/logout
  ?client_id={client_id}
  &post_logout_redirect_uri={callback}?logout=true
```

After logout → callback receives `logout=true` → redirect to `/admin` homepage.

---

## 🧩 Fallback Mode

If Keycloak fails or is disabled:

* `/admin` shows “Keycloak not enabled” page
* `/login`, `/logout` return HTTP 503

Useful for local debug without SSO dependency.

---

## 🪲 Debugging

| Problem                            | Likely Cause                     | Fix                                                     |
| ---------------------------------- | -------------------------------- | ------------------------------------------------------- |
| `❌ Keycloak initialization failed` | Missing `KEYCLOAK_CLIENT_SECRET` | Add secret to `.env`                                    |
| `SSO callback: invalid_grant`      | Code expired or reused           | Retry login                                             |
| `userinfo_fetch_failed`            | Access token invalid             | Check Keycloak server logs                              |
| Redis session lost after 1h        | TTL expiration                   | Re-login or extend TTL                                  |
| `SSL: CERTIFICATE_VERIFY_FAILED`   | Self-signed cert in dev          | Set `KEYCLOAK_VERIFY_SSL=false` + `PYTHONHTTPSVERIFY=0` |

Logs include emoji markers for quick grep:

```
💾 Redis session
🔁 SSO error
🔒 Logout
✅ Ready
```

---


## 🧪 Local Development Setup

### 1️⃣ Create LEO BOT Client

Follow the detailed setup guide here:
📘 **[`README-SETUP-LEOBOT-CLIENT.md`](README-SETUP-LEOBOT-CLIENT.md)**
This document explains how to configure the Keycloak client for **LEO BOT** with correct redirect URIs, scopes, and secrets.

---

### 2️⃣ Run Development Shell Script

Start the full development stack (PostgreSQL, Keycloak Docker, and LEO BOT backend):

```bash
./start_dev.sh
```

This script will automatically:

* Launch PostgreSQL
* Spin up a Keycloak container (with dev credentials)
* Start the LEO BOT FastAPI server with `.env` configuration

---

### 3️⃣ Access the Admin Portal

Once all services are up, open your browser and visit:

```
https://leobot.example.com/admin
```

You’ll be redirected to the Keycloak login page and, upon success, into the **LEO BOT Admin Dashboard** authenticated via SSO.


---

## 🧾 Summary

* Uses **FastAPIKeycloak** for OIDC login/logout
* Stores session in **Redis** (TTL 1h)
* Environment-driven, no hardcoded secrets
* Securely supports both dev (no SSL) and production (strict SSL)
* Clear fallback behavior when SSO is disabled

---

## 🧭 Next Steps

* [ ] Integrate session TTL refresh (sliding window)
* [ ] Add user roles from Keycloak groups
* [ ] Add audit logging of login/logout events
* [ ] Optionally encrypt Redis session data

