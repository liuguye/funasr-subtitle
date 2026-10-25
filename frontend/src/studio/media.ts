// 和后端 localfiles.MEDIA_SUFFIXES、原来的拖放区保持同一份接受范围。

export const ACCEPT_MEDIA = [
  "audio/*", "video/*",
  ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".oga", ".opus", ".wma",
  ".aiff", ".aif", ".alac", ".ape", ".wv", ".amr", ".ac3", ".mka", ".caf", ".dts",
  ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".ts", ".m2ts",
  ".mts", ".vob", ".mpg", ".mpeg", ".3gp", ".3g2", ".ogv", ".rmvb", ".asf", ".f4v",
].join(",");

const MEDIA_EXT = new Set(ACCEPT_MEDIA.split(",").filter((item) => item.startsWith(".")));

export function isMediaName(name: string): boolean {
  const dot = name.lastIndexOf(".");
  if (dot < 0) return false;
  return MEDIA_EXT.has(name.slice(dot).toLowerCase());
}
