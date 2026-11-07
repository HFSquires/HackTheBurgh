# Second Thought — account site

A page where you sign in with **Auth0** and save your delivery details, payment preferences and monthly budget.
The extension signs in with the same account and uses them at checkout.

```
public/            the page (static): index.html, app.js, styles.css, config.js
api/profile.js     GET / PUT / DELETE your account (Vercel serverless function)
lib/auth.js        verifies the Auth0 ID token (signature, issuer, audience, expiry)
lib/firestore.js   Firestore via the Admin SDK, server-side only
lib/validate.js    allowed fields only; refuses card numbers, expiry dates and security codes
firestore.rules    deny all direct access from browsers
```

**What's stored:** name, email, phone, address; preferred payment method; cards as *nickname + brand + last 4 digits*;
monthly budget and spend. **Never** card numbers, expiry dates or security codes: the API rejects anything that
looks like one, and the page won't let you type more than 4 digits.

**How it's secured:** the browser never talks to Firestore (rules deny everything). Every read and write goes
through `/api/profile`, which only acts on the document of the user whose Auth0 token it just verified.

## Try it locally (demo mode)

```bash
python3 -m http.server 5180 --directory web/public
```

Open http://localhost:5180 → **Try it without signing in**. With `public/config.js` empty, it saves to this
browser only.

## Set it up for real (all free tiers)

You need three free accounts. Use the same browser tab order below; it takes about 15 minutes.

### 1. Firebase (database)

1. https://console.firebase.google.com → **Add project** (Google Analytics: off is fine). Stay on the free Spark plan.
2. **Build → Firestore Database → Create database** → production mode → a region near you (e.g. `europe-west2`).
3. **Rules** tab → replace with the contents of `firestore.rules` → **Publish**.
4. **Project settings (⚙) → Service accounts → Generate new private key**. This downloads a JSON file.
   **It's a secret:** don't commit it or share it. You'll paste it into Vercel in step 3.

### 2. Auth0 (sign-in)

1. https://auth0.com → sign up (free) → create a tenant (e.g. `second-thought`, region EU).
2. **Applications → Create Application** → name "Second Thought" → **Single Page Web Applications** → Create.
3. On its **Settings** tab, note the **Domain** and **Client ID**, then fill in (replace the placeholders; the
   Vercel URL comes in step 3, so you can come back to this):
   - **Allowed Callback URLs:** `https://YOUR-APP.vercel.app, http://localhost:5180, https://YOUR-EXTENSION-ID.chromiumapp.org/`
   - **Allowed Logout URLs:** `https://YOUR-APP.vercel.app, http://localhost:5180`
   - **Allowed Web Origins:** `https://YOUR-APP.vercel.app, http://localhost:5180`
   - **Allowed Origins (CORS):** `https://YOUR-APP.vercel.app, http://localhost:5180, chrome-extension://YOUR-EXTENSION-ID`
   - **Refresh Token Rotation:** on.
   - Save Changes.
4. `YOUR-EXTENSION-ID` is the ID shown on the extension's card in `chrome://extensions`.

### 3. Vercel (hosting + the API, free `.vercel.app` domain)

1. Put `web/public/config.js` values in: `auth0Domain` = the Auth0 Domain, `auth0ClientId` = the Client ID.
   These are public identifiers, not secrets.
2. Deploy the `web` folder, either way:
   - **From GitHub:** push this repo, then https://vercel.com/new → import it → set **Root Directory** to `web`.
   - **From your terminal:** `cd web && npx vercel` (it asks you to log in).
3. In the Vercel project → **Settings → Environment Variables**, add:
   - `AUTH0_DOMAIN` = your Auth0 Domain (e.g. `second-thought.eu.auth0.com`)
   - `AUTH0_CLIENT_ID` = your Auth0 Client ID
   - `FIREBASE_SERVICE_ACCOUNT` = the **entire contents** of the JSON file from Firebase step 4
4. **Redeploy** (Deployments → ⋯ → Redeploy) so the variables take effect.
5. Your site is at `https://<project>.vercel.app`. Put that URL into the Auth0 settings from step 2.

### 4. Connect the extension

In `extension/src/config.js`, fill in `ACCOUNT`:

```js
ACCOUNT: {
  site: "https://<project>.vercel.app",
  auth0Domain: "second-thought.eu.auth0.com",
  auth0ClientId: "<Client ID>",
},
```

Reload the extension in `chrome://extensions`, open its **Options** → **Sign in**. It syncs straight away, then
hourly and when Chrome starts.

## API

All requests need `Authorization: Bearer <Auth0 ID token>`.

| Method | Body | Result |
| --- | --- | --- |
| `GET /api/profile` | | `{ profile, payment: { preferred, cards[] }, budget: { monthly, spent, currency }, updatedAt, email }` |
| `PUT /api/profile` | same shape (without `updatedAt`, `email`) | the saved account, or `400 { error }` |
| `DELETE /api/profile` | | `{ deleted: true }` |
