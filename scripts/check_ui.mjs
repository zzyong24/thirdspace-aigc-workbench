const request = AIGC_UI_REQUEST;
const task = await taskSpace(request.space || 'AIGC workbench UI regression');
if (task.ownership !== 'agent') throw new Error('Original browser space needs explicit user resume');
const page = task.page(request.space ? request.page : 'p1');
await page.goto(request.url);
await page.waitForSelector('h2');
const projects = await page.evaluate(() => JSON.parse(document.querySelector('#board-data').textContent).projects);
if (!projects.length) throw new Error('UI fixture needs at least one project');
const project = projects[0].path;
let checks = 0;
for (const width of [1440, 768, 390]) {
  await page.cdp('Emulation.setDeviceMetricsOverride', {width, height: 900, deviceScaleFactor: 1, mobile: false});
  if (width < 768) {
    await page.waitForSelector('button[aria-label="导航菜单"]');
    await page.click('button[aria-label="导航菜单"]');
    await page.waitForSelector('button[aria-label="关闭导航菜单"]');
    await page.click('button[aria-label="关闭导航菜单"]');
    await page.waitForSelector('button[aria-label="关闭导航菜单"]', {state: 'hidden'});
    checks += 2;
  }
  for (const view of ['progress', 'documents', 'assets', 'materials', 'prompts', 'files']) {
    await page.goto(request.url + '#project=' + encodeURIComponent(project) + '&view=' + view);
    await page.waitForSelector('h2');
    const state = await page.evaluate(() => {
      const fixture = JSON.parse(document.querySelector('#board-data').textContent);
      const missing = [...document.images].filter(i => i.src.includes(location.host) && (!i.complete || i.naturalWidth === 0)).map(i => i.getAttribute('src'));
      return {width: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1, missing, fixtureProjects: fixture.projects.length, text: document.querySelector('main').textContent};
    });
    // Images may finish after React; wait on the observable condition, not a delay.
    await page.waitForFunction(() => [...document.images].filter(i => i.src.includes(location.host)).every(i => i.complete && i.naturalWidth > 0), undefined, {timeout: 10000});
    if (state.overflow || !state.text.trim()) throw new Error(JSON.stringify({view, ...state}));
    console.log(JSON.stringify({width, view, overflow: false, imagesLoaded: true}));
    checks += 2;
  }
}
await page.goto(request.url + '#overview');
await page.fill('input[placeholder="搜索作品名称"]', 'NO_MATCH_AIGC_TEST_9182');
await page.waitForFunction(() => document.querySelector('input[placeholder="搜索作品名称"]').closest('.section-card').querySelectorAll('.work-name').length === 0);
await page.fill('input[placeholder="搜索作品名称"]', '');
checks++;
await page.cdp('Emulation.clearDeviceMetricsOverride');
console.log(JSON.stringify({passed: checks, spaceId: task.spaceId}));
if (!request.space) await task.finish({keep: []});
