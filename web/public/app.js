// Account page: Auth0 sign-in, then load/save the account through /api/profile (which stores it in Firestore).
// Without Auth0 settings in config.js it runs in demo mode, saving only to this browser's localStorage.
(() => {
  const cfg = window.ACCOUNT_CONFIG || {};
  const configured = !!(cfg.auth0Domain && cfg.auth0ClientId);
  const $ = (id) => document.getElementById(id);
  const METHODS = [
    ["card", "Card"], ["paypal", "PayPal"], ["apple_pay", "Apple Pay"],
    ["google_pay", "Google Pay"], ["klarna", "Klarna"], ["clearpay", "Clearpay"],
  ];
  const BRANDS = ["Visa", "Mastercard", "Amex", "Maestro", "Other"];
  const DEMO_KEY = "second-thought-demo-account";

  let auth0Client = null;
  let account = null;

  const show = (id) => ["landing", "app", "loading"].forEach((x) => ($(x).hidden = x !== id));
  const status = (text, kind = "") => {
    $("status").textContent = text;
    $("status").className = kind;
  };

  // ---------- Backend: the real API, or localStorage in demo mode ----------

  async function idToken() {
    await auth0Client.getTokenSilently(); // refreshes the session (and ID token) if needed
    return (await auth0Client.getIdTokenClaims()).__raw;
  }

  async function request(method, body) {
    if (!configured) {
      if (method === "GET") return JSON.parse(localStorage.getItem(DEMO_KEY) || "null") || { profile: {}, payment: { preferred: null, cards: [] }, budget: { monthly: 0, spent: 0, currency: "GBP" } };
      if (method === "DELETE") return localStorage.removeItem(DEMO_KEY), { deleted: true };
      if (/(?:\d[ -]?){12,}/.test(JSON.stringify(body))) throw new Error("That looks like a card number. We never store card numbers: only a nickname and the last 4 digits.");
      const saved = { ...body, updatedAt: new Date().toISOString() };
      localStorage.setItem(DEMO_KEY, JSON.stringify(saved));
      return saved;
    }
    const res = await fetch("/api/profile", {
      method,
      headers: { authorization: `Bearer ${await idToken()}`, ...(body ? { "content-type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  }

  // ---------- Form <-> account ----------

  function renderMethods(preferred) {
    $("methods").replaceChildren(
      ...METHODS.map(([value, label]) => {
        const l = document.createElement("label");
        l.className = "method";
        const r = Object.assign(document.createElement("input"), { type: "radio", name: "payment.preferred", value, checked: value === preferred });
        l.append(r, document.createTextNode(label));
        return l;
      })
    );
  }

  function cardRow(card = {}) {
    const row = document.createElement("div");
    row.className = "card-row";
    row.innerHTML = `
      <label>Nickname<input class="nick" maxlength="40" placeholder="e.g. Everyday debit" /></label>
      <label>Brand<select class="brand">${BRANDS.map((b) => `<option>${b}</option>`).join("")}</select></label>
      <label>Last 4 digits<input class="last4" inputmode="numeric" maxlength="4" placeholder="1234" autocomplete="off" /></label>
      <button type="button" class="link remove">Remove</button>`;
    row.querySelector(".nick").value = card.nickname || "";
    row.querySelector(".brand").value = BRANDS.includes(card.brand) ? card.brand : "Visa";
    const last4 = row.querySelector(".last4");
    last4.value = card.last4 || "";
    // Only ever 4 digits: a pasted full card number is cut to nothing, with a warning.
    last4.addEventListener("input", () => {
      const digits = last4.value.replace(/\D/g, "");
      if (digits.length > 4) {
        last4.value = "";
        status("Just the last 4 digits, please. Never the full card number.", "err");
      } else last4.value = digits;
    });
    row.querySelector(".remove").addEventListener("click", () => row.remove());
    return row;
  }

  function fill(a) {
    const form = $("form");
    for (const el of form.querySelectorAll("input[name], select[name]")) {
      if (el.type === "radio") continue;
      const [group, key] = el.name.split(".");
      const v = a[group]?.[key];
      el.value = v == null || v === 0 ? (el.tagName === "SELECT" ? el.value : "") : v;
    }
    renderMethods(a.payment?.preferred);
    $("cards").replaceChildren(...(a.payment?.cards || []).map(cardRow));
    $("updated").textContent = a.updatedAt ? `Last saved ${new Date(a.updatedAt).toLocaleString()}.` : "";
    updateMeter();
  }

  function read() {
    const form = $("form");
    const a = { profile: {}, payment: { preferred: null, cards: [] }, budget: {} };
    for (const el of form.querySelectorAll("input[name], select[name]")) {
      const [group, key] = el.name.split(".");
      if (el.type === "radio") {
        if (el.checked) a.payment.preferred = el.value;
      } else a[group][key] = el.type === "number" ? Number(el.value) || 0 : el.value.trim();
    }
    a.payment.cards = [...$("cards").querySelectorAll(".card-row")].map((row) => ({
      nickname: row.querySelector(".nick").value.trim(),
      brand: row.querySelector(".brand").value,
      last4: row.querySelector(".last4").value.trim(),
    }));
    return a;
  }

  function updateMeter() {
    const monthly = Number($("form").elements["budget.monthly"].value) || 0;
    const spent = Number($("form").elements["budget.spent"].value) || 0;
    const cur = $("form").elements["budget.currency"].value;
    const fmt = (n) => new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(n);
    const pct = monthly > 0 ? Math.min(100, (spent / monthly) * 100) : 0;
    $("meter-fill").style.width = `${pct}%`;
    $("meter-fill").style.background = pct > 90 ? "var(--bad)" : pct > 60 ? "var(--warn)" : "var(--good)";
    $("meter-text").textContent = monthly > 0 ? `${fmt(Math.max(monthly - spent, 0))} left of ${fmt(monthly)} this month.` : "No budget set. The extension will only compare prices.";
  }

  // ---------- Views ----------

  async function showApp(email) {
    show("loading");
    $("who").hidden = false;
    $("who-email").textContent = email || "Demo account";
    $("demo-fill").hidden = configured;
    try {
      account = await request("GET");
      fill(account);
      show("app");
    } catch (e) {
      show("app");
      fill({ profile: {}, payment: { cards: [] }, budget: {} });
      status(`Couldn't load your details: ${e.message}`, "err");
    }
  }

  function showLanding() {
    $("who").hidden = true;
    $("demo-fill").hidden = true;
    $("sign-in").hidden = !configured;
    $("try-demo").hidden = configured;
    show("landing");
  }

  // ---------- Events ----------

  $("sign-in").addEventListener("click", () => auth0Client.loginWithRedirect());
  $("try-demo").addEventListener("click", () => showApp(null));
  // Demo mode: fill the form with the made-up shopper from persona.js (not saved until Save is clicked).
  $("demo-fill").addEventListener("click", () => {
    const p = window.ST?.persona;
    if (!p) return;
    fill({ profile: p.profile, payment: p.payment, budget: p.budget });
    status(`Filled in ${p.name}'s details. Click Save to keep them.`, "ok");
  });
  $("sign-out").addEventListener("click", () => {
    if (!configured) return showLanding();
    auth0Client.logout({ logoutParams: { returnTo: location.origin } });
  });
  $("add-card").addEventListener("click", () => {
    if ($("cards").children.length >= 5) return status("You can save up to 5 cards.", "err");
    const row = cardRow();
    $("cards").append(row);
    row.querySelector(".nick").focus();
  });
  $("form").addEventListener("input", (e) => {
    if (e.target.name?.startsWith("budget.")) updateMeter();
  });
  $("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const a = read();
    const bad = a.payment.cards.find((c) => !/^\d{4}$/.test(c.last4));
    if (bad) return status("Each card needs exactly the last 4 digits.", "err");
    $("save").disabled = true;
    status("Saving…");
    try {
      account = await request("PUT", a);
      fill(account);
      status("Saved. The extension picks this up next time it syncs.", "ok");
    } catch (err) {
      status(err.message, "err");
    } finally {
      $("save").disabled = false;
    }
  });
  $("delete").addEventListener("click", async () => {
    if (!confirm("Delete all your saved details? This can't be undone.")) return;
    try {
      await request("DELETE");
      account = null;
      fill({ profile: {}, payment: { cards: [] }, budget: {} });
      status("Your data has been deleted.", "ok");
    } catch (err) {
      status(err.message, "err");
    }
  });

  // ---------- Start ----------

  (async () => {
    $("demo-banner").hidden = configured;
    if (!configured) return showLanding();
    try {
      auth0Client = await auth0.createAuth0Client({
        domain: cfg.auth0Domain,
        clientId: cfg.auth0ClientId,
        authorizationParams: { redirect_uri: location.origin, scope: "openid profile email" },
        cacheLocation: "localstorage",
        useRefreshTokens: true,
      });
      const q = new URLSearchParams(location.search);
      if (q.has("code") && q.has("state")) {
        await auth0Client.handleRedirectCallback();
        history.replaceState({}, document.title, location.pathname);
      }
      if (await auth0Client.isAuthenticated()) {
        const user = await auth0Client.getUser();
        return showApp(user?.email);
      }
    } catch (e) {
      console.error(e);
    }
    showLanding();
  })();
})();
