export type Mode = 'redact' | 'placeholder' | 'synthetic';
export type OutputFormat = 'pdf' | 'docx' | 'txt';
export type DocumentResult = {
  id: string;
  created: string;
  filename?: string | null;
  mode: Mode;
  status: 'queued' | 'processing' | 'complete' | 'failed';
  counts: Record<string, number>;
  sensitivity: number;
  source_type?: string;
  layout_preserved?: boolean;
  expires_at?: string | null;
  error?: string | null;
  warning?: string | null;
};
export type GuestState = { document: DocumentResult | null; csrf_token: string; expires_at: string | null };
export type ConcealedDetection = { category: string; occurrence: number; replacement: string };
export type ScanReport = {
  sensitivity: number;
  counts: Record<string, number>;
  total_detections: number;
  source_type: string;
  layout_preserved: boolean;
  ocr_performed: boolean;
  warnings: string[];
  limitations: string[];
};
export type RevealedDetection = { category: string; occurrence: number; original: string };
export type DetectionReview = { detections: ConcealedDetection[]; scan_report: ScanReport };
export const modeLabels: Record<Mode, [string, string]> = {
  redact: ['Mask', 'Masked'], placeholder: ['Label', 'Labelled'], synthetic: ['Replace', 'Replaced'],
};
export const categoryLabels: Record<string, string> = {
  private_person: 'Names', private_address: 'Addresses', private_email: 'Emails',
  private_phone: 'Phone numbers', private_date: 'Dates', private_url: 'URLs',
  account_number: 'Accounts', secret: 'Secrets',
};
