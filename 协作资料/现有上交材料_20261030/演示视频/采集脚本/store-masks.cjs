'use strict';

// CSS privacy masks only: original names, status, counts and ACS remain in the DOM.
function storeMask() {
  const ownNames = new Set(['跨域故障协调智能体','跨域订单应用智能体','跨域数据库协同智能体','跨域数据库备智能体','跨域入口运维智能体','跨域业务验证智能体','跨域接入体检智能体']);
  function update() {
    if (!document.documentElement) return;
    if (!document.getElementById('video-store-privacy')) {
      const style = document.createElement('style');
      style.id = 'video-store-privacy';
      style.textContent = `html{zoom:1.25} ::-webkit-scrollbar{display:none}
        .partner-card>*{visibility:hidden!important}.partner-card{background:#1f2937!important}
        header [title="Contributor"]{visibility:hidden!important}
        .store-agent-card-footer>span,
        #storeAcsFacts dd:nth-of-type(1),#storeAcsFacts dd:nth-of-type(2),#storeAcsFacts dd:nth-of-type(5),
        .store-agent-card:not([data-video-own-card]) .store-agent-name,
        .store-agent-card:not([data-video-own-card]) .store-agent-description{
          color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;
          background:#1f2937!important;pointer-events:none!important;user-select:none!important}
        #storeRawDetails,#storeCopyAcs{visibility:hidden!important;pointer-events:none!important}
        #storeAcsFacts dd:nth-of-type(1) *,#storeAcsFacts dd:nth-of-type(2) *,#storeAcsFacts dd:nth-of-type(5) *{
          color:transparent!important;-webkit-text-fill-color:transparent!important;pointer-events:none!important}`;
      document.documentElement.appendChild(style);
    }
    for (const card of document.querySelectorAll('.store-agent-card')) {
      if (ownNames.has(card.querySelector('.store-agent-name')?.textContent.trim())) card.setAttribute('data-video-own-card','true');
    }
  }
  new MutationObserver(update).observe(document,{childList:true,subtree:true});
  document.addEventListener('DOMContentLoaded',update);
  window.__refreshPrivacyMasks=update;
  update();
}
module.exports={storeMask};
