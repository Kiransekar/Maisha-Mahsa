import 'reflect-metadata';
import { ValidationPipe, Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

import { AppModule } from './app.module';
import { assertProductionSecrets, DEFAULT_PASSWORD, DEFAULT_SESSION_SECRET } from './auth/auth';

async function bootstrap() {
  // Fail fast: refuse to boot in production with the shipped default secrets (P1-SECRETS).
  assertProductionSecrets({
    environment: process.env.MAISHA_ENVIRONMENT ?? 'development',
    appPassword: process.env.MAISHA_APP_PASSWORD ?? DEFAULT_PASSWORD,
    sessionSecret: process.env.MAISHA_SESSION_SECRET ?? DEFAULT_SESSION_SECRET,
  });

  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(new ValidationPipe({ transform: true, whitelist: true }));

  const config = new DocumentBuilder()
    .setTitle('Maisha API')
    .setDescription('Indian startup financial suite — NestJS. Every result validated by Mahsa.')
    .setVersion('4.0.0')
    .build();
  SwaggerModule.setup('docs', app, SwaggerModule.createDocument(app, config));

  const port = Number(process.env.PORT ?? 8000);
  await app.listen(port);
  new Logger('Bootstrap').log(`Maisha API on :${port} — docs at /docs`);
}
bootstrap();
