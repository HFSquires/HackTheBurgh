// Run: node extension/checks.cjs. Tests the actual adapter and decision-step selection without browser/network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const load = (file, context) => vm.runInContext(fs.readFileSync(path.join(__dirname, 'src', file), 'utf8'), context);
(async () => {
  const calls = [];
  const d = { verdict: 'reconsider', risk: 'overdraft', title: 'Overdraft warning', message: 'Projected below zero.',
    today: '2026-11-02', month: '2026-11', price: 100, paymentPlan: 'pay_now',
    netWorth: { now: 1200, goal: 1350, forecastEndWithout: 1450 },
    cashFlow: { lowestWithPurchase: -50, horizon: '2026-11-30' },
    savings: { monthlyTarget: 150, forecastSaved: 20, suggestedDailyBudget: 15 } };
  const context = vm.createContext({ Intl, AbortSignal, URL, Date, window: { matchMedia: () => ({ matches: false }) },
    fetch: async (url, options) => { calls.push(JSON.parse(options.body)); return { ok: true, json: async () => d }; } });
  load('config.js', context);
  context.ST.log = Object.assign(() => {}, { error() {} });
  load('precheck.js', context); load('overlay.js', context);
  const payload = { total: 100, currency: 'GBP' };
  const settings = { bankPersona: 'persona001', monthlySavings: 150 };
  let result = await context.ST.precheck.modelVerdict(payload, settings);
  assert.equal(calls[0].monthlySavings, 150); assert.equal(calls[0].bank.persona, 'persona001');
  assert.equal(result.risk, 'overdraft'); assert.equal(result.financeAction.id, 'pay_in_3');
  assert.equal(result.budgetInfo, null); assert.equal(result.chart.start, 1200);
  const prices = { alternatives: [{ merchant: 'A', price: 90 }], verdict: 'good' };
  result = await context.ST.precheck.withBudget(prices, { ...payload, total: 200 }, { ...settings, monthlySavings: 300 });
  assert.equal(calls.at(-1).price, 200); assert.equal(calls.at(-1).monthlySavings, 300);
  assert.equal(result.alternatives, prices.alternatives); assert.equal(result.risk, 'overdraft');
  d.paymentPlan = 'pay_in_3'; d.comparison = { payNow: { lowestWithPurchase: -150 }, payIn3: d.cashFlow };
  d.payments = [{ amount: 33.33, date: '2026-11-02' }];
  result = await context.ST.precheck.modelVerdict({ ...payload, paymentPlan: 'pay_in_3' }, settings);
  assert.equal(calls.at(-1).paymentPlan, 'pay_in_3'); assert.equal(result.financeAction.id, 'pay_now');
  assert.match(result.comparison.schedule, /33.33/); assert.match(result.comparison.payNow, /150/);
  for (const [risk, verdict] of [['overdraft', 'reconsider'], ['savings', 'caution'], ['none', 'good'], ['unknown', 'neutral']]) {
    const steps = context.ST.Overlay.prototype.decisions({ risk, verdict, alternatives: prices.alternatives, priceOutlook: {} });
    assert.deepEqual(Array.from(steps), ['budget', 'wait', 'switch']); // Retains the newer one-decision-at-a-time UI.
  }
  assert.equal(await context.ST.precheck.modelVerdict(payload, { bankPersona: '' }), null);
  assert.equal((await context.ST.precheck.modelVerdict({ ...payload, currency: 'USD' }, settings)).risk, 'unknown');
  context.fetch = async () => { throw new Error('offline'); };
  result = await context.ST.precheck.withBudget(prices, payload, settings);
  assert.equal(result.risk, 'unknown'); assert.equal(result.verdict, 'neutral'); assert.equal(result.chart, null);
  context.fetch = async () => ({ ok: true, json: async () => ({ title: 'No salary', verdict: 'neutral' }) });
  assert.equal((await context.ST.precheck.modelVerdict(payload, settings)).risk, 'unknown');
  const { cleanAccount, emptyAccount } = await import('../web/lib/validate.js');
  assert.equal(emptyAccount().budget.monthlySavings, 0);
  assert.equal(cleanAccount({ budget: { monthlySavings: 150 } }).account.budget.monthlySavings, 150);
  for (const goal of [-1, Infinity, NaN, true, '150', 1000001]) assert.ok(cleanAccount({ budget: { monthlySavings: goal } }).error);
  console.log('Frontend model adapter, decision steps, pay-in-3, failure and account checks passed.');
})().catch(e => { console.error(e); process.exitCode = 1; });
