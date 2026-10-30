(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const scenarios = {
    stale_endpoint: '应用与数据库分别提供证据，协调者据此修正连接地址。',
    database_paused: '应用报告连接失败，数据库智能体检查自身状态并恢复服务。',
    combined: '一次遇到两个问题，观察协调者如何依据新证据分步修复。',
    agent_offline: '原服务成员退出后，观察协调者是否能发现替代者并继续任务。',
    unknown_fault: '没有足够证据时，观察系统如何保留现场并转交人工。'
  };
  const defaultSteps = [...document.querySelectorAll('.workflow-step')].map((node) => ({
    node,
    title: node.querySelector('h3').textContent,
    detail: node.querySelector('.step-detail').textContent,
    agent: node.querySelector('.step-agent').textContent
  }));
  const statusLabels = {
    pending: '等待开始', waiting: '等待开始', queued: '等待开始', idle: '等待开始',
    running: '正在进行', working: '正在进行', in_progress: '正在进行',
    completed: '已完成', complete: '已完成', success: '已完成', passed: '已完成', done: '已完成',
    failed: '未完成', error: '未完成', rejected: '已阻止', canceled: '已取消', cancelled: '已取消',
    skipped: '未执行', blocked: '等待人工', awaiting_input: '等待人工', manual: '转交人工', warning: '需要关注'
  };
  let busy = false;
  let activeRunId = null;
  let pollTimer = null;
  let stateTimer = null;
  let lastAnnouncement = '';
  let lastState = null;

  const show = (element, visible) => { element.hidden = !visible; };
  const setText = (element, value) => {
    if (!element) return;
    const next = value == null ? '' : String(value);
    if (element.textContent !== next) element.textContent = next;
  };
  const rawText = (value) => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const statusKey = (value) => String(value || 'pending').toLowerCase().replaceAll('-', '_');
  const visualStatus = (value) => {
    const key = statusKey(value);
    if (['completed', 'complete', 'success', 'passed', 'done'].includes(key)) return 'completed';
    if (['running', 'working', 'in_progress'].includes(key)) return 'running';
    if (['failed', 'error', 'rejected', 'canceled', 'cancelled'].includes(key)) return 'failed';
    if (['blocked', 'awaiting_input', 'manual', 'warning'].includes(key)) return 'warning';
    if (key === 'skipped') return 'skipped';
    return 'pending';
  };
  const readable = (value, fallback = '—') => {
    if (value == null) return fallback;
    if (typeof value === 'object') return value.message || value.detail || value.status || rawText(value);
    return String(value);
  };
  const announce = (message) => {
    if (message === lastAnnouncement) return;
    lastAnnouncement = message;
    setText($('#live-status'), message);
  };
  const errorMessage = (error) => error instanceof Error ? error.message : String(error);
  const setError = (message) => {
    setText($('#error-banner'), message);
    show($('#error-banner'), Boolean(message));
  };
  const setBusy = (value) => {
    busy = value;
    $('#start-button').disabled = value;
    $('#scenario').disabled = value;
    setText($('#start-button-label'), value ? '协作正在进行…' : '开始一次协同修复');
  };
  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, headers: { Accept: 'application/json', ...options.headers } });
      let body;
      try { body = await response.json(); } catch { throw new Error('演示服务返回了无法读取的内容，请检查服务是否已启动。'); }
      if (!response.ok) throw new Error(readable(body.error || body.detail, `服务请求失败（${response.status}）`));
      return body;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('演示服务响应超时，请稍后重试。');
      if (error instanceof TypeError) throw new Error('无法连接演示服务，请确认本地服务仍在运行。');
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function isVerified(value) {
    if (value === true) return true;
    if (value && typeof value === 'object') return value.verified === true || value.ok === true || isVerified(value.status);
    return ['verified', 'connected', 'registered', 'valid', 'passed', 'ready', 'success', 'completed', 'ok'].includes(String(value || '').toLowerCase());
  }
  function renderPlatform(platform = {}) {
    const registrationStatus = String(platform.registration_status || platform.registrationStatus || platform.review_status || platform.reviewStatus || platform.registration?.status || '').toLowerCase();
    const draft = /draft|pending_review|awaiting_review|under_review|草稿|待审核|未审核/.test(registrationStatus) || platform.approved === false || /草稿|未审核|尚未审核/.test(platform.note || '');
    const registrationVerified = isVerified(platform.registered) && !draft;
    document.querySelectorAll('[data-platform]').forEach((element) => {
      const field = element.dataset.platform;
      const value = platform[field];
      const concreteAic = typeof value === 'string' && value.trim().length > 3 && !/^(pending|null|none|local|draft|unregistered|not_|待|未)/i.test(value.trim());
      const verified = field === 'registered' ? registrationVerified : field === 'aic' ? registrationVerified && (isVerified(value) || concreteAic) : isVerified(value);
      element.classList.toggle('verified', verified);
      setText(element.querySelector('.check-symbol'), verified ? '✓' : '○');
      const knownUnavailable = value === false || value == null || ['pending', 'not_connected', 'unregistered', 'not_registered', 'not_configured'].includes(String(value).toLowerCase());
      const label = field === 'registered' && draft ? '草稿未审核' : field === 'aic' && draft ? '待审核' : verified ? (field === 'aic' ? '身份已获' : '已验证') : knownUnavailable ? '待接入' : '待验证';
      setText(element.querySelector('b'), label);
    });
    setText($('#platform-note'), platform.note || '正式平台状态以实际返回的接入证据为准。');
    setText($('#platform-raw'), rawText(platform));
  }
  const agentStatus = (status) => {
    const key = statusKey(status);
    if (['online', 'ready', 'healthy', 'running', 'available', 'registered', 'active'].includes(key)) return ['在线', ''];
    if (['failed', 'error', 'unhealthy'].includes(key)) return ['异常', 'error'];
    if (['offline', 'stopped', 'unavailable', 'disconnected'].includes(key)) return ['离线', 'offline'];
    if (['working', 'busy'].includes(key)) return ['执行中', ''];
    return ['待检查', 'offline'];
  };
  function renderAgents(agents) {
    if (!Array.isArray(agents) || !agents.length) {
      if (!$('#agents-list .empty-agents')) {
        $('#agents-list').replaceChildren();
        const text = document.createElement('p');
        text.className = 'empty-agents';
        text.textContent = '暂无可用成员。启动演示服务后，这里会显示实际名单。';
        $('#agents-list').append(text);
      }
      return;
    }
    const existing = new Map([...document.querySelectorAll('#agents-list .agent')].map((node) => [node.dataset.agent, node]));
    $('#agents-list .empty-agents')?.remove();
    const validIds = new Set();
    agents.forEach((agent, index) => {
      const id = String(agent.id || `agent-${index}`);
      validIds.add(id);
      let node = existing.get(id);
      if (!node) {
        node = document.createElement('div');
        node.className = 'agent';
        node.dataset.agent = id;
        const icon = document.createElement('span');
        icon.className = 'agent-icon';
        icon.setAttribute('aria-hidden', 'true');
        const body = document.createElement('div');
        body.className = 'agent-body';
        const line = document.createElement('div');
        line.className = 'agent-line';
        const name = document.createElement('span');
        name.className = 'agent-name';
        const state = document.createElement('span');
        state.className = 'agent-state';
        line.append(name, state);
        const role = document.createElement('p');
        role.className = 'agent-role';
        const endpoint = document.createElement('details');
        endpoint.className = 'agent-endpoint';
        const summary = document.createElement('summary');
        summary.textContent = '服务地址';
        const address = document.createElement('p');
        endpoint.append(summary, address);
        body.append(line, role, endpoint);
        node.append(icon, body);
        $('#agents-list').append(node);
      }
      setText(node.querySelector('.agent-icon'), String(index + 1).padStart(2, '0'));
      setText(node.querySelector('.agent-name'), agent.name || agent.id || `智能体 ${index + 1}`);
      const roles = { leader: '发现成员，协调任务与修复顺序', application: '检查网站状态与连接配置', database: '检查数据库，执行授权修复', verification: '独立确认网站恢复与数据一致' };
      setText(node.querySelector('.agent-role'), roles[agent.role] || agent.role || '独立服务成员');
      const [label, style] = agentStatus(agent.status);
      setText(node.querySelector('.agent-state'), label);
      node.querySelector('.agent-state').className = `agent-state ${style}`;
      const endpoint = node.querySelector('.agent-endpoint');
      show(endpoint, Boolean(agent.endpoint));
      setText(endpoint.querySelector('p'), agent.endpoint || '尚未提供');
    });
    existing.forEach((node, id) => { if (!validIds.has(id)) node.remove(); });
  }
  function renderRun(run) {
    if (!run) return;
    const runStyle = visualStatus(run.status);
    const running = ['running', 'pending'].includes(runStyle);
    setBusy(running);
    const runLabel = statusLabels[statusKey(run.status)] || readable(run.status);
    setText($('#run-status'), runLabel);
    $('#run-status').className = `run-status ${runStyle === 'warning' ? 'failed' : runStyle}`;
    setText($('#run-caption'), `本次任务：${$('#scenario option[value="' + (scenarios[run.scenario] ? run.scenario : $('#scenario').value) + '"]').textContent}`);
    const steps = Array.isArray(run.steps) ? run.steps : [];
    defaultSteps.forEach((base, index) => {
      const step = steps[index];
      const state = step ? visualStatus(step.status) : 'pending';
      base.node.className = `workflow-step ${state}`;
      setText(base.node.querySelector('h3'), step?.title || base.title);
      setText(base.node.querySelector('.step-status'), step ? (statusLabels[statusKey(step.status)] || readable(step.status)) : '等待开始');
      setText(base.node.querySelector('.step-detail'), step?.detail ? readable(step.detail) : base.detail);
      setText(base.node.querySelector('.step-agent'), step?.agent ? readable(step.agent) : base.agent);
      setText(base.node.querySelector('.step-marker span'), state === 'completed' ? '✓' : state === 'failed' ? '!' : index + 1);
      const evidence = base.node.querySelector('.step-evidence');
      const hasEvidence = step?.evidence != null;
      show(evidence, hasEvidence);
      if (hasEvidence) setText(evidence.querySelector('pre'), rawText(step.evidence));
    });
    const current = steps.find((step) => visualStatus(step.status) === 'running');
    announce(current ? `正在${current.title}` : `本次协作${runLabel}`);
    show($('#run-record'), true);
    setText($('#run-raw'), rawText(run));
    renderResult(run.result);
    if (run.error) setError(`本次运行未完成：${readable(run.error)}`);
    return running;
  }

  function renderResult(result) {
    show($('#result-panel'), Boolean(result));
    if (!result) return;
    const outcome = String(result.outcome || '').toLowerCase();
    const manual = /manual|unknown|blocked|escalat|human|unresolved|转人工|未知/.test(outcome);
    const failure = !manual && /fail|error|rejected/.test(outcome);
    $('#result-panel').className = `result-panel${manual ? ' attention' : failure ? ' failure' : ''}`;
    const titles = { restored: '服务已恢复', recovered: '服务已恢复', repaired: '服务已恢复', healthy: '服务正常，无需修改', no_change: '服务正常，无需修改', manual: '已保留证据，等待人工处理', manual_required: '已保留证据，等待人工处理', escalated: '已保留证据，等待人工处理', failed: '本次未能恢复服务' };
    setText($('#result-title'), titles[outcome] || (manual ? '已保留证据，等待人工处理' : failure ? '本次未能恢复服务' : '本次协作已完成'));
    setText($('#result-description'), manual ? '系统没有在证据不足时继续修改，现场与检查结果已保留。' : failure ? '查看步骤证据了解阻塞位置，然后重新执行验证。' : '结论来自独立复核，可展开上方步骤查看每次行动的依据。');
    setText($('#before-status'), readable(result.before_status));
    setText($('#after-status'), readable(result.after_status));
    const mutations = result.mutations;
    setText($('#mutation-count'), typeof mutations === 'number' ? `${mutations} 次` : Array.isArray(mutations) ? `${mutations.length} 次` : readable(mutations));
    setText($('#data-status'), result.data_unchanged === true ? '保持一致' : result.data_unchanged === false ? '需要检查' : '未验证');
  }

  async function refreshState({ renderLatest = false } = {}) {
    let receivedState = false;
    try {
      const state = await api('/api/state');
      receivedState = true;
      lastState = state;
      renderPlatform(state.platform);
      renderAgents(state.agents);
      $('#local-dot').className = 'status-dot ready';
      setText($('#local-label'), '本地协作服务已连接');
      setText($('#local-caption'), '可运行真实的隔离故障演示');
      if (renderLatest && state.run && !busy && !activeRunId) {
        activeRunId = state.run.id;
        if (scenarios[state.run.scenario]) $('#scenario').value = state.run.scenario;
        setText($('#scenario-hint'), scenarios[$('#scenario').value]);
        if (renderRun(state.run)) schedulePoll();
      }
    } catch (error) {
      console.error('状态刷新失败', error);
      $('#local-dot').className = 'status-dot error';
      setText($('#local-label'), receivedState ? '服务已连接，页面显示失败' : '本地服务暂不可用');
      setText($('#local-caption'), receivedState ? '请刷新页面查看最新状态' : '请检查服务，页面将自动重试');
      if (receivedState) setError(`读取服务成功，但页面显示失败：${errorMessage(error)}`);
      if (!lastState) {
        setText($('#agents-list .empty-agents'), '暂时无法获取成员名单，请确认本地演示服务已启动。');
        setText($('#platform-note'), '无法读取平台状态。当前页面未确认正式接入。');
      }
    }
  }
  function schedulePoll(delay = 700) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(pollRun, delay);
  }
  async function pollRun() {
    if (!activeRunId) return;
    try {
      const payload = await api(`/api/runs/${encodeURIComponent(activeRunId)}`);
      const run = payload.run || payload;
      setError('');
      if (renderRun(run)) schedulePoll();
      else {
        activeRunId = null;
        refreshState();
      }
    } catch (error) {
      setError(`${errorMessage(error)} 已暂停获取进度，2 秒后自动重试。`);
      schedulePoll(2000);
    }
  }
  $('#scenario').addEventListener('change', () => setText($('#scenario-hint'), scenarios[$('#scenario').value]));
  $('#run-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    clearTimeout(pollTimer);
    setBusy(true);
    setError('');
    renderResult(null);
    setText($('#run-status'), '正在开始');
    $('#run-status').className = 'run-status running';
    defaultSteps.forEach((base, index) => {
      base.node.className = 'workflow-step pending';
      setText(base.node.querySelector('h3'), base.title);
      setText(base.node.querySelector('.step-detail'), base.detail);
      setText(base.node.querySelector('.step-agent'), base.agent);
      setText(base.node.querySelector('.step-status'), '等待开始');
      setText(base.node.querySelector('.step-marker span'), index + 1);
      show(base.node.querySelector('.step-evidence'), false);
    });
    show($('#run-record'), false);
    try {
      const result = await api('/api/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario: $('#scenario').value }) });
      if (!result.id) throw new Error('服务没有返回任务编号，请检查后重试。');
      activeRunId = result.id;
      announce('协同修复已开始');
      schedulePoll(0);
      refreshState();
    } catch (error) {
      setError(errorMessage(error));
      setBusy(false);
      setText($('#run-status'), '启动失败');
      $('#run-status').className = 'run-status failed';
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { refreshState(); if (activeRunId) schedulePoll(0); }
  });
  window.addEventListener('pagehide', () => { clearTimeout(pollTimer); clearInterval(stateTimer); });
  refreshState({ renderLatest: true });
  stateTimer = setInterval(() => { if (!document.hidden) refreshState(); }, 5000);
})();
