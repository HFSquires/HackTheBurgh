// Silent price checks started when something goes in the basket, kept for 30 minutes so the checkout can show its
// answer instantly instead of waiting ~40s for a fresh web search. Runs in the background worker (stored in
// chrome.storage.session, which survives the worker going to sleep) or, on the demo page, in sessionStorage.
globalThis.ST = globalThis.ST || {};

(() => {
  const KEY = "second-thought-prechecks";
  const MAX_AGE = 30 * 60 * 1000;
  const MAX_ENTRIES = 20;
  const pending = new Map(); // checks still running, so a second request waits for the first

  const store = {
    async get() {
      if (globalThis.chrome?.storage?.session) return (await chrome.storage.session.get(KEY))[KEY] || [];
      try { return JSON.parse(sessionStorage.getItem(KEY)) || []; } catch { return []; }
    },
    async set(list) {
      if (globalThis.chrome?.storage?.session) return chrome.storage.session.set({ [KEY]: list });
      try { sessionStorage.setItem(KEY, JSON.stringify(list)); } catch {}
    },
  };

  const baseDomain = (url) => {
    const p = new URL(url).hostname.replace(/^www\./, "").split(".");
    const twoPart = p.length >= 3 && p[p.length - 1].length === 2 && /^(co|com|org|net|ac|gov)$/.test(p[p.length - 2]);
    return p.slice(twoPart ? -3 : -2).join(".");
  };
  const words = (s) =>
    (s || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, " ").split(" ")
      .filter((w) => w.length >= 3 && !/^(the|and|for|with|pre|order|edition|new|pack)$/.test(w));
  const namesOf = (payload) => (payload.items || []).map((i) => i.name).filter(Boolean);

  // Same store, same number of items, and each item's name mostly found in one of the checked names.
  function sameBasket(entry, payload) {
    const names = namesOf(payload);
    if (!names.length || entry.domain !== baseDomain(payload.url) || entry.names.length !== names.length) return false;
    return names.every((n) => {
      const want = [...new Set(words(n))];
      return want.length && entry.names.some((m) => {
        const have = new Set(words(m));
        return want.filter((w) => have.has(w)).length / want.length >= 0.6;
      });
    });
  }

  // A recent (or still running) check of this basket, or null.
  async function find(payload) {
    try {
      for (const p of pending.values()) if (sameBasket(p, payload)) return { result: await p.promise, at: p.at, stage: p.stage };
      const list = (await store.get()).filter((e) => Date.now() - e.at < MAX_AGE);
      return list.reverse().find((e) => sameBasket(e, payload)) || null;
    } catch {
      return null;
    }
  }

  // Runs `analyze(payload)` unless this basket was checked recently; remembers the answer.
  async function run(payload, analyze) {
    const existing = await find(payload);
    if (existing) return { ...existing, reused: true };
    const entry = { domain: baseDomain(payload.url), names: namesOf(payload), price: payload.total, at: Date.now(), stage: payload.stage };
    const key = `${entry.domain}|${entry.names.join("|")}`;
    const promise = analyze(payload).then(async (result) => {
      const list = (await store.get()).filter((e) => Date.now() - e.at < MAX_AGE);
      list.push({ ...entry, result });
      await store.set(list.slice(-MAX_ENTRIES));
      return result;
    });
    pending.set(key, { ...entry, promise });
    try {
      return { result: await promise, at: entry.at, stage: entry.stage, reused: false };
    } finally {
      pending.delete(key);
    }
  }

  const money = (n, currency = "GBP") => {
    try { return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(n); } catch { return n.toFixed(2); }
  };

  // Bank picture, if one is saved (persona.js or a future bank connection): what's safe to spend before payday.
  const bank = (settings) => (settings?.money && ST.persona ? ST.persona.safeToSpend(settings.money) : null);
  const inDays = (n) => (n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`);

  // The budget verdict, worked out here from the saved budget (no AI needed): fits / tight / over / no budget.
  // With a bank picture, "over" also means it would eat into money needed for bills due before payday.
  function budgetVerdict(total, currency, settings) {
    const budget = Number(settings?.budget) || 0;
    if (!(budget > 0) || total == null) {
      return { verdict: "neutral", title: "Here's how this price compares", message: "Add a monthly budget in settings and we'll also tell you whether this fits your plan.", insights: [] };
    }
    const left = budget - (Number(settings.spent) || 0);
    const b = bank(settings);
    const insights = [
      { label: "Budget left this month", value: money(Math.max(left, 0), currency) },
      { label: "After this", value: money(left - total, currency) },
    ];
    if (b) {
      insights.push({ label: b.payday ? `Safe to spend until ${b.payday.name.toLowerCase().includes("wage") ? "payday" : b.payday.name.toLowerCase()}` : "Safe to spend", value: money(Math.max(b.safe, 0), currency) });
      if (b.nextBill) insights.push({ label: `${b.nextBill.name} due`, value: `${inDays(b.nextBill.inDays)} · ${money(b.nextBill.amount, currency)}` });
    }
    if (b && total > b.safe) {
      const bills = b.upcoming.map((u) => u.name.toLowerCase()).slice(0, 3).join(", ");
      return {
        verdict: "reconsider",
        title: "This could leave you short",
        message: `After ${bills ? `${bills} ` : ""}due before payday${b.payday ? ` (${inDays(b.payday.inDays)})` : ""}, you have ${money(Math.max(b.safe, 0), currency)} to spend. This is ${money(total, currency)}.`,
        insights,
      };
    }
    if (total > left) {
      return { verdict: "reconsider", title: "This would put you over budget", message: `It's ${money(total, currency)} and you have ${money(Math.max(left, 0), currency)} left this month.`, insights };
    }
    if (total > 0.6 * left) {
      return { verdict: "caution", title: "Worth a pause", message: `This uses most of the ${money(left, currency)} you have left this month${b?.nextBill ? `, with ${b.nextBill.name.toLowerCase()} due ${inDays(b.nextBill.inDays)}` : ""}.`, insights };
    }
    return { verdict: "good", title: "This fits your budget", message: `You'll still have ${money(left - total, currency)} left this month${b ? ` and ${money(b.safe - total, currency)} safe to spend before payday` : ""}.`, insights };
  }

  // Turn an earlier price check into the checkout answer: keep its alternatives and outlook, redo the budget part
  // against the real checkout total (delivery included).
  function forCheckout(earlier, payload, settings) {
    const verdict = budgetVerdict(payload.total, payload.currency, settings);
    const cheaper = (earlier.alternatives || []).length > 0;
    const actions = verdict.verdict === "good" || verdict.verdict === "neutral"
      ? [{ id: "proceed", label: cheaper ? "Buy here instead" : "Continue to pay", variant: cheaper ? "secondary" : "primary" }, { id: "dismiss", label: "Dismiss", variant: "ghost" }]
      : [{ id: "remind", label: "Remind me in 24h", variant: cheaper ? "secondary" : "primary", confirmation: "Got it. We'll remind you tomorrow." }, { id: "proceed", label: "Buy here anyway", variant: "ghost" }];
    return { ...earlier, ...verdict, fromEarlierCheck: true, insights: [...verdict.insights, ...(earlier.insights || []).filter((i) => /prices compared/i.test(i.label))].slice(0, 4), actions };
  }

  // Money left this month, attached to every answer so the page can say "£X over budget" at Place order.
  // `safe` (bank picture) is what's left before payday after upcoming bills; the pause uses the lower of the two.
  function budgetInfo(settings) {
    const budget = Number(settings?.budget) || 0;
    if (!(budget > 0)) return null;
    const left = budget - (Number(settings.spent) || 0);
    const b = bank(settings);
    return { budget, spent: Number(settings.spent) || 0, left, safe: b ? b.safe : null, payday: b?.payday ? { name: b.payday.name, inDays: b.payday.inDays } : null };
  }

  // The affordability model: will this purchase keep the customer on their net-worth goal this month, judged from
  // their accounts read through Open Banking. Null when it's not configured, not running, or has too little history.
  async function modelVerdict(total, currency) {
    const m = ST.config.MODEL || {};
    if (!m.url || !(total > 0) || (currency && currency !== "GBP")) return null;
    try {
      const res = await fetch(`${m.url.replace(/\/$/, "")}/decide`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ bank: { baseUrl: m.bankUrl, persona: m.persona }, price: Math.round(total * 100) / 100 }),
        signal: AbortSignal.timeout(10000),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(d.error || `HTTP ${res.status}`);
      ST.log("affordability model: answer", { price: d.price, verdict: d.verdict, headroom: d.netWorth?.headroom, daysToAfford: d.daysToAfford });
      if (!["good", "caution", "reconsider"].includes(d.verdict)) return null;
      const nw = d.netWorth;
      const month = new Date(`${d.month}-01T12:00:00`).toLocaleDateString("en-GB", { month: "long" });
      const payday = d.income?.nextPayday ? Math.max(0, Math.round((new Date(`${d.income.nextPayday}T12:00:00`) - new Date(`${d.today}T12:00:00`)) / 86400000)) : null;
      const spare = Math.max(nw.surplusWithout, 0);
      const text = {
        good: ["Fits your savings goal", `You'd still end ${month} ${money(nw.headroom)} ahead of your goal.`],
        caution: ["Tight against your goal", `You'd end ${month} only ${money(nw.headroom)} ahead of your goal.`],
        reconsider: [
          "You can't afford this right now",
          `It would leave you ${money(-nw.headroom)} short of your savings goal this ${month}.` +
            (d.daysToAfford ? ` Wait about ${d.daysToAfford} days and it fits.` : " It won't fit within the next 3 months."),
        ],
      }[d.verdict];
      return {
        verdict: d.verdict,
        title: text[0],
        message: text[1],
        insights: [
          { label: `Spare in ${month}`, value: money(spare) },
          payday != null && { label: "Next payday", value: payday === 0 ? "today" : `in ${payday} days` },
        ].filter(Boolean),
        budgetInfo: { budget: d.income?.salary || 0, spent: 0, left: spare, safe: null, payday: null, leftLabel: `spare in ${month} before you miss your savings goal`, fromModel: true },
        // The month the model forecast, for the panel's chart: money across all accounts today, then salary, bills and
        // everyday spending to the month's end (which adds up to the model's forecastEndWithout), and the goal.
        chart: {
          today: d.today,
          end: `${d.month}-${new Date(+d.month.slice(0, 4), +d.month.slice(5, 7), 0).getDate()}`,
          start: nw.now,
          goal: nw.goal,
          price: d.price,
          payday: d.income?.salaryDueThisMonth > 0 ? d.income.nextPayday : null,
          salary: d.income?.salaryDueThisMonth || 0,
          due: (d.regularDueThisMonth || []).map((r) => [r.due, r.amount]),
          everyday: d.everyday?.remainder || 0,
          endWithout: nw.forecastEndWithout,
        },
      };
    } catch (e) {
      ST.log.error("affordability model: not reachable, using the saved budget", e.message);
      return null;
    }
  }

  // The budget part of an answer: the model's verdict when it answers, else the saved budget's numbers.
  async function withBudget(result, payload, settings) {
    const m = await modelVerdict(payload.total, payload.currency);
    if (!m) return { ...result, budgetInfo: budgetInfo(settings) };
    const { budgetInfo: info, ...verdict } = m;
    return { ...result, ...verdict, budgetInfo: info };
  }

  ST.precheck = { run, find, forCheckout, budgetVerdict, budgetInfo, withBudget, modelVerdict, baseDomain };
})();
