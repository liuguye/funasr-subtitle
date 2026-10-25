import { useCallback, useMemo, useState } from "react";
import { App as AntApp, Button, Card, Flex, Space, Tag, Typography } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { exportUrl } from "../api";
import type { ExportFormat, Segment } from "../types";
import { SectionLabel } from "./SectionLabel";
import type { JobWithOutput } from "./types";

const { Text } = Typography;
const EXPORT_FORMATS: ExportFormat[] = ["srt", "vtt", "txt", "json"];
const TRANSLATOR_URL = "https://tools.newzone.top/zh/subtitle-translator";

function formatTimestamp(ms: number): string {
  const totalMs = Math.max(0, Math.round(ms));
  const h = Math.floor(totalMs / 3_600_000);
  const m = Math.floor((totalMs % 3_600_000) / 60_000);
  const s = Math.floor((totalMs % 60_000) / 1000);
  const ms3 = totalMs % 1000;
  const pad = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(ms3, 3)}`;
}

export function TranscriptCard({ job }: { job: JobWithOutput }) {
  const { message } = AntApp.useApp();
  const [copied, setCopied] = useState(false);
  const fullText = useMemo(() => job.segments.map((s) => s.text).join("\n"), [job.segments]);
  const copyAll = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
      message.success(`已复制 ${job.segments.length} 句`);
    } catch {
      message.error("复制没成功，再试一次");
    }
  }, [fullText, job.segments.length, message]);

  const written = job.written_files ?? [];

  return (
    <Card className="deck-card rise" variant="outlined">
      <Flex justify="space-between" align="center" wrap gap={12} style={{ marginBottom: 14 }}>
        <SectionLabel en="TRANSCRIPT">
          {job.filename} · {job.segments.length} 句
        </SectionLabel>
        <Space wrap>
          {EXPORT_FORMATS.map((fmt) => (
            <Button
              key={fmt}
              size="small"
              variant="outlined"
              icon={<DownloadOutlined />}
              href={exportUrl(job.id, fmt)}
              download
              onClick={() => message.info(`已开始下载 .${fmt}`)}
            >
              .{fmt}
            </Button>
          ))}
          <Button size="small" color="primary" variant="filled" onClick={copyAll}>
            {copied ? "已复制 ✓" : "复制全文"}
          </Button>
        </Space>
      </Flex>
      {job.output_note && (
        <Text type="secondary" style={{ fontSize: 12 }}>{job.output_note}</Text>
      )}
      {job.write_error && (
        <div className="q-note warn">{job.write_error}</div>
      )}
      {written.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {written.map((path) => (
            <div key={path} className="q-note ok mono">{path}</div>
          ))}
        </div>
      )}
      <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>
        想翻成双语字幕？把 .srt 导入{" "}
        <a href={TRANSLATOR_URL} target="_blank" rel="noreferrer">字幕翻译器</a>
      </Text>
      <div className="scroll-fade" style={{ marginTop: 12, maxHeight: 420, overflow: "auto", paddingRight: 6 }}>
        {job.segments.length === 0 ? (
          <Text type="secondary">
            没听到人声。可能是纯音乐、静音，或者这个文件没有音轨。换个文件再试。
          </Text>
        ) : (
          job.segments.map((seg: Segment, i) => (
            <div className="seg-row" key={i}>
              <span className="ts" style={{ fontSize: 12.5 }}>
                {formatTimestamp(seg.start_ms)}
                <br />
                {formatTimestamp(seg.end_ms)}
              </span>
              <span className="seg-text">
                {seg.speaker && <Tag color="gold" style={{ marginRight: 6 }}>{seg.speaker}</Tag>}
                {seg.text}
              </span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
