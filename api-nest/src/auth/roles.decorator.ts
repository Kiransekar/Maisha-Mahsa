import { SetMetadata } from '@nestjs/common';

import { Role } from './auth';

export const ROLES_KEY = 'roles';
/** Restrict a route/controller to specific roles (overrides the method-based default). */
export const Roles = (...roles: Role[]) => SetMetadata(ROLES_KEY, roles);
