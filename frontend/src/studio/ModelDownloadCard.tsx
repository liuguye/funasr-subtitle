import { useCallback, useEffect, useRef, useState } from "react";
import { App as AntApp, Button, Card, Flex, Progress, Typography } from "antd";
import { downloadModel, subscribeModelDownload, SubtitleApiError, type WsHandle } from "../api";
import type { ModelInfo } from "../types";
import { STUDIO } from "../theme";
import { SectionLabel } from "./SectionLabel";

const { Text } = Typography;

export function ModelDownloadCard({
  model,
  onDownloaded,
}: {
  model: ModelInfo;
  onDownloaded: () => void;
}) {
  const { message } = AntApp.useApp();
  const [downloading, setDownloading] = useState(false);
  const [percent, setPercent] = useState(0);
  const [detail, setDetail] = useState("");
  const wsRef = useRef<WsHandle | null>(null);
  useEffect(() => () => wsRef.current?.close(), []);

  const start = useCallback(async () => {
    setPercent(0);
    setDetail("");
    setDownloading(true);
    wsRef.current?.close();
    wsRef.current = subscribeModelDownload(model.id, {
      onEvent: (ev) => {
        if (ev.type === "download") {
          setPercent(ev.percent);
          setDetail(`${ev.downloaded_mb.toFixed(0)} / ${ev.total_mb.toFixed(0)} MB`);
        } else if (ev.type === "done") {
          setPercent(100);
          setDownloading(false);
          wsRef.current?.close();
          wsRef.current = null;
          message.success("模型已就绪");
          onDownloaded();
        } else if (ev.type === "error") {
          message.error("下载失败，点重试");
          setDownloading(false);
        }
      },
      onError: () => {
        message.error("连不上后台了，下载中断");
        setDownloading(false);
      },
    });
    try {
      await downloadModel(model.id);
    } catch (e) {
      message.error(e instanceof SubtitleApiError ? e.message : "下载没发出去，重试一下");
      setDownloading(false);
      wsRef.current?.close();
      wsRef.current = null;
    }
  }, [model.id, onDownloaded, message]);

  return (
    <Card className="deck-card rise d1" variant="outlined" styles={{ body: { padding: 22 } }}>
      <SectionLabel en="FIRST RUN">先下模型</SectionLabel>
      <Flex justify="space-between" align="center" gap={16} wrap>
        <Text type="secondary">
          第一次要用，需要先下模型 <Text strong style={{ color: STUDIO.text }}>{model.name}</Text>
          （约 {model.size_mb.toFixed(0)} MB）。下完就彻底离线，不再联网。
        </Text>
        <Button color="primary" variant="solid" loading={downloading} onClick={start}>
          {downloading ? "正在下载…" : "下载模型"}
        </Button>
      </Flex>
      {(downloading || percent > 0) && (
        <div style={{ marginTop: 14 }}>
          <Progress percent={Math.round(percent)} strokeColor={STUDIO.amber} />
          {detail && <Text type="secondary" className="mono" style={{ fontSize: 12 }}>{detail}</Text>}
        </div>
      )}
    </Card>
  );
}
