const $ = (id) => document.getElementById(id);
const fields = ["apiKey", "model", "budget", "spent", "monthlySavings", "bankPersona"];
const DEFAULT_MODEL = "gpt-6-luna";
const RETIRED = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]; // shut down 11 Dec 2026
const PROFILE = ["givenName", "familyName", "email", "phone", "address1", "address2", "city", "postcode", "country"];

function status(text, kind = "") {
  $("status").textContent = text;
  $("status").className = kind;
}

function loadFields() {
  return chrome.storage.local.get([...fields, "profile"]).then((s) => {
    for (const f of fields) if (s[f] != null) $(f).value = s[f];
    for (const f of PROFILE) $(`p-${f}`).value = s.profile?.[f] || "";
    if (s.bankPersona === undefined) $("bankPersona").value = ST.config.MODEL?.persona || "";
    if (!s.model || RETIRED.includes(s.model)) $("model").value = DEFAULT_MODEL;
  });
}
loadFields();

// ---------- Demo shopper (persona.js): fills the form and saves a bank picture ----------

const money = (n, currency = "GBP") => {
  try { return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(n); } catch { return String(n); }
};
const inDays = (n) => (n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`);
const row = (left, right, cls = "") => {
  const li = document.createElement("li");
  const a = document.createElement("span");
  a.textContent = left;
  const b = document.createElement("span");
  b.textContent = right;
  if (cls) b.className = cls;
  li.append(a, b);
  return li;
};

async function renderMoney() {
  const { money: m } = await chrome.storage.local.get("money");
  $("money").hidden = !m;
  $("demo-clear").hidden = !m;
  if (!m) return;
  const b = ST.persona.safeToSpend(m);
  const cur = m.currency || "GBP";
  $("m-balance").textContent = money(b.balance, cur);
  $("m-safe").textContent = money(b.safe, cur);
  $("m-safe-sub").textContent = b.payday ? `until ${b.payday.name.toLowerCase()} ${inDays(b.payday.inDays)}` : "";
  $("m-savings").textContent = m.savings ? money(m.savings.balance, cur) : "–";
  $("m-savings-sub").textContent = m.savings?.goal ? `of ${money(m.savings.goal, cur)} for ${m.savings.goalName || "a goal"}` : "";
  $("m-bills").replaceChildren(...b.upcoming.map((u) => row(`${u.name} · ${inDays(u.inDays)}`, money(u.amount, cur))));
  if (!b.upcoming.length) $("m-bills").append(row("Nothing due before payday", ""));
  $("m-recent").replaceChildren(
    ...(m.recent || []).slice(0, 6).map((t) => row(`${t.merchant}`, t.amount < 0 ? `+${money(-t.amount, cur)}` : money(t.amount, cur), t.amount < 0 ? "in" : "muted"))
  );
}

$("demo-use").addEventListener("click", async () => {
  await chrome.storage.local.set(ST.persona.settings());
  await loadFields();
  await renderMoney();
  status(`Using ${ST.persona.name}'s details. Open a checkout to see the verdict.`, "ok");
});
$("demo-clear").addEventListener("click", async () => {
  await chrome.storage.local.remove("money");
  await renderMoney();
  status("Bank picture removed. The verdict now uses the budget only.", "ok");
});
renderMoney();

// ---------- Account (Auth0 sign-in, synced from the account page) ----------

const sendAccount = async (type) => {
  const res = await chrome.runtime.sendMessage({ type });
  if (!res?.ok) throw new Error(res?.error || "No response");
  return res.data;
};

async function renderAccount(st) {
  st ||= await sendAccount("ST_ACCOUNT_STATUS");
  const signedIn = st.signedIn;
  $("acct-sign-in").hidden = signedIn || !st.configured;
  $("acct-sync").hidden = !signedIn;
  $("acct-sign-out").hidden = !(signedIn || st.expired);
  $("acct-site").hidden = !st.site;
  if (st.site) $("acct-site").href = st.site;
  $("acct-text").textContent = !st.configured
    ? "Account sign-in isn't set up in this build yet (ACCOUNT in src/config.js). You can still enter details below."
    : signedIn
      ? `Signed in${st.email ? ` as ${st.email}` : ""}. ${st.syncedAt ? `Synced ${new Date(st.syncedAt).toLocaleString()}.` : "Not synced yet."} Your delivery details, budget and payment preference below come from your account.`
      : st.expired
        ? "Your sign-in has expired. Sign in again to keep your details in sync."
        : "Sign in to use the delivery details, payment preferences and budget saved on your account page.";
  if (st.expired) $("acct-sign-in").hidden = false;
}

const acctAction = (type, busy, done) => async () => {
  status(busy);
  try {
    const st = await sendAccount(type);
    await loadFields();
    await renderAccount(st || undefined);
    status(done, "ok");
  } catch (e) {
    status(e.message, "err");
    renderAccount();
  }
};
$("acct-sign-in").addEventListener("click", acctAction("ST_ACCOUNT_SIGN_IN", "Opening sign-in…", "Signed in and synced."));
$("acct-sync").addEventListener("click", acctAction("ST_ACCOUNT_SYNC", "Syncing…", "Synced from your account."));
$("acct-sign-out").addEventListener("click", acctAction("ST_ACCOUNT_SIGN_OUT", "Signing out…", "Signed out."));
renderAccount().catch(() => {});

