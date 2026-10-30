'use strict';

// Reusable real-browser recorder. Never starts a recording merely by requiring it.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const VIEWPORT = { width: 1920, height: 1080 };
const PACKAGE = process.env.PLAYWRIGHT_PACKAGE || 'D:/Tools/ClaudeToolchain/browser/node_modules/playwright';
const TOOLCHAIN = path.resolve(PACKAGE, '../../..');

function tools() {
  let config = {};
  try { config = JSON.parse(fs.readFileSync(path.join(TOOLCHAIN, 'config/tools.json'), 'utf8')); } catch {}
  return {
    ffprobe: process.env.FFPROBE_PATH || config.ffprobe || 'ffprobe',
    python: process.env.PYTHON_PATH || config.python || 'python',
  };
}

function clippedBox(box) {
  if (!box) return null;
  const x = Math.max(0, Math.min(VIEWPORT.width, box.x));
  const y = Math.max(0, Math.min(VIEWPORT.height, box.y));
  const right = Math.max(x, Math.min(VIEWPORT.width, box.x + box.width));
  const bottom = Math.max(y, Math.min(VIEWPORT.height, box.y + box.height));
  return { x, y, width: right - x, height: bottom - y };
}

function traceFrames(tracePath) {
  const code = [
    'import json,sys,zipfile',
    'frames=[]',
    'with zipfile.ZipFile(sys.argv[1]) as z:',
    ' for name in z.namelist():',
    '  if not name.endswith(".trace"): continue',
    '  for line in z.read(name).decode("utf-8").splitlines():',
    '   try: row=json.loads(line)',
    '   except ValueError: continue',
    '   if row.get("type")=="screencast-frame" and isinstance(row.get("frameSwapWallTime"),(int,float)):',
    '    frames.append({k:row.get(k) for k in ("pageId","timestamp","frameSwapWallTime","width","height")})',
    'frames.sort(key=lambda x:x["frameSwapWallTime"])',
    'print(json.dumps({"frame_count":len(frames),"first":frames[0] if frames else None,"last":frames[-1] if frames else None}))',
  ].join('\n');
  return JSON.parse(execFileSync(tools().python, ['-c', code, tracePath], { encoding: 'utf8', windowsHide: true, maxBuffer: 1024 * 1024 }));
}

function probeVideo(videoPath) {
  return JSON.parse(execFileSync(tools().ffprobe, ['-v', 'error', '-select_streams', 'v:0', '-read_intervals', '%+#1',
    '-show_entries', 'format=duration,start_time:format_tags=creation_time:stream=width,height,r_frame_rate,avg_frame_rate,start_time:packet=pts_time,dts_time',
    '-of', 'json', videoPath], { encoding: 'utf8', windowsHide: true, maxBuffer: 1024 * 1024 }));
}

