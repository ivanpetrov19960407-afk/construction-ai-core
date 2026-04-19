export type GSNSectionCode = "AR" | "KZH" | "KM" | "OV" | "VK" | "EM";

export interface GSNSectionStatus {
  section: GSNSectionCode | string;
  completion_pct: number;
  missing: string[];
  present: string[];
}

export interface GSNChecklist {
  project_id?: string;
  completion_pct: number;
  sections: GSNSectionStatus[];
}

export interface ScheduleRisk {
  title: string;
  level: "high" | "medium" | "low" | string;
  details?: string;
}

export interface ScheduleForecast {
  predicted_completion: string;
  avg_delay_days: number;
  delay_rate: number;
  risks: ScheduleRisk[];
  recommendations: string[];
}

export type SignStatus = "draft" | "approved" | "signed";
