// Decides whether the current page is a checkout, and pulls what we can out of it for the backend.
globalThis.ST = globalThis.ST || {};

(() => {
  // Checkout-ish URLs across common platforms: Shopify (/checkouts/), Amazon (/gp/buy/, /checkout/),
  // WooCommerce (/checkout/), Magento (/onestepcheckout), eBay (pay.ebay.*), Stripe/PayPal hosted pages.
  const URL_HINT = /(check-?out|\/gp\/buy\/|\/payment|\/billing|place-?order|order[-_/]?review|\/purchase\b|\/buy\/)/i;
  const HOST_HINT = /^(pay|checkout|secure-?checkout|buy)\./i;
  // "Buy now" is left out on purpose: it appears on almost every product page.
  const BUTTON_HINT =
    /^\s*(place (your )?order|pay( now| securely| £| \$| €|$)|complete (your )?(purchase|order|payment)|confirm (and|&) pay|confirm (purchase|order|payment)|submit order|buy and pay|purchase|order and pay|pay with)/i;

  const SYMBOL = { "£": "GBP", $: "USD", "€": "EUR", "¥": "JPY", "₹": "INR", "US$": "USD", "A$": "AUD", "C$": "CAD" };
  const NUM = String.raw`\d{1,3}(?:[,.\s ]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?`;
  // "£1,234.56", "US$ 12", "GBP 12.00", "12,34 €", "12.00 GBP"
  const MONEY = new RegExp(
    String.raw`(US\$|A\$|C\$|[£$€¥₹])\s?(${NUM})|\b(GBP|USD|EUR|AUD|CAD|INR|JPY)\s?[£$€]?\s?(${NUM})|(${NUM})\s?(€|£|GBP|EUR|USD)(?!\w)`,
    "i"
  );
  const MONEY_G = new RegExp(MONEY.source, "gi");

  // Handles both "1,234.56" and "1.234,56".
  function toNumber(raw) {
    let s = raw.replace(/[\s ]/g, "");
    const lastSep = Math.max(s.lastIndexOf("."), s.lastIndexOf(","));
    if (lastSep !== -1 && s.length - lastSep - 1 <= 2) {
      s = s.slice(0, lastSep).replace(/[.,]/g, "") + "." + s.slice(lastSep + 1);
    } else {
      s = s.replace(/[.,]/g, "");
    }
    return parseFloat(s);
  }

  function parseMoney(text) {
    const m = text && text.match(MONEY);
    if (!m) return null;
    const [sym, num] = m[1] ? [m[1], m[2]] : m[3] ? [m[3], m[4]] : [m[6], m[5]];
    const currency = SYMBOL[sym] || sym.toUpperCase();
    const amount = toNumber(num);
    return Number.isFinite(amount) ? { currency: currency.length === 3 ? currency : "GBP", amount } : null;
  }

  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);

  function hasCheckoutButton() {
    const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"], a[role="button"], [role="button"]');
    for (const b of buttons) {
      const label = (b.textContent || b.value || b.getAttribute("aria-label") || "").trim();
      if (label.length < 40 && BUTTON_HINT.test(label) && visible(b)) return true;
    }
    return false;
  }

  // Needs a checkout signal *and* a price on the page, to avoid firing on random pages.
  function isCheckout() {
    const signal =
      URL_HINT.test(location.pathname + location.search) || HOST_HINT.test(location.hostname) || hasCheckoutButton();
    return signal && MONEY.test(document.body?.innerText || "");
  }

  // Find the order total: a "total" label (not subtotal/savings/tax) with a money amount nearby.
  // Prefer explicit labels like "order total"; among equals take the last one on the page.
  function findTotal() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let best = null;
    while (walker.nextNode()) {
      const text = walker.currentNode.nodeValue;
      if (text.length > 60 || !/total/i.test(text)) continue;
      if (/sub-?total|saving|discount|tax|vat|items? total|before/i.test(text)) continue;
      const el0 = walker.currentNode.parentElement;
      if (!el0 || !visible(el0)) continue;
      const rank = /(order|grand|estimated) total|total (due|to pay|payable|amount)|amount due|you pay/i.test(text) ? 2 : 1;
      let el = el0;
      for (let i = 0; el && i < 4; i++, el = el.parentElement) {
        const t = el.innerText || "";
        if (t.length > 200) break;
        const money = parseMoney(t);
        if (money) {
          if (!best || rank >= best.rank) best = { ...money, rank };
          break;
        }
      }
    }
    if (best) return best;

    // Fallback: the biggest amount on the page.
    const all = [...(document.body.innerText || "").matchAll(MONEY_G)].map((m) => parseMoney(m[0])).filter(Boolean);
    return all.sort((a, b) => b.amount - a.amount)[0] || null;
  }

  // Basket-row text that isn't the product: buttons, labels and stock notes.
  const ITEM_JUNK = /^(sub-?total|total|price|remove|delete|edit|change|update|save for later|move to (wish ?list|favourites)|add to (wish ?list|favourites)|each|in stock|out of stock|free (delivery|returns)|qty|quantity|[-+−])$/i;

  function findItems() {
    const sel = [
      "[data-st-item]",
      '[class*="cart-item" i]', '[class*="cartitem" i]', '[class*="line-item" i]', '[class*="lineitem" i]',
      '[class*="basket-item" i]', '[class*="order-item" i]', '[class*="product-item" i]',
      '[data-testid*="line-item" i]', '[data-testid*="cart-item" i]',
    ].join(",");
    const nodes = [...document.querySelectorAll(sel)].filter((n) => visible(n) && !n.parentElement?.closest(sel));
    return nodes.slice(0, 20).map((n) => {
      const text = n.innerText || "";
      const price = parseMoney(text);
      const qtyMatch = text.match(/(?:qty|quantity)\s*:?\s*(\d+)|[×x]\s*(\d+)\b/i);
      const lines = text
        .split("\n")
        .map((s) => s.replace(/(?:qty|quantity)\s*:?\s*\d+/gi, "").trim())
        .filter((s) => s && !MONEY.test(s) && !ITEM_JUNK.test(s));
      let name = lines[0] || "";
      let rest = lines.slice(1);
      // Brand on its own line above the product ("Sony" / "Grand Theft Auto VI, PS5"): join them.
      if (name.length <= 20 && name.split(/\s+/).length <= 2 && rest[0]?.length > 12) {
        name = `${name} ${rest[0]}`;
        rest = rest.slice(1);
      }
      // What's left usually holds the variant: "Forest · M", "Colour: Navy", "Size 10", "Pre-order".
      const variant = rest
        .join(" · ")
        .split("·")
        .map((s) => s.trim())
        .filter(Boolean)
        .join(" · ");
      return { name, variant, qty: Number(qtyMatch?.[1] || qtyMatch?.[2]) || 1, price: price?.amount ?? null };
    });
  }

  // Which way the shopper chose to pay (type only, never card data), so the same option can be picked elsewhere.
  const PAYMENT_TYPES = [
    ["paypal", /paypal/i],
    ["apple_pay", /apple\s?pay/i],
    ["google_pay", /google\s?pay|gpay/i],
    ["klarna", /klarna/i],
    ["clearpay", /clearpay|afterpay/i],
    ["card", /card|credit|debit/i],
  ];
  function paymentMethod() {
    for (const r of document.querySelectorAll('input[type="radio"]:checked, [role="radio"][aria-checked="true"]')) {
      const label = [r.labels?.[0]?.textContent, r.value, r.name, r.getAttribute("aria-label"), r.textContent].filter(Boolean).join(" ");
      const hit = PAYMENT_TYPES.find(([, re]) => re.test(label));
      if (hit) return hit[0];
    }
    return null;
  }

  // Visible text for the backend to reason over, with obvious personal data stripped.
  function pageText() {
    return (document.body.innerText || "")
      .replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, "[email]")
      .replace(/\b(?:\d[ -]?){8,}\b/g, "[number]")
      .replace(/\s+/g, " ")
      .slice(0, 4000);
  }

  function scrape() {
    const total = findTotal();
    const site =
      document.querySelector('meta[property="og:site_name"]')?.content ||
      document.querySelector('meta[name="application-name"]')?.content;
    return {
      url: location.href,
      merchant: site || location.hostname.replace(/^(www|pay|checkout|secure)\./, ""),
      pageTitle: document.title,
      total: total?.amount ?? null,
      currency: total?.currency ?? "GBP",
      items: findItems(),
      paymentMethod: paymentMethod(),
      pageText: pageText(),
      timestamp: new Date().toISOString(),
    };
  }

  ST.detect = { isCheckout, scrape, parseMoney, PAYMENT_TYPES };
})();
