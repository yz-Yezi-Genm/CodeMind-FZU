// Run with Playwright CLI run-code against the Vite student entry.
async (page) => {
  function check(condition, message) {
    if (!condition) throw new Error(message);
  }

  const home = new URL('/', page.url());
  const conversationId = '550e8400-e29b-41d4-a716-446655440001';
  const timestamp = '2026-11-24T02:00:00Z';
  const excerpt = '这是一条用于验证界面展示的引用。';
  const citation = {
    document_id: '550e8400-e29b-41d4-a716-446655440010',
    version_id: '550e8400-e29b-41d4-a716-446655440011',
    chunk_id: '550e8400-e29b-41d4-a716-446655440012',
    title: '测试政策文件',
    source_url: 'https://www.fzu.edu.cn/',
    locator: '第 2 条',
    original_locator: '原文件第 3 页',
    excerpt,
    source_verification_status: 'verified',
    timeliness_verification_status: 'historical',
    retrieval_status: 'enabled',
  };
  const answer = {
    request_id: '550e8400-e29b-41d4-a716-446655440000',
    conversation_id: conversationId,
    status: 'answered',
    answer: '请查阅所附资料了解历史年度的办理要求。',
    answer_mode: 'historical',
    clarifying_question: null,
    citations: [citation, { ...citation, title: '仅用于联调的资料', source_url: 'https://example.invalid/policy' }],
    warnings: [{ code: 'HISTORICAL_REFERENCE', message: '当前资料仅用于历史年度参考。' }],
    created_at: timestamp,
  };
  const clarification = {
    ...answer, status: 'needs_clarification', answer: null, answer_mode: null,
    clarifying_question: '请问你咨询的是哪一学年的评定？', citations: [], warnings: [],
  };
  const insufficient = {
    ...answer, status: 'insufficient_evidence', answer_mode: 'insufficient_data',
    answer: null, citations: [],
    warnings: [{ code: 'NO_EVIDENCE', message: '目前没有足够的资料确认这一点。' }],
  };
  let respond = route => route.fulfill({ json: answer });
  const requests = [];
  await page.route('**/api/v1/health', route => route.fulfill({
    json: { status: 'ok', service: 'codemind-fzu-api', version: '0.1.0', timestamp },
  }));
  await page.route('**/api/v1/ask', route => {
    const request = route.request();
    check(request.method() === 'POST', '问答未使用 POST');
    requests.push(request.postDataJSON());
    return respond(route);
  });

  const entryModule = /\/src\/student\/demo-entry\.ts(?:\?.*)?$/;
  let loadEntry;
  const entryDelay = new Promise(resolve => { loadEntry = resolve; });
  await page.route(entryModule, async route => {
    await entryDelay;
    await route.continue();
  }, { times: 1 });
  try {
    await Promise.all([
      page.waitForRequest(entryModule),
      page.goto(new URL('?preview=1', home).href, { waitUntil: 'domcontentloaded' }),
    ]);
    check(await page.locator('#student-startup').isVisible() && !await page.locator('#demo-entry').isVisible(),
      '入口模块和样式加载前显示了登录页');
  } finally {
    loadEntry();
  }
  await page.getByLabel('用户名', { exact: true }).fill('demo');
  await page.getByLabel('密码', { exact: true }).fill('123456');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByText('后端已连接', { exact: true }).waitFor();
  const input = page.locator('#ask-input');
  const send = page.getByRole('button', { name: '发送', exact: true });
  const newChat = page.getByRole('button', { name: /新建对话/ });
  const status = page.locator('#ask-status');

  for (const [label, words] of [
    ['竞赛认定', '创新学分'], ['奖学金申请', '奖学金'],
    ['推免条件咨询', '推免'], ['学院资源导航', '实验室'],
  ]) {
    await page.getByRole('button', { name: new RegExp(label) }).click();
    check((await input.inputValue()).includes(words), `快捷问题未填入：${label}`);
  }
  await input.fill('奖学金怎么申请？');
  await input.press('Shift+Enter');
  check((await input.inputValue()).endsWith('\n') && requests.length === 0, '换行触发了发送');

  let finishClarification;
  const delayed = new Promise(resolve => { finishClarification = resolve; });
  respond = async route => {
    await delayed;
    await route.fulfill({ json: clarification });
  };
  try {
    await Promise.all([page.waitForRequest('**/api/v1/ask'), input.press('Enter')]);
    await page.getByText('正在请求回答…', { exact: true }).waitFor();
    check(await send.isDisabled() && await newChat.isDisabled(), '请求期间控件可重复触发');
    await input.press('Enter');
    check(requests.length === 1 && requests[0].query === '奖学金怎么申请？'
      && requests[0].conversation_id === null, '首轮请求或防重复提交不正确');
  } finally {
    finishClarification();
  }
  await page.getByText(clarification.clarifying_question, { exact: true }).waitFor();

  respond = route => route.fulfill({ json: answer });
  await input.fill('2026 学年');
  await send.click();
  await page.getByRole('heading', { name: '已回答', exact: true }).waitFor();
  check(requests[1].conversation_id === conversationId, '补充问题没有沿用首轮 ID');
  await page.getByText(/历史资料参考/).waitFor();
  const sources = page.getByRole('region', { name: '引用来源' });
  const linkedCitation = sources.locator('details').filter({ hasText: citation.title });
  await linkedCitation.getByText(citation.title, { exact: true }).click();
  await linkedCitation.getByText(/原文件第 3 页/).waitFor();
  await linkedCitation.getByText(excerpt, { exact: true }).waitFor();
  const sourceLink = sources.getByRole('link', { name: '查看原始来源' });
  check(await sourceLink.getAttribute('href') === citation.source_url, '来源链接不等于接口返回值');
  await sources.getByText('仅用于联调的资料', { exact: true }).click();
  check(await sourceLink.count() === 1 && !(await sources.textContent()).includes(citation.chunk_id), '生成了多余链接或暴露内部标识');

  respond = route => route.fulfill({ json: insufficient });
  await input.fill('2099 年推免政策是什么？');
  await send.click();
  await page.getByRole('heading', { name: '证据不足', exact: true }).waitFor();
  await page.getByText(insufficient.warnings[0].message, { exact: true }).waitFor();
  check(await page.locator('.student-turn').last().getByRole('link').count() === 0, '证据不足生成了来源链接');

  const failureInput = '发送失败后保留这个问题';
  await input.fill(failureInput);
  async function expectFailure() {
    await send.click();
    await status.filter({ hasText: /重试|重新发送|再发送|无法连接后端/ }).waitFor();
    check(await input.inputValue() === failureInput && await send.isEnabled(), '请求失败后无法重试');
    check(await page.locator('.student-turn').count() === 3, '失败请求被添加为正常回答');
    return status.textContent();
  }
  for (const [code, httpStatus, message] of [
    ['INVALID_REQUEST', 400, '问题格式'],
    ['RATE_LIMITED', 429, '频繁'],
    ['INTERNAL_ERROR', 500, '服务暂时'],
    ['MODEL_UNAVAILABLE', 503, '模型暂时不可用'],
    ['MODEL_TIMEOUT', 504, '超时'],
  ]) {
    respond = route => route.fulfill({
      status: httpStatus, json: { request_id: answer.request_id, error: { code, message: '仅用于测试的内部错误细节', retryable: true } },
    });
    const notice = await expectFailure();
    check(notice.includes(message) && !notice.includes('内部错误细节'), `错误提示不匹配：${code}`);
  }
  respond = route => route.fulfill({ json: { ...answer, conversation_id: 'bad' } });
  check((await expectFailure()).includes('会话编号'), '无效会话响应没有明确提示');
  respond = route => route.fulfill({ json: { ...answer, citations: [{ ...citation, source_url: null }] } });
  check((await expectFailure()).includes('无效或空数据'), '缺少来源的引用未触发格式错误');
  respond = route => route.abort('internetdisconnected');
  check((await expectFailure()).includes('无法连接后端'), '断网提示不正确');

  respond = route => route.fulfill({ json: { ...answer, answer_mode: 'insufficient_data' } });
  await send.click();
  const recovered = page.locator('.student-turn').nth(3);
  await recovered.getByRole('heading', { name: '已回答', exact: true }).waitFor();
  await recovered.getByText('回答依据：证据不足', { exact: true }).waitFor();
  check(requests.at(-1).conversation_id === conversationId, '错误恢复丢失当前会话');

  await newChat.click();
  check(await page.locator('.student-turn').count() === 0, '新建对话没有清空记录');
  respond = route => route.fulfill({ json: {
    ...answer, answer_mode: 'current_policy', citations: [],
    warnings: [{ code: 'MOCK_AGENT', message: '当前使用模拟 Agent。' }],
  } });
  await input.fill('新问题');
  await send.click();
  await page.getByRole('heading', { name: '模拟回答', exact: true }).waitFor();
  check(await page.locator('.student-answer-mode').count() === 0, '模拟回答显示了正式政策依据');
  check(requests.at(-1).conversation_id === null, '新建对话沿用了旧 ID');
  respond = route => route.fulfill({ json: answer });
  const workspaceModule = /\/src\/student\/main\.ts(?:\?.*)?$/;
  let loadWorkspace;
  const workspaceDelay = new Promise(resolve => { loadWorkspace = resolve; });
  await page.route(workspaceModule, async route => {
    await workspaceDelay;
    await route.continue();
  }, { times: 1 });
  try {
    await Promise.all([page.waitForRequest(workspaceModule), page.reload({ waitUntil: 'domcontentloaded' })]);
    check(await page.locator('#student-startup').isVisible()
      && !await page.locator('#demo-entry').isVisible() && !await input.isVisible(), '已登录刷新时闪出了登录页或半成品工作台');
  } finally {
    loadWorkspace();
  }
  await input.waitFor();
  check(!await page.locator('#student-startup').isVisible(), '工作台显示后仍有启动提示遮挡');
  check(await page.locator('.student-turn').count() === 0, '刷新没有回到新的问答会话');
  await input.fill('刷新后的问题');
  await send.click();
  await page.locator('.student-turn').first().waitFor();
  check(requests.at(-1).conversation_id === null, '刷新后发送了旧 ID');
  return '学生端浏览器回归通过（三种状态、四场景入口、多轮、引用、错误恢复、刷新与新建会话）。';
}
