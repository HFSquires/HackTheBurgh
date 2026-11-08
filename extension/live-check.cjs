// Real ChatGPT check of the two AI features, with your own key (sent only to OpenAI or ELM, as in the extension):
//   OPENAI_API_KEY=<your key> node extension/live-check.cjs          optional: MODEL=<model name>
// 1. a price search for one product, as at checkout; 2. matching a checkout form's fields to saved details
// (labels only, never values). Prints what came back. Costs a few pence; writes nothing.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const apiKey = process.env.OPENAI_API_KEY;
if (!apiKey) {
  console.log('Set OPENAI_API_KEY to your OpenAI or ELM key, e.g.\n  OPENAI_API_KEY=... node extension/live-check.cjs');
  process.exit(1);
}
const settings = { apiKey, model: process.env.MODEL || '' };
const context = vm.createContext({ fetch, AbortSignal, URL, Date, Intl, setTimeout, clearTimeout, console });
for (const file of ['config.js', 'live.js']) {
  if (file === 'live.js') context.ST.log = Object.assign((...a) => console.log('  log:', ...a), { error: (...a) => console.log('  error:', ...a) });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'src', file), 'utf8'), context);
}
const { ST } = context;

(async () => {
  console.log(`Using ${ST.apiFor(apiKey).name}, model ${settings.model || '(extension default)'}\n`);

  console.log('1. Price search: Grand Theft Auto VI, PS5 at Smyths for £69.99 ...');
  let started = Date.now();
  try {
    const r = await ST.live.analyze({
      merchant: 'Smyths Toys', url: 'https://www.smythstoys.com/uk/en-gb/checkout', total: 69.99, currency: 'GBP',
      items: [{ name: 'Grand Theft Auto VI', variant: 'PS5', qty: 1, price: 69.99 }], pageText: '',
    }, settings);
    console.log(`   ${((Date.now() - started) / 1000).toFixed(1)} s`);
    console.log('   cheaper:', (r.alternatives || []).map((a) => `${a.merchant} £${a.price} ${a.url}`));
    const checked = r.insights?.find((i) => /prices compared/i.test(i.label));
    if (checked) console.log(`   ${checked.label}: ${checked.value}`);
  } catch (e) {
    console.log('   FAILED:', e.message);
  }

  console.log('\n2. Form filling: which saved detail goes in each field (labels only) ...');
  started = Date.now();
  const fields = ['Email address', 'Confirm Email Address', 'Phone number', 'Address finder (enter postcode)', 'Pincode', 'Town / City', 'First name', 'Last name']
    .map((label, field) => ({ field, label, name: '', placeholder: '', type: 'text', autocomplete: '' }));
  try {
    const m = await ST.live.mapFields({ fields, details: ['email', 'phone', 'postcode', 'address1', 'city', 'givenName', 'familyName'] }, settings);
    console.log(`   ${((Date.now() - started) / 1000).toFixed(1)} s`);
    for (const { field, detail } of m) console.log(`   ${fields[field].label} -> ${detail}`);
  } catch (e) {
    console.log('   FAILED:', e.message);
  }
})();
