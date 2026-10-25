import { useRef, useState } from "react";
import { Button, Card, Checkbox, Flex, Input, Typography, Upload } from "antd";
import { ArrowDownOutlined, ArrowUpOutlined, AudioOutlined } from "@ant-design/icons";
import type { ExportFormat } from "../types";
import { ACCEPT_MEDIA } from "./media";
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

export function BatchQueue({
  items,
  running,
  selectedKey,
  exportFormats,
  modelNotDownloaded,
  onSelect,
  onFormats,
  onFiles,
  onPathText,
  onApplyDirectory,
  onPathChange,
  onPathCommit,
  onMove,
  onRemove,
  onClear,
  onStart,
  onCancel,
}: {
  items: QueueItem[];
  running: boolean;
  selectedKey: string | null;
  exportFormats: ExportFormat[];
  modelNotDownloaded: boolean;
  onSelect: (key: string) => void;
  onFormats: (formats: ExportFormat[]) => void;
  onFiles: (files: File[]) => void;
  onPathText: (text: string) => void;
  onApplyDirectory: (directory: string) => void;
  onPathChange: (key: string, path: string) => void;
  onPathCommit: (key: string) => void;
  onMove: (key: string, dir: -1 | 1) => void;
  onRemove: (key: string) => void;
  onClear: () => void;
  onStart: () => void;
  onCancel: (stopAfter: boolean) => void;
}) {
  const [pathDraft, setPathDraft] = useState("");
  const [mediaDir, setMediaDir] = useState("");
  const pending = useRef<File[]>([]);
  const timer = useRef<number | null>(null);
  const waiting = items.filter((it) => it.status === "waiting").length;
  const missingPath = items.filter((it) => it.status === "waiting" && it.pathState !== "ok").length;
  const finished = items.some((it) => it.status === "done" || it.status === "cancelled");

  let startLabel = "开始转写";
  if (running) startLabel = "正在转写…";
  else if (modelNotDownloaded && waiting > 0) startLabel = waiting > 1 ? `下载并转写（${waiting} 个）` : "下载并转写";
  else if (waiting > 1) startLabel = `开始转写（${waiting} 个）`;

  return (
    <Card className="deck-card rise d1" variant="outlined">
      <SectionLabel en="QUEUE">队列</SectionLabel>
      <Upload.Dragger
        className="drop-zone bay-drop"
        accept={ACCEPT_MEDIA}
        multiple
        showUploadList={false}
        beforeUpload={(file) => {
          pending.current.push(file as unknown as File);
          if (timer.current != null) window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => {
            const batch = pending.current.splice(0);
            onFiles(batch);
          }, 0);
          return false;
        }}
      >
        <Flex vertical align="center" gap={10} style={{ padding: "8px 0" }}>
          <span className="eq"><i /><i /><i /><i /><i /></span>
          <Text type="secondary" className="label-hint">一次拖进多个音频或视频，也可以点击选择</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            常见格式都能读。要写到源文件旁边，需要本机绝对路径。
          </Text>
        </Flex>
      </Upload.Dragger>

      <details className="path-add">
        <summary>从本机路径添加</summary>
        <Text type="secondary" style={{ fontSize: 12, display: "block", margin: "8px 0" }}>
          每行一个绝对路径。填文件夹则只加入这一层的音视频。这样字幕能直接写到源文件旁边。
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
                  : "未填路径 · 完成后只在页面里下载";
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
                  <Input
                    size="small"
                    style={{ marginTop: 8 }}
                    value={item.sourcePath}
                    placeholder="本机绝对路径（可选，用来把字幕写到旁边）"
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => onPathChange(item.key, e.target.value)}
                    onBlur={() => onPathCommit(item.key)}
                  />
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
        默认「视频.mp4」得到旁边的「视频.srt」。同名字幕会被盖掉。没填路径的，仍可在结果里下载。
      </Text>

      {items.some((it) => it.file && !it.sourcePath.trim()) && (
        <Flex gap={8} style={{ marginTop: 12 }} wrap>
          <Input
            value={mediaDir}
            onChange={(e) => setMediaDir(e.target.value)}
            placeholder="媒体所在文件夹，按文件名补全路径"
          />
          <Button onClick={() => onApplyDirectory(mediaDir)}>补全路径</Button>
        </Flex>
      )}

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
          {missingPath} 个还没有可用的本机路径，完成后只能在页面里下载。
        </Text>
      )}
    </Card>
  );
}
