// Sign in to your Second Thought account (Auth0) from the extension, and sync the details saved on the account page
// (delivery details, payment preferences, budget) into extension storage. Runs in the background worker.
//
// Sign-in uses Auth0's Authorization Code flow with PKCE through chrome.identity.launchWebAuthFlow, so no secret is
// stored in the extension. The ID token is kept in chrome.storage.local and sent to the account site's /api/profile.
globalThis.ST = globalThis.ST || {};

(() => {
  const KEY = "account";
  const cfg = () => ST.config.ACCOUNT || {};
  const configured = () => !!(cfg().site && cfg().auth0Domain && cfg().auth0ClientId);

  const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const random = (n = 32) => b64url(crypto.getRandomValues(new Uint8Array(n)));
  const sha256 = async (s) => b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
  const claimsOf = (jwt) => JSON.parse(atob(jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));

  async function status() {
    const { [KEY]: a } = await chrome.storage.local.get(KEY);
    return {
      configured: configured(),
      site: cfg().site || null,
      signedIn: !!a?.idToken && a.expiresAt > Date.now(),
      expired: !!a?.idToken && a.expiresAt <= Date.now(),
      email: a?.email || null,
      syncedAt: a?.syncedAt || null,
    };
  }

  async function signIn() {
    if (!configured()) throw new Error("Account sign-in isn't set up yet: fill in ACCOUNT in src/config.js.");
    const { auth0Domain: domain, auth0ClientId: clientId } = cfg();
    const redirectUri = chrome.identity.getRedirectURL(); // https://<extension-id>.chromiumapp.org/
    const verifier = random(48);
    const state = random(16);
    const url = new URL(`https://${domain}/authorize`);
    Object.entries({
      response_type: "code",
      client_id: clientId,
      redirect_uri: redirectUri,
      scope: "openid profile email",
      code_challenge: await sha256(verifier),
      code_challenge_method: "S256",
      state,
    }).forEach(([k, v]) => url.searchParams.set(k, v));

    ST.log("account: opening Auth0 sign-in", { redirectUri });
    const back = new URL(await chrome.identity.launchWebAuthFlow({ url: url.href, interactive: true }));
    if (back.searchParams.get("state") !== state) throw new Error("Sign-in was interrupted. Please try again.");
    if (back.searchParams.get("error")) throw new Error(back.searchParams.get("error_description") || back.searchParams.get("error"));

    const res = await fetch(`https://${domain}/oauth/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ grant_type: "authorization_code", client_id: clientId, code_verifier: verifier, code: back.searchParams.get("code"), redirect_uri: redirectUri }),
    });
    const tokens = await res.json().catch(() => ({}));
    if (!res.ok || !tokens.id_token) throw new Error(tokens.error_description || `Auth0 sign-in failed (${res.status})`);
    const claims = claimsOf(tokens.id_token);
    await chrome.storage.local.set({ [KEY]: { idToken: tokens.id_token, expiresAt: claims.exp * 1000, email: claims.email || null } });
    ST.log("account: signed in", { email: claims.email ? "(email received)" : null });
    await sync();
    return status();
  }

  // Pull the saved account into the keys the rest of the extension already uses.
  async function sync() {
    const { [KEY]: a } = await chrome.storage.local.get(KEY);
    if (!a?.idToken) return null;
    if (a.expiresAt <= Date.now()) {
      ST.log("account: sign-in expired, sign in again to sync");
      return null;
    }
    const res = await fetch(`${cfg().site.replace(/\/$/, "")}/api/profile`, { headers: { authorization: `Bearer ${a.idToken}` } });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      await chrome.storage.local.set({ [KEY]: { ...a, expiresAt: 0 } });
      throw new Error("Please sign in again.");
    }
    if (!res.ok) throw new Error(data.error || `Sync failed (${res.status})`);

    await chrome.storage.local.set({
      profile: data.profile || {},
      budget: Number(data.budget?.monthly) || 0,
      spent: Number(data.budget?.spent) || 0,
      monthlySavings: Number(data.budget?.monthlySavings) || 0,
      paymentPreference: { preferred: data.payment?.preferred || null, cards: data.payment?.cards || [] },
      [KEY]: { ...a, syncedAt: Date.now() },
    });
    ST.log("account: synced", {
      detailFields: Object.keys(data.profile || {}),
      budgetSet: (data.budget?.monthly || 0) > 0,
      preferredPayment: data.payment?.preferred || null,
      savedCards: (data.payment?.cards || []).length,
    });
    return status();
  }

  async function signOut() {
    await chrome.storage.local.remove([KEY, "paymentPreference"]);
    ST.log("account: signed out (saved details stay until you change them)");
    return status();
  }

  ST.account = { status, signIn, sync, signOut };
})();
