/**
 * LLM transports for the Maisha drafting layer. Faithful port of api/app/llm/client.py.
 * Each client takes a system prompt, a user prompt, and a JSON schema, and returns the model's
 * response parsed as a JSON object — the schema is enforced by the provider's constrained
 * decoding so a malformed claim cannot come back. We fail loud (LLMError) rather than fabricate.
 */

export class LLMError extends Error {}

export interface LLMClient {
  complete(args: { system: string; user: string; schema: object }): Promise<Record<string, any>>;
}

async function fetchJson(url: string, init: RequestInit, timeoutMs: number, label: string): Promise<any> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...init, signal: ctrl.signal });
    if (!resp.ok) throw new LLMError(`${label} failed: HTTP ${resp.status}`);
    return await resp.json();
  } catch (e) {
    if (e instanceof LLMError) throw e;
    throw new LLMError(`${label} failed: ${(e as Error).message}`);
  } finally {
    clearTimeout(t);
  }
}

/** Returns canned objects in order (the last repeats). Ignores the prompt. Tests + `off` provider. */
export class CannedClient implements LLMClient {
  private i = 0;
  constructor(private readonly responses: Record<string, any>[]) {
    if (responses.length === 0) throw new Error('CannedClient needs at least one response');
  }
  async complete(): Promise<Record<string, any>> {
    const resp = this.responses[Math.min(this.i, this.responses.length - 1)];
    this.i += 1;
    return resp;
  }
}

/** Local Ollama chat with structured output (`format` = JSON schema), temperature 0. */
export class OllamaClient implements LLMClient {
  constructor(
    private readonly baseUrl: string,
    private readonly model: string,
    private readonly opts: { temperature?: number; timeoutMs?: number } = {},
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  async complete(args: { system: string; user: string; schema: object }): Promise<Record<string, any>> {
    const payload = {
      model: this.model,
      messages: [
        { role: 'system', content: args.system },
        { role: 'user', content: args.user },
      ],
      stream: false,
      format: args.schema,
      options: { temperature: this.opts.temperature ?? 0 },
    };
    const body = await fetchJson(
      `${this.baseUrl}/api/chat`,
      { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) },
      this.opts.timeoutMs ?? 30_000,
      'Ollama /api/chat',
    );
    const content = body?.message?.content ?? '';
    let obj: any;
    try {
      obj = JSON.parse(content);
    } catch {
      throw new LLMError(`Ollama returned non-JSON content: ${String(content).slice(0, 200)}`);
    }
    if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
      throw new LLMError('Ollama returned a non-object claim');
    }
    return obj;
  }
}

/**
 * Anthropic Messages API fallback. Forces the `emit_action_claim` tool so the model must return
 * a schema-valid tool input. Raw fetch mirrors the Python httpx client (anthropic-version header,
 * tool_choice: {type:"tool"}).
 */
export class ClaudeClient implements LLMClient {
  private static readonly TOOL_NAME = 'emit_action_claim';

  constructor(
    private readonly model: string,
    private readonly apiKey: string,
    private readonly opts: { baseUrl?: string; timeoutMs?: number; maxTokens?: number } = {},
  ) {
    if (!apiKey) throw new LLMError('ClaudeClient requires MAISHA_CLAUDE_API_KEY');
    this.opts.baseUrl = (opts.baseUrl ?? 'https://api.anthropic.com').replace(/\/+$/, '');
  }

  async complete(args: { system: string; user: string; schema: object }): Promise<Record<string, any>> {
    const payload = {
      model: this.model,
      max_tokens: this.opts.maxTokens ?? 2048,
      system: args.system,
      messages: [{ role: 'user', content: args.user }],
      tools: [
        {
          name: ClaudeClient.TOOL_NAME,
          description: 'Emit the structured ActionClaim for this query.',
          input_schema: args.schema,
        },
      ],
      tool_choice: { type: 'tool', name: ClaudeClient.TOOL_NAME },
    };
    const body = await fetchJson(
      `${this.opts.baseUrl}/v1/messages`,
      {
        method: 'POST',
        headers: {
          'x-api-key': this.apiKey,
          'anthropic-version': '2023-06-01',
          'content-type': 'application/json',
        },
        body: JSON.stringify(payload),
      },
      this.opts.timeoutMs ?? 30_000,
      'Claude /v1/messages',
    );
    for (const block of body?.content ?? []) {
      if (block?.type === 'tool_use' && block?.name === ClaudeClient.TOOL_NAME) {
        if (block.input && typeof block.input === 'object') return block.input;
      }
    }
    throw new LLMError('Claude response had no emit_action_claim tool_use block');
  }
}

/** Construct the client for the configured provider (env-driven). `off` → a CannedClient that abstains. */
export function buildClient(): LLMClient {
  const provider = process.env.MAISHA_LLM_PROVIDER ?? 'off';
  const temperature = Number(process.env.MAISHA_LLM_TEMPERATURE ?? 0);
  const timeoutMs = Number(process.env.MAISHA_LLM_TIMEOUT_MS ?? 30_000);
  if (provider === 'ollama') {
    return new OllamaClient(
      process.env.MAISHA_OLLAMA_URL ?? 'http://127.0.0.1:11434',
      process.env.MAISHA_OLLAMA_MODEL ?? 'qwen3:14b',
      { temperature, timeoutMs },
    );
  }
  if (provider === 'claude') {
    return new ClaudeClient(
      process.env.MAISHA_CLAUDE_MODEL ?? 'claude-opus-4-8',
      process.env.MAISHA_CLAUDE_API_KEY ?? '',
      { baseUrl: process.env.MAISHA_CLAUDE_BASE_URL, timeoutMs },
    );
  }
  if (provider === 'off') return new CannedClient([{ domain: '', abstained: true }]);
  throw new LLMError(`unknown MAISHA_LLM_PROVIDER: ${provider}`);
}
