// Content-script side of the backend. Calls go through the background worker (which can make
// cross-origin requests). Outside the extension (the demo page) it falls back to the mock.
globalThis.ST = globalThis.ST || {};

(() => {
  const inExtension = () => typeof chrome !== "undefined" && !!chrome.runtime?.id;

  async function call(type, payload) {
    if (!inExtension()) {
      return type === "ST_ANALYZE" ? ST.mock.analyze(payload) : ST.mock.action(payload);
    }
    const res = await chrome.runtime.sendMessage({ type, payload });
    if (!res?.ok) throw new Error(res?.error || "No response from background");
    return res.data;
  }

  // Demo page (no extension): the same staged behaviour, with the mock and the demo shopper's budget and bank
  // picture (persona.js). MOCK_BUDGET in config.js overrides the budget part.
  const demoSettings = () => ({ ...(ST.persona ? ST.persona.settings() : {}), ...(ST.config.MOCK_BUDGET || {}) });
  // Price comparison and "could get cheaper" together, as the background does.
  async function demoBoth(payload) {
    ST.mock.outlook(payload).then((o) => ST.precheck.addOutlook(payload, o));
    return ST.mock.analyze(payload).catch((e) => {
      if (!ST.config.MODEL?.url || !(demoSettings().bankPersona ?? ST.config.MODEL.persona)) throw e;
      return { alternatives: [], insights: [], searchFailed: e.message };
    });
  }
  async function demoAnalyze(payload) {
    if (ST.config.MOCK_VERDICT_OVERRIDE) {
      return { ...await ST.mock.analyze(payload), mockVerdict: true, budgetInfo: null };
    }
    const earlier = !ST.config.MOCK_SCENARIO && (await ST.precheck.find(payload));
    const result = earlier ? ST.precheck.forCheckout(earlier.result, payload, demoSettings()) : await demoBoth(payload);
    if (earlier) ST.log("analyse: reused the price check from earlier", { stage: earlier.stage });
    return ST.precheck.withBudget(result, payload, demoSettings());
  }

  ST.api = {
    analyze: (payload) => (inExtension() ? call("ST_ANALYZE", payload) : demoAnalyze(payload)),
    // The affordability model alone (fast); null when it's off or unreachable.
    afford: (payload) => (inExtension() ? call("ST_AFFORD", payload) : ST.config.MOCK_VERDICT_OVERRIDE ? Promise.resolve(null) : ST.precheck.modelVerdict(payload, demoSettings())),
    // Silent check when something goes in the basket; the checkout reuses it.
    precheck: async (payload) => {
      if (inExtension()) return call("ST_PRECHECK", payload);
      const { result } = await ST.precheck.run(payload, demoBoth);
      return ST.precheck.withBudget(result, payload, demoSettings());
    },
    // "Likely cheaper soon?": a separate, slower call started alongside analyze().
    outlook: (payload) => (inExtension() ? call("ST_OUTLOOK", payload) : ST.config.MOCK_VERDICT_OVERRIDE ? Promise.resolve(null) : ST.mock.outlook(payload)),
    action: (payload) => call("ST_ACTION", payload),
    openLog: () => (inExtension() ? call("ST_OPEN_LOG") : Promise.resolve()),
    // Next step on another store's page (AI fallback). Null when there's no API key or no extension.
    aiStep: (payload) => (inExtension() ? call("ST_AI_STEP", payload) : Promise.resolve(null)),
    // Which saved detail goes in form fields the rules couldn't place (labels only). Null without the extension or a key.
    aiFields: (payload) => (inExtension() ? call("ST_AI_FIELDS", payload) : Promise.resolve(null)),
    // This page's tab, so a hand-off can follow the tab it opened across sites. Null on the demo page.
    tabId: () => (inExtension() ? call("ST_TAB_ID").catch(() => null) : Promise.resolve(null)),
    // Extension: background builds the basket link and opens a new tab. Demo page: same tab, link as-is.
    async prepareCheckout({ alt, details, wanted }) {
      if (inExtension()) return call("ST_PREPARE", { alt, details, wanted });
      await ST.handoff.save(ST.handoff.record(alt.url, alt.merchant, details, false, wanted));
      return { url: alt.url, method: "product-page", sameTab: true };
    },
  };
})();
