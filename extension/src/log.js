// Activity log: what the extension did and why, for debugging. Kept in chrome.storage (last 300 entries) and shown on
// the settings page. The background worker is the only writer; pages send their entries to it.
// Never logs API keys, form values or card data: only events and short summaries.
globalThis.ST = globalThis.ST || {};

(() => {
  const KEY = "second-thought-log";
  const MAX = 300;
  const isWorker = typeof window === "undefined";
  const inExtension = () => typeof chrome !== "undefined" && !!chrome.runtime?.id;

  const clip = (v) => {
    if (v === undefined) return undefined;
    let s;
    try { s = typeof v === "string" ? v : JSON.stringify(v); } catch { s = String(v); }
    return s && s.length > 1200 ? `${s.slice(0, 1200)}…` : s;
  };

  let queue = Promise.resolve();
  function append(entry) {
    queue = queue
      .then(async () => {
        const { [KEY]: log = [] } = await chrome.storage.local.get(KEY);
        log.push(entry);
        await chrome.storage.local.set({ [KEY]: log.slice(-MAX) });
      })
      .catch(() => {});
    return queue;
  }

  function log(event, data, level = "info") {
    const entry = { t: Date.now(), where: isWorker ? "background" : location.hostname, level, event, data: clip(data) };
    (level === "error" ? console.warn : console.log)("[Second Thought]", event, data ?? "");
    if (!inExtension()) return;
    if (isWorker) return void append(entry);
    try {
      chrome.runtime.sendMessage({ type: "ST_LOG", payload: entry }).catch(() => {});
    } catch {
      // extension was reloaded; this page's script is orphaned
    }
  }

  ST.log = log;
  ST.log.error = (event, data) => log(event, data, "error");
  ST.log.append = append;
  ST.log.KEY = KEY;
})();
