// Playwright CLI run-code. Use the local stage2_offline_app test server.
async (page) => {
  const records = [];
  const input = page.locator('#ask-input');
  function check(value, message) {
    if (!value) throw new Error(message);
  }
  await page.getByLabel('用户名', { exact: true }).fill('demo');
  await page.getByLabel('密码', { exact: true }).fill('123456');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByText('后端已连接', { exact: true }).waitFor();

  async function submit(query, conversationId, expectedStatus) {
    const turnIndex = await page.locator('.student-turn').count();
    await input.fill(query);
    const [reply] = await Promise.all([
      page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/v1/ask'),
      input.press('Enter'),
    ]);
    const sent = reply.request().postDataJSON();
    const body = await reply.json();
    check(sent.query === query && sent.conversation_id === conversationId, '请求问题或会话 ID 有误');
    check(reply.status() === 200 && body.status === expectedStatus, '问答结果与离线样例不符');
    check(body.request_id && body.request_id === reply.headers()['x-request-id'], '请求编号不匹配');
    check(body.conversation_id && (!conversationId || conversationId === body.conversation_id), '响应会话 ID 有误');
    const heading = { answered: '已回答', needs_clarification: '需要补充信息', insufficient_evidence: '证据不足' };
    const turn = page.locator('.student-turn').nth(turnIndex);
    await turn.getByRole('heading', { name: heading[expectedStatus], exact: true }).waitFor();
    const content = body.clarifying_question || body.answer;
    check((await turn.locator('.student-answer > p').allTextContents()).includes(content), '正文与响应不符');
    if (expectedStatus === 'answered') {
      check(body.citations.length > 0, '缺少检索引用');
      for (const citation of body.citations) {
        const details = turn.locator('details').filter({ has: page.getByText(citation.title, { exact: true }) });
        await details.locator('summary').click();
        await details.getByText(citation.excerpt, { exact: true }).waitFor();
        check(!citation.locator || (await details.textContent()).includes(citation.locator), '定位未显示');
        check(new URL(citation.source_url).hostname === 'example.invalid' && await details.getByRole('link').count() === 0,
          '合成测试引用不应出现可点击链接');
      }
    } else {
      check(body.citations.length === 0 && await turn.locator('details').count() === 0, '额外引用');
    }
    records.push({ query, sent_conversation_id: conversationId, conversation_id: body.conversation_id,
      request_id: body.request_id, status: body.status, mode: body.answer_mode, citations: body.citations.length });
    return body.conversation_id;
  }
  for (const [scene, title, expected, query] of [
    ['s1', '竞赛认定', 'needs_clarification'],
    ['s2', '奖学金申请', 'answered', '2026年优秀学生综合奖学金申请需要提交什么材料？'],
    ['s3', '推免条件咨询', 'insufficient_evidence'],
    ['s4', '学院资源导航', 'insufficient_evidence'],
  ]) {
    await page.locator('#new-chat').click();
    await page.getByRole('button', { name: new RegExp(title) }).click();
    const session = await submit(query || await input.inputValue(), null, expected);
    await page.screenshot({ path: scene + '-offline.png', fullPage: true });
    if (scene === 's1') await submit('我的作品名称是基于多源数据的城市交通流量预测。', session, 'needs_clarification');
    if (scene === 's2') await submit('2026年优秀学生综合奖学金金额是多少？', session, 'insufficient_evidence');
  }
  return records;
}
