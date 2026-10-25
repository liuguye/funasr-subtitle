// 浏览器 File 一般没有绝对路径。Electron / 部分本地壳会在 file.path 上带一份。

export function pathFromFile(file: File): string {
  const maybe = (file as File & { path?: string }).path;
  if (typeof maybe !== "string") return "";
  const text = maybe.trim();
  if (!text || text.startsWith("blob:")) return "";
  const windows = /^[A-Za-z]:[\\/]/.test(text);
  const unc = text.startsWith("\\\\");
  const posix = text.startsWith("/");
  return windows || unc || posix ? text : "";
}

export function newKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `q-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
