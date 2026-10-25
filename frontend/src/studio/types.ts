// 批量队列用的前端类型。后端 Job 模型没加字段，写盘结果是 done 载荷上多出来的键。

import type { ExportFormat, Job, Language, Stage } from "../types";

export type QueueStatus = "waiting" | "running" | "done" | "error" | "cancelled";

export type PathState = "empty" | "ok" | "bad";

export interface JobWithOutput extends Job {
  source_path?: string | null;
  written_files?: string[];
  write_error?: string | null;
  output_note?: string | null;
}

export interface QueueItem {
  key: string;
  name: string;
  file: File | null;
  sourcePath: string;
  pathState: PathState;
  pathMessage: string;
  status: QueueStatus;
  percent: number;
  stage: Stage | null;
  job: JobWithOutput | null;
  error: string | null;
  detail: string | null;
  writtenFiles: string[];
  writeError: string | null;
  outputNote: string;
}

export interface RunOptions {
  modelId: string;
  language: Language;
  diarization: boolean;
  hotwords: string;
  useGpu: boolean;
  maxChars: number;
  punctuation: "auto" | "on" | "off";
  exportFormats: ExportFormat[];
}

export const QUEUE_STATUS_LABEL: Record<QueueStatus, string> = {
  waiting: "等待",
  running: "转写中",
  done: "完成",
  error: "失败",
  cancelled: "已取消",
};
