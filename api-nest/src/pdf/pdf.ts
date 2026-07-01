/**
 * Statutory document PDFs. Port of api/app/core/pdf.py (which used ReportLab). Builders are pure:
 * they take a fully-computed data dict (exact paise, computed upstream by the payroll engine) and
 * return PDF bytes. They never compute money — they only render it (via formatInr).
 */
import { join } from 'path';
import PDFDocument from 'pdfkit';

import { formatInr } from '../common/money';

// DejaVu Sans is bundled (assets/fonts/) because it carries the ₹ glyph (U+20B9) that pdfkit's
// built-in Helvetica lacks. Resolved relative to the compiled file so it works in the container.
const FONT_DIR = join(__dirname, '..', '..', 'assets', 'fonts');
const FONT_REGULAR = join(FONT_DIR, 'DejaVuSans.ttf');
const FONT_BOLD = join(FONT_DIR, 'DejaVuSans-Bold.ttf');

/** A new PDF document with the ₹-capable fonts registered as `body` / `bold`. */
function newDoc(title: string): PDFKit.PDFDocument {
  const doc = new PDFDocument({ size: 'A4', margin: 48, info: { Title: title, Author: 'Maisha-Mahsa' } });
  doc.registerFont('body', FONT_REGULAR);
  doc.registerFont('bold', FONT_BOLD);
  doc.font('body');
  return doc;
}

function toBuffer(doc: PDFKit.PDFDocument): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    doc.on('data', (c: Buffer) => chunks.push(c));
    doc.on('end', () => resolve(Buffer.concat(chunks)));
    doc.on('error', reject);
    doc.end();
  });
}

const inr = (paise: unknown) => formatInr(Math.trunc(Number(paise)));

export interface PayslipData {
  company: string;
  employee_name: string;
  employee_code: string;
  period: string;
  earnings: [string, number][];
  deductions: [string, number][];
  gross: number;
  total_deductions: number;
  net: number;
}

/** Monthly payslip PDF. */
export function payslipPdf(data: PayslipData): Promise<Buffer> {
  const doc = newDoc(`Payslip ${data.period}`);
  doc.font('bold').fontSize(18).text(`${data.company} — Payslip`);
  doc.font('body').moveDown(0.3).fontSize(10).fillColor('#444').text(`${data.employee_name} (${data.employee_code})  ·  ${data.period}`);
  doc.moveDown(1).fillColor('#000');

  const rows = Math.max(data.earnings.length, data.deductions.length);
  doc.font('bold').fontSize(11).text('Earnings', 48, doc.y, { continued: false });
  const startY = doc.y;
  // Two side-by-side columns: earnings (left), deductions (right).
  doc.font('body').fontSize(10);
  for (let i = 0; i < rows; i++) {
    const y = startY + 6 + i * 16;
    const e = data.earnings[i];
    const d = data.deductions[i];
    if (e) doc.text(`${e[0]}`, 48, y).text(inr(e[1]), 200, y, { width: 90, align: 'right' });
    if (d) doc.text(`${d[0]}`, 320, y).text(inr(d[1]), 470, y, { width: 90, align: 'right' });
  }
  const totalsY = startY + 6 + rows * 16 + 8;
  doc.font('bold').fontSize(10.5).text('Gross', 48, totalsY).text(inr(data.gross), 200, totalsY, { width: 90, align: 'right' });
  doc.text('Total deductions', 320, totalsY).text(inr(data.total_deductions), 470, totalsY, { width: 90, align: 'right' });
  doc.font('bold').moveDown(3).fontSize(14).text(`Net pay: ${inr(data.net)}`, 48);
  return toBuffer(doc);
}

export interface Form16Data {
  company: string;
  tan?: string | null;
  employee_name: string;
  pan?: string | null;
  financial_year: string;
  assessment_year: string;
  rows: [string, number][];
  total_tax_deducted: number;
}

/** Form 16 — Part B (salary TDS certificate). */
export function form16Pdf(data: Form16Data): Promise<Buffer> {
  const doc = newDoc(`Form 16 ${data.financial_year}`);
  doc.font('bold').fontSize(16).text('FORM NO. 16 — Part B');
  doc.font('body').moveDown(0.3).fontSize(9).fillColor('#444').text('[See rule 31(1)(a)] · Certificate under section 203 of the Income-tax Act, 1961');
  doc.moveDown(0.8).fillColor('#000').fontSize(10);
  doc.text(`Employer: ${data.company} (TAN: ${data.tan || '—'})`);
  doc.text(`Employee: ${data.employee_name} (PAN: ${data.pan || '—'})`);
  doc.text(`Financial Year: ${data.financial_year}  ·  Assessment Year: ${data.assessment_year}`);
  doc.moveDown(1);

  const startY = doc.y;
  doc.fontSize(10);
  const allRows: [string, number][] = [...data.rows, ['Total tax deducted (TDS)', data.total_tax_deducted]];
  allRows.forEach(([label, amount], i) => {
    const y = startY + i * 18;
    const last = i === allRows.length - 1;
    doc.font(last ? 'bold' : 'body').text(label, 48, y).text(inr(amount), 400, y, { width: 110, align: 'right' });
  });
  doc.font('body').fontSize(9).fillColor('#444').text(
    'This is Part B (salary breakup & tax computation) generated from payroll. Part A (TDS deposited) is issued via TRACES.',
    48,
    startY + allRows.length * 18 + 20,
  );
  return toBuffer(doc);
}
