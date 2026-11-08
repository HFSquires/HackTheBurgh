// What an account may hold, and nothing else. Card numbers and security codes are refused outright: we only keep
// payment *preferences* (which method, and a card's nickname / brand / last 4 digits).

export const PAYMENT_METHODS = ["card", "paypal", "apple_pay", "google_pay", "klarna", "clearpay"];
export const CARD_BRANDS = ["Visa", "Mastercard", "Amex", "Maestro", "Other"];
const PROFILE_FIELDS = ["givenName", "familyName", "email", "phone", "address1", "address2", "city", "postcode", "country"];
const MAX_CARDS = 5;

export const emptyAccount = () => ({
  profile: {},
  payment: { preferred: null, cards: [] },
  budget: { monthly: 0, spent: 0, monthlySavings: 0, currency: "GBP" },
});

const str = (v, max) => (typeof v === "string" ? v.trim().slice(0, max) : "");
const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= 1_000_000 ? Math.round(n * 100) / 100 : 0;
};

// A run of 12+ digits (spaces/dashes allowed) anywhere looks like a card number.
const looksLikeCardNumber = (s) => /(?:\d[ -]?){12,}/.test(s);

// Returns { account } or { error } (a message safe to show the user).
export function cleanAccount(input) {
  if (!input || typeof input !== "object") return { error: "Nothing to save." };
  if (looksLikeCardNumber(JSON.stringify(input))) {
    return { error: "That looks like a card number. We never store card numbers: only a nickname and the last 4 digits." };
  }
  if (/"(cvv|cvc|csc|securityCode|cardNumber|pan|expiry)"/i.test(JSON.stringify(input))) {
    return { error: "Card numbers, expiry dates and security codes can't be saved here." };
  }

  const profile = {};
  for (const f of PROFILE_FIELDS) {
    const v = str(input.profile?.[f], f === "email" ? 200 : 120);
    if (v) profile[f] = v;
  }
  if (profile.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(profile.email)) return { error: "That email address doesn't look right." };

  const preferred = PAYMENT_METHODS.includes(input.payment?.preferred) ? input.payment.preferred : null;
  const rawCards = Array.isArray(input.payment?.cards) ? input.payment.cards : [];
  if (rawCards.length > MAX_CARDS) return { error: `You can save up to ${MAX_CARDS} cards.` };
  const cards = [];
  for (const c of rawCards) {
    const last4 = typeof c?.last4 === "string" ? c.last4.trim() : "";
    if (!/^\d{4}$/.test(last4)) return { error: "Each card needs exactly the last 4 digits." };
    cards.push({
      nickname: str(c?.nickname, 40) || "Card",
      brand: CARD_BRANDS.includes(c?.brand) ? c.brand : "Other",
      last4,
    });
  }

  const currency = /^[A-Z]{3}$/.test(input.budget?.currency || "") ? input.budget.currency : "GBP";
  const savings = input.budget?.monthlySavings ?? 0;
  if (typeof savings !== "number" || !Number.isFinite(savings) || savings < 0 || savings > 1000000)
    return { error: "Enter a monthly savings goal between 0 and 1,000,000." };
  const budget = { monthlySavings: num(savings), monthly: num(input.budget?.monthly), spent: num(input.budget?.spent), currency };

  return { account: { profile, payment: { preferred, cards }, budget } };
}