async function startCapture({ outputDir, privateDir, initScript, storageState, headless = true } = {}) {
  if (!outputDir || !privateDir) throw new Error('outputDir and privateDir are required');
  outputDir = path.resolve(outputDir);
  privateDir = path.resolve(privateDir);
  const relativePrivate = path.relative(outputDir, privateDir);
  if (!relativePrivate || (!relativePrivate.startsWith('..' + path.sep) && !path.isAbsolute(relativePrivate))) {
    throw new Error('privateDir must be outside the shared outputDir');
  }
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(privateDir, { recursive: true });
  for (const name of ['video.webm', 'actions.json']) {
    if (fs.existsSync(path.join(outputDir, name))) throw new Error('Existing capture would be overwritten: ' + name);
  }
  const sessionId = new Date().toISOString().replace(/[:.]/g, '-') + '-' + process.pid;
  const sessionPrivate = path.join(privateDir, sessionId);
  const videoTemporary = path.join(sessionPrivate, 'video');
  fs.mkdirSync(videoTemporary, { recursive: true });
  if (!process.env.PLAYWRIGHT_BROWSERS_PATH && fs.existsSync(path.join(TOOLCHAIN, 'browsers'))) {
    process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(TOOLCHAIN, 'browsers');
  }
  const { chromium } = require(PACKAGE);
  const browser = await chromium.launch({ headless, channel: process.env.CAPTURE_BROWSER_CHANNEL || 'chrome' });
  let context;
  try {
    context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2,
      recordVideo: { dir: videoTemporary, size: VIEWPORT }, ...(storageState ? { storageState } : {}) });
    // This must precede newPage so the first video frame can also appear in the trace.
    await context.tracing.start({ screenshots: true, snapshots: false, sources: false });
    let page;
    let pendingClick = null;
    const browserClicks = [];
    await context.exposeBinding('__codexCaptureClick', async (source, event) => {
      if (source.page !== page) return;
      let offset = { x: 0, y: 0 };
      if (source.frame !== page.mainFrame()) {
        try { offset = await (await source.frame.frameElement()).boundingBox() || offset; } catch {}
      }
      const click = { ...event, receivedAtMs: Date.now(),
        point: { x: Math.max(0, Math.min(1920, event.clientX + offset.x)), y: Math.max(0, Math.min(1080, event.clientY + offset.y)) },
        targetBox: clippedBox({ ...event.rect, x: event.rect.x + offset.x, y: event.rect.y + offset.y }) };
      browserClicks.push(click);
      if (pendingClick) { pendingClick.event = click; pendingClick.resolve(click); }
    });
    await context.addInitScript(() => {
      document.addEventListener('click', event => {
        const target = event.target instanceof Element ? event.target : document.documentElement;
        const rect = target.getBoundingClientRect();
        const eventEpochMs = event.timeStamp > 1e12 ? event.timeStamp : performance.timeOrigin + event.timeStamp;
        window.__codexCaptureClick({ eventEpochMs, browserDateNowMs: Date.now(), isTrusted: event.isTrusted,
          clientX: event.clientX, clientY: event.clientY,
          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } }).catch(() => {});
      }, true);
    });
    if (initScript) await context.addInitScript(initScript);
    const pageCreateBeforeMs = Date.now();
    page = await context.newPage();
    const pageCreatedMs = Date.now();
    const clockBeforeMs = Date.now();
    const browserClock = await page.evaluate(() => ({ dateNowMs: Date.now(), performanceEpochMs: performance.timeOrigin + performance.now() }));
    const clockAfterMs = Date.now();
    const clockCalibration = { roundTripMs: clockAfterMs - clockBeforeMs,
      browserMinusNodeMidpointMs: browserClock.dateNowMs - (clockBeforeMs + clockAfterMs) / 2,
      performanceMinusBrowserDateMs: browserClock.performanceEpochMs - browserClock.dateNowMs,
      note: 'Same-host wall-clock comparison; transport round trip bounds this one sample, not all later clock drift.' };
    const actions = [];
    const privateActions = [];
    let finished = null;

    function add(kind, label, startedMs, endedMs, details = {}, privateDetails = {}) {
      const action = { id: actions.length + 1, kind, label: String(label || kind), startedMs, endedMs, ...details };
      actions.push(action);
      privateActions.push({ ...action, ...privateDetails });
      return action;
    }

    async function click(locator, label) {
      if (pendingClick) throw new Error('Capture clicks must be sequential');
      const started = Date.now();
      await locator.scrollIntoViewIfNeeded();
      const box = clippedBox(await locator.boundingBox());
      let resolve;
      const observed = new Promise(done => { resolve = done; });
      pendingClick = { resolve, event: null };
      try {
        await locator.click();
        const afterClick = Date.now();
        const event = pendingClick.event || await Promise.race([observed, new Promise(done => setTimeout(() => done(null), 500))]);
        return add('click', label, started, afterClick, { box, point: event?.point || null,
          eventMs: event?.eventEpochMs ?? (started + afterClick) / 2,
          eventTimeSource: event ? 'browser performance.timeOrigin + click.timeStamp' : 'host action interval midpoint fallback',
          browserClickObserved: Boolean(event), browserEventTrusted: event?.isTrusted ?? null,
          fallbackIntervalMs: event ? null : [started, afterClick] }, { selector: locator.toString(), browserClick: event });
      } finally { pendingClick = null; }
    }

    async function navigate(url, label) {
      const started = Date.now();
      const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
      add('navigate', label, started, Date.now(), { eventMs: started, box: {x:0,y:0,...VIEWPORT}, eventTimeSource: 'host Date.now before page.goto' }, { url });
      return response;
    }

    async function scroll(locator, label) {
      const started = Date.now();
      await locator.scrollIntoViewIfNeeded();
      const ended = Date.now();
      return add('scroll', label, started, ended, { eventMs: started, box: clippedBox(await locator.boundingBox()),
        eventTimeSource: 'host Date.now before scrollIntoViewIfNeeded' }, { selector: locator.toString() });
    }

    async function holdScreenshot(name, seconds = 3) {
      if (!Number.isFinite(seconds) || seconds < 0 || seconds > 60) throw new Error('Hold seconds must be between 0 and 60');
      if (!name || path.basename(name) !== name || /[\\/]/.test(name)) throw new Error('Screenshot name must be a filename');
      const filename = name.endsWith('.png') ? name : name + '.png';
      const destination = path.join(outputDir, filename);
      if (fs.existsSync(destination)) throw new Error('Screenshot already exists: ' + filename);
      const started = Date.now();
      await page.waitForTimeout(seconds * 1000);
      const screenshotAt = Date.now();
      await page.screenshot({ path: destination, fullPage: false, scale: 'device' });
      return add('holdScreenshot', filename, started, Date.now(), { eventMs: screenshotAt,
        screenshot: filename, requestedHoldSeconds: seconds, eventTimeSource: 'host Date.now immediately before screenshot' });
    }

    async function hover(locator, label) {
      const started = Date.now();
      await locator.hover();
      return add('hover', label, started, Date.now(), {eventMs: started, box: clippedBox(await locator.boundingBox()), eventTimeSource:'host Date.now before locator.hover'}, {selector:locator.toString()});
    }

    async function wheel(locator, deltaY, label) {
      await locator.hover();
      const box=clippedBox(await locator.boundingBox());
      const started=Date.now();
      await page.mouse.wheel(0,deltaY);
      await page.waitForTimeout(350);
      return add('scroll',label,started,Date.now(),{eventMs:started,box,deltaY,eventTimeSource:'host Date.now before genuine mouse.wheel'}, {selector:locator.toString()});
    }

    function finish(extra = {}) {
      if (finished) return finished;
      finished = (async () => {
        const captureEndMs = Date.now();
        const tracePath = path.join(sessionPrivate, 'trace.zip');
        const video = page.video();
        const failures = [];
        try { await context.tracing.stop({ path: tracePath }); } catch (error) { failures.push({ stage: 'trace_stop', name: error.name }); }
        await context.close();
        const closedAtMs = Date.now();
        if (!video) throw new Error('No Playwright video artifact exists');
        const videoPath = path.join(outputDir, 'video.webm');
        await video.saveAs(videoPath);
        await browser.close();
        let probe = {}, trace = {};
        try { probe = probeVideo(videoPath); } catch (error) { failures.push({ stage: 'ffprobe', name: error.name }); }
        try { trace = traceFrames(tracePath); } catch (error) { failures.push({ stage: 'trace_frames', name: error.name }); }
        const tags = probe.format?.tags || {};
        const creationText = Object.entries(tags).find(([key]) => key.toLowerCase() === 'creation_time')?.[1];
        const creationMs = creationText ? Date.parse(creationText) : NaN;
        const firstFrameMs = trace.first?.frameSwapWallTime;
        const packetPts = Number(probe.packets?.[0]?.pts_time);
        const hasTrace = Number.isFinite(firstFrameMs);
        const videoT0Ms = hasTrace ? firstFrameMs - (Number.isFinite(packetPts) ? packetPts * 1000 : 0)
          : Number.isFinite(creationMs) ? creationMs : pageCreateBeforeMs;
        const timing = {
          videoT0Utc: new Date(videoT0Ms).toISOString(), videoT0EpochMs: videoT0Ms,
          method: hasTrace ? 'first trace screencast frameSwapWallTime minus encoded first packet PTS'
            : 'bounded approximation using recorder creation_time or host newPage start',
          creationTimeUtc: Number.isFinite(creationMs) ? new Date(creationMs).toISOString() : null,
          firstTraceFrameWallTimeMs: firstFrameMs ?? null, firstPacketPtsSeconds: Number.isFinite(packetPts) ? packetPts : null,
          creationToFirstTraceFrameMs: hasTrace && Number.isFinite(creationMs) ? firstFrameMs - creationMs : null,
          traceFrameCount: trace.frame_count ?? 0, clockCalibration,
          approximationIntervalEpochMs: hasTrace ? null : [Number.isFinite(creationMs) ? creationMs : pageCreateBeforeMs, closedAtMs],
          nominalFrameQuantumMs: 40,
          limitation: hasTrace
            ? 'Estimated visual alignment: 25 fps quantization (~40 ms), first traced/encoded frame correspondence and browser/host clock sampling. No sub-frame accuracy is claimed.'
            : 'No trace frame anchor: creation_time marks recorder construction, not first displayed frame; the recorded interval is a broad bound, not exact synchronization.',
          sourceBasis: 'Playwright 1.64.1 coreBundle.js: VideoRecorder passes frameSwapWallTime; FfmpegVideoRecorder emits timestamp minus creationTimeMs and writes creation_time metadata.',
        };
        const publicActions = actions.map(action => ({ id: action.id, kind: action.kind, label: action.label,
          atSeconds: ((action.eventMs ?? action.startedMs) - videoT0Ms) / 1000,
          startSeconds: (action.startedMs - videoT0Ms) / 1000, endSeconds: (action.endedMs - videoT0Ms) / 1000,
          eventTimeSource: action.eventTimeSource, box: action.box || null, point: action.point || null,
          ...(action.kind === 'click' ? { browserClickObserved: action.browserClickObserved, browserEventTrusted: action.browserEventTrusted } : {}),
          ...(action.screenshot ? { screenshot: action.screenshot, requestedHoldSeconds: action.requestedHoldSeconds } : {}),
        }));
        const result = { schema: 'capture-session/1', video: 'video.webm', viewport: VIEWPORT, deviceScaleFactor: 2,
          videoSize: VIEWPORT, screenshotScale: 'device', coordinates: '1920x1080 CSS pixels; boxes clipped to viewport',
          videoProbe: { width: probe.streams?.[0]?.width ?? null, height: probe.streams?.[0]?.height ?? null,
            durationSeconds: Number(probe.format?.duration) || null, frameRate: probe.streams?.[0]?.avg_frame_rate || null },
          timing, actions: publicActions, captureErrors: failures, extra };
        fs.writeFileSync(path.join(sessionPrivate, 'actions-private.json'), JSON.stringify({ pageCreateBeforeMs, pageCreatedMs,
          captureEndMs, closedAtMs, privateActions, browserClicks, probe, trace }, null, 2));
        fs.writeFileSync(path.join(outputDir, 'actions.json'), JSON.stringify(result, null, 2));
        return result;
      })();
      return finished;
    }
    return { page, context, browser, click, navigate, scroll, hover, wheel, holdScreenshot, finish };
  } catch (error) {
    if (context) await context.close().catch(() => {});
    await browser.close().catch(() => {});
    throw error;
  }
}

module.exports = { startCapture };
