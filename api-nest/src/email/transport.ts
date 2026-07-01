/**
 * Email transports. Faithful port of api/app/core/email/transport.py. The transport is the
 * network boundary — tests/dev use InMemoryTransport; production uses SmtpTransport (nodemailer,
 * imported lazily so the dependency is only needed when actually dispatching).
 */

export interface SentMessage {
  to: string;
  subject: string;
  html: string;
}

export interface Transport {
  send(args: { to: string; subject: string; html: string; sender: string }): Promise<void>;
}

/** Captures sent messages instead of dispatching — for tests and dry runs. */
export class InMemoryTransport implements Transport {
  readonly sent: SentMessage[] = [];
  async send(args: { to: string; subject: string; html: string; sender: string }): Promise<void> {
    this.sent.push({ to: args.to, subject: args.subject, html: args.html });
  }
}

export interface SmtpConfig {
  host: string;
  port: number;
  username?: string | null;
  password?: string | null;
  useTls?: boolean;
}

/** Sends via SMTP using nodemailer (lazy import). */
export class SmtpTransport implements Transport {
  constructor(private readonly cfg: SmtpConfig) {}

  async send(args: { to: string; subject: string; html: string; sender: string }): Promise<void> {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const nodemailer = require('nodemailer');
    const transporter = nodemailer.createTransport({
      host: this.cfg.host,
      port: this.cfg.port,
      secure: this.cfg.useTls ?? false,
      auth: this.cfg.username ? { user: this.cfg.username, pass: this.cfg.password ?? '' } : undefined,
    });
    await transporter.sendMail({
      from: args.sender,
      to: args.to,
      subject: args.subject,
      text: 'This message requires an HTML-capable client.',
      html: args.html,
    });
  }
}

/** Build a transport from env. Defaults to InMemory unless MAISHA_SMTP_ENABLED=true. */
export function buildTransport(): Transport {
  if (process.env.MAISHA_SMTP_ENABLED !== 'true') return new InMemoryTransport();
  return new SmtpTransport({
    host: process.env.MAISHA_SMTP_HOST ?? '127.0.0.1',
    port: Number(process.env.MAISHA_SMTP_PORT ?? 1025),
    username: process.env.MAISHA_SMTP_USERNAME || null,
    password: process.env.MAISHA_SMTP_PASSWORD || null,
    useTls: process.env.MAISHA_SMTP_USE_TLS === 'true',
  });
}
