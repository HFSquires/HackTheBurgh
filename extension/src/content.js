// Entry point: watches for checkout pages, runs the analysis and wires the overlay to the backend.
(() => {
  const ST = globalThis.ST;
  const html = document.documentElement;
  if (html.dataset.secondThought) return; // already running (e.g. demo page + extension)
  html.dataset.secondThought = "1";

  const VERDICTS = ["good", "caution", "reconsider", "neutral"];
  const VARIANTS = ["primary", "secondary", "ghost"];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // Closing the panel keeps the extension quiet on this store for the rest of the session.
  const dismissedKey = () => `second-thought:quiet:${location.hostname}`;
  const isQuiet = () => {
    try { return !!sessionStorage.getItem(dismissedKey()); } catch { return false; }
  };

  const overlay = new ST.Overlay();
  overlay.onClose = () => {
    try { sessionStorage.setItem(dismissedKey(), "1"); } catch {}
  };

  let running = false;
  let handledHref = null;
  let lastPayload = null;
  let lastResult = null;

  const money = (n, currency, digits = 2) => {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
    } catch {
      return n.toFixed(digits);
    }
  };
  const isWebUrl = (u) => {
    try { return ["http:", "https:"].includes(new URL(u).protocol); } catch { return false; }
  };

  // Cheaper options, cheapest first. Savings are worked out from the scraped total if the backend doesn't send them.
  function normalizeAlternatives(list, payload) {
    return (Array.isArray(list) ? list : [])
      .filter((a) => a && a.merchant && isWebUrl(a.url) && Number.isFinite(Number(a.price)))
      .map((a) => {
        const price = Number(a.price);
        const currency = a.currency || payload?.currency || "GBP";
        const savings = a.savings != null ? Number(a.savings) : payload?.total != null ? payload.total - price : null;
        return {
          merchant: String(a.merchant),
          url: String(a.url),
          note: a.note ? String(a.note) : "",
          variant: a.variant ? String(a.variant) : "",
          // Backends that don't say are assumed to send exact matches.
          match: ["exact", "different_variant", "similar_item"].includes(a.match) ? a.match : "exact",
          matchNote: a.matchNote ? String(a.matchNote) : "",
          price,
          priceText: money(price, currency),
          savings,
          savingsText: savings > 0 ? `Save ${money(savings, currency)}` : "",
          savingsShort: savings > 0 ? money(savings, currency, savings >= 100 ? 0 : 2) : "",
        };
      })
      .filter((a) => a.savings == null || a.savings > 0) // only show it if it's actually cheaper
      .sort((a, b) => (a.match !== "exact") - (b.match !== "exact") || a.price - b.price) // exact matches first
      .slice(0, 3);
  }

  // "Likely cheaper soon": only shown when there's a drop worth waiting for (likely/possible, and below the total).
  function normalizeOutlook(o, payload) {
    if (!o || !["likely", "possible"].includes(o.likelihood) || !o.reason) return null;
    const currency = payload?.currency || "GBP";
    const expected = Number(o.expectedPrice) > 0 ? Number(o.expectedPrice) : null;
    if (expected != null && payload?.total != null && expected >= payload.total) return null;
    const date = /^\d{4}-\d{2}-\d{2}$/.test(o.byDate || "") ? new Date(`${o.byDate}T12:00:00`) : null;
    return {
      likelihood: o.likelihood,
      expectedPrice: expected,
      expectedText: expected != null ? money(expected, currency) : "",
      byDate: date ? o.byDate : "",
      byText: date ? date.toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "",
      reason: String(o.reason),
      signals: (Array.isArray(o.signals) ? o.signals : []).slice(0, 3).map(String),
    };
  }

  // Be forgiving about what the backend sends so a bad response never breaks the page.
  function normalize(r, payload) {
    const str = (v) => (v == null ? "" : String(v));
    const actions = (Array.isArray(r?.actions) ? r.actions : [])
      .filter((a) => a && a.id && a.label)
      .slice(0, 4)
      .map((a) => ({
        id: str(a.id),
        label: str(a.label),
        variant: VARIANTS.includes(a.variant) ? a.variant : "secondary",
        confirmation: a.confirmation ? str(a.confirmation) : null,
      }));
    return {
      verdict: VERDICTS.includes(r?.verdict) ? r.verdict : "neutral",
      title: str(r?.title) || "Here's what we found",
      message: str(r?.message),
      insights: (Array.isArray(r?.insights) ? r.insights : [])
        .filter((i) => i && i.label != null && i.value != null)
        .slice(0, 4)
        .map((i) => ({ label: str(i.label), value: str(i.value) })),
      actions: actions.length ? actions : [{ id: "proceed", label: "Continue", variant: "primary" }],
      alternatives: normalizeAlternatives(r?.alternatives, payload),
      priceOutlook: normalizeOutlook(r?.priceOutlook, payload),
      fromEarlierCheck: !!r?.fromEarlierCheck,
      budgetInfo: r?.budgetInfo && Number.isFinite(Number(r.budgetInfo.left)) ? { ...r.budgetInfo, left: Number(r.budgetInfo.left) } : null,
      sessionId: r?.sessionId ?? null,
    };
  }

  async function handleAction(action) {
    if (action.id === "retry") return run({ force: true });
    if (action.id === "alternative") return switchStore(action);

    reportAction(action);
    if (action.confirmation) overlay.showConfirmation(action.confirmation);
    else overlay.dismiss(true);
  }

  // Tell the backend what the user chose; don't block the UI on it.
  function reportAction(action) {
    ST.api
      .action({
        actionId: action.id,
        sessionId: lastResult?.sessionId,
        verdict: lastResult?.verdict,
        alternative: action.alternative ? { merchant: action.alternative.merchant, url: action.alternative.url, price: action.alternative.price } : undefined,
        outlook: action.id === "watch" ? lastResult?.priceOutlook : undefined,
        purchase: lastPayload,
      })
      .catch(() => {});
  }

  // "Go to checkout at X": show a preparing state while the background finds the fastest route to X's checkout
  // (basket link where the store supports one), then open it. X's page fills in the details (handoff.js).
  async function switchStore(action) {
    const alt = action.alternative;
    // Not the exact item (other colour/size, or a similar product): say so and let the shopper decide first.
    if (alt.match !== "exact" && !action.confirmed) {
      return overlay.showMismatch(alt, {
        onContinue: () => switchStore({ ...action, confirmed: true }),
        onBack: () => overlay.showResult(lastResult, handleAction),
      });
    }
    reportAction(action);
    ST.log("switch: clicked alternative", { merchant: alt.merchant, url: alt.url, match: alt.match, price: alt.price });
    overlay.showAnalysing(
      [`Checking how ${alt.merchant}'s checkout works`, "Adding your items to the basket", "Opening checkout"],
      `Preparing your checkout at ${alt.merchant}`
    );
    const started = Date.now();
    let route = null;
    try {
      // Re-read the page now: the shopper may have changed payment method or options since the analysis.
      const now = ST.detect.scrape();
      const item = now.items[0] || lastPayload?.items?.[0] || {};
      const wanted = {
        name: item.name || lastPayload?.pageTitle || "",
        // Exact match: the shopper's own variant. Otherwise the variant they just agreed to.
        variant: alt.match === "exact" ? item.variant || "" : alt.variant || "",
        qty: item.qty || 1,
        // What they picked on this checkout; else their saved preference from the account page.
        paymentMethod: now.paymentMethod || lastPayload?.paymentMethod || (await ST.handoff.savedPaymentMethod()),
      };
      const details = await ST.handoff.collectDetails();
      ST.log("switch: wanted item", { ...wanted, detailFields: Object.keys(details) });
      route = await ST.api.prepareCheckout({ alt, details, wanted });
      ST.log("switch: route", route);
    } catch (e) {
      ST.log.error("switch: preparing failed, opening the link as-is", e.message);
    }
    await sleep(2200 - (Date.now() - started));
    await overlay.finishSteps();

    if (!route) {
      window.open(alt.url, "_blank", "noopener");
      return overlay.showConfirmation(`Opened ${alt.merchant}. Add the item to your basket there.`, 2600);
    }
    if (route.sameTab) return location.assign(route.url);
    overlay.showConfirmation(
      route.method === "product-page"
        ? `Opened ${alt.merchant}. We'll add it to your basket and fill in your details.`
        : `Opened ${alt.merchant} with your basket ready. We'll fill in your details.`,
      2600
    );
  }

  // No budget saved: don't pretend to check one. (Demo page, no extension storage: show them all, the mock has a budget.)
  async function analysisSteps() {
    const steps = ST.config.ANALYSIS_STEPS;
    if (typeof chrome === "undefined" || !chrome.storage?.local) return steps;
    try {
      const { budget } = await chrome.storage.local.get("budget");
      return budget > 0 ? steps : steps.filter((s) => !/budget/i.test(s));
    } catch {
      return steps;
    }
  }

  async function run({ force = false } = {}) {
    if (running) return;
    if (!force && isQuiet()) return;
    running = true;
    handledHref = location.href;

    overlay.showAnalysing(await analysisSteps());
    const started = Date.now();
    lastPayload = ST.detect.scrape();
    ST.log("analyse: start", {
      url: location.href,
      total: lastPayload.total,
      currency: lastPayload.currency,
      items: lastPayload.items,
      paymentMethod: lastPayload.paymentMethod,
    });

    // Started now, alongside the price comparison, so its web search doesn't hold the result up.
    const outlookCall = ST.api
      .outlook(lastPayload)
      .then((o) => {
        ST.log("outlook: result", { seconds: ((Date.now() - started) / 1000).toFixed(1), likelihood: o?.likelihood ?? null });
        return o;
      })
      .catch((e) => {
        ST.log.error("outlook: failed", e.message);
        return null;
      });

    let result = null;
    let error = null;
    try {
      result = normalize(await ST.api.analyze(lastPayload), lastPayload);
      ST.log("analyse: result", {
        seconds: ((Date.now() - started) / 1000).toFixed(1),
        verdict: result.verdict,
        alternatives: result.alternatives.map((a) => `${a.merchant} ${a.priceText} (${a.match}) ${a.url}`),
      });
    } catch (e) {
      error = e;
      ST.log.error("analyse: failed", e.message);
    }
    // Answer already known from the basket: a short glow, not the full "analysing" wait.
    await sleep((result?.fromEarlierCheck ? 1200 : ST.config.MIN_ANALYSING_MS) - (Date.now() - started));

    lastResult = result;
    if (error) await overlay.showError(`Something went wrong: ${error.message}`, handleAction);
    else {
      // A backend may already have sent the outlook with the result; otherwise it fills in when its call finishes.
      result.outlookPending = !result.priceOutlook;
      // Nothing to act on (fits the budget or no budget set, nothing cheaper): a small note that fades, not a panel.
      const quietly = (result.verdict === "good" || result.verdict === "neutral") && !result.alternatives.length && !result.priceOutlook;
      if (quietly) {
        ST.log("checkout: all fine, showing a quiet note", { verdict: result.verdict });
        overlay.showQuiet({
          title: result.verdict === "good" ? "Fits your budget" : "No cheaper price found",
          sub: result.verdict === "good" ? result.message : "We didn't find it cheaper at other stores.",
          tone: result.verdict === "good" ? "good" : "neutral",
        });
      } else {
        await overlay.showResult(result, handleAction);
      }
      if (result.outlookPending) {
        outlookCall.then((o) => {
          if (lastResult !== result) return; // re-analysed since
          result.priceOutlook = normalizeOutlook(o, lastPayload);
          result.outlookPending = false;
          // A drop worth waiting for turns the quiet note into the full panel; otherwise just update it.
          if (quietly && result.priceOutlook && !isQuiet()) overlay.showResult(result, handleAction);
          else if (!quietly) overlay.setOutlook(result.priceOutlook);
        });
      }
    }
    running = false;
  }

  // ---------- Earlier stages (stages.js) ----------

  // Product page: nothing visible. Adding to basket starts a silent price check that the checkout reuses.
  ST.stages.onAddToBasket(() => {
    if (ST.detect.isCheckout()) return;
    const payload = ST.stages.productPayload();
    const item = payload.items[0];
    if (!item.name || payload.total == null) {
      ST.log("add to basket: couldn't read the product, skipped the early check", { name: item.name, price: payload.total });
      return;
    }
    ST.log("add to basket: checking prices quietly", { item: item.name, price: payload.total });
    ST.api.precheck(payload).catch((e) => ST.log.error("precheck failed", e.message));
  });

  // Basket page: the moment to mention a cheaper price, before any forms. A small pill, no glow.
  async function basketStage() {
    handledHref = location.href;
    if (isQuiet()) return;
    const payload = { ...ST.detect.scrape(), stage: "basket" };
    if (!payload.items.length || payload.total == null) return;
    ST.log("basket: checking prices quietly", { items: payload.items.map((i) => i.name), total: payload.total });
    let result;
    try {
      result = normalize(await ST.api.precheck(payload), payload);
    } catch (e) {
      ST.log.error("basket: price check failed", e.message);
      return;
    }
    if (handledHref !== location.href || isQuiet()) return;
    lastPayload = payload;
    lastResult = result;
    const best = result.alternatives[0];
    if (!best) return ST.log("basket: nothing cheaper, staying quiet");
    ST.log("basket: showing the cheaper-elsewhere pill", { merchant: best.merchant, price: best.price });
    overlay.showNudge({
      title: `${best.savingsShort ? `${best.savingsShort} cheaper` : "Cheaper"} at ${best.merchant}`,
      sub: best.match === "exact" ? `Same item, ${best.priceText}` : best.matchNote || "A different version",
      cta: "See",
      onOpen: () => overlay.showResult(result, handleAction),
    });
  }

  // "Place order" while over budget: pause once with the numbers. Never blocks: "Buy anyway" lets the next click
  // through. Shown even if the panel was dismissed earlier, because this is the moment that matters.
  let pausedOnce = false;
  function placeOrderGuard(e) {
    if (pausedOnce || !lastResult?.budgetInfo || lastPayload?.total == null || !ST.detect.isCheckout()) return;
    const el = e.type === "submit" ? e.submitter || e.target.querySelector?.('[type="submit"]') : ST.stages.clickable(e.target);
    if (!ST.stages.isPlaceOrder(el)) return;
    const { left } = lastResult.budgetInfo;
    const total = lastPayload.total;
    if (total <= left) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    pausedOnce = true;
    const cur = lastPayload.currency;
    const alt = lastResult.alternatives?.[0];
    ST.log("place order: paused once, over budget", { total, left, button: ST.stages.labelOf(el) });
    overlay.showOverBudget({
      overBy: money(total - left, cur),
      left: money(Math.max(left, 0), cur),
      total: money(total, cur),
      alt,
      onStop: () => {
        reportAction({ id: "not_now" });
        overlay.showConfirmation("Good call. Your basket is still here if you change your mind.", 2600);
      },
      onBuyAnyway: () => {
        reportAction({ id: "buy_anyway" });
        overlay.showConfirmation("OK. Click Place order again to finish.", 2600);
      },
      onSwitch: () => switchStore({ id: "alternative", alternative: alt }),
    });
  }
  window.addEventListener("click", placeOrderGuard, true);
  window.addEventListener("submit", placeOrderGuard, true);

  // Checkout pages are often SPAs or render late, so keep checking.
  // A hand-off to a cheaper store (see handoff.js) takes priority over analysing the page.
  let checking = false;
  async function check() {
    if (checking || running || handledHref === location.href) return;
    checking = true;
    try {
      if (await ST.handoff.resume(overlay)) handledHref = location.href;
      else if (ST.detect.isCheckout()) run();
      else if (ST.stages.isBasketPage()) basketStage();
    } catch (e) {
      // never let a hand-off problem break the page
      ST.log.error("page check failed", `${e.message}\n${e.stack || ""}`.slice(0, 600));
    } finally {
      checking = false;
    }
  }
  check();
  setInterval(check, 1000);

  // Toolbar icon click → force a run on this page.
  if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg?.type === "ST_RUN") {
        ST.log("toolbar: forced analysis", location.href);
        run({ force: true });
      }
    });
  }

  ST.run = run;
})();
