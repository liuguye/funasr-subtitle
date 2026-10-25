// 批量队列专用接口。单文件上传仍可走这里：没有 source_path 时只上传，不写盘。

import { SubtitleApiError, type ApiError } from "../api";
import type { RunOptions } from "./types";

export interface ResolvedPath {
  input: string;
  path: string;
  name: string;
  exists: boolean;
  error: string | null;
}

export interface ResolveResponse {
  items: ResolvedPath[];
  truncated: boolean;
}

async function parseError(res: Response): Promise<never> {
  let code = `http_${res.status}`;
  let message = res.statusText || "请求失败";
  let detail: string | undefined;
  try {
    const body = await res.json();
    if (body && body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      detail = body.error.detail;
    }
  } catch {
    // 非 JSON
  }
  const err: ApiError = { code, message, detail };
  throw new SubtitleApiError(err);
}

export interface PickResponse {
  paths: string[];
  cancelled: boolean;
  truncated: boolean;
}

export function pickLocalMedia(mode: "files" | "directory"): Promise<PickResponse> {
  return fetch("/api/local-media/pick", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  }).then(async (res) => {
    if (!res.ok) return parseError(res);
    return res.json() as Promise<PickResponse>;
  });
}

export function resolveLocalMedia(body: {
  paths?: string[];
  directory?: string;
  names?: string[];
  expand?: boolean;
}): Promise<ResolveResponse> {
  return fetch("/api/local-media/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      paths: body.paths ?? [],
      directory: body.directory ?? "",
      names: body.names ?? [],
      expand: body.expand ?? true,
    }),
  }).then(async (res) => {
    if (!res.ok) return parseError(res);
    return res.json() as Promise<ResolveResponse>;
  });
}

export async function createOutputJob(
  file: File | null,
  sourcePath: string,
  opts: RunOptions,
): Promise<{ job_id: string }> {
  const form = new FormData();
  if (file) form.append("file", file);
  if (sourcePath) form.append("source_path", sourcePath);
  form.append("export_formats", opts.exportFormats.join(","));
  if (opts.modelId) form.append("model_id", opts.modelId);
  form.append("language", opts.language);
  form.append("diarization", opts.diarization ? "true" : "false");
  form.append("hotwords", opts.hotwords);
  form.append("use_gpu", opts.useGpu ? "true" : "false");
  form.append("max_chars", String(opts.maxChars));
  form.append("punctuation", opts.punctuation);

  const res = await fetch("/api/jobs/local", { method: "POST", body: form });
  if (!res.ok) return parseError(res);
  return res.json() as Promise<{ job_id: string }>;
}
