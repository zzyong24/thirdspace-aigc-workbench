// Run through `ego-browser nodejs`, never through plain node.
// Globals taskSpace/claimTaskSpace are provided by Ego Lite's runtime.
const fs = await import('node:fs/promises');
const input = typeof AIGC_BROWSER_REQUEST === 'undefined' ? {} : AIGC_BROWSER_REQUEST;
if (!input.stateFile || !input.url) throw new Error('stateFile and url are required');
const address = new URL(input.url);
if (address.protocol !== 'https:' || !['runninghub.cn', 'www.runninghub.cn', 'runninghub.ai', 'www.runninghub.ai', 'rhtv.runninghub.cn', 'rhtv.runninghub.ai'].includes(address.hostname)) {
  throw new Error('Expected an HTTPS RunningHub URL');
}
let binding;
try { binding = JSON.parse(await fs.readFile(input.stateFile, 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
// Persist the browser identity BEFORE navigation. A failed round must resume it.
const space = await taskSpace(binding ? binding.spaceId : `AIGC · ${input.project}`);
if (space.ownership !== 'agent') throw new Error('waiting_browser: original space requires explicit user resume');
if (!binding) {
  binding = { version: 1, spaceId: space.spaceId, page: 'p1', url: input.url };
  await fs.writeFile(input.stateFile, JSON.stringify(binding, null, 2), { mode: 0o600 });
}
if (binding.url !== input.url) throw new Error('Canvas changed; recover the original binding before continuing');
const page = space.page(binding.page);
if ((await page.url()) !== input.url) await page.goto(input.url);
const snapshot = await page.snapshot();
console.log(JSON.stringify({ spaceId: space.spaceId, page: binding.page, url: await page.url(), title: await page.title(), snapshot }));
// Keep the bound space agent-owned for subsequent generation/recovery.
// `finish` is performed once by the generation agent when the work is complete.
