importScripts("config.js", "log.js", "persona.js", "mock.js", "live.js", "handoff.js", "prepare.js", "precheck.js", "account.js");

const getSettings = () => chrome.storage.local.get(["apiKey", "model", "budget", "spent", "money"]);

async function post(path, body) {
  const res = await fetch(`${ST.config.BACKEND_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Backend ${res.status}`);
  return res.json();
}

// Same checkout seen again within 15 minutes (page reload, sign-in round trip): reuse the answer instead of
// paying for another full web search. Keyed on store, total and items, so a changed basket is re-checked.
const RECENT_MS = 15 * 60 * 1000;
const recent = new Map();
const analysisKey = (p) => JSON.stringify([p.merchant, p.total, p.currency, (p.items || []).map((i) => [i.name, i.variant, i.qty])]);

// kind = "analyse" or "outlook": the two calls are cached separately.
async function cached(kind, payload, fresh) {
  const key = kind + analysisKey(payload);
  const hit = recent.get(key);
  if (hit && Date.now() - hit.at < RECENT_MS) {
    ST.log(`${kind}: reused the result from earlier`, { secondsAgo: Math.round((Date.now() - hit.at) / 1000) });
    return hit.result;
  }
  // Two tabs/reloads asking at once share one request.
  const pending = fresh(payload);
  recent.set(key, { at: Date.now(), result: pending });
  try {
    const result = await pending;
    recent.set(key, { at: Date.now(), result });
    return result;
  } catch (e) {
    recent.delete(key);
    throw e;
  }
}

// Checkout: if this basket was price-checked when it was added (precheck.js), answer instantly from that, with the
// budget verdict redone against the real total. Otherwise run the full analysis.
async function analyze(payload) {
  const settings = await getSettings();
  const earlier = await ST.precheck.find(payload);
  let result;
  if (earlier) {
    ST.log("analyse: reused the price check from earlier", { stage: earlier.stage, secondsAgo: Math.round((Date.now() - earlier.at) / 1000) });
    result = ST.precheck.forCheckout(earlier.result, payload, settings);
  } else {
    result = await checkBoth(payload);
  }
  return ST.precheck.withBudget(result, payload, settings);
}

// Silent price check when something goes in the basket (or the basket page is opened): no UI, just remembered,
// plus a "-£3" badge on the toolbar icon when it's cheaper elsewhere.
async function precheck(payload, sender) {
  if (!payload?.items?.length || payload.total == null) return null;
  const { result, reused } = await ST.precheck.run(payload, checkBoth);
  ST.log(reused ? "precheck: already checked" : "precheck: done", {
    stage: payload.stage,
    items: payload.items.map((i) => i.name),
    cheaper: (result.alternatives || []).map((a) => `${a.merchant} ${a.price}`),
  });
  const best = Math.max(0, ...(result.alternatives || []).filter((a) => !ST.excludedStore(a)).map((a) => payload.total - Number(a.price)).filter(Number.isFinite));
  const tabId = sender?.tab?.id;
  if (tabId != null && best >= 1) {
    const sym = { GBP: "£", USD: "$", EUR: "€" }[payload.currency] || "";
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#16a34a" }).catch(() => {});
    chrome.action.setBadgeText({ tabId, text: `-${sym}${Math.round(best)}` }).catch(() => {});
    chrome.action.setTitle({ tabId, title: `Cheaper elsewhere: save about ${sym}${best.toFixed(2)}` }).catch(() => {});
  }
  return ST.precheck.withBudget(result, payload, await getSettings());
}
const outlook = (payload) => cached("outlook", payload, outlookFresh);

// The price comparison and "could it get cheaper if you wait?" together, so the page shows one settled decision
// instead of changing under the shopper. The slower outlook search is capped so it can't hold the checkout up.
const OUTLOOK_WAIT_MS = 40000;
async function checkBoth(payload) {
  const giveUp = new Promise((resolve) => setTimeout(() => resolve(null), OUTLOOK_WAIT_MS));
  const [result, o] = await Promise.all([
    cached("analyse", payload, analyzeFresh),
    Promise.race([
      outlook(payload).catch((e) => (ST.log.error("outlook: failed", e.message), null)),
      giveUp.then(() => (ST.log("outlook: too slow, showing the result without it"), null)),
    ]),
  ]);
  return result.priceOutlook ? result : { ...result, priceOutlook: o };
}

