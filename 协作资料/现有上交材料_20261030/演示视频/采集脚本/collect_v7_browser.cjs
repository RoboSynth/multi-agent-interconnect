'use strict';

// Records public GitHub pages. Requiring this module never starts a browser.
const fs = require('node:fs');
const path = require('node:path');
const { startCapture } = require('./capture-session.cjs');
const REPO = 'https://github.com/AIP-PUB/ACPs-community';
const ISSUE_QUERY = 'is:issue created:2026-10-18T08:29:20Z..2026-10-18T08:29:40Z';

function anonymousGithub() {
  const css = `
    html { zoom: 1.25 !important; }
    ::-webkit-scrollbar { display: none; }
    [data-hovercard-type="user"],
    [data-hovercard-url^="/users/"],
    [data-testid="author-filter-link"],
    [class*="summaryContainer"] > a:first-child,
    a.author,
    img.avatar-user,
    .head-ref,
    [data-component="BranchName"]:not([href^="/AIP-PUB/ACPs-community/"]),
    [data-component="BranchName"]:not([href^="/AIP-PUB/ACPs-community/"]) + [role="tooltip"] {
      visibility: hidden !important;
      pointer-events: none !important;
    }
  `;
  const install = () => {
    if (!document.documentElement || document.getElementById('v7-identity-mask')) return;
    const style = document.createElement('style');
    style.id = 'v7-identity-mask';
    style.textContent = css;
    (document.head || document.documentElement).appendChild(style);
  };
  new MutationObserver(install).observe(document, { childList: true, subtree: true });
  install();
  document.addEventListener('DOMContentLoaded', install, { once: true });
}

async function checkMasks(page, label) {
  const result = await page.evaluate(() => {
    const identities = new Set();
    for (const el of document.querySelectorAll('[data-hovercard-url^="/users/"]')) {
      const name = el.getAttribute('data-hovercard-url').split('/')[2];
      if (name) identities.add(name);
    }
    for (const el of document.querySelectorAll('.head-ref a,[data-component="BranchName"]')) {
      const url = new URL(el.getAttribute('href') || '/', location.origin);
      const owner = url.pathname.split('/')[1];
      if (owner && owner !== 'AIP-PUB') identities.add(owner);
    }
    const hidden = el => {
      if (!el || !el.getClientRects().length) return true;
      for (let p = el; p; p = p.parentElement) {
        const style = getComputedStyle(p);
        if (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) === 0) return true;
      }
      return false;
    };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let visibleIdentityText = 0;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!Array.from(identities).some(name => node.textContent.includes(name))) continue;
      if (!hidden(node.parentElement)) visibleIdentityText += 1;
    }
    const targets = Array.from(document.querySelectorAll('[data-hovercard-type="user"],[data-testid="author-filter-link"],[class*="summaryContainer"] > a:first-child,a.author,img.avatar-user,.head-ref,[data-component="BranchName"]:not([href^="/AIP-PUB/ACPs-community/"])'));
    return { maskStyleInstalled: Boolean(document.getElementById('v7-identity-mask')),
      maskedIdentityElements: targets.filter(hidden).length,
      visibleIdentityElements: targets.filter(el => !hidden(el)).length,
      visibleIdentityText,
      zoom: getComputedStyle(document.documentElement).zoom,
      devicePixelRatio: window.devicePixelRatio };
  });
  if (!result.maskStyleInstalled || result.visibleIdentityElements || result.visibleIdentityText) {
    const error = new Error('Privacy mask check failed at ' + label);
    error.maskAudit = result;
    throw error;
  }
  return { label, ...result };
}

