async (page) => {
  await page.getByRole('searchbox', { name: '智能体 AIC', exact: true }).evaluate(el => {
    el.style.setProperty('color', 'transparent', 'important');
    el.style.setProperty('-webkit-text-fill-color', 'transparent', 'important');
    el.style.setProperty('text-shadow', 'none', 'important');
    el.style.setProperty('background', '#1f2937', 'important');
    el.style.setProperty('caret-color', 'transparent', 'important');
  });
}