// Priority: the team backend if configured, else live analysis with the user's OpenAI key, else the mock.
async function analyzeFresh(payload) {
  if (ST.config.BACKEND_URL) {
    ST.log("analyse: using team backend", ST.config.BACKEND_URL);
    return post("/analyze", payload);
  }
  const settings = await getSettings();
  if (settings.apiKey) {
    ST.log(`analyse: asking ${ST.apiFor(settings.apiKey).name} with web search`, { model: settings.model || "(default)" });
    return ST.live.analyze(payload, settings);
  }
  ST.log("analyse: no OpenAI key saved, using sample data");
  return ST.mock.analyze(payload);
}

// "Likely cheaper soon?" runs alongside the analysis. A team backend sends it inside /analyze instead (null here).
async function outlookFresh(payload) {
  if (ST.config.BACKEND_URL) return null;
  const settings = await getSettings();
  if (settings.apiKey) {
    ST.log("outlook: checking price history and upcoming sales", { model: settings.model || "(default)" });
    return ST.live.outlook(payload, settings);
  }
  return ST.mock.outlook(payload);
}

async function action(payload) {
  if (payload.actionId === "remind") await scheduleReminder(payload.purchase);
  if (payload.actionId === "watch") await watchPrice(payload);
  if (ST.config.BACKEND_URL) return post("/action", payload);
  return { ok: true };
}

// "Remind me in 24h": a real alarm + notification that reopens the checkout.
async function scheduleReminder(purchase) {
  if (!purchase?.url) return;
  const id = `remind:${Date.now()}`;
  await chrome.storage.local.set({ [id]: { url: purchase.url, merchant: purchase.merchant, total: purchase.total, currency: purchase.currency } });
  chrome.alarms.create(id, { delayInMinutes: 24 * 60 });
}

// "Wait, notify me if it drops": re-check the price twice a day (web search) until it drops, or until a week after the
// date the drop was expected (30 days if none was given, 60 at most).
const DAY = 24 * 60 * 60 * 1000;
const WATCH_EVERY_MIN = 12 * 60;

async function watchPrice({ purchase, outlook }) {
  if (!purchase?.url) return;
  const item = purchase.items?.[0] || {};
  const id = `watch:${Date.now()}`;
  const expected = Date.parse(outlook?.byDate ? `${outlook.byDate}T23:59:59` : "") || Date.now() + 23 * DAY;
  const record = {
    url: purchase.url,
    merchant: purchase.merchant,
    item: item.name || purchase.pageTitle || "",
    variant: item.variant || "",
    qty: item.qty || 1,
    currency: purchase.currency,
    paid: purchase.total,
    target: outlook?.expectedPrice ?? null,
    until: Math.min(expected + 7 * DAY, Date.now() + 60 * DAY),
    created: Date.now(),
  };
  await chrome.storage.local.set({ [id]: record });
  chrome.alarms.create(id, { delayInMinutes: WATCH_EVERY_MIN, periodInMinutes: WATCH_EVERY_MIN });
  ST.log("watch: started", { item: record.item, paid: record.paid, target: record.target, until: new Date(record.until).toDateString() });
}

const fmtMoney = (n, currency) => {
  try { return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "GBP" }).format(n); } catch { return n.toFixed(2); }
};

async function checkWatch(id) {
  const { [id]: r } = await chrome.storage.local.get(id);
  if (!r) return chrome.alarms.clear(id);
  const settings = await getSettings();
  if (!settings.apiKey) return ST.log("watch: skipped, no OpenAI key saved", r.item);
  const now = await ST.live.checkPrice(r, settings).catch((e) => {
    ST.log.error("watch: price check failed", e.message);
    return null;
  });
  // A drop: at or under the expected price, or at least 3% under what they nearly paid (smaller moves are noise).
  const dropped = !!now?.found && now.price > 0 &&
    ((r.target != null && now.price <= r.target) || (r.paid != null && now.price <= r.paid * 0.97));
  ST.log("watch: checked", { item: r.item, paid: r.paid, target: r.target, now: now?.found ? `${now.merchant} ${now.price} ${now.url}` : "not found", dropped });

  if (dropped) {
    await chrome.alarms.clear(id);
    await chrome.storage.local.set({ [id]: { ...r, url: now.url || r.url } }); // the click opens the deal
    const saved = r.paid != null ? `, ${fmtMoney(r.paid - now.price, r.currency)} less than at ${r.merchant}` : "";
    return chrome.notifications.create(id, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "The price dropped",
      message: `${r.item} is ${fmtMoney(now.price, r.currency)} at ${now.merchant}${saved}. Click to have a look.`,
    });
  }
  if (Date.now() > r.until) {
    await chrome.alarms.clear(id);
    return chrome.notifications.create(id, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "No price drop yet",
      message: `${r.item} hasn't got cheaper${now?.found ? ` (lowest now ${fmtMoney(now.price, r.currency)})` : ""}. We've stopped watching. Click to pick up where you left off.`,
    });
  }
  await chrome.storage.local.set({ [id]: { ...r, lastPrice: now?.found ? now.price : null, lastChecked: Date.now() } });
}

