# Turning on "Continue with Google"

The Google button only shows when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in `.env`.
This takes about 5 minutes and is free.

## 1. Create the Google keys

1. Open <https://console.cloud.google.com/> and sign in with your Google account.
2. At the top, click the project picker, then **New project**. Name it `DermaCareAI` and click **Create**.
3. Go to **APIs & Services → OAuth consent screen** (on newer screens: **Google Auth Platform → Branding**).
   - User type: **External**. App name: `DermaCareAI`. Add your email as support and developer contact.
   - Scopes: you don't need to add any. The app asks only for `openid`, `email` and `profile`.
   - **Audience / Test users:** while the app is in "Testing", only the Google accounts you add here
     can log in. Add your own email and your friends' emails.
4. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
   - Application type: **Web application**. Name: `DermaCareAI local`.
   - **Authorised redirect URIs**: add exactly
     `http://127.0.0.1:8010/auth/google/callback`
   - Click **Create**. Copy the **Client ID** and **Client secret**.

## 2. Put the keys in `.env`

Open `.env` in the project folder (never commit this file) and fill in:

```
GOOGLE_CLIENT_ID=paste-the-client-id-here
GOOGLE_CLIENT_SECRET=paste-the-client-secret-here
```

Then restart the site (VS Code task **DermaCareAI: Restart** or `scripts\restart.ps1`).
Open <http://127.0.0.1:8010/auth/login>. Use `127.0.0.1`, not `localhost`, because the redirect URI must match exactly.

## If Google says "Error 400: redirect_uri_mismatch"

Google compares the return address character by character. Check in **Credentials → your OAuth client →
Authorised redirect URIs** (not "Authorised JavaScript origins") that it is exactly:

    http://127.0.0.1:8010/auth/google/callback

- `http`, not `https`; `127.0.0.1`, not `localhost`; port `8010`; no slash at the end.
- If you open the site as `http://localhost:8010`, it now switches to `127.0.0.1` by itself before going to Google.
- The address the site sends is written to the server log (`google sign-in: redirect_uri sent to Google = ...`).
- To force one fixed address (for example a public link), set `GOOGLE_REDIRECT_URI=` in `.env`.
- After saving in Google Cloud it can take a few minutes before the new address is accepted.

## Using it with the public link

Each Cloudflare quick-tunnel link is new, so Google needs that exact address too. After starting the public link,
add `https://<your-link>.trycloudflare.com/auth/google/callback` to the redirect URIs in step 1.4.
It can take a few minutes for Google to accept a new redirect URI.

## How it works (for reviewers)

- OpenID Connect through Authlib. State and nonce are checked, and the ID token is verified against Google's keys.
- Only emails that Google marks as verified are accepted.
- If an account with the same email already exists, Google is linked to it. Otherwise a new account is made with
  no password (the person can add one later on the **My account** page).
- Switched-off or deleted accounts can't log in with Google either.
- Logins and new links are written to the audit log.
