/** User management (admin-only) + self-service MFA enrollment. */
import { BadRequestException, Body, Controller, Get, Param, Patch, Post } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { IsBoolean, IsIn, IsOptional, IsString, MinLength } from 'class-validator';

import { ROLES } from './auth';
import { currentUser } from './request-context';
import { Roles } from './roles.decorator';
import { UsersService } from './users.service';

class CreateUserDto {
  @IsString() email: string;
  @IsString() @MinLength(8) password: string;
  @IsOptional() @IsIn(ROLES as unknown as string[]) role?: string;
  @IsOptional() @IsString() name?: string;
}
class UpdateUserDto {
  @IsOptional() @IsIn(ROLES as unknown as string[]) role?: string;
  @IsOptional() @IsBoolean() active?: boolean;
}
class TotpDto {
  @IsString() totp: string;
}

@ApiTags('users')
@Controller('api/users')
export class UsersController {
  constructor(private readonly users: UsersService) {}

  @Get()
  @Roles('admin')
  list() {
    return this.users.list();
  }

  @Post()
  @Roles('admin')
  create(@Body() body: CreateUserDto) {
    return this.users.create(body);
  }

  @Patch(':id')
  @Roles('admin')
  update(@Param('id') id: string, @Body() body: UpdateUserDto) {
    return this.users.update(id, body);
  }

  // ---- self-service MFA (any authenticated user enrols their own) ----
  @Post('me/mfa/begin')
  beginMfa() {
    const id = currentUser()?.sub;
    if (!id || id === 'bootstrap') throw new BadRequestException('MFA enrolment requires a real user account (not the bootstrap admin)');
    return this.users.beginMfa(id);
  }

  @Post('me/mfa/confirm')
  confirmMfa(@Body() body: TotpDto) {
    const id = currentUser()?.sub;
    if (!id || id === 'bootstrap') throw new BadRequestException('MFA enrolment requires a real user account');
    return this.users.confirmMfa(id, body.totp);
  }
}
