import { useState, type DragEvent } from "react";
import { Button, Card, Checkbox, Flex, Input, Typography } from "antd";
import { ArrowDownOutlined, ArrowUpOutlined, AudioOutlined, FolderOpenOutlined } from "@ant-design/icons";
import type { ExportFormat } from "../types";
import { filesFromDrop, pathsFromDrop } from "./dropPaths";
import { pathFromFile } from "./paths";
import { SectionLabel } from "./SectionLabel";
import { QUEUE_STATUS_LABEL, type QueueItem, type QueueStatus } from "./types";

const { Text } = Typography;
const FORMAT_OPTIONS: { label: string; value: ExportFormat }[] = [
  { label: ".srt", value: "srt" },
  { label: ".vtt", value: "vtt" },
  { label: ".txt", value: "txt" },
  { label: ".json", value: "json" },
];

function chipClass(status: QueueStatus): string {
  if (status === "running") return "chip run";
  if (status === "done") return "chip done";
  if (status === "error") return "chip err";
  return "chip";
}

function rowClass(item: QueueItem, selected: boolean): string {
  const tone = item.status === "running"
    ? "run"
    : item.status === "done"
      ? "done"
      : item.status === "error"
        ? "err"
        : item.status === "cancelled"
          ? "cancel"
          : "";
  return `q-row${tone ? ` ${tone}` : ""}${selected ? " picked" : ""}`;
}

function tagFile(file: File, hinted: string): File {
  if (!hinted || pathFromFile(file)) return file;
  try {
    Object.defineProperty(file, "path", { value: hinted, configurable: true });
  } catch {
    (file as File & { path?: string }).path = hinted;
  }
  return file;
}

function baseName(path: string): string {
  const cut = path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || path;
  return cut.toLowerCase();
}

