// Hand-off to a cheaper store: when the user picks an alternative, remember their delivery details and, on the
// other store, add the item to the basket, go to checkout and fill the form. Never touches card fields and never
// clicks "place order" / "pay": the user always reviews and pays themselves.
globalThis.ST = globalThis.ST || {};

(() => {
  const KEY = "second-thought-handoff";
  const MAX_AGE = 30 * 60 * 1000;
  const MAX_STEPS = 8;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const hasChromeStorage = () => typeof chrome !== "undefined" && !!chrome.storage?.local;

  // chrome.storage in the extension; localStorage on the demo page (same origin there).
  const store = {
    async get(key = KEY) {
      if (hasChromeStorage()) return (await chrome.storage.local.get(key))[key] || null;
      try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
    },
    async set(value) {
      if (hasChromeStorage()) return chrome.storage.local.set({ [KEY]: value });
      try { localStorage.setItem(KEY, JSON.stringify(value)); } catch {}
    },
    async clear() {
      if (hasChromeStorage()) return chrome.storage.local.remove(KEY);
      try { localStorage.removeItem(KEY); } catch {}
    },
  };

  // "shop.example.co.uk" and "checkout.example.co.uk" count as the same store.
  function baseDomain(host) {
    const p = host.replace(/^www\./, "").split(".");
    const twoPart = p.length >= 3 && p[p.length - 1].length === 2 && /^(co|com|org|net|ac|gov)$/.test(p[p.length - 2]);
    return p.slice(twoPart ? -3 : -2).join(".");
  }

  // ---------- Form fields ----------

  // Order matters: more specific fields first. [key, autocomplete token, hint regex on name/id/label/placeholder]
  const FIELDS = [
    ["email", /^email$/, /e-?mail/],
    ["phone", /^tel/, /phone|mobile|\btel\b|telephone/],
    ["postcode", /^postal-code$/, /post.?code|postal|zip|pin.?code|eircode/],
    ["address2", /^address-line2$/, /address.?(line)?.?2|apartment|\bapt\b|suite|flat|unit/],
    ["address1", /^(address-line1|street-address)$/, /address|street/],
    ["city", /^address-level2$/, /city|town|locality/],
    ["country", /^country(-name)?$/, /country/],
    ["region", /^address-level1$/, /county|state|province|region/],
    ["givenName", /^given-name$/, /first.?name|fname|given/],
    ["familyName", /^family-name$/, /last.?name|lname|surname|family/],
    ["fullName", /^name$/, /full.?name|your name|^name\b|\bname$/],
  ];
  // Payment, passwords and anything account-ish are never read or written.
  const SENSITIVE = /card|cc-|cvc|cvv|csc|expir|security.?code|iban|sort.?code|account|password|promo|coupon|discount|gift|company|business/;

  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);

  function formFields() {
    return [...document.querySelectorAll("input, select, textarea")].filter((el) => {
      if (el.disabled || el.readOnly || !visible(el)) return false;
      // Hidden helper inputs (e.g. Shopify's autofill capture fields) aren't for people; leave them alone.
      if (el.tabIndex < 0 || el.closest('[aria-hidden="true"]')) return false;
      return !/^(hidden|password|checkbox|radio|submit|button|file|image|number|date)$/i.test(el.type || "");
    });
  }

  const hintOf = (el) =>
    [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), el.labels?.[0]?.textContent].filter(Boolean).join(" ").toLowerCase();

  function fieldKey(el) {
    const tokens = (el.getAttribute("autocomplete") || "").toLowerCase().split(/\s+/);
    const ac = tokens[tokens.length - 1] || "";
    const hint = hintOf(el);
    if (ac.startsWith("cc-") || SENSITIVE.test(hint)) return null;
    for (const [key, acRe, hintRe] of FIELDS) if (ac && acRe.test(ac)) return key;
    for (const [key, , hintRe] of FIELDS) if (hintRe.test(hint)) return key;
    return null;
  }

  function readValue(el) {
    if (el.tagName === "SELECT") return el.selectedOptions[0]?.textContent.trim() || "";
    return el.value.trim();
  }

  // What the user already typed on this checkout.
  function captureDetails() {
    const details = {};
    for (const el of formFields()) {
      const key = fieldKey(el);
      const value = key && readValue(el);
      if (value && !details[key]) details[key] = value;
    }
    return details;
  }

  // Sets a value in a way React/Vue/Angular forms notice.
  function setValue(el, value) {
    if (el.tagName === "SELECT") {
      const v = value.toLowerCase();
      const opt = [...el.options].find((o) => o.value.toLowerCase() === v || o.textContent.trim().toLowerCase() === v);
      if (!opt || opt.selected) return false;
      el.value = opt.value;
    } else {
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
    return true;
  }

  // Bridge full name <-> first/last name.
  function withNames(details) {
    const d = { ...details };
    if (!d.fullName && d.givenName) d.fullName = [d.givenName, d.familyName].filter(Boolean).join(" ");
    if (d.fullName && !d.givenName) {
      const parts = d.fullName.split(/\s+/);
      d.givenName = parts[0];
      d.familyName = parts.slice(1).join(" ");
    }
    return d;
  }

  function fill(details) {
    const d = withNames(details);
    let filled = 0;
    const done = new Set(); // one field per kind, the first on the page (the main form)
    for (const el of formFields()) {
      const key = fieldKey(el);
      // "Confirm email" / "Re-enter email" takes the same email again.
      const again = key === "email" && /confirm|re-?enter|repeat|verify|again/.test(hintOf(el));
      if (!key || !d[key] || (done.has(key) && !again)) continue;
      done.add(key);
      if (el.tagName !== "SELECT" && el.value.trim()) continue; // never overwrite what's there
      if (setValue(el, key === "phone" ? phoneFor(el, d.phone) : d[key])) filled++;
    }
    return filled;
  }

  // The LLM fills the form: every site's form is different, so it matches each empty field to the kind of saved
  // detail it asks for, from the labels alone (it never sees the values). The rules in fill() then cover anything it
  // left, and everything when there's no API key. Payment, password and account fields are never sent or filled.
  async function aiFill(details) {
    const d = withNames(details);
    const kinds = Object.keys(d).filter((k) => d[k]);
    const empty = formFields().filter((el) => (el.tagName === "SELECT" ? !el.value : !readValue(el)) &&
      !paymentField(el) && !SENSITIVE.test(`${hintOf(el)} ${el.getAttribute("autocomplete") || ""}`));
    if (!empty.length || !kinds.length) return 0;
    let matches = null;
    try {
      matches = await ST.api.aiFields({
        fields: empty.map((el, i) => ({ field: i, label: fieldLabel(el), name: el.name, placeholder: el.placeholder, type: el.type, autocomplete: el.getAttribute("autocomplete") || "" })),
        details: kinds,
      });
    } catch (e) {
      ST.log.error("handoff: AI field matching failed", e.message);
    }
    let n = 0;
    for (const { field, detail } of matches || []) {
      const el = empty[field];
      if (el && d[detail] && !readValue(el) && setValue(el, detail === "phone" ? phoneFor(el, d.phone) : d[detail])) n++;
    }
    if (matches?.length) ST.log("handoff: AI matched fields the rules couldn't", matches.map((m) => `${empty[m.field] ? fieldLabel(empty[m.field]) : "?"} -> ${m.detail}`));
    return n;
  }

  // Only empty fields of one kind (e.g. the postcode box of a delivery check), with the saved value.
  function fillOnly(details, kind) {
    const value = withNames(details || {})[kind];
    if (!value) return 0;
    let n = 0;
    for (const el of formFields()) {
      if (fieldKey(el) === kind && !readValue(el) && !paymentField(el) && setValue(el, kind === "phone" ? phoneFor(el, value) : value)) n++;
    }
    return n;
  }
  // Questions the AI may ask that a saved detail answers.
  const SAVED_ASK = [
    ["postcode", /post.?code|postal|zip|pin.?code|eircode/i],
    ["email", /e-?mail/i],
    ["phone", /phone|mobile/i],
    ["city", /\b(town|city)\b/i],
    ["fullName", /\b(your|full) name\b/i],
  ];

  // Card, payment or password fields, also unlabelled ones ("MM / YY", "•••" next to "Expiry" / "CVC"): never sent anywhere.
  function paymentField(el) {
    if (el.matches(CARD_OR_PASSWORD) || el.closest(PAYMENT_AREA)) return true;
    const near = el.closest("div, label, p")?.textContent || "";
    return /mm\s*\/\s*yy|^[•*·\s]+$|expir|cvc|cvv|card/i.test(`${el.placeholder || ""} ${near.length < 60 ? near : ""}`);
  }

  // UK numbers in the form the field expects: "07700 900123" style (with the leading 0) wherever the country code is
  // shown separately or the field is too short for "+44"; as saved otherwise.
  function phoneFor(el, phone) {
    const digits = String(phone).replace(/[^\d+]/g, "");
    const uk = digits.match(/^(?:\+44|0044|44)(\d{10})$/) || digits.match(/^0(\d{10})$/);
    if (!uk) return phone;
    const near = el.closest("div, fieldset, label")?.parentElement?.textContent || "";
    const codeShown = /\+\s?44\b/.test(near) && !/\+\s?44\b/.test(el.value);
    const max = el.maxLength > 0 ? el.maxLength : Infinity;
    if (codeShown || max < 13) return max === 10 ? uk[1] : `0${uk[1]}`;
    return phone;
  }

  // Address finders (type a postcode, then choose from a list): choose the saved address, so the form doesn't stop
  // at "Please add a delivery address". Matches the saved first line of the address against the list.
  const norm = (s) => ` ${String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()} `;
  async function chooseFromAddressFinders(d) {
    const want = norm(d.address1);
    if (want.trim().length < 3) return 0;
    const finders = formFields().filter((el) => el.value.trim() &&
      (/find|look ?up|search/.test(hintOf(el)) || el.getAttribute("role") === "combobox" || el.hasAttribute("aria-autocomplete")));
    let chosen = 0;
    for (const el of finders) {
      for (let i = 0; i < 8; i++) {
        const options = [...document.querySelectorAll('[role="option"], [role="listbox"] li, ul li')].filter((o) => visible(o) && o.textContent.length < 200);
        const option = options.find((o) => norm(o.textContent).includes(want));
        if (option) {
          for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) option.dispatchEvent(new MouseEvent(type, { bubbles: true }));
          ST.log("handoff: chose the saved address from the address finder", { option: option.textContent.trim().slice(0, 80) });
          chosen++;
          break;
        }
        await sleep(500);
      }
    }
    return chosen;
  }

  // ---------- Buttons ----------

  const ADD_TO_BASKET = /^\s*(add to (cart|basket|bag|trolley)|add$|pre-?order( now)?$)/i;
  const GO_TO_CHECKOUT = /^\s*(proceed to checkout|go to checkout|continue to checkout|secure checkout|checkout( securely| now)?|check out)\s*$/i;
  // Belt and braces, whatever the rules or the AI pick: never click these.
  // Never clicked, whatever the rules or the AI pick: anything that buys, pays, uses an express wallet or an account.
  // "Pre-order" on a product page just adds to the basket, so it's allowed there.
  const NEVER_ANYWHERE = /place (your )?order|confirm( and| &)? ?(pay|order|purchase|payment)|complete (your )?(order|purchase|payment)|submit order|pay now|^pay\b|\bpay (£|\$|€|securely|with)|buy now|1-click|apple ?pay|google ?pay|g ?pay|shop ?pay|paypal|klarna|clearpay|express checkout|subscribe|sign ?in|log ?in|sign ?up|register|create (an )?account|^(accept|agree|allow)( all)?( cookies)?$|accept (all |additional )?cookies|allow (all )?cookies|i agree|agree (to|and)/i;
  // On the checkout itself, be stricter: nothing about ordering or paying at all.
  const NEVER_AT_CHECKOUT = /order|pay|purchase|confirm/i;
  const forbidden = (label) =>
    NEVER_ANYWHERE.test(label) || (ST.detect.isCheckout() && !GO_TO_CHECKOUT.test(label) && NEVER_AT_CHECKOUT.test(label));

  const labelOf = (el) =>
    (el.getAttribute("aria-label") || el.textContent || el.value || el.title || el.querySelector?.("img")?.alt || "").replace(/\s+/g, " ").trim();

  // ---------- What an element actually does (not just what it says) ----------

  // In ids, names, classes and data-* attributes, e.g. id="place-order-button", data-action="submit-payment".
  const RISKY_CODE = /(place|submit|complete|confirm)[-_ ]?(your[-_ ]?)?(order|purchase|payment)|pay[-_ ]?(now|button|btn|submit)|submit[-_ ]?payment|payment[-_ ]?(submit|button|btn)|buy[-_ ]?now|one[-_ ]?click|1[-_ ]?click|express[-_ ]?(checkout|pay)|apple[-_ ]?pay|google[-_ ]?pay|gpay|shop(ify)?[-_ ]?pay|paypal|klarna|clearpay|afterpay|log[-_ ]?in|sign[-_ ]?(in|up)|signin|signup|register|subscribe/i;
  // Where a link goes or a form posts to.
  const RISKY_URL = /(place|submit|complete|confirm)[-_]?(order|purchase|payment)|\/orders?\/(confirm|submit|place|complete)|\/payments?\/(confirm|submit|process|authori[sz]e)|\/pay(\/|$|\?)|1[-_]?click|buy[-_]?now|\/(login|signin|sign-in|logon|register)\b|\/account\/(login|register)|paypal\.com|klarna\.com|pay\.google\.com|clearpay|afterpay|subscribe/i;
  const PAYMENT_AREA = '[id*="payment" i], [class*="payment" i], [data-testid*="payment" i], [aria-label*="payment" i]';
  const CARD_OR_PASSWORD = 'input[type="password"], [autocomplete^="cc-"], [name*="card" i], [name*="cvv" i], [name*="cvc" i], iframe[src*="pay" i], iframe[title*="card" i], iframe[title*="payment" i]';

  const short = (u) => {
    try {
      const url = new URL(u, location.href);
      return (url.host === location.host ? "" : url.host) + url.pathname.slice(0, 60);
    } catch {
      return "";
    }
  };

  // The form a click would submit, if any (submit buttons, and <button>s with no type inside a form).
  function formSubmittedBy(el) {
    const isSubmit = (el.tagName === "BUTTON" && (el.getAttribute("type") || "submit").toLowerCase() === "submit") ||
      (el.tagName === "INPUT" && /^(submit|image)$/i.test(el.type));
    return isSubmit ? el.form : null;
  }

  // Everything we can tell about what clicking `el` will do.
  function whatItDoes(el) {
    const code = [el.id, el.getAttribute("name"), el.getAttribute("class"), el.getAttribute("value"), el.getAttribute("formaction"),
      ...[...el.attributes].filter((a) => a.name.startsWith("data-") || a.name === "aria-describedby").map((a) => `${a.name}=${a.value}`)]
      .filter(Boolean).join(" ").slice(0, 400);
    const link = el.closest("a[href]");
    const href = link && !/^(javascript:|#)/i.test(link.getAttribute("href")) ? link.href : "";
    const form = formSubmittedBy(el);
    const formAction = form ? el.getAttribute("formaction") || form.getAttribute("action") || location.href : "";
    return {
      label: labelOf(el).slice(0, 60),
      code,
      href,
      form,
      formAction: formAction && new URL(formAction, location.href).href,
      formHasCardOrPassword: !!form?.querySelector(CARD_OR_PASSWORD),
      inPaymentArea: !!el.closest(PAYMENT_AREA),
    };
  }

  // Why clicking `el` isn't allowed, or null if it's fine. Checks the label AND what the element really does.
  function blockReason(el) {
    const d = whatItDoes(el);
    if (forbidden(d.label)) return `its label "${d.label}" is a purchase, payment, account or consent action`;
    const code = d.code.match(RISKY_CODE);
    if (code) return `it's coded as "${code[0]}" (${d.code.slice(0, 80)})`;
    if (d.href && RISKY_URL.test(d.href)) return `it links to ${short(d.href)}`;
    if (d.form && RISKY_URL.test(d.formAction)) return `it submits a form to ${short(d.formAction)}`;
    if (d.formHasCardOrPassword) return "it submits a form with card or password fields";
    if (d.inPaymentArea && !/^(select|input|label)$/i.test(el.tagName)) return "it's inside the payment section";
    return null;
  }

  // Click, with a safety net: while our click is being handled, any order/payment form submission is cancelled,
  // even if the button looked harmless (e.g. a "Continue" that really places the order).
  async function safeClick(el, why = "click") {
    const reason = blockReason(el);
    if (reason) {
      ST.log.error("safety: refused to click", { element: labelOf(el).slice(0, 60), reason });
      return false;
    }
    const guard = (e) => {
      const form = e.target;
      const action = (e.submitter?.getAttribute("formaction") || form.getAttribute("action") || location.href);
      const risky = RISKY_URL.test(new URL(action, location.href).href) || form.querySelector(CARD_OR_PASSWORD) ||
        (e.submitter && blockReason(e.submitter));
      if (risky) {
        e.preventDefault();
        e.stopImmediatePropagation();
        ST.log.error("safety: cancelled a form submission", { after: why, action: short(action) });
      }
    };
    document.addEventListener("submit", guard, true);
    try {
      el.click();
    } finally {
      setTimeout(() => document.removeEventListener("submit", guard, true), 3000);
    }
    return true;
  }

  function findButton(re) {
    const els = document.querySelectorAll('button, a, input[type="submit"], input[type="button"], [role="button"]');
    for (const el of els) {
      const label = labelOf(el);
      if (label.length < 40 && re.test(label) && visible(el) && !el.disabled && !blockReason(el)) return el;
    }
    return null;
  }

  // Pick the same way of paying as on the original store (a radio/option only; card details stay with the user).
  function choosePayment(method) {
    const re = ST.detect.PAYMENT_TYPES.find(([m]) => m === method)?.[1];
    if (!re) return false;
    for (const r of document.querySelectorAll('input[type="radio"], [role="radio"]')) {
      const label = [r.labels?.[0]?.textContent, r.value, r.getAttribute("aria-label"), r.textContent].filter(Boolean).join(" ");
      if (!re.test(label)) continue;
      if (r.checked || r.getAttribute("aria-checked") === "true") return true;
      (r.labels?.[0] || r).click(); // selecting a payment option only; nothing is submitted (and no safeClick: it's in the payment area by design)
      return true;
    }
    return false;
  }

  // ---------- Asking the shopper ----------

  const MAX_ASKS = 4; // per hand-off, so a confused page can't keep prompting
  // Never prompted for, whatever the AI or the form wants.
  const NEVER_ASK = /card|cvv|cvc|csc|expir|security.?code|password|passcode|\bpin\b|one.?time|verification code|sort.?code|iban|bank|sign ?in|log ?in/i;
  // Typing an answer won't get past these.
  const CANT_TYPE_PAST = /sign ?in|log ?in|account|captcha|robot|out of stock|sold out|unavailable|blocked|access denied/i;

  // Shows a question in the panel and waits. Remembers the answer on the hand-off so later pages (and the AI) have it.
  async function askShopper(h, ask, { question, title, placeholder, type, key }) {
    if (NEVER_ASK.test(question) || (h.asks || 0) >= MAX_ASKS) return null;
    h.asks = (h.asks || 0) + 1;
    await store.set(h);
    ST.log("handoff: asking the shopper", { question, asks: h.asks });
    const answer = await ask({ title: title || `One thing we need at ${h.merchant}`, question, placeholder, type });
    ST.log("handoff: shopper answered", answer == null ? "skipped" : "(answer given)");
    if (answer == null) return null;
    h.answers = [...(h.answers || []), { question, answer }];
    if (key) h.details = { ...h.details, [key]: answer };
    await store.set(h);
    return answer;
  }

  // For the activity log only: strip what looks personal (names/addresses after "deliver to", postcodes, card or
  // phone digits, emails). The log is for debugging, not a copy of the shopper's details.
  const redact = (t = "") =>
    t
      .replace(/\b(deliver(ing)?|ship(ping)?|send(ing)?|dispatch(ing)?)( to)?\b.*$/i, "$1 [address]")
      .replace(/\b(paying|pay) with\b.*$/i, "$1 with [payment]")
      .replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, "[email]")
      .replace(/\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b/gi, "[postcode]")
      .replace(/\d{4,}/g, "[number]")
      .slice(0, 50);

  // ---------- Page readiness ----------

  // Wait until the page stops changing (SPAs and slow product pages keep rendering after load), up to `max` ms.
  async function settle(max = 6000) {
    const started = Date.now();
    let last = -1;
    let stableFor = 0;
    while (Date.now() - started < max) {
      const n = document.querySelectorAll("button, a[href], select, input").length;
      stableFor = n === last && document.readyState === "complete" ? stableFor + 400 : 0;
      if (stableFor >= 800) break;
      last = n;
      await sleep(400);
    }
    return Date.now() - started;
  }

  // Cookie banners hide the page behind them. Always take the privacy-friendly choice; never accept.
  const COOKIE_AREA = '[id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i], [id*="onetrust" i], [class*="onetrust" i], [id*="gdpr" i], [class*="cmp" i], [aria-label*="cookie" i], [aria-label*="consent" i], [aria-label*="privacy" i]';
  const REJECT = /^(reject( all)?( cookies)?|decline( all)?|deny( all)?|refuse( all)?|(use |allow )?(only )?(strictly )?(necessary|essential)( cookies)?( only)?|necessary only|essential only|continue without accepting)$/i;

  async function rejectCookies() {
    const candidates = [...document.querySelectorAll('button, a[role="button"], [role="button"], input[type="button"], input[type="submit"]')];
    const btn =
      candidates.find((b) => visible(b) && REJECT.test(labelOf(b)) && b.closest(COOKIE_AREA)) ||
      candidates.find((b) => visible(b) && /^(reject all|reject all cookies|decline all)$/i.test(labelOf(b))) ||
      document.querySelector("#onetrust-reject-all-handler");
    if (!btn || !visible(btn)) return false;
    ST.log("page: cookie banner, chose the privacy option", labelOf(btn));
    btn.click(); // only ever a reject/necessary-only button
    await sleep(800);
    return true;
  }

  // ---------- AI fallback ----------

  // A numbered list of what can be clicked or chosen, for the model. Navigation chrome is left out to keep it short.
  function snapshot() {
    const sel = 'button, a[href], [role="button"], [role="radio"], [role="option"], select, input[type="submit"], input[type="radio"], label';
    const out = [];
    for (const el of document.querySelectorAll(sel)) {
      if (out.length >= 120) break;
      if (el.tagName === "LABEL" && el.control?.type !== "radio") continue;
      if (el.tagName === "INPUT" && el.type === "radio" && (!visible(el) || el.labels?.length)) continue; // its label is listed instead
      if (!visible(el) || el.disabled) continue;
      // aria-hidden usually means decorative, but modals (cookie banners) aria-hide the whole page: keep what's visible then.
      if (el.closest('[aria-hidden="true"]') && !document.querySelector('[role="dialog"], [aria-modal="true"], ' + COOKIE_AREA)) continue;
      const text = labelOf(el).slice(0, 60);
      if (el.closest("header, footer, nav") && !/basket|bag|cart|checkout/i.test(text)) continue;
      if (el.tagName === "SELECT") {
        const opts = [...el.options].map((o) => o.textContent.trim()).slice(0, 25);
        out.push({ el, info: { kind: "dropdown", label: labelOf(el.labels?.[0] || el).slice(0, 40), selected: el.selectedOptions[0]?.textContent.trim(), options: opts } });
        continue;
      }
      if (!text) continue;
      const checked = el.control?.checked || el.checked || el.getAttribute("aria-checked") === "true" || el.getAttribute("aria-pressed") === "true";
      const does = whatItDoes(el);
      const blocked = blockReason(el);
      out.push({
        el,
        info: {
          kind: el.tagName === "A" ? "link" : el.tagName === "LABEL" || el.type === "radio" ? "option" : "button",
          text,
          ...(checked ? { selected: true } : {}),
          ...(does.href ? { goes_to: short(does.href) } : {}),
          ...(does.form ? { submits_form_to: short(does.formAction) } : {}),
          ...(blocked ? { blocked: true } : {}),
        },
      });
    }
    return out;
  }

  // Let the model drive up to a few steps on this page. Returns "acted", "done", "stuck:<reason>" or null (no AI).
  // Rough fingerprint of what's on screen, to tell whether a click changed anything.
  const pageState = () => `${location.href}|${snapshot().map((e) => e.info.text || e.info.selected || "").join("|")}|${(document.body.innerText || "").length}`;
  const MAX_HISTORY = 10;

  async function remember(h, entry) {
    h.history = [...(h.history || []), entry].slice(-MAX_HISTORY);
    await store.set(h);
  }

  async function aiDrive(h, status, ask) {
    // A click that navigated away last time: note it worked, now that we're on the new page.
    const last = h.history?.[h.history.length - 1];
    if (last && last.result === "pending") {
      last.result = last.page === location.pathname ? "page reloaded" : `went to ${location.pathname}`;
      await store.set(h);
    }
    let repeats = 0;
    for (let i = 0; i < 4; i++) {
      // Postcode boxes for stock or delivery checks on the way (Argos's trolley): type the saved postcode in.
      if (fillOnly(h.details, "postcode")) {
        ST.log("handoff: typed the saved postcode into a delivery check");
        await sleep(400);
      }
      const els = snapshot();
      let step;
      const started = Date.now();
      ST.log("ai: asking for next step", {
        page: location.href,
        elements: els.length,
        wanted: h.wanted,
        sees: els.map((e, n) => `${n}:${redact(e.info.text || e.info.label)}${e.info.blocked ? "(blocked)" : ""}`).join(" | "),
      });
      try {
        step = await ST.api.aiStep({
          store: h.merchant,
          url: location.href,
          title: document.title,
          wanted: h.wanted || {},
          saved_details: Object.keys(withNames(h.details || {})).filter((k) => h.details?.[k] || (k === "fullName" && h.details?.givenName)),
          shopper_answers: h.answers || [],
          history: (h.history || []).map(({ page, action, element, value, result }) => ({ page, action, element, value, result })),
          elements: els.map((e, n) => ({ n, ...e.info })),
        });
      } catch (e) {
        ST.log.error("ai: request failed", e.message);
        return `stuck:AI step failed (${e.message})`;
      }
      if (!step) {
        ST.log("ai: skipped, no OpenAI key saved in settings");
        return null;
      }
      const target = els[step.index]?.el;
      ST.log("ai: answer", {
        seconds: ((Date.now() - started) / 1000).toFixed(1),
        ...step,
        element: target ? labelOf(target).slice(0, 60) || target.tagName : null,
      });
      if (step.action === "done") return "done";
      // Missing a detail (or stuck on something an answer could fix): ask the shopper, then carry on with it.
      if (step.action === "ask" || (step.action === "stuck" && !CANT_TYPE_PAST.test(step.reason || ""))) {
        const question = step.action === "ask" && step.question
          ? step.question
          : `${step.reason || "We got stuck"}. Anything that would help us carry on?`;
        // Asking for something already saved (a postcode, an email...): type it in, or answer with it, not the shopper.
        const kind = step.action === "ask" && SAVED_ASK.find(([, re]) => re.test(question))?.[0];
        const saved = kind && withNames(h.details || {})[kind];
        if (saved) {
          const typed = fillOnly(h.details, kind) || formFields().some((el) => fieldKey(el) === kind && readValue(el));
          h.answers = [...(h.answers || []), { question, answer: typed ? `The saved ${kind} is already typed into the page` : saved }];
          await store.set(h);
          ST.log("handoff: answered from saved details instead of asking", { kind, typedIntoPage: typed > 0 });
          continue;
        }
        const answer = await askShopper(h, ask, {
          question,
          placeholder: step.action === "ask" ? "Type your answer" : "e.g. size 10, the blue one, standard delivery",
          title: step.action === "ask" ? undefined : `Stuck at ${h.merchant}`,
        });
        if (answer == null) return `stuck:${step.reason || "Needed a detail from you"}`;
        status(`Setting up your order at ${h.merchant}`, "Thanks, carrying on…");
        continue;
      }
      if (step.action === "stuck") return `stuck:${step.reason}`;

      if (!target) return `stuck:Couldn't find what to click`;
      const element = labelOf(target).slice(0, 60) || target.tagName;
      // Same click on the same page already did nothing: don't loop on it.
      const tried = (h.history || []).some(
        (x) => x.page === location.pathname && x.action === step.action && x.element === element && (x.value || "") === (step.value || "") && x.result === "no visible change"
      );
      if (tried) {
        ST.log.error("ai: wanted to repeat a step that did nothing", { action: step.action, element });
        if (++repeats >= 2) return "stuck:Couldn't get past this page";
        await remember(h, { page: location.pathname, action: step.action, element, value: step.value, result: "no visible change (repeat refused, try something else)" });
        continue;
      }
      const unsafe = step.action === "select" ? null : blockReason(target);
      if (unsafe) {
        ST.log.error("ai: blocked a risky click", { element, reason: unsafe, does: (({ form, ...d }) => d)(whatItDoes(target)) });
        return `stuck:Stopped before "${element.slice(0, 30)}" because ${unsafe}`;
      }
      const before = pageState();
      await remember(h, { page: location.pathname, action: step.action, element, value: step.value, result: "pending" });

      status(`Setting up your order at ${h.merchant}`, step.reason || "Working through the page…");
      if (step.action === "select" && target.tagName === "SELECT") {
        const v = step.value.toLowerCase();
        const opt = [...target.options].find((o) => o.textContent.trim().toLowerCase() === v) ||
          [...target.options].find((o) => o.textContent.trim().toLowerCase().includes(v));
        if (!opt) {
          ST.log.error("ai: option not in dropdown", { wanted: step.value, options: [...target.options].map((o) => o.textContent.trim()) });
          return `stuck:Option "${step.value}" isn't available`;
        }
        target.value = opt.value;
        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        if (ADD_TO_BASKET.test(element) || /add to (cart|basket|bag|trolley)/i.test(element)) {
          h.added = true;
          await store.set(h);
        }
        await safeClick(target, `AI: ${element}`);
      }
      await sleep(2000); // page updates, or navigates (then the next page load carries on)
      const changed = pageState() !== before;
      h.history[h.history.length - 1].result = changed ? "page changed" : "no visible change";
      await store.set(h);
      ST.log("ai: step result", { element, result: h.history[h.history.length - 1].result });
    }
    // Still on this page after several steps: hand back instead of spinning quietly.
    return "stuck:Couldn't get past this page";
  }

  // ---------- Flow ----------

  // Saved settings + whatever was typed on this checkout (typed wins).
  async function collectDetails() {
    const profile = (await store.get("profile")) || {};
    return { ...profile, ...captureDetails() };
  }

  // What the destination store's page picks up. `added` = the link already put the item in the basket.
  // `wanted` = { name, variant, qty, paymentMethod } from the original checkout.
  // `productUrl` = the product page, to fall back to if a basket link doesn't actually add the item.
  function record(url, merchant, details, added, wanted = {}, productUrl = url) {
    // Started on the product page: never send the shopper back there from the basket.
    const triedProductPage = new URL(url).pathname === new URL(productUrl).pathname;
    return { domain: baseDomain(new URL(url).hostname), merchant, details, wanted, productUrl, triedProductPage, created: Date.now(), step: 0, added };
  }

  const atCheckoutForm = () => ST.detect.isCheckout() && formFields().some(fieldKey);

  // Is the wanted item on this page (basket/checkout)? true / false, or null when we can't tell (no name).
  // Matches most of the name's words, so "Sony Grand Theft Auto VI, PS5" finds "Grand Theft Auto VI (PS5)".
  const words = (s) =>
    (s || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, " ").split(" ")
      .filter((w) => w.length >= 3 && !/^(the|and|for|with|pre|order|edition|new|pack)$/.test(w));
  function basketHasItem(h) {
    const want = [...new Set(words(h.wanted?.name))];
    if (!want.length) return null;
    const page = ` ${words(document.body.innerText).join(" ")} `;
    return want.filter((w) => page.includes(` ${w} `)).length / want.length >= 0.6;
  }

  // Basket pages often fill in their items after loading: look again for a few seconds before deciding it's missing.
  async function basketHasItemSoon(h) {
    for (let i = 0; i < 4; i++) {
      const has = basketHasItem(h);
      if (has !== false) return has;
      await sleep(1500);
    }
    return basketHasItem(h);
  }

  // The basket link didn't add the item: try the product page once, else hand back. Never check out without it.
  async function itemMissing(h, status, overToYou) {
    const page = ` ${words(document.body.innerText).join(" ")} `;
    ST.log.error("handoff: the item isn't in this basket, so not going to checkout", {
      wanted: h.wanted?.name,
      wordsNotFound: [...new Set(words(h.wanted?.name))].filter((w) => !page.includes(` ${w} `)),
      page: location.pathname,
    });
    h.added = false;
    if (h.productUrl && !h.triedProductPage && new URL(h.productUrl).pathname !== location.pathname) {
      h.triedProductPage = true;
      await store.set(h);
      status(`Setting up your order at ${h.merchant}`, "The basket link didn't add it. Opening the product page instead…");
      location.assign(h.productUrl);
      return true;
    }
    await store.set(h);
    overToYou(`We couldn't spot ${h.wanted?.name || "your item"} in your ${h.merchant} basket, so we stopped before checkout. Check your basket`);
    return true;
  }

  const fieldLabel = (el) =>
    (el.labels?.[0]?.textContent || el.getAttribute("aria-label") || el.placeholder || el.name || "").replace(/\s+/g, " ").replace(/\*/g, "").trim();
  const INPUT_TYPE = { email: "email", phone: "tel" };

  // Every checkout needs these, even when the form doesn't mark them required.
  const ESSENTIAL = new Set(["email", "givenName", "familyName", "fullName", "address1", "city", "postcode"]);

  // Needed fields still empty after filling, that the shopper can answer (never payment or passwords).
  function missingFields() {
    const seen = new Set();
    return formFields().filter((el) => {
      if (el.tagName === "SELECT" || readValue(el)) return false;
      const required = el.required || el.getAttribute("aria-required") === "true" || el.getAttribute("aria-invalid") === "true" || ESSENTIAL.has(fieldKey(el));
      const label = fieldLabel(el);
      const hint = `${label} ${el.name} ${el.id} ${el.getAttribute("autocomplete") || ""}`.toLowerCase();
      if (!required || !label || SENSITIVE.test(hint) || NEVER_ASK.test(hint) || seen.has(label)) return false;
      seen.add(label);
      return true;
    });
  }

  // Ask for whatever the form still needs, one field at a time, and type it in.
  async function askForMissing(h, ask) {
    let filled = 0;
    for (const el of missingFields()) {
      const key = fieldKey(el);
      const label = fieldLabel(el);
      const answer = await askShopper(h, ask, {
        question: `${h.merchant} needs your ${label.toLowerCase()}, and we don't have it saved.`,
        title: `Missing: ${label}`,
        placeholder: label,
        type: INPUT_TYPE[key] || "text",
        key,
      });
      if (answer == null) break;
      if (el.isConnected && setValue(el, answer)) filled++;
    }
    return filled;
  }

  async function finishAtCheckout(h, status, ask) {
    status(`Filling your details at ${h.merchant}`, "Name, email and delivery address…");
    const fillAll = async () => (await aiFill(h.details)) + fill(h.details); // the LLM first, then the rules
    let n = await fillAll();
    if (!n) { await sleep(1500); n = await fillAll(); } // late-rendering forms
    if (await chooseFromAddressFinders(h.details)) {
      await sleep(800);
      n += await fillAll(); // the chosen address often reveals more address fields
    }
    n += await askForMissing(h, ask);
    const paid = h.wanted?.paymentMethod && choosePayment(h.wanted.paymentMethod);
    // This tab is now on the cheapest price we found: no price search here from now on (content.js).
    try { sessionStorage.setItem(AT_CHEAPEST, h.merchant || "1"); } catch {}
    ST.log("handoff: at checkout", { fieldsFilled: n, detailsAvailable: Object.keys(h.details), paymentWanted: h.wanted?.paymentMethod, paymentSelected: !!paid });
    await store.clear();
    const payName = { paypal: "PayPal", apple_pay: "Apple Pay", google_pay: "Google Pay", klarna: "Klarna", clearpay: "Clearpay", card: "card" }[h.wanted?.paymentMethod];
    const left = missingFields().length;
    status(
      n ? (left ? "Most of your details are filled in" : "Your details are filled in") : `You're at checkout on ${h.merchant}`,
      (n
        ? left ? "Fill in the rest and check them, then pay." : "Check them, then pay."
        : Object.keys(h.details).length
          ? "We couldn't match the form fields, so fill them in as usual."
          : "Add your details in Second Thought's settings to have them filled in next time.") +
        (paid ? ` We picked ${payName} like last time.` : "") +
        " Card details are never filled in for you.",
      true
    );
    return true;
  }

  // Runs on every page load. Returns true if it took over this page.
  const loggedMismatch = new Set();

  async function resume(overlay) {
    const h = await store.get();
    if (!h) return false;
    if (Date.now() - h.created > MAX_AGE) {
      ST.log("handoff: expired (over 30 min old), dropped", h.merchant);
      return store.clear().then(() => false);
    }
    // Extension: the tab that was opened for it, whatever site it's on now. Demo page: same store only.
    const mine = h.tabId != null ? (await ST.api.tabId()) === h.tabId : baseDomain(location.hostname) === h.domain;
    if (!mine) {
      if (!loggedMismatch.has(location.href)) {
        loggedMismatch.add(location.href);
        ST.log("handoff: pending for another tab", { expected: h.tabId ?? h.domain, thisPage: baseDomain(location.hostname) });
      }
      return false;
    }
    ST.log("handoff: picked up on this page", { url: location.href, step: h.step + 1, of: MAX_STEPS, addedToBasket: h.added, wanted: h.wanted });

    const status = (title, sub, done = false) => overlay.showStatus({ title, sub, done });
    const ask = (opts) => overlay.ask(opts);
    const overToYou = (why) => {
      ST.log("handoff: handed back to the shopper", why || "(no reason)");
      overlay.logLink = true;
      return status(`Over to you at ${h.merchant}`, `${why ? why + ". " : ""}${h.added ? "It's in your basket: carry on to checkout" : "Add it to your basket as usual"} and we'll fill in your details there.`, true);
    };

    if (h.step >= MAX_STEPS) {
      await store.clear();
      overToYou("We couldn't get to checkout automatically");
      return true;
    }
    h.step++;
    await store.set(h);

    status(`Setting up your order at ${h.merchant}`, "Waiting for the page to load…");
    const waited = await settle();
    if (await rejectCookies()) await settle(3000);
    ST.log("page: ready", { waitedMs: waited, buttonsAndLinks: document.querySelectorAll("button, a[href]").length });

    if (atCheckoutForm()) {
      if ((await basketHasItemSoon(h)) === false) return itemMissing(h, status, overToYou);
      return finishAtCheckout(h, status, ask);
    }

    // 1) Simple rules: basket already has the item -> checkout button.
    const checkout = findButton(GO_TO_CHECKOUT);
    if (checkout && (h.added || /cart|basket|bag|trolley/i.test(location.pathname + location.hash) || h.step > 1)) {
      if ((await basketHasItemSoon(h)) === false) return itemMissing(h, status, overToYou);
      ST.log("handoff: rule clicked checkout", labelOf(checkout));
      status(`Going to checkout at ${h.merchant}`, "Your item is in the basket.");
      await sleep(400);
      await safeClick(checkout, "rule: checkout");
      return true;
    }

    // 2) AI fallback: chooses the variant, adds to basket, finds checkout on pages the rules don't know.
    ST.log("handoff: no checkout button found by rules, trying AI");
    const ai = await aiDrive(h, status, ask);
    ST.log("handoff: AI outcome", ai ?? "not available");
    if (ai === "done") {
      await sleep(1000);
      if (atCheckoutForm()) return finishAtCheckout(h, status, ask);
    }
    if (ai?.startsWith("stuck:")) {
      overToYou(ai.slice(6));
      return true;
    }
    if (ai === "acted") return true;

    // 3) No AI available: only add to basket ourselves if no size/colour choice is needed.
    const needsChoice = !!h.wanted?.variant && !h.added;
    const add = !h.added && !needsChoice && findButton(ADD_TO_BASKET);
    if (add) {
      ST.log("handoff: rule clicked add to basket", labelOf(add));
      status(`Adding to your basket at ${h.merchant}`, "Same item, lower price.");
      h.added = true;
      await store.set(h);
      await safeClick(add, "rule: add to basket");
      await sleep(2500);
      const next = findButton(GO_TO_CHECKOUT);
      if (next) {
        status(`Going to checkout at ${h.merchant}`, "Your item is in the basket.");
        await safeClick(next, "rule: checkout");
      } else {
        const basket = [...document.querySelectorAll("a[href]")].find((a) => /\/(cart|basket|bag|trolley)\b/i.test(a.pathname) && visible(a) && !blockReason(a));
        if (basket) await safeClick(basket, "rule: basket link");
        else location.assign(new URL("/checkout", location.origin));
      }
      return true;
    }

    overToYou(needsChoice ? `Choose ${h.wanted.variant}` : "");
    return true;
  }

  // The preferred payment method saved on the account page (synced by the extension), or null.
  const savedPaymentMethod = async () => (await store.get("paymentPreference"))?.preferred || null;

  const AT_CHEAPEST = "second-thought:at-cheapest";
  const atCheapest = () => { try { return !!sessionStorage.getItem(AT_CHEAPEST); } catch { return false; } };

  ST.handoff = { KEY, atCheapest, savedPaymentMethod, record, collectDetails, resume, forbidden, blockReason, whatItDoes, safeClick, save: (r) => store.set(r) };
})();
