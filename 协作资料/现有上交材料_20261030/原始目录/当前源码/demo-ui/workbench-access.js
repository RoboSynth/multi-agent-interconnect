'use strict';
(function () {
  const labels = {complete: '已采集范围内，双方记录一致', incomplete: '已采集，记录尚不完整', invalid: '部分记录无法读取或解析', not_collected: '未采集到此事故的访问记录'};
  const number = value => Number.isFinite(value) ? String(value) : '—';
  function node(tag, className, value) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (value !== undefined) result.textContent = value;
    return result;
  }
  window.renderWorkbenchAccess = function (summary) {
    const root = document.getElementById('access-reconciliation');
    if (!root) return;
    root.replaceChildren();
    const status = summary?.status || 'not_collected';
    root.append(node('p', 'resolution-note access-status', labels[status] || labels.not_collected));
    if (!summary) {
      root.append(node('p', 'empty', '选择事故后，按该事故已捕获的任务核对双方访问记录。'));
      return;
    }
    const grid = node('div', 'business-facts access-grid');
    const items = [['捕获任务', summary.captured_start_tasks], ['应有双方记录', summary.expected_access_records],
      ['实际访问记录', summary.actual_access_records], ['缺少记录', summary.missing_records],
      ['多余记录', summary.extra_records], ['生命周期未完整', summary.incomplete_task_lifecycles]];
    for (const [title, value] of items) {
      const item = node('span');
      item.append(node('strong', '', number(value)), node('span', '', title));
      grid.append(item);
    }
    root.append(grid);
    const bad = (summary.invalid_records?.messages || 0) + (summary.invalid_records?.access || 0);
    const partial = (summary.partial_records?.messages || 0) + (summary.partial_records?.access || 0);
    const unreadable = (summary.read_errors?.messages || 0) + (summary.read_errors?.access || 0);
    root.append(node('p', 'resolution-note', '捕获源 ' + number(summary.sources?.message_files) + ' 份，访问源 ' + number(summary.sources?.access_files) +
      ' 份；无法解析 ' + bad + ' 行，尾行未结束 ' + partial + ' 行，无法读取 ' + unreadable + ' 份。'));
    if (summary.unrelated_access_records_excluded) root.append(node('p', 'resolution-note', '已排除其他任务或会话的 ' + number(summary.unrelated_access_records_excluded) + ' 条访问记录。'));
    root.append(node('p', 'resolution-note', summary.scope || '仅此事故的已捕获访问记录，不代表平台总量或Monitor入库。'));
    if (bad || unreadable) root.append(node('p', 'resolution-note', summary.parse_scope || '有无法归属的源记录，不能据此确认完整。'));
  };
}());
