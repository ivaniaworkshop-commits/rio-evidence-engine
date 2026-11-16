const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html=fs.readFileSync(path.join(__dirname,'../rio_pey_codi/static/index.html'),'utf8');
const field=html.match(/<input\s+id="sale-order"[^>]*>/);
assert(field,'shared folio input must exist');
const pattern=field[0].match(/\spattern="([^"]+)"/);
assert(pattern,'shared folio must have a native validation pattern');
// HTML pattern attributes use Unicode sets (v); an empty optional input is exempt in the browser.
const nativePattern=new RegExp(`^(?:${pattern[1]})$`,'v');
for(const valid of ['A','sale-123','X.y_z','a'.repeat(70)]) assert(nativePattern.test(valid),valid);
for(const invalid of ['-bad','a b','a@b','a'.repeat(71),'á']) assert(!nativePattern.test(invalid),invalid);
console.log('SHARED_SALE_NATIVE_PATTERN_OK');
