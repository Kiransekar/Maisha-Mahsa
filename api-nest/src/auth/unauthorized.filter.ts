/** Turn 401s into a login redirect for browser page loads; keep JSON 401 for API/XHR. */
import { ArgumentsHost, Catch, ExceptionFilter, UnauthorizedException } from '@nestjs/common';
import { Request, Response } from 'express';

@Catch(UnauthorizedException)
export class UnauthorizedRedirectFilter implements ExceptionFilter {
  catch(_exc: UnauthorizedException, host: ArgumentsHost): void {
    const ctx = host.switchToHttp();
    const req = ctx.getRequest<Request>();
    const res = ctx.getResponse<Response>();
    const wantsHtml =
      req.method === 'GET' &&
      (req.headers.accept ?? '').includes('text/html') &&
      !req.path.startsWith('/api') &&
      !req.path.startsWith('/docs');
    if (wantsHtml) {
      res.redirect(302, '/login');
      return;
    }
    // Fixed message — don't echo internal exception text back to the client.
    res.status(401).json({ statusCode: 401, message: 'Unauthorized', error: 'Unauthorized' });
  }
}
