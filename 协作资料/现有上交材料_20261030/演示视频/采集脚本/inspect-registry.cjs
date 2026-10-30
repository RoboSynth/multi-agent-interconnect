async (page) => {
  return await page.evaluate(() => ({
    account: [...document.querySelectorAll('p')].filter(e=>e.getBoundingClientRect().top<100).map(e => ({tag:e.tagName,class:e.className,parent:e.parentElement.className,grandparent:e.parentElement.parentElement.className,greatGrandparent:e.parentElement.parentElement.parentElement.className})),
    areas: [...document.querySelectorAll('textarea')].map(e=>({id:e.id,placeholder:e.placeholder,class:e.className,rows:e.rows,rect:e.getBoundingClientRect().toJSON(),font:getComputedStyle(e).font,lineHeight:getComputedStyle(e).lineHeight,whiteSpace:getComputedStyle(e).whiteSpace,overflowWrap:getComputedStyle(e).overflowWrap,padding:getComputedStyle(e).padding,lines:e.value.split('\n').map((l,i)=>/"(?:aic|provider|name|url|endPoints|skills)"/.test(l)?{line:i,key:l.match(/"([^"]+)"/)?.[1],length:l.length}:null).filter(Boolean)})),
    cells: [...document.querySelectorAll('td')].filter(e=>e.innerText.includes('智能体身份码')).map(e=>({class:e.className,nextClass:e.nextElementSibling?.className})),
    scrollContainers: [...document.querySelectorAll('[class*=scroll]')].filter(e=>e.scrollHeight>e.clientHeight+50).map(e=>({tag:e.tagName,class:e.className,id:e.id,height:e.clientHeight,scrollHeight:e.scrollHeight}))
  }));
}
