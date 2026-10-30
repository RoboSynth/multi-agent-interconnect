'use strict';

// These masks cover identifiers only. Page values, order and status are untouched.
function rankingMask() {
  const install = () => {
    if (!document.documentElement || document.getElementById('video-privacy-css')) return;
    const s = document.createElement('style'); s.id = 'video-privacy-css';
    s.textContent = `html{zoom:1.25} ::-webkit-scrollbar{display:none}
      #rankingRows td:first-child{color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;background:#1f2937!important}
      .partner-card>*{visibility:hidden!important}
      .partner-card{background:#1f2937!important}
      header summary[title="Contributor"]{visibility:hidden!important}`;
    document.documentElement.appendChild(s);
  };
  new MutationObserver(install).observe(document, {childList:true,subtree:true}); install();
}

function registryMask() {
  let busy = false;
  const styleId = 'video-privacy-css';
  const install = () => {
    if (!document.documentElement || busy) return;
    busy = true;
    if (!document.getElementById(styleId)) {
      const s = document.createElement('style'); s.id=styleId;
      s.textContent=`html{zoom:1.25} ::-webkit-scrollbar{display:none}
        .horizontal-header-right .el-dropdown{visibility:hidden!important}
        tr:nth-child(2)>td.el-descriptions__content:nth-child(2){color:transparent!important;-webkit-text-fill-color:transparent!important;background:#1f2937!important}
        textarea[placeholder*="ACS"]:not([data-video-masked]){color:transparent!important;-webkit-text-fill-color:transparent!important}
        [data-video-mask-box]{position:fixed;pointer-events:none;background:#1f2937!important;z-index:2147483645}
        [data-video-mirror]{position:fixed;left:0;top:0;visibility:hidden;pointer-events:none;margin:0;z-index:-1}`;
      document.documentElement.appendChild(s);
    }
    busy = false;
  };
  const update = () => {
    install(); if (!document.body) return;
    for (const box of document.querySelectorAll('[data-video-mask-box]')) box.remove();
    for (const area of document.querySelectorAll('textarea[placeholder*="ACS"]')) {
      if (!area.value) continue;
      const cs = getComputedStyle(area), rect = area.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      const scale = rect.width / area.offsetWidth;
      const mirror = document.createElement('div'); mirror.setAttribute('data-video-mirror','');
      for(const p of ['font','letterSpacing','lineHeight','padding','border','boxSizing','whiteSpace','overflowWrap','wordBreak','tabSize']) mirror.style[p]=cs[p];
      mirror.style.width=area.offsetWidth+'px';
      const text=document.createTextNode(area.value); mirror.appendChild(text); document.body.appendChild(mirror);
      const mr=mirror.getBoundingClientRect();
      const re=/^.*(?:"aic"|"provider"|"url"|"name"\s*:\s*"[^"\n]+").*$/gm;
      // Agent names are public product names. Only provider names and identity/endpoint rows are covered.
      const providerNames=[];
      try {const a=JSON.parse(area.value);if(a.provider?.name)providerNames.push(a.provider.name);}catch{}
      for(const match of area.value.matchAll(re)) {
        if(!/"aic"|"url"/.test(match[0]) && !providerNames.some(n=>match[0].includes(n)))continue;
        const range=document.createRange(); range.setStart(text,match.index);range.setEnd(text,match.index+match[0].length);
        for(const rr of range.getClientRects()) {
          const top=Math.max(rect.top+2, rect.top+rr.top-mr.top-area.scrollTop*scale-1);
          const bottom=Math.min(rect.bottom-2,rect.top+rr.bottom-mr.top-area.scrollTop*scale+2);
          if(bottom<=top)continue;
          const box=document.createElement('div');box.setAttribute('data-video-mask-box','');
          Object.assign(box.style,{left:(rect.left+2)/scale+'px',top:top/scale+'px',width:(rect.width-4)/scale+'px',height:(bottom-top)/scale+'px'});
          document.body.appendChild(box);
        }
      }
      mirror.remove(); area.setAttribute('data-video-masked','true');
    }
  };
  let scheduled=false;
  const schedule=()=>{install();if(!scheduled){scheduled=true;requestAnimationFrame(()=>{scheduled=false;update();});}};
  new MutationObserver(ms=>{if(ms.some(m=>[...m.addedNodes].some(n=>n.nodeType===1&&!n.hasAttribute?.('data-video-mask-box')&&!n.hasAttribute?.('data-video-mirror')&&n.id!==styleId)))schedule();}).observe(document,{childList:true,subtree:true});
  document.addEventListener('scroll',update,true);window.addEventListener('resize',update);document.addEventListener('DOMContentLoaded',schedule); install();
  window.__refreshPrivacyMasks=update;
}

module.exports={rankingMask,registryMask};
