// @vitest-environment node
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterAll(() => server.close());

describe('MSW runtime contract', () => {
  it('supports session create, list and message history endpoints', async () => {
    const created = await fetch('http://localhost/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'MSW 测试' }),
    });
    expect(created.status).toBe(200);
    const session = (await created.json()) as { session_id: string };
    const listed = await fetch('http://localhost/api/v1/sessions');
    expect(
      ((await listed.json()) as Array<{ session_id: string }>).some(
        (item) => item.session_id === session.session_id,
      ),
    ).toBe(true);
    const history = await fetch(`http://localhost/api/v1/sessions/${session.session_id}/messages`);
    expect(await history.json()).toEqual([]);
  });

  it('deletes one session message by its stable id', async () => {
    const created = await fetch('http://localhost/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'MSW 删除消息' }),
    });
    const session = (await created.json()) as { session_id: string };
    await fetch('http://localhost/api/v1/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id, message: '删除我' }),
    });
    const stored = (await (
      await fetch(`http://localhost/api/v1/sessions/${session.session_id}/messages`)
    ).json()) as Array<{ id: string }>;

    const deleted = await fetch(
      `http://localhost/api/v1/sessions/${session.session_id}/messages/${stored[0].id}`,
      { method: 'DELETE' },
    );
    const missing = await fetch(
      `http://localhost/api/v1/sessions/${session.session_id}/messages/${stored[0].id}`,
      { method: 'DELETE' },
    );
    const history = await fetch(`http://localhost/api/v1/sessions/${session.session_id}/messages`);

    expect(deleted.status).toBe(200);
    expect(await deleted.json()).toMatchObject({ deleted_ids: [stored[0].id] });
    expect(missing.status).toBe(404);
    expect(await history.json()).toEqual([]);
  });

  it('runs the offline artifact + skill + SSE flow with the current v1 shapes', async () => {
    const created = await fetch('http://localhost/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'MSW 主流程' }),
    });
    const session = (await created.json()) as { session_id: string };
    const artifactForm = new FormData();
    artifactForm.append('file', new File(['work order'], 'orders.txt', { type: 'text/plain' }));
    const artifactResponse = await fetch('http://localhost/api/v1/artifacts', {
      method: 'POST',
      body: artifactForm,
    });
    const artifact = (await artifactResponse.json()) as { artifact_id: string };

    const runResponse = await fetch('http://localhost/api/v1/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: session.session_id,
        message: '分析工单',
        source: 'expert',
        skill_names: ['offline-manufacturing'],
        artifact_ids: [artifact.artifact_id],
      }),
    });
    expect(runResponse.status).toBe(202);
    const run = (await runResponse.json()) as {
      run_id: string;
      input_artifact_ids: string[];
      intent: { requested_skills: string[] };
    };
    expect(run.input_artifact_ids).toEqual([artifact.artifact_id]);
    expect(run.intent.requested_skills).toEqual(['offline-manufacturing']);
    expect((run.intent as { source?: string }).source).toBe('expert');

    const stream = await fetch(`http://localhost/api/v1/runs/${run.run_id}/stream`);
    const sse = await stream.text();
    expect(sse).toContain('event: token.delta');
    expect(sse).toContain('event: run.completed');
    const snapshot = await fetch(`http://localhost/api/v1/runs/${run.run_id}`);
    expect(((await snapshot.json()) as { status: string }).status).toBe('completed');
  });

  it('validates, imports, trusts, revokes and deletes an isolated mock skill', async () => {
    const skillFile = new File(
      ['---\nname: e2e-skill\ndescription: test\n---\nbody'],
      'e2e-skill.md',
      { type: 'text/markdown' },
    );
    const validationForm = new FormData();
    validationForm.append('file', skillFile);
    expect(
      (
        await fetch('http://localhost/api/v1/skills/validate', {
          method: 'POST',
          body: validationForm,
        })
      ).status,
    ).toBe(200);
    const importForm = new FormData();
    importForm.append('file', skillFile);
    expect(
      (await fetch('http://localhost/api/v1/skills/import', { method: 'POST', body: importForm }))
        .status,
    ).toBe(200);
    expect(
      (
        await fetch('http://localhost/api/v1/skills/e2e-skill/trust', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ trusted: true }),
        })
      ).status,
    ).toBe(200);
    expect(
      (await fetch('http://localhost/api/v1/skills/e2e-skill/trust', { method: 'DELETE' })).status,
    ).toBe(200);
    expect(
      (await fetch('http://localhost/api/v1/skills/e2e-skill', { method: 'DELETE' })).status,
    ).toBe(204);
  });
});
