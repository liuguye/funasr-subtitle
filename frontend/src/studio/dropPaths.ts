// 从拖放事件里尽量取出本机绝对路径。
// Chrome / Edge 通常不给路径；资源管理器有时会在 text/uri-list 里放 file://。
// Electron 等壳会把路径放在 File.path 上，那部分由 pathFromFile 读取。

import { isMediaName } from "./media";

const MAX_DROP = 300;

type EntryItem = DataTransferItem & {
  webkitGetAsEntry?: () => FileSystemEntry | null;
};

function fileUrlToPath(line: string): string {
  const text = line.trim().replace(/^["']|["']$/g, "");
  if (!text || text.startsWith("#")) return "";
  if (/^[A-Za-z]:[\\/]/.test(text) || text.startsWith("\\\\")) return text;
  if (text.startsWith("/") && !text.toLowerCase().startsWith("/http")) return text;
  if (!text.toLowerCase().startsWith("file:")) return "";
  try {
    const url = new URL(text);
    let path = decodeURIComponent(url.pathname);
    const host = url.hostname;
    if (host && host.toLowerCase() !== "localhost") {
      return `\\\\${host}${path.replace(/\//g, "\\")}`;
    }
    if (/^\/[A-Za-z]:\//.test(path)) path = path.slice(1);
    if (/^[A-Za-z]:[\\/]/.test(path) || path.startsWith("/")) return path;
    return "";
  } catch {
    return "";
  }
}

export function pathsFromDrop(dt: DataTransfer | null): string[] {
  if (!dt) return [];
  let raw = "";
  try {
    raw = `${dt.getData("text/uri-list")}\n${dt.getData("text/plain")}`;
  } catch {
    raw = "";
  }
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const path = fileUrlToPath(line);
    if (!path || seen.has(path)) continue;
    seen.add(path);
    out.push(path);
  }
  return out;
}

function readAll(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const all: FileSystemEntry[] = [];
    const next = () => {
      reader.readEntries((batch) => {
        if (!batch.length) {
          resolve(all);
          return;
        }
        all.push(...batch);
        next();
      }, reject);
    };
    next();
  });
}

function fileOf(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function collect(entry: FileSystemEntry, out: File[], nested: boolean): Promise<void> {
  if (out.length >= MAX_DROP) return;
  if (nested && entry.name.startsWith(".")) return;
  if (entry.isFile) {
    if (nested && !isMediaName(entry.name)) return;
    out.push(await fileOf(entry as FileSystemFileEntry));
    return;
  }
  if (!entry.isDirectory) return;
  const children = await readAll((entry as FileSystemDirectoryEntry).createReader());
  for (const child of children) {
    await collect(child, out, true);
    if (out.length >= MAX_DROP) return;
  }
}

export async function filesFromDrop(dt: DataTransfer | null): Promise<File[]> {
  if (!dt) return [];
  const entries: FileSystemEntry[] = [];
  for (const item of Array.from(dt.items ?? [])) {
    const entry = (item as EntryItem).webkitGetAsEntry?.() ?? null;
    if (entry) entries.push(entry);
  }
  if (entries.length === 0) return Array.from(dt.files ?? []).slice(0, MAX_DROP);
  const out: File[] = [];
  try {
    for (const entry of entries) {
      await collect(entry, out, false);
      if (out.length >= MAX_DROP) break;
    }
  } catch {
    if (out.length === 0) return Array.from(dt.files ?? []).slice(0, MAX_DROP);
  }
  return out.length ? out : Array.from(dt.files ?? []).slice(0, MAX_DROP);
}