$("save").addEventListener("click", async () => {
  const savings = Number($("monthlySavings").value);
  if (!Number.isFinite(savings) || savings < 0 || savings > 1000000) return status("Enter a savings goal between £0 and £1,000,000.", "err");
  await chrome.storage.local.set({
    monthlySavings: savings,
    bankPersona: $("bankPersona").value,
    apiKey: $("apiKey").value.trim(),
    model: $("model").value.trim() || DEFAULT_MODEL,
    budget: Number($("budget").value) || 0,
    spent: Number($("spent").value) || 0,
    profile: Object.fromEntries(PROFILE.map((f) => [f, $(`p-${f}`).value.trim()]).filter(([, v]) => v)),
  });
  status("Saved. Refresh a checkout page to try it.", "ok");
});

// Lists models with the key: cheap, and confirms both the key and that the chosen model is available.
$("test").addEventListener("click", async () => {
  const key = $("apiKey").value.trim();
  if (!key) return status("Paste a key first.", "err");
  status("Checking…");
  const api = ST.apiFor(key);
  try {
    const res = await fetch(`${api.base}/models`, { headers: { authorization: `Bearer ${key}` } });
    const data = await res.json();
    if (!res.ok) return status(data?.error?.message || `Error ${res.status}`, "err");
    const model = $("model").value.trim() || DEFAULT_MODEL;
    const has = data.data?.some((m) => m.id === model);
    status(has ? `${api.name} key works, and ${model} is available.` : `${api.name} key works, but "${model}" isn't on this account.`, has ? "ok" : "err");
  } catch (e) {
    status(`Couldn't reach ${api.name}: ${e.message}`, "err");
  }
});

// ---------- Price watches ----------

const send = (type, payload) => chrome.runtime.sendMessage({ type, payload }).then((r) => r?.data);
const fmt = (n, currency) => {
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "GBP" }).format(n); } catch { return String(n); }
};

async function renderWatches() {
  const watches = (await send("ST_WATCHES")) || [];
  $("watch-empty").hidden = watches.length > 0;
  $("watch-list").replaceChildren(
    ...watches.map((w) => {
      const li = document.createElement("li");
      const text = document.createElement("div");
      const what = document.createElement("div");
      what.className = "what";
      what.textContent = `${w.item}${w.variant ? ` · ${w.variant}` : ""}`;
      const sub = document.createElement("div");
      sub.className = "sub";
      sub.textContent = [
        w.paid != null && `${fmt(w.paid, w.currency)} at ${w.merchant}`,
        w.target != null && `hoping for ~${fmt(w.target, w.currency)}`,
        w.lastPrice != null && `lowest last check ${fmt(w.lastPrice, w.currency)}`,
        `until ${new Date(w.until).toLocaleDateString()}`,
      ].filter(Boolean).join(" · ");
      text.append(what, sub);
      const buttons = document.createElement("div");
      buttons.className = "row-buttons";
      const check = document.createElement("button");
      check.textContent = "Check now";
      check.onclick = async () => {
        check.disabled = true;
        check.textContent = "Checking…";
        await send("ST_CHECK_WATCH", w.id);
        renderWatches();
      };
      const stop = document.createElement("button");
      stop.textContent = "Stop";
      stop.onclick = async () => {
        await send("ST_STOP_WATCH", w.id);
        renderWatches();
      };
      buttons.append(check, stop);
      li.append(text, buttons);
      return li;
    })
  );
}
renderWatches();
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && Object.keys(changes).some((k) => k.startsWith("watch:"))) renderWatches();
});

// ---------- Activity log ----------

const LOG_KEY = "second-thought-log";

function pretty(data) {
  if (!data) return "";
  try {
    return JSON.stringify(JSON.parse(data), null, 2);
  } catch {
    return data;
  }
}

async function renderLog() {
  const { [LOG_KEY]: log = [] } = await chrome.storage.local.get(LOG_KEY);
  const list = $("log-list");
  list.replaceChildren(
    ...log
      .slice()
      .reverse()
      .map((e) => {
        const li = document.createElement("li");
        if (e.level === "error") li.className = "error";
        const meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = `${new Date(e.t).toLocaleTimeString()} · ${e.where} · `;
        const ev = document.createElement("span");
        ev.className = "event";
        ev.textContent = e.event;
        li.append(meta, ev);
        if (e.data) {
          const d = document.createElement("div");
          d.className = "data";
          d.textContent = pretty(e.data);
          li.append(d);
        }
        return li;
      })
  );
  $("log-empty").hidden = log.length > 0;
}

$("copy-log").addEventListener("click", async () => {
  const { [LOG_KEY]: log = [] } = await chrome.storage.local.get(LOG_KEY);
  const text = log.map((e) => `${new Date(e.t).toISOString()} [${e.where}] ${e.level === "error" ? "ERROR " : ""}${e.event}${e.data ? " " + e.data : ""}`).join("\n");
  await navigator.clipboard.writeText(text);
  status("Log copied.", "ok");
});

$("clear-log").addEventListener("click", async () => {
  await chrome.storage.local.remove(LOG_KEY);
  renderLog();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[LOG_KEY]) renderLog();
});
renderLog();
if (location.hash === "#log") $("log").scrollIntoView();
