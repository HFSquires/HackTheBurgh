// A made-up shopper for demos: who they are, how they pay, and their money this month (balance, bills, payday).
// Nothing here is real. The phone number is in Ofcom's reserved drama range and the email is on example.com.
// "Use demo details" in Options writes this into the same storage keys a real account sync fills, so the extension
// behaves exactly as it would for a signed-in user; the demo pages read it directly.
globalThis.ST = globalThis.ST || {};

(() => {
  const PERSONA = {
    name: "Jamie Ferguson",
    about: "3rd-year Informatics student at Edinburgh. Part-time at a café, student loan three times a year.",
    profile: {
      givenName: "Jamie",
      familyName: "Ferguson",
      email: "jamie.ferguson@example.com",
      phone: "07700 900123",
      address1: "14/3 Marchmont Road",
      address2: "",
      city: "Edinburgh",
      postcode: "EH9 1HX",
      country: "United Kingdom",
    },
    payment: {
      preferred: "card",
      cards: [
        { nickname: "Everyday debit", brand: "Visa", last4: "4821" },
        { nickname: "Monzo", brand: "Mastercard", last4: "0934" },
      ],
    },
    // Discretionary "shopping" budget: what the verdict is mostly judged against.
    budget: { monthly: 250, spent: 138, currency: "GBP" },
    // The bank picture behind that budget. Day numbers are days of the month, so the demo stays current.
    money: {
      currency: "GBP",
      balance: 312.4, // current account right now
      savings: { balance: 850, goal: 1200, goalName: "Interrail in June" },
      income: [
        { name: "Café wages", amount: 620, day: 25 },
        { name: "Student loan instalment", amount: 1890, date: "2027-01-08" },
      ],
      bills: [
        { name: "Rent", amount: 495, day: 1 },
        { name: "Gym", amount: 22, day: 3 },
        { name: "Phone", amount: 18, day: 12 },
        { name: "Spotify", amount: 5.99, day: 15 },
        { name: "Electricity", amount: 38, day: 20 },
      ],
      // Last couple of weeks, newest first. Shown in Options so the demo has a story to point at.
      recent: [
        { date: "2026-11-06", merchant: "Tesco Express", amount: 14.2, category: "Groceries" },
        { date: "2026-11-05", merchant: "Deliveroo", amount: 23.4, category: "Eating out" },
        { date: "2026-11-04", merchant: "Lothian Buses", amount: 2.0, category: "Transport" },
        { date: "2026-11-03", merchant: "Gym", amount: 22, category: "Bills" },
        { date: "2026-11-02", merchant: "Amazon", amount: 31.99, category: "Shopping" },
        { date: "2026-11-01", merchant: "Rent", amount: 495, category: "Bills" },
        { date: "2026-10-31", merchant: "The Pear Tree", amount: 18.6, category: "Eating out" },
        { date: "2026-10-29", merchant: "Blackwell's", amount: 42.5, category: "Shopping" },
        { date: "2026-10-28", merchant: "Lidl", amount: 27.35, category: "Groceries" },
        { date: "2026-10-25", merchant: "Café wages", amount: -620, category: "Income" },
      ],
    },
  };

  const DAY = 24 * 60 * 60 * 1000;
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

  // Next time a day-of-month (or fixed date) comes round, from `now`. Today counts as "today", not next month.
  function nextDue(item, now = new Date()) {
    const today = startOfDay(now);
    if (item.date) return new Date(`${item.date}T00:00:00`);
    let d = new Date(today.getFullYear(), today.getMonth(), item.day);
    if (d < today) d = new Date(today.getFullYear(), today.getMonth() + 1, item.day);
    return d;
  }
  const daysUntil = (date, now = new Date()) => Math.round((startOfDay(date) - startOfDay(now)) / DAY);

  // What's left to spend between now and the next payday once the bills due before it are paid.
  function safeToSpend(money = PERSONA.money, now = new Date()) {
    const paydays = (money.income || []).map((i) => ({ ...i, due: nextDue(i, now) })).sort((a, b) => a.due - b.due);
    const payday = paydays[0] || null;
    const upcoming = (money.bills || [])
      .map((b) => ({ ...b, due: nextDue(b, now) }))
      .filter((b) => !payday || b.due <= payday.due)
      .sort((a, b) => a.due - b.due);
    const committed = upcoming.reduce((s, b) => s + b.amount, 0);
    return {
      currency: money.currency || "GBP",
      balance: money.balance,
      committed,
      safe: Math.round((money.balance - committed) * 100) / 100,
      payday: payday && { name: payday.name, amount: payday.amount, due: payday.due, inDays: daysUntil(payday.due, now) },
      nextBill: upcoming[0] && { name: upcoming[0].name, amount: upcoming[0].amount, due: upcoming[0].due, inDays: daysUntil(upcoming[0].due, now) },
      upcoming: upcoming.map((b) => ({ name: b.name, amount: b.amount, inDays: daysUntil(b.due, now) })),
    };
  }

  // The storage keys the extension reads (same ones account.js fills from a real account).
  const settings = () => ({
    profile: { ...PERSONA.profile },
    budget: PERSONA.budget.monthly,
    spent: PERSONA.budget.spent,
    paymentPreference: { preferred: PERSONA.payment.preferred, cards: PERSONA.payment.cards.map((c) => ({ ...c })) },
    money: JSON.parse(JSON.stringify(PERSONA.money)),
  });

  ST.persona = { ...PERSONA, settings, safeToSpend, nextDue, daysUntil };
})();
