/** Correlation id + structured access log + request metrics. Plain express middleware (app.use). */
import { randomUUID } from 'crypto';

import { enterRequest } from '../auth/request-context';
import { decInflight, incInflight, recordRequest } from './metrics';

const JSON_LOGS = process.env.MAISHA_LOG_JSON === 'true' || process.env.MAISHA_ENVIRONMENT === 'production';

export function observabilityMiddleware(req: any, res: any, next: () => void): void {
  const requestId = (typeof req.headers['x-request-id'] === 'string' && req.headers['x-request-id']) || randomUUID();
  res.setHeader('x-request-id', requestId);
  enterRequest({ requestId }); // the guard later attaches the user to this same state
  incInflight();
  const start = Date.now();
  res.on('finish', () => {
    const ms = Date.now() - start;
    decInflight();
    recordRequest(req.method, res.statusCode, ms);
    if (JSON_LOGS) {
      // eslint-disable-next-line no-console
      console.log(JSON.stringify({ level: 'info', t: new Date().toISOString(), msg: 'http', requestId, method: req.method, path: req.path, status: res.statusCode, ms }));
    } else {
      // eslint-disable-next-line no-console
      console.log(`${req.method} ${req.path} ${res.statusCode} ${ms}ms [${requestId.slice(0, 8)}]`);
    }
  });
  next();
}