async function main() {
  const outputDir = path.resolve(process.env.V7_OUTPUT_DIR || path.join(__dirname, '../V7-opensource'));
  const privateDir = path.resolve(process.env.V7_PRIVATE_DIR || path.join(__dirname, '../../../.cache/视频采集_20261029/V7-browser'));
  const capture = await startCapture({ outputDir, privateDir, initScript: anonymousGithub, headless: true });
  const { page } = capture;
  page.setDefaultTimeout(25000);
  const checks = [];
  let errorName = null;
  try {
    for (const pr of [{ number: 13, files: 14, diff: '+1,599 −11' }, { number: 14, files: 3, diff: '+159 −5' }]) {
      await capture.navigate(`${REPO}/pull/${pr.number}`, `PR ${pr.number}: official conversation page`);
      await page.getByRole('heading', { level: 1 }).waitFor();
      await page.locator('#prs-files-anchor-tab').waitFor();
      checks.push(await checkMasks(page, `PR ${pr.number} conversation`));
      await capture.holdScreenshot(`pr-${pr.number}-overview.png`, 4);
      await capture.click(page.locator('#prs-files-anchor-tab'), `PR ${pr.number}: open Files changed`);
      await page.waitForURL(`**/pull/${pr.number}/files`);
      await page.locator('#diffstat').waitFor();
      const diff = (await page.locator('#diffstat').innerText()).replace(/\s+/g, ' ').trim();
      if (diff !== pr.diff) throw new Error('Current PR diff count changed; refresh contributions before recording');
      await page.getByRole('link', { name: `Files changed ${pr.files}`, exact: true }).waitFor();
      checks.push(await checkMasks(page, `PR ${pr.number} files`));
      await capture.holdScreenshot(`pr-${pr.number}-files.png`, 4);
    }
    await capture.navigate(`${REPO}/issues?q=${encodeURIComponent(ISSUE_QUERY)}`, 'Official issue list: four specified contributions');
    await page.getByRole('heading', { name: '4 results', exact: true }).waitFor();
    for (const number of [15, 16, 17, 18]) {
      await page.locator(`a[href="${REPO}/issues/${number}"]`).waitFor();
    }
    checks.push(await checkMasks(page, 'Issues 15 to 18 list'));
    await capture.holdScreenshot('issues-15-18.png', 5);
    await capture.scroll(page.locator(`a[href="${REPO}/issues/15"]`), 'Show issue 15 and closed status of issue 16');
    checks.push(await checkMasks(page, 'Issues 15 to 18 lower view'));
    await capture.holdScreenshot('issues-15-18-detail.png', 3);
  } catch (error) {
    errorName = error.name;
    fs.mkdirSync(privateDir, { recursive: true });
    fs.writeFileSync(path.join(privateDir, 'last-capture-error.txt'), error.stack || String(error));
    if (error.maskAudit) fs.writeFileSync(path.join(privateDir, 'last-mask-audit.json'), JSON.stringify(error.maskAudit, null, 2));
  } finally {
    const result = await capture.finish({ source: 'Live public GitHub pages', repository: 'AIP-PUB/ACPs-community',
      status: errorName ? 'incomplete' : 'completed', errorClass: errorName, privacyChecks: checks,
      identityMasking: 'CSS visibility masks only; no title, state, count, source code or result text changed.',
      issueFilter: ISSUE_QUERY, hiddenScrollbars: true, pageZoom: '125%', rawTraceShared: false });
    fs.writeFileSync(path.join(outputDir, 'browser-capture-summary.json'), JSON.stringify({
      status: result.extra.status, errorClass: errorName, screenshots: result.actions.filter(x => x.screenshot).map(x => x.screenshot),
      video: result.video, videoProbe: result.videoProbe, actionCount: result.actions.length,
      privacyChecks: checks, officialPages: [`${REPO}/pull/13`, `${REPO}/pull/14`, `${REPO}/issues?q=${encodeURIComponent(ISSUE_QUERY)}`]
    }, null, 2) + '\n');
    console.log(JSON.stringify({ status: result.extra.status, screenshots: result.actions.filter(x => x.screenshot).length,
      actionCount: result.actions.length, durationSeconds: result.videoProbe.durationSeconds, errorClass: errorName }));
  }
  if (errorName) process.exitCode = 1;
}

module.exports = { anonymousGithub, checkMasks, main };
if (require.main === module) main().catch(error => { console.error(error.name); process.exitCode = 1; });
