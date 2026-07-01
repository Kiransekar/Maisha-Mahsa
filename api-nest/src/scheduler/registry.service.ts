/**
 * Domain registry: discovers every SnapshotProducer (the 12 domain services) at runtime via
 * Nest's DiscoveryService, so the scheduler/CFO jobs iterate all domains without per-module
 * wiring. Replaces the Python DomainRouter for the jobs' purposes.
 */
import { Injectable, OnModuleInit } from '@nestjs/common';
import { DiscoveryService } from '@nestjs/core';

import { SnapshotProducer } from '../core/loop.service';

function isSnapshotProducer(x: any): x is SnapshotProducer {
  return x && typeof x.domain === 'string' && typeof x.buildSnapshot === 'function';
}

@Injectable()
export class DomainRegistry implements OnModuleInit {
  private services: SnapshotProducer[] = [];

  constructor(private readonly discovery: DiscoveryService) {}

  onModuleInit(): void {
    const found = new Map<string, SnapshotProducer>();
    for (const wrapper of this.discovery.getProviders()) {
      const instance = wrapper.instance;
      if (isSnapshotProducer(instance)) found.set(instance.domain, instance);
    }
    // Stable order by domain name.
    this.services = [...found.values()].sort((a, b) => a.domain.localeCompare(b.domain));
  }

  all(): SnapshotProducer[] {
    return this.services;
  }

  get(domain: string): SnapshotProducer | undefined {
    return this.services.find((s) => s.domain === domain);
  }

  domains(): string[] {
    return this.services.map((s) => s.domain);
  }
}
