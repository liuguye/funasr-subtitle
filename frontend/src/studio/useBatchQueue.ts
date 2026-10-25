// 队列在浏览器里串行提交：上一件 done / error / cancelled 之后才发下一件。
// 真正的转写仍走后端那一个 worker。

import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelJob,
  subscribeJob,
  SubtitleApiError,
  type WsHandle,
} from "../api";
import { createOutputJob, resolveLocalMedia, type ResolvedPath } from "./api";
import { newKey, pathFromFile } from "./paths";
import type { JobWithOutput, QueueItem, RunOptions } from "./types";

type Notice = (level: "success" | "info" | "warning" | "error", text: string) => void;

function blank(partial: Pick<QueueItem, "key" | "name" | "file" | "sourcePath">): QueueItem {
  return {
    ...partial,
    pathState: "empty",
    pathMessage: "",
    status: "waiting",
    percent: 0,
    stage: null,
    job: null,
    error: null,
    detail: null,
    writtenFiles: [],
    writeError: null,
    outputNote: "",
  };
}

function applyResolved(item: QueueItem, row: ResolvedPath | undefined): QueueItem {
  if (!item.sourcePath.trim()) {
    return { ...item, pathState: "empty", pathMessage: "", sourcePath: "" };
  }
  if (!row || !row.exists || !row.path) {
    return {
      ...item,
      pathState: "bad",
      pathMessage: row?.error || "找不到这个文件",
    };
  }
  return {
    ...item,
    sourcePath: row.path,
    name: item.file ? item.name : row.name || item.name,
    pathState: "ok",
    pathMessage: "完成后写到这个文件旁边",
  };
}

