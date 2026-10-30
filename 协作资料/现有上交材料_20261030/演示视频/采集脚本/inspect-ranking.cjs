async (page) => {
  return await page.evaluate(() => ({
    footers: [...document.querySelectorAll('footer,[role=contentinfo]')].map(e=>({tag:e.tagName,id:e.id,class:e.className})),
    partners: [...document.querySelectorAll('a[href*="edu.cn"]')].slice(0,3).map(e=>({tag:e.tagName,id:e.id,class:e.className,parent:e.parentElement.className,grandparent:e.parentElement.parentElement.className})),
    identities: [...document.querySelectorAll('[title],iframe,summary')].filter(e => e.tagName==='IFRAME' || e.tagName==='SUMMARY').map(e=>({tag:e.tagName,id:e.id,class:e.className,aria:e.getAttribute('aria-label')})),
    region: [...document.querySelectorAll('[aria-label]')].filter(e=>(e.getAttribute('aria-label')||'').includes('排行榜')).map(e=>({tag:e.tagName,id:e.id,class:e.className,label:e.getAttribute('aria-label')})),
    stats: {rows:document.querySelectorAll('#rankingRows tr').length}
  }));
}
