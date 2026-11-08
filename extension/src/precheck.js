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

  // "Could it get cheaper?" finished after the price check was saved: add it, so the checkout can reuse both.
  async function addOutlook(payload, priceOutlook) {
    if (!priceOutlook) return;
    const domain = baseDomain(payload.url);
    const names = namesOf(payload).join("|");
    const list = await store.get();
    const entry = list.find((e) => e.domain === domain && e.names.join("|") === names);
    if (!entry || entry.result.priceOutlook) return;
    entry.result = { ...entry.result, priceOutlook };
    await store.set(list);
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

  // What the customer can pay with right now, read from their banks through Open Banking (here the mock bank):
  // money in current and savings accounts, unused arranged overdraft and unused card credit. Null if unknown.
  async function cashPosition(m, persona) {
    const opts = { signal: AbortSignal.timeout(5000) };
    const bank = m.bankUrl.replace(/\/$/, "");
    const res = await fetch(`${bank}/mock/consent`, {
      ...opts, method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ persona }),
    });
    const { consents } = await res.json();
    if (!Array.isArray(consents) || !consents.length) return null;
    const out = { inAccounts: 0, overdraftLeft: 0, cardCreditLeft: 0 };
    for (const c of consents) {
      const base = `${bank}/providers/${c.provider}/open-banking/v3.1/aisp`;
      const get = (path) => fetch(base + path, { ...opts, headers: { authorization: `Bearer ${c.access_token}` } }).then((r) => r.json()).then((j) => j.Data || {});
      for (const a of (await get("/accounts")).Account || []) {
        const all = (await get(`/accounts/${a.AccountId}/balances`)).Balance || [];
        const b = all.find((x) => x.Type === "InterimAvailable") || all.find((x) => x.Type === "InterimBooked");
        if (!b) continue;
        const amount = Number(b.Amount.Amount) * (b.CreditDebitIndicator === "Debit" ? -1 : 1);
        const limit = (b.CreditLine || []).filter((l) => !l.Included).reduce((s, l) => s + Number(l.Amount.Amount), 0);
        if (a.AccountSubType === "CreditCard") out.cardCreditLeft += Math.max(0, limit + amount);
        else {
          out.inAccounts += Math.max(0, amount);
          out.overdraftLeft += Math.max(0, limit + Math.min(0, amount));
        }
      }
    }
    return out;
  }

  // The LLM rewrites the panel's words from the model's figures, but only if it keeps the most serious problem:
  // "can't pay" must stay "can't pay", an overdraft must stay an overdraft. Otherwise the built-in words stay.
  const MUST_SAY = { cannot: /can.?t pay|more than you have|not enough/i, overdraft: /overdra|below (zero|£0)|minus|[−-]£\d/i };
  const phrased = new Map(); // same facts, same words: a check asks twice (quick answer, then the full one)
  async function phraseWith(phrase, facts, must) {
    const key = JSON.stringify(facts);
    if (!phrased.has(key)) phrased.set(key, phrase(facts).catch((e) => (phrased.delete(key), Promise.reject(e))));
    let timer;
    const tooSlow = new Promise((_, no) => (timer = setTimeout(() => no(new Error("took over 8 s")), 8000)));
    const words = await Promise.race([phrased.get(key), tooSlow]).finally(() => clearTimeout(timer));
    if (must && !must.test(`${words.title} ${words.message}`)) throw new Error("left out the main warning");
    return words;
  }
  const phraser = (settings) => (settings?.apiKey && ST.live?.phraseDecision ? (facts) => ST.live.phraseDecision(facts, settings) : null);

  // The statistical forecast is authoritative. A saved shopping budget or LLM wording must not
  // conceal a projected overdraft or a failed bank check.
  async function modelVerdict(payload, settings = {}) {
    const m = ST.config.MODEL || {};
    const persona = settings.bankPersona ?? m.persona;
    if (!m.url || !persona) return null;
    const unavailable = {
      verdict: "neutral", risk: "unknown", title: "Your bank forecast is unavailable",
      message: "We couldn’t check your overdraft risk or savings goal. Check your balance before buying.",
      insights: [], budgetInfo: null, chart: null,
    };
    if (payload.currency !== "GBP") return { ...unavailable, message: "The sample bank uses pounds. We can’t assess this purchase in another currency." };
    const offer = payload.paymentOptions?.find(o => o.paymentPlan === "pay_in_3");
    if (payload.paymentPlan === null) return { ...unavailable, title: "Check this payment plan",
      message: "We can’t yet forecast the repayment terms of the selected checkout option." };
    if (payload.paymentPlan === "pay_in_3" && !offer) return { ...unavailable, title: "Instalments not found",
      message: "No supported pay-in-3 option is visible at this checkout." };
    try {
      const res = await fetch(`${m.url.replace(/\/$/, "")}/decide`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ bank: { baseUrl: m.bankUrl, persona }, price: payload.total,
          monthlySavings: settings.monthlySavings ?? 0, paymentPlan: payload.paymentPlan || "pay_now" }),
        signal: AbortSignal.timeout(15000),
      });
      if (!res.ok) return unavailable;
      const d = await res.json();
      if (!d.cashFlow || !d.savings) return { ...unavailable, title: d.title || unavailable.title, message: d.message || unavailable.message };
      const nw = d.netWorth;
      const spread = d.paymentPlan === "pay_in_3";
      const short = {
        overdraft: ["Overdraft risk", `At your usual spending rate, your balance could fall to ${money(d.cashFlow.lowestWithPurchase)}.`],
        savings: ["Savings goal at risk", `This could leave you ${money(d.savings.shortfall)} short of your ${money(d.savings.monthlyTarget)} goal.`],
        none: ["Fits your plan", "Your savings goal stays on track at your usual spending rate."],
      }[d.risk];
      let title = short ? (spread ? "Pay in 3: " + short[0].toLowerCase() : short[0]) : d.title;
      let message = spread && d.comparison && d.risk === "overdraft"
        ? (d.cashFlow.lowestWithPurchase > d.comparison.payNow.lowestWithPurchase + 0.01
            ? "Spreading payments helps, but you’re still projected to go overdrawn."
            : "Spreading payments doesn’t remove the projected overdraft.")
        : short ? short[1] : d.message;

      // Overdraft forecast: can they pay at all today? More than their money plus overdraft and card credit is a
      // payment that would be refused, which outranks the forecast.
      const firstPayment = spread ? d.payments?.[0]?.amount ?? payload.total : payload.total;
      const cash = d.risk === "overdraft" ? await cashPosition(m, persona).catch(() => null) : null;
      const shortBy = cash ? firstPayment - (cash.inAccounts + cash.overdraftLeft + cash.cardCreditLeft) : 0;
      if (shortBy > 0) {
        title = "You can’t pay for this";
        message = `It’s ${money(shortBy)} more than you have, even with your overdraft.`;
      }

      // The LLM writes the words from the same figures, if it keeps the main warning (see phraseWith).
      const phrase = phraser(settings);
      if (phrase) {
        const facts = {
          risk: shortBy > 0 ? "cannot pay at all" : d.risk,
          paymentPlan: spread ? "pay in 3" : "pay now",
          price: payload.total,
          shortByEvenWithOverdraftAndCard: shortBy > 0 ? Math.round(shortBy) : null,
          lowestBalanceThisMonth: Math.round(d.cashFlow.lowestWithPurchase),
          lowestBalanceDate: d.cashFlow.lowestDate,
          monthEndBalance: Math.round(d.cashFlow.forecastMonthEnd),
          savingsShortfall: d.savings.shortfall > 0 ? Math.round(d.savings.shortfall) : null,
          monthlySavingsGoal: Math.round(d.savings.monthlyTarget),
          payNowLowestBalance: spread && d.comparison ? Math.round(d.comparison.payNow.lowestWithPurchase) : null,
          builtInWording: `${title}. ${message}`,
        };
        try {
          ({ title, message } = await phraseWith(phrase, facts, shortBy > 0 ? MUST_SAY.cannot : d.risk === "overdraft" ? MUST_SAY.overdraft : null));
          ST.log("affordability: words written by the LLM", { title, message });
        } catch (e) {
          ST.log.error("affordability: kept the built-in words", e.message);
        }
      }
      return {
        verdict: d.verdict, risk: d.risk,
        title,
        message,
        explanation: d.message,
        forecastNote: `Sample bank · forecast as of ${d.today} · main current account · ${spread ? "illustrative interest-free pay in 3" : "pay now"}.`,
        financeAction: spread ? { id: "pay_now", label: "Compare pay now" }
          : offer ? { id: "pay_in_3", label: `Check ${offer.label}` } : null,
        paymentLabel: spread ? offer.label : "Pay now",
        paymentSummary: spread ? `${d.payments.map(p => money(p.amount)).join(" + ")} · monthly estimate` : "",
        laterPayments: spread ? "Upcoming payments: " + d.payments.slice(1).map(p =>
          `${money(p.amount)} in ${new Date(`${p.date}T12:00:00`).toLocaleDateString("en-GB", { month: "long" })}`).join(" and ") + "." : "",
        monthEnd: {
          month: new Date(`${d.month}-01T12:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" }),
          payNow: d.comparison ? d.comparison.payNow.forecastMonthEnd : d.cashFlow.forecastMonthEnd,
          payIn3: spread ? d.cashFlow.forecastMonthEnd : null,
        },
        comparison: d.comparison ? {
          payNow: money(d.comparison.payNow.lowestWithPurchase), payIn3: money(d.comparison.payIn3.lowestWithPurchase),
          horizon: d.cashFlow.horizon, schedule: d.payments.map(p => `${money(p.amount)} on ${p.date}`).join("; "),
          note: d.paymentAssumption,
        } : null,
        insights: [
          { label: "Lowest projected balance", value: money(d.cashFlow.lowestWithPurchase) },
          { label: "Monthly savings goal", value: money(d.savings.monthlyTarget) },
          { label: "Projected savings this month", value: money(d.savings.forecastSaved) },
          { label: "Suggested daily budget", value: money(d.savings.suggestedDailyBudget) },
        ],
        budgetInfo: null, // The bank warning replaces the manual-budget Place order guard.
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
      ST.log.error("affordability model: unavailable", e.message);
      return unavailable;
    }
  }

  // The budget part of an answer: the model's verdict when it answers, else the saved budget's numbers.
  async function withBudget(result, payload, settings) {
    const m = await modelVerdict(payload, settings);
    if (!m) return { ...result, budgetInfo: budgetInfo(settings) };
    const { budgetInfo: info, ...verdict } = m;
    return { ...result, ...verdict, budgetInfo: info };
  }

  ST.precheck = { run, find, forCheckout, budgetVerdict, budgetInfo, withBudget, modelVerdict, addOutlook, baseDomain };
})();
