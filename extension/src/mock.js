// Stand-in for the real backend. Returns responses in the same shape the backend must return
// (see README.md), so the UI can be built and demoed before the backend is ready.
globalThis.ST = globalThis.ST || {};

(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const fmt = (amount, currency = "GBP") => {
    try {
      return new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(amount);
    } catch {
      return `${amount.toFixed(2)}`;
    }
  };

  const round = (n) => Math.round(n * 100) / 100;

  // A link that lands on the other store's checkout with the basket already filled in.
  // The real backend should return a cart permalink (see README); the mock fakes one.
  const altUrl = (p, merchant, price) => {
    if (ST.config.MOCK_ALT_URL) {
      const u = new URL(ST.config.MOCK_ALT_URL);
      u.searchParams.set("store", merchant);
      u.searchParams.set("total", round(price).toFixed(2));
      return u.toString();
    }
    // No real store to send people to: on the demo page, loop back to the demo checkout; on real sites, no link
    // (the alternative is then dropped rather than opening a search page nobody can check out from).
    if (typeof location !== "undefined" && /^(localhost|127\.0\.0\.1)$/.test(location.hostname)) {
      return new URL("checkout.html", location.href).toString();
    }
    return null;
  };

  // Next Black Friday (the day after the 4th Thursday of November), as YYYY-MM-DD.
  const blackFriday = () => {
    const now = new Date();
    for (const y of [now.getFullYear(), now.getFullYear() + 1]) {
      const firstThu = ((4 - new Date(y, 10, 1).getDay() + 7) % 7) + 1;
      const d = new Date(y, 10, firstThu + 22);
      if (d > now) return `${y}-11-${String(d.getDate()).padStart(2, "0")}`;
    }
  };
  const outlook = (p) => ({
    likelihood: "likely",
    expectedPrice: round(p.total * 0.78),
    byDate: blackFriday(),
    reason: "Jackets like this were about 20% off last Black Friday, and it's coming up.",
    signals: ["£139 at Outdoor Depot on Black Friday 2025", "Price unchanged for 8 weeks"],
  });

  const scenarios = {
    good: (p) => ({
      verdict: "good",
      title: "This fits your plan",
      message: `You budgeted for this. After ${fmt(p.total, p.currency)} you'll still have room left in Shopping this month.`,
      insights: [
        { label: "Shopping budget left", value: fmt(420, p.currency) },
        { label: "After this", value: fmt(420 - p.total, p.currency) },
      ],
      // Fits the budget AND is cheaper elsewhere: the two are shown separately.
      alternatives: p.total > 60
        ? [{ merchant: "Outdoor Depot", price: round(p.total * 0.9), note: "Same items · free delivery", match: "exact", url: altUrl(p, "Outdoor Depot", p.total * 0.9) }]
        : [],
      actions: [
        { id: "proceed", label: p.total > 60 ? "Buy here instead" : "Continue to pay", variant: p.total > 60 ? "secondary" : "primary" },
        { id: "dismiss", label: "Dismiss", variant: "ghost" },
      ],
    }),
    neutral: (p) => ({
      verdict: "neutral",
      title: "Here's how this price compares",
      message: "Add a monthly budget in settings and we'll also tell you whether this fits your plan.",
      insights: [],
      alternatives: [
        { merchant: "Outdoor Depot", price: round(p.total * 0.86), note: "Same items · free delivery", match: "exact", url: altUrl(p, "Outdoor Depot", p.total * 0.86) },
      ],
      actions: [
        { id: "proceed", label: "Buy here instead", variant: "secondary" },
        { id: "dismiss", label: "Dismiss", variant: "ghost" },
      ],
    }),
    caution: (p) => ({
      verdict: "caution",
      title: "You might want to wait on this",
      message: `This uses most of what's left for Shopping this month. The same basket is cheaper at Outdoor Depot.`,
      insights: [
        { label: "Shopping budget left", value: fmt(p.total * 1.25, p.currency) },
        { label: "After this", value: fmt(p.total * 0.25, p.currency) },
      ],
      alternatives: [
        { merchant: "Outdoor Depot", price: round(p.total * 0.86), note: "Same items · free delivery", match: "exact", url: altUrl(p, "Outdoor Depot", p.total * 0.86) },
        { merchant: "Peak & Pine", price: round(p.total * 0.8), note: "Delivery in 2 days", match: "different_variant", variant: "Moss · M", matchNote: "Moss green, not Forest", url: altUrl(p, "Peak & Pine", p.total * 0.8) },
      ],
      actions: [
        { id: "remind", label: "Remind me in 24h", variant: "secondary", confirmation: "Got it. We'll check in tomorrow." },
        { id: "proceed", label: "Buy here anyway", variant: "ghost" },
      ],
    }),
    reconsider: (p) => ({
      verdict: "reconsider",
      title: "This could leave you short",
      message: `Paying ${fmt(p.total, p.currency)} now puts you ${fmt(p.total * 0.4, p.currency)} over budget, with rent due on the 1st.`,
      insights: [
        { label: "Over budget by", value: fmt(p.total * 0.4, p.currency) },
        { label: "Rent due", value: "in 6 days" },
      ],
      actions: [
        { id: "save", label: "Save for later", variant: "primary", confirmation: "Saved. We'll tell you when it fits." },
        { id: "remind", label: "Remind me after payday", variant: "secondary", confirmation: "We'll remind you after payday." },
        { id: "proceed", label: "Buy anyway", variant: "ghost" },
      ],
    }),
  };

  ST.mock = {
    async analyze(payload) {
      await sleep(1800 + Math.random() * 1200);
      const total = payload.total ?? 0;
      const pick = ST.config.MOCK_SCENARIO || (total < 60 ? "good" : total < 250 ? "caution" : "reconsider");
      if (pick === "error") throw new Error("Mock backend error");
      return scenarios[pick]({ ...payload, total });
    },
    // Comes in a few seconds after the analysis, like the real separate call.
    async outlook(payload) {
      await sleep(4500 + Math.random() * 1500);
      const total = payload.total ?? 0;
      return total > 60 ? outlook({ ...payload, total }) : { likelihood: "unlikely", expectedPrice: null, byDate: "", reason: "", signals: [] };
    },
    async action() {
      await sleep(300);
      return { ok: true };
    },
  };
})();
