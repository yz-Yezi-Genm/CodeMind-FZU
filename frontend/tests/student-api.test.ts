import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, ask, fetchHealth } from '../src/shared/api.ts';

const conversationId = '550e8400-e29b-41d4-a716-446655440001';
const createdAt = '2026-11-24T02:00:00Z';
const citation = {
  document_id: '550e8400-e29b-41d4-a716-446655440010',
  version_id: '550e8400-e29b-41d4-a716-446655440011',
  chunk_id: '550e8400-e29b-41d4-a716-446655440012',
  title: '测试资料',
  source_url: 'https://example.invalid/test-policy',
  locator: '第 2 条',
  excerpt: '用于核对引用展示。',
  source_verification_status: 'verified',
  timeliness_verification_status: 'historical',
  retrieval_status: 'enabled',
};
const answer = {
  request_id: '550e8400-e29b-41d4-a716-446655440000',
  conversation_id: conversationId,
  status: 'answered',
  answer: '请查阅所附资料。',
  answer_mode: 'historical',
  clarifying_question: null,
  citations: [citation],
  warnings: [],
  created_at: createdAt,
};
const query = '奖学金的申请条件是什么？';

test('健康检查使用统一路径，并识别异常响应', async t => {
  const health = { status: 'ok', service: 'codemind-fzu-api', version: '0.1.0', timestamp: createdAt };
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(health));
  assert.deepEqual(await fetchHealth(), health);
  assert.equal(fetch.mock.calls[0]?.arguments[0], '/api/v1/health');

  fetch.mock.mockImplementation(async () => Response.json({ ...health, timestamp: null }));
  await assert.rejects(fetchHealth(), { code: 'INVALID_RESPONSE' });
});

test('问答发送契约字段并沿用首轮的会话 ID', async t => {
  const clarification = {
    ...answer, status: 'needs_clarification', answer: null, answer_mode: null,
    clarifying_question: '请问是哪个学年的奖学金？', citations: [],
  };
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(answer));
  fetch.mock.mockImplementationOnce(async () => Response.json(clarification));
  const first = await ask({ query });
  assert.equal(first.status, 'needs_clarification');
  const second = await ask({ query: '2026 学年', conversation_id: first.conversation_id });
  assert.equal(second.status, 'answered');
  assert.equal(second.answer_mode, 'historical');
  assert.deepEqual(second.citations, [citation]);
  assert.deepEqual(fetch.mock.calls.map(({ arguments: [path, init] }) => [
    path, init?.method, JSON.parse(String(init?.body)),
  ]), [
    ['/api/v1/ask', 'POST', { query, conversation_id: null }],
    ['/api/v1/ask', 'POST', { query: '2026 学年', conversation_id: conversationId }],
  ]);
});

test('证据不足仍是正常响应，原因可由 warnings 提供', async t => {
  const response = {
    ...answer, status: 'insufficient_evidence', answer_mode: 'insufficient_data',
    answer: null, citations: [], warnings: [{ code: 'NO_EVIDENCE', message: '当前缺少可核对的政策资料。' }],
  };
  t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  assert.deepEqual(await ask({ query }), response);
});

test('兼容 Alpha Mock 的空回答模式，同时拒绝缺少标记或混入引用的响应', async t => {
  const response = {
    ...answer, answer_mode: null, citations: [],
    warnings: [{ code: 'MOCK_AGENT', message: '当前响应由 MockAgentService 生成。' }],
  };
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  assert.deepEqual(await ask({ query }), response);

  fetch.mock.mockImplementation(async () => Response.json({ ...response, warnings: [] }));
  await assert.rejects(ask({ query }), { code: 'INVALID_RESPONSE' });

  fetch.mock.mockImplementation(async () => Response.json({ ...response, citations: [citation] }));
  await assert.rejects(ask({ query }), { code: 'INVALID_RESPONSE' });
});

test('拒绝缺失、null、空字符串或纯空白的引用来源', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(answer));
  for (const link of [undefined, null, '', '  ']) {
    fetch.mock.mockImplementation(async () => Response.json({
      ...answer, citations: [{ ...citation, source_url: link }],
    }));
    await assert.rejects(ask({ query }), { code: 'INVALID_RESPONSE' });
  }
});

test('已回答可以使用公共契约中的四种回答模式', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(answer));
  for (const mode of ['current_policy', 'historical', 'procedure_reference', 'insufficient_data']) {
    fetch.mock.mockImplementation(async () => Response.json({ ...answer, answer_mode: mode }));
    assert.equal((await ask({ query })).answer_mode, mode);
  }
});

test('拒绝无效会话、错误的状态组合和畸形引用', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(answer));
  await assert.rejects(ask({ query, conversation_id: 'not-a-uuid' }), { code: 'INVALID_CONVERSATION' });
  assert.equal(fetch.mock.callCount(), 0);
  const overrides = [
    { conversation_id: undefined },
    { conversation_id: 'invalid' },
    { status: 'other' },
    { answer_mode: null },
    { answer_mode: 'unknown_mode' },
    { status: 'needs_clarification', answer: null, answer_mode: null, clarifying_question: '追问' },
    { status: 'insufficient_evidence', answer_mode: 'insufficient_data', citations: [], answer: null },
    { citations: [{ ...citation, locator: [] }] },
    { warnings: [null] },
  ];
  for (const fields of overrides) {
    fetch.mock.mockImplementation(async () => Response.json({ ...answer, ...fields }));
    await assert.rejects(ask({ query }), { code: 'INVALID_RESPONSE' }, JSON.stringify(fields));
  }
  fetch.mock.mockImplementation(async () => new Response('not JSON'));
  await assert.rejects(ask({ query }), { code: 'INVALID_RESPONSE' });
});

test('按 Beta 口径处理 HTTP 400、429、500、503 和 504', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(answer));
  const cases = [
    [400, 'INVALID_REQUEST', false],
    [429, 'RATE_LIMITED', true],
    [500, 'INTERNAL_ERROR', false],
    [503, 'MODEL_UNAVAILABLE', true],
    [504, 'MODEL_TIMEOUT', true],
  ] as const;
  for (const [status, code, retryable] of cases) {
    fetch.mock.mockImplementation(async () => Response.json({
      request_id: answer.request_id, error: { code, message: '后端错误样例', retryable },
    }, { status }));
    await assert.rejects(ask({ query }), { status, code, retryable });
  }
  fetch.mock.mockImplementation(async () => new Response('Bad Gateway', { status: 502 }));
  await assert.rejects(ask({ query }), { status: 502, code: 'HTTP_502' });
});

test('断网和客户端超时有不同的错误码，超时也覆盖读取响应正文', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('offline'); });
  await assert.rejects(ask({ query }), { code: 'NETWORK_ERROR' });

  t.mock.timers.enable({ apis: ['setTimeout'] });
  fetch.mock.mockImplementation(async (_url, init) => {
    const body = new ReadableStream({
      start(controller) {
        const signal = init?.signal;
        signal?.addEventListener('abort', () => controller.error(signal.reason), { once: true });
      },
    });
    return new Response(body);
  });
  const pending = assert.rejects(ask({ query }), (error: unknown) =>
    error instanceof ApiError && error.status === 0 && error.code === 'REQUEST_TIMEOUT');
  await Promise.resolve();
  t.mock.timers.tick(45_000);
  await pending;
});
