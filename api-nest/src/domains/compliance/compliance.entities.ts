/**
 * Compliance uses only the shared `compliance_calendar` table (PRD §3.10) — no domain-local
 * tables. Re-export it so the module can register it via TypeOrmModule.forFeature.
 */
export { ComplianceCalendar } from '../../common/shared.entities';