export function useBatchQueue(getOptions: () => RunOptions, notify: Notice) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [running, setRunning] = useState(false);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const itemsRef = useRef<QueueItem[]>([]);
  const runningRef = useRef(false);
  const stopRef = useRef(false);
  const activeKeyRef = useRef<string | null>(null);
  const wsRef = useRef<WsHandle | null>(null);
  const getOptionsRef = useRef(getOptions);
  const notifyRef = useRef(notify);
  getOptionsRef.current = getOptions;
  notifyRef.current = notify;

  const commit = useCallback((next: QueueItem[]) => {
    itemsRef.current = next;
    setItems(next);
  }, []);

  const update = useCallback((key: string, patch: Partial<QueueItem>) => {
    commit(itemsRef.current.map((it) => (it.key === key ? { ...it, ...patch } : it)));
  }, [commit]);

  useEffect(() => () => wsRef.current?.close(), []);

  const confirmPaths = useCallback(async (keys: string[]) => {
    const current = itemsRef.current.filter((it) => keys.includes(it.key) && it.sourcePath.trim());
    if (current.length === 0) return;
    try {
      const res = await resolveLocalMedia({
        paths: current.map((it) => it.sourcePath.trim()),
        expand: false,
      });
      if (res.truncated) notifyRef.current("warning", "路径太多，只核对了前面一部分");
      const byKey = new Map<string, ResolvedPath>();
      current.forEach((it, i) => byKey.set(it.key, res.items[i]));
      commit(itemsRef.current.map((it) => (byKey.has(it.key) ? applyResolved(it, byKey.get(it.key)) : it)));
    } catch (e) {
      const text = e instanceof SubtitleApiError ? e.message : "路径没核对成";
      notifyRef.current("error", text);
    }
  }, [commit]);

  const addFiles = useCallback((files: File[]) => {
    if (files.length === 0) return;
    const existing = itemsRef.current;
    const fresh: QueueItem[] = [];
    let skipped = 0;
    for (const file of files) {
      const dup = existing.concat(fresh).some((it) => {
        if (it.file && it.file.name === file.name && it.file.size === file.size && it.file.lastModified === file.lastModified) {
          return true;
        }
        return false;
      });
      if (dup) {
        skipped += 1;
        continue;
      }
      fresh.push(blank({
        key: newKey(),
        name: file.name,
        file,
        sourcePath: pathFromFile(file),
      }));
    }
    if (fresh.length === 0) {
      if (skipped) notifyRef.current("info", "这些文件已经在队列里");
      return;
    }
    commit([...itemsRef.current, ...fresh]);
    const withPath = fresh.filter((it) => it.sourcePath.trim()).map((it) => it.key);
    if (withPath.length) void confirmPaths(withPath);
    if (skipped) notifyRef.current("info", `已加入 ${fresh.length} 个，跳过 ${skipped} 个重复的`);
  }, [commit, confirmPaths]);

  const addPathText = useCallback(async (text: string) => {
    const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (lines.length === 0) {
      notifyRef.current("info", "先贴上路径，一行一个");
      return;
    }
    let res;
    try {
      res = await resolveLocalMedia({ paths: lines });
    } catch (e) {
      notifyRef.current("error", e instanceof SubtitleApiError ? e.message : "路径没核对成");
      return;
    }
    if (res.truncated) notifyRef.current("warning", "只加入了前 300 个");
    const known = new Set(
      itemsRef.current.map((it) => it.sourcePath).filter(Boolean),
    );
    const fresh: QueueItem[] = [];
    const problems: string[] = [];
    for (const row of res.items) {
      if (!row.exists || !row.path) {
        if (row.error) problems.push(row.error);
        continue;
      }
      if (known.has(row.path)) continue;
      known.add(row.path);
      const item = blank({ key: newKey(), name: row.name || row.path, file: null, sourcePath: row.path });
      fresh.push({ ...item, pathState: "ok", pathMessage: "完成后写到这个文件旁边" });
    }
    if (fresh.length) commit([...itemsRef.current, ...fresh]);
    if (problems.length) {
      const head = problems.slice(0, 3).join("；");
      notifyRef.current("warning", fresh.length ? `有 ${problems.length} 条没加进去：${head}` : head);
    } else if (fresh.length === 0) {
      notifyRef.current("info", "没有新的文件可加入");
    } else {
      notifyRef.current("success", `已加入 ${fresh.length} 个`);
    }
  }, [commit]);

  const applyDirectory = useCallback(async (directory: string) => {
    const dir = directory.trim();
    if (!dir) {
      notifyRef.current("info", "先填媒体所在的文件夹");
      return;
    }
    const pending = itemsRef.current.filter((it) => it.file && !it.sourcePath.trim());
    if (pending.length === 0) {
      notifyRef.current("info", "队列里没有还缺路径的文件");
      return;
    }
    let res;
    try {
      res = await resolveLocalMedia({ directory: dir, names: pending.map((it) => it.name) });
    } catch (e) {
      notifyRef.current("error", e instanceof SubtitleApiError ? e.message : "文件夹没核对成");
      return;
    }
    const byKey = new Map<string, ResolvedPath>();
    pending.forEach((it, i) => {
      const row = res.items[i];
      if (row) byKey.set(it.key, row);
    });
    let ok = 0;
    commit(itemsRef.current.map((it) => {
      const row = byKey.get(it.key);
      if (!row) return it;
      const next = applyResolved({ ...it, sourcePath: row.path || it.sourcePath }, row);
      if (next.pathState === "ok") ok += 1;
      return next.pathState === "ok" ? next : { ...it, sourcePath: dir.replace(/[\\/]+$/, "") + "/" + it.name, pathState: "bad", pathMessage: row.error || "这个文件夹里没有同名文件" };
    }));
    notifyRef.current(ok ? "success" : "warning", ok ? `补上了 ${ok} 个路径` : "没有对上同名文件");
  }, [commit]);

  const setPath = useCallback((key: string, sourcePath: string) => {
    update(key, { sourcePath, pathState: "empty", pathMessage: "" });
  }, [update]);

  const commitPath = useCallback((key: string) => {
    const item = itemsRef.current.find((it) => it.key === key);
    if (!item) return;
    if (!item.sourcePath.trim()) {
      update(key, { sourcePath: "", pathState: "empty", pathMessage: "" });
      return;
    }
    void confirmPaths([key]);
  }, [confirmPaths, update]);

  const move = useCallback((key: string, dir: -1 | 1) => {
    const list = itemsRef.current;
    const index = list.findIndex((it) => it.key === key);
    const target = index + dir;
    if (index < 0 || target < 0 || target >= list.length) return;
    if (list[index].status === "running" || list[target].status === "running") return;
    const next = list.slice();
    const [row] = next.splice(index, 1);
    next.splice(target, 0, row);
    commit(next);
  }, [commit]);

  const remove = useCallback(async (key: string) => {
    const item = itemsRef.current.find((it) => it.key === key);
    if (item?.status === "running" && item.job) {
      try { await cancelJob(item.job.id); } catch { /* 队列会在取消事件里收口 */ }
    }
    commit(itemsRef.current.filter((it) => it.key !== key));
  }, [commit]);

  const clearFinished = useCallback(() => {
    commit(itemsRef.current.filter((it) => it.status !== "done" && it.status !== "cancelled"));
  }, [commit]);

  const runOne = useCallback(async (key: string, opts: RunOptions) => {
    const item = itemsRef.current.find((it) => it.key === key);
    if (!item || item.status !== "waiting") return;

    let sourcePath = item.sourcePath.trim();
    if (sourcePath) {
      try {
        const checked = await resolveLocalMedia({ paths: [sourcePath], expand: false });
        const row = checked.items[0];
        const next = applyResolved({ ...item, sourcePath }, row);
        update(key, { sourcePath: next.sourcePath, pathState: next.pathState, pathMessage: next.pathMessage });
        if (next.pathState !== "ok") {
          update(key, {
            status: "error",
            error: item.file
              ? "路径不对，这一条没有开始。清空路径可以只在页面里出字幕，或改成正确的绝对路径。"
              : (next.pathMessage || "找不到这个文件"),
          });
          return;
        }
        sourcePath = next.sourcePath;
      } catch (e) {
        update(key, {
          status: "error",
          error: e instanceof SubtitleApiError ? e.message : "路径没核对成",
        });
        return;
      }
    } else if (!item.file) {
      update(key, { status: "error", error: "没有文件，也没有本机路径" });
      return;
    }

    update(key, {
      status: "running",
      percent: 0,
      stage: null,
      error: null,
      detail: null,
      job: null,
      writtenFiles: [],
      writeError: null,
      outputNote: "",
    });
    activeKeyRef.current = key;
    setActiveKey(key);

    await new Promise<void>((resolve) => {
      let settled = false;
      const finish = (patch: Partial<QueueItem>) => {
        if (settled) return;
        settled = true;
        wsRef.current?.close();
        wsRef.current = null;
        update(key, patch);
        resolve();
      };
      void (async () => {
        try {
          const { job_id } = await createOutputJob(sourcePath ? null : item.file, sourcePath, opts);
          const placeholder: JobWithOutput = {
            id: job_id,
            filename: item.name,
            status: "queued",
            percent: 0,
            options: {
              model_id: opts.modelId,
              language: opts.language,
              diarization: opts.diarization,
              hotwords: opts.hotwords,
              use_gpu: opts.useGpu,
              max_chars: opts.maxChars,
              punctuation: opts.punctuation,
            },
            segments: [],
            created_at: new Date().toISOString(),
          };
          update(key, { job: placeholder });
          wsRef.current = subscribeJob(job_id, {
            onEvent: (ev) => {
              if (ev.type === "progress") {
                update(key, { stage: ev.stage, percent: ev.percent });
              } else if (ev.type === "done") {
                const job = ev.job as JobWithOutput;
                finish({
                  status: "done",
                  percent: 100,
                  stage: "assembling",
                  job,
                  writtenFiles: job.written_files ?? [],
                  writeError: job.write_error ?? null,
                  outputNote: job.output_note ?? "",
                });
              } else if (ev.type === "error") {
                if (ev.code === "cancelled") {
                  finish({ status: "cancelled", percent: 0, stage: null, job: placeholder });
                } else {
                  finish({
                    status: "error",
                    error: ev.message || "转写没完成",
                    detail: ev.detail ?? null,
                  });
                }
              }
            },
            onError: () => finish({ status: "error", error: "连不上后台了，转写中断" }),
            onClose: () => {
              if (!settled) finish({ status: "error", error: "后台断了，请点重试" });
            },
          });
        } catch (e) {
          finish({
            status: "error",
            error: e instanceof SubtitleApiError ? e.message : "任务没发出去，重试一下",
            detail: e instanceof SubtitleApiError ? (e.detail ?? null) : null,
          });
        }
      })();
    });
  }, [update]);

  const start = useCallback(async () => {
    if (runningRef.current) return;
    if (!itemsRef.current.some((it) => it.status === "waiting")) return;
    runningRef.current = true;
    stopRef.current = false;
    setRunning(true);
    const opts = getOptionsRef.current();
    try {
      while (!stopRef.current) {
        const next = itemsRef.current.find((it) => it.status === "waiting");
        if (!next) break;
        await runOne(next.key, opts);
      }
    } finally {
      runningRef.current = false;
      activeKeyRef.current = null;
      setActiveKey(null);
      setRunning(false);
      stopRef.current = false;
    }
  }, [runOne]);

  const cancelCurrent = useCallback(async (stopAfter: boolean) => {
    if (stopAfter) stopRef.current = true;
    const key = activeKeyRef.current;
    const item = key ? itemsRef.current.find((it) => it.key === key) : undefined;
    if (item?.job && item.status === "running") {
      try { await cancelJob(item.job.id); } catch { /* 界面等 websocket 收口 */ }
    }
  }, []);

  const retry = useCallback((key: string) => {
    const item = itemsRef.current.find((it) => it.key === key);
    if (!item || item.status === "running") return;
    update(key, {
      status: "waiting",
      percent: 0,
      stage: null,
      error: null,
      detail: null,
      job: null,
      writtenFiles: [],
      writeError: null,
      outputNote: "",
    });
    if (!runningRef.current) void start();
  }, [start, update]);

  return {
    items,
    running,
    activeKey,
    addFiles,
    addPathText,
    applyDirectory,
    setPath,
    commitPath,
    move,
    remove,
    clearFinished,
    start,
    cancelCurrent,
    retry,
  };
}