async function listWatches() {
  const all = await chrome.storage.local.get(null);
  return Object.entries(all).filter(([k]) => k.startsWith("watch:")).map(([id, r]) => ({ id, ...r }));
}

async function stopWatch(id) {
  await chrome.alarms.clear(id);
  await chrome.storage.local.remove(id);
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name.startsWith("watch:")) return checkWatch(alarm.name);
  if (!alarm.name.startsWith("remind:")) return;
  const { [alarm.name]: r } = await chrome.storage.local.get(alarm.name);
  if (!r) return;
  const amount = r.total != null ? ` (${r.currency} ${r.total.toFixed(2)})` : "";
  chrome.notifications.create(alarm.name, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: "Still thinking about it?",
    message: `You paused a purchase at ${r.merchant}${amount} yesterday. Click to pick up where you left off.`,
  });
});

chrome.notifications.onClicked.addListener(async (id) => {
  const { [id]: r } = await chrome.storage.local.get(id);
  if (r?.url) chrome.tabs.create({ url: r.url });
  chrome.storage.local.remove(id);
  chrome.notifications.clear(id);
});

// Browser use: the model sees the tab as well as the list of what can be clicked. Only the tab being driven is
// captured, and only while it's the visible one (captureVisibleTab can't see background tabs).
async function screenshot(tab) {
  if (!tab?.active) return null;
  try {
    return await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 60 });
  } catch (e) {
    ST.log.error("ai: screenshot failed, using the element list only", e.message);
    return null;
  }
}

async function aiStep(payload, sender) {
  const settings = await getSettings();
  if (!settings.apiKey) return null;
  const image = await screenshot(sender?.tab);
  ST.log("ai: page sent to model", { elements: payload.elements?.length, screenshot: !!image });
  return ST.live.nextStep(payload, settings, image);
}

function openLog() {
  return chrome.tabs.create({ url: chrome.runtime.getURL("options.html#log") });
}

// Account: keep saved details fresh (hourly, and when Chrome starts).
chrome.alarms.create("account-sync", { periodInMinutes: 60 });
const syncQuietly = () => ST.account.sync().catch((e) => ST.log.error("account: sync failed", e.message));
chrome.runtime.onStartup.addListener(syncQuietly);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "account-sync") syncQuietly();
});

const handlers = {
  ST_ACCOUNT_STATUS: () => ST.account.status(),
  ST_ACCOUNT_SIGN_IN: () => ST.account.signIn(),
  ST_ACCOUNT_SYNC: () => ST.account.sync(),
  ST_ACCOUNT_SIGN_OUT: () => ST.account.signOut(),
  ST_ANALYZE: analyze,
  ST_PRECHECK: precheck,
  ST_OUTLOOK: outlook,
  ST_ACTION: action,
  ST_PREPARE: (p) => ST.prepare.prepareCheckout(p),
  ST_AI_STEP: aiStep,
  ST_LOG: (entry) => ST.log.append(entry),
  ST_OPEN_LOG: openLog,
  ST_TAB_ID: (_p, sender) => sender?.tab?.id ?? null,
  ST_WATCHES: listWatches,
  ST_CHECK_WATCH: checkWatch,
  ST_STOP_WATCH: stopWatch,
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const handler = handlers[msg?.type];
  if (!handler) return false;
  Promise.resolve()
    .then(() => handler(msg.payload, sender))
    .then((data) => sendResponse({ ok: true, data }))
    .catch((err) => {
      if (msg.type !== "ST_LOG") ST.log.error(`background: ${msg.type} failed`, String(err?.message || err));
      sendResponse({ ok: false, error: String(err?.message || err) });
    });
  return true; // keep the channel open for the async response
});

// Clicking the toolbar icon forces an analysis on the current tab.
chrome.action.onClicked.addListener((tab) => {
  if (tab.id != null) chrome.tabs.sendMessage(tab.id, { type: "ST_RUN" }).catch(() => {});
});

// First install: open settings so the user can add their key.
chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason !== "install") return;
  const { apiKey } = await getSettings();
  if (!apiKey) chrome.runtime.openOptionsPage();
});
