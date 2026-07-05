/** User accounts, credentials, and MFA. Break-glass bootstrap admin from MAISHA_APP_PASSWORD. */
import { BadRequestException, Injectable, Logger, OnModuleInit, UnauthorizedException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { User } from '../common/shared.entities';
import { hashPassword, normalizeRole, randomTotpSecret, Role, totpUri, verifyPasswordHash, verifyTotp } from './auth';

export interface AuthedUser {
  id: string;
  role: Role;
}

@Injectable()
export class UsersService implements OnModuleInit {
  private readonly log = new Logger('auth.users');

  constructor(@InjectRepository(User) private readonly repo: Repository<User>) {}

  /** Seed a break-glass admin from the env password if there are no users yet. */
  async onModuleInit(): Promise<void> {
    const count = await this.repo.count().catch(() => 0);
    const pw = process.env.MAISHA_APP_PASSWORD;
    if (count === 0 && pw) {
      const email = process.env.MAISHA_ADMIN_EMAIL ?? 'admin@maisha.local';
      await this.repo.save(this.repo.create({ email, name: 'Bootstrap Admin', role: 'admin', password_hash: hashPassword(pw), active: 1 }));
      this.log.log(`seeded bootstrap admin '${email}' from MAISHA_APP_PASSWORD`);
    }
  }

  /** Verify email + password (+ TOTP when MFA is on). Returns the authed identity or throws 401. */
  async verifyLogin(email: string, password: string, totp?: string): Promise<AuthedUser> {
    const user = await this.repo.findOne({ where: { email: email.toLowerCase().trim() } });
    if (!user || !user.active || !user.password_hash || !verifyPasswordHash(password, user.password_hash)) {
      throw new UnauthorizedException('invalid credentials');
    }
    if (user.mfa_enabled) {
      if (!totp || !user.mfa_secret || !verifyTotp(user.mfa_secret, totp)) throw new UnauthorizedException('invalid or missing MFA code');
    }
    return { id: user.id, role: normalizeRole(user.role) };
  }

  async create(input: { email: string; password: string; role?: string; name?: string }): Promise<{ id: string; email: string; role: string }> {
    const email = input.email.toLowerCase().trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new BadRequestException('invalid email');
    if ((input.password ?? '').length < 8) throw new BadRequestException('password must be at least 8 characters');
    if (await this.repo.findOne({ where: { email } })) throw new BadRequestException('email already exists');
    const role = normalizeRole(input.role ?? 'viewer');
    const u = await this.repo.save(this.repo.create({ email, name: input.name ?? null, role, password_hash: hashPassword(input.password), active: 1 }));
    return { id: u.id, email: u.email, role: u.role };
  }

  async list(): Promise<Array<{ id: string; email: string; role: string; active: number; mfa: boolean }>> {
    const rows = await this.repo.find({ order: { created_at: 'ASC' } });
    return rows.map((u) => ({ id: u.id, email: u.email, role: normalizeRole(u.role), active: u.active, mfa: !!u.mfa_enabled }));
  }

  async update(id: string, patch: { role?: string; active?: boolean }): Promise<{ id: string; role: string; active: number }> {
    const u = await this.repo.findOne({ where: { id } });
    if (!u) throw new BadRequestException('unknown user');
    if (patch.role != null) u.role = normalizeRole(patch.role);
    if (patch.active != null) u.active = patch.active ? 1 : 0;
    await this.repo.save(u);
    return { id: u.id, role: u.role, active: u.active };
  }

  /** Start MFA enrollment: store a secret and return the otpauth URI to scan. */
  async beginMfa(id: string): Promise<{ secret: string; otpauth_uri: string }> {
    const u = await this.repo.findOne({ where: { id } });
    if (!u) throw new BadRequestException('unknown user');
    const secret = randomTotpSecret();
    u.mfa_secret = secret;
    u.mfa_enabled = 0; // not active until a code is confirmed
    await this.repo.save(u);
    return { secret, otpauth_uri: totpUri(secret, u.email) };
  }

  /** Confirm enrollment with a code from the authenticator, then activate MFA. */
  async confirmMfa(id: string, totp: string): Promise<{ mfa_enabled: boolean }> {
    const u = await this.repo.findOne({ where: { id } });
    if (!u || !u.mfa_secret) throw new BadRequestException('start enrollment first');
    if (!verifyTotp(u.mfa_secret, totp)) throw new BadRequestException('code did not verify');
    u.mfa_enabled = 1;
    await this.repo.save(u);
    return { mfa_enabled: true };
  }

  async byId(id: string): Promise<User | null> {
    return this.repo.findOne({ where: { id } });
  }
}