export function BatchQueue({
  items,
  running,
  picking,
  selectedKey,
  exportFormats,
  modelNotDownloaded,
  onSelect,
  onFormats,
  onFiles,
  onPick,
  onPathText,
  onMove,
  onRemove,
  onClear,
  onStart,
  onCancel,
}: {
  items: QueueItem[];
  running: boolean;
  picking: boolean;
  selectedKey: string | null;
  exportFormats: ExportFormat[];
  modelNotDownloaded: boolean;
  onSelect: (key: string) => void;
  onFormats: (formats: ExportFormat[]) => void;
  onFiles: (files: File[]) => void;
  onPick: (mode: "files" | "directory") => void;
  onPathText: (text: string) => void;
  onMove: (key: string, dir: -1 | 1) => void;
  onRemove: (key: string) => void;
  onClear: () => void;
  onStart: () => void;
  onCancel: (stopAfter: boolean) => void;
}) {
  const [pathDraft, setPathDraft] = useState("");
  const [over, setOver] = useState(false);
  const waiting = items.filter((it) => it.status === "waiting").length;
  const missingPath = items.filter((it) => it.status === "waiting" && it.pathState !== "ok").length;
  const finished = items.some((it) => it.status === "done" || it.status === "cancelled");

  let startLabel = "开始转写";
  if (running) startLabel = "正在转写…";
  else if (modelNotDownloaded && waiting > 0) startLabel = waiting > 1 ? `下载并转写（${waiting} 个）` : "下载并转写";
  else if (waiting > 1) startLabel = `开始转写（${waiting} 个）`;

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setOver(false);
    const uris = pathsFromDrop(event.dataTransfer);
    const files = await filesFromDrop(event.dataTransfer);
    const byName = new Map(uris.map((path) => [baseName(path), path]));
    const tagged = files.map((file) => tagFile(file, byName.get(file.name.toLowerCase()) || ""));
    const anyPath = tagged.some((file) => pathFromFile(file));
    if (uris.length && !anyPath) {
      onPathText(uris.join("\n"));
      return;
    }
    if (tagged.length) {
      onFiles(tagged);
      return;
    }
    if (uris.length) onPathText(uris.join("\n"));
  }

  return (
    <Card className="deck-card rise d1" variant="outlined">
      <SectionLabel en="QUEUE">队列</SectionLabel>
      <div
        className={`file-bay${over ? " over" : ""}`}
        onDragEnter={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false);
        }}
        onDrop={(e) => { void handleDrop(e); }}
        onClick={(e) => {
          const target = e.target as HTMLElement;
          if (target.closest("button, a, input, textarea, summary")) return;
          if (!picking) onPick("files");
        }}
      >
        <Flex vertical align="center" gap={10}>
          <span className="eq"><i /><i /><i /><i /><i /></span>
          <Text type="secondary" className="label-hint">
            把音视频拖到这里，或点下面的按钮。可以一次选多个。
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            「选择文件」会打开系统窗口，带上真实路径，字幕直接写在源文件旁边。
          </Text>
          <div className="bay-actions" onClick={(e) => e.stopPropagation()}>
            <Button
              color="primary"
              variant="solid"
              autoInsertSpace={false}
              loading={picking}
              onClick={() => onPick("files")}
            >
              选择文件
            </Button>
            <Button
              variant="outlined"
              icon={<FolderOpenOutlined />}
              autoInsertSpace={false}
              disabled={picking}
              onClick={() => onPick("directory")}
            >
              选择文件夹
            </Button>
          </div>
          {picking && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              系统窗口已打开。若被浏览器挡住，到任务栏点开它。
            </Text>
          )}
        </Flex>
      </div>

      <details className="path-add">
        <summary>手动粘贴路径</summary>
        <Text type="secondary" style={{ fontSize: 12, display: "block", margin: "8px 0" }}>
          一般不用填。每行一个绝对路径；文件夹只加入这一层的音视频。
        </Text>
        <Input.TextArea
          value={pathDraft}
          onChange={(e) => setPathDraft(e.target.value)}
          autoSize={{ minRows: 3, maxRows: 8 }}
          placeholder={"D:\\影片\\a.mp4\n/home/me/Videos"}
        />
        <div className="action-row">
          <Button
            variant="outlined"
            autoInsertSpace={false}
            onClick={() => {
              onPathText(pathDraft);
              setPathDraft("");
            }}
          >
            加入队列
          </Button>
        </div>
      </details>

      {items.length > 0 && (
        <div className="q-list">
          {items.map((item, index) => {
            const note = item.status === "done" || item.status === "error"
              ? (item.writeError || item.outputNote || item.error || item.pathMessage)
              : item.pathState === "bad"
                ? item.pathMessage
                : item.pathState === "ok"
                  ? item.pathMessage
                  : "浏览器没给路径。点「选择文件」再选一次，字幕就会写到旁边。";
            const noteClass = item.writeError || item.pathState === "bad" || item.status === "error"
              ? "q-note warn"
              : item.pathState === "ok" || item.writtenFiles.length > 0
                ? "q-note ok"
                : "q-note";
            return (
              <div
                key={item.key}
                className={rowClass(item, selectedKey === item.key)}
                onClick={() => onSelect(item.key)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onSelect(item.key);
                }}
                role="button"
                tabIndex={0}
              >
                <div className="q-idx">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <div className="q-head">
                    <div className="q-name">{item.name}</div>
                    <div className="q-actions" onClick={(e) => e.stopPropagation()}>
                      <span className={chipClass(item.status)}>
                        {item.status === "running" ? `${Math.round(item.percent)}%` : QUEUE_STATUS_LABEL[item.status]}
                      </span>
                      <Button
                        size="small"
                        variant="text"
                        aria-label="上移"
                        icon={<ArrowUpOutlined />}
                        disabled={index === 0 || item.status === "running"}
                        onClick={() => onMove(item.key, -1)}
                      />
                      <Button
                        size="small"
                        variant="text"
                        aria-label="下移"
                        icon={<ArrowDownOutlined />}
                        disabled={index === items.length - 1 || item.status === "running"}
                        onClick={() => onMove(item.key, 1)}
                      />
                      <Button size="small" variant="text" autoInsertSpace={false} onClick={() => onRemove(item.key)}>移除</Button>
                    </div>
                  </div>
                  {item.pathState === "ok" && item.sourcePath && (
                    <div className="q-note ok mono">{item.sourcePath}</div>
                  )}
                  {note && <div className={noteClass}>{note}</div>}
                  {item.writtenFiles.map((path) => (
                    <div key={path} className="q-note ok mono">{path}</div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="format-row">
        <Text type="secondary" style={{ fontSize: 12 }}>写到源文件旁边</Text>
        <Checkbox.Group
          value={exportFormats}
          options={FORMAT_OPTIONS}
          onChange={(values) => onFormats(values as ExportFormat[])}
        />
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        默认「视频.mp4」得到旁边的「视频.srt」。同名字幕会被盖掉。没拿到路径的，仍可在结果里下载。
      </Text>

      <div className="action-row">
        <Button
          color="primary"
          variant="solid"
          size="large"
          icon={<AudioOutlined />}
          disabled={waiting === 0}
          loading={running}
          onClick={onStart}
        >
          {startLabel}
        </Button>
        {running && waiting > 0 && (
          <Button variant="outlined" onClick={() => onCancel(false)}>跳过当前</Button>
        )}
        {running && (
          <Button variant="outlined" autoInsertSpace={false} onClick={() => onCancel(true)}>
            {waiting > 0 ? "停止队列" : "取消"}
          </Button>
        )}
        {finished && !running && (
          <Button variant="text" onClick={onClear}>清掉已完成</Button>
        )}
      </div>
      {waiting === 0 && !running && (
        <Text type="secondary" style={{ fontSize: 12 }}>先加一个音视频，才能开始转写。</Text>
      )}
      {missingPath > 0 && !running && (
        <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 6 }}>
          {missingPath} 个还没有本机路径。点「选择文件」用系统窗口再选一次，就会写到旁边。
        </Text>
      )}
    </Card>
  );
}
