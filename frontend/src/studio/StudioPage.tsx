// 当前页面。原 App.tsx 留着方便跟上游合并，这里用同一套主题、接口和文案习惯。

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App as AntApp, Alert, Button, Flex, Popconfirm, Tag, Tooltip } from "antd";
import { PoweroffOutlined, ReloadOutlined } from "@ant-design/icons";
import { getModels, shutdown, SubtitleApiError } from "../api";
import type { ExportFormat, Language, ModelInfo } from "../types";
import { BatchQueue } from "./BatchQueue";
import { ModelDownloadCard } from "./ModelDownloadCard";
import { ProgressCard } from "./ProgressCard";
import { SettingsCard } from "./SettingsCard";
import { TranscriptCard } from "./TranscriptCard";
import type { RunOptions } from "./types";
import { useBatchQueue } from "./useBatchQueue";

export default function StudioPage() {
  const { message } = AntApp.useApp();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelId, setModelId] = useState("");
  const [language, setLanguage] = useState<Language>("zh");
  const [diarization, setDiarization] = useState(false);
  const [hotwords, setHotwords] = useState("");
  const [maxChars, setMaxChars] = useState(30);
  const [punctuation, setPunctuation] = useState<"auto" | "on" | "off">("auto");
  const [exportFormats, setExportFormats] = useState<ExportFormat[]>(["srt"]);
  const [compute, setCompute] = useState("CPU · …");
  const [backendKind, setBackendKind] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const useGpu = false;

  const loadModels = useCallback(async () => {
    setModelsError(null);
    try {
      const res = await getModels();
      setModels(res.models);
      setModelId((cur) => cur || res.default_id);
      if (res.compute) setCompute(res.compute);
      if (res.backend) setBackendKind(res.backend);
    } catch (e) {
      setModelsError(e instanceof SubtitleApiError ? e.message : "拿不到模型列表，后台可能还没起来");
    }
  }, []);

  useEffect(() => { void loadModels(); }, [loadModels]);

  const currentModel = useMemo(() => models.find((m) => m.id === modelId), [models, modelId]);
  const diarAvailable = !!currentModel?.diarization;
  const supportsHotwords = /contextual/.test(modelId);
  const modelNotDownloaded = !!currentModel && !currentModel.downloaded;

  const getOptions = useCallback((): RunOptions => ({
    modelId,
    language,
    diarization: diarization && diarAvailable,
    hotwords: hotwords.trim(),
    useGpu,
    maxChars,
    punctuation,
    exportFormats,
  }), [modelId, language, diarization, diarAvailable, hotwords, maxChars, punctuation, exportFormats]);

  const notify = useCallback((level: "success" | "info" | "warning" | "error", text: string) => {
    message[level](text);
  }, [message]);

  const queue = useBatchQueue(getOptions, notify);
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !queue.running) void loadModels();
    wasRunning.current = queue.running;
  }, [queue.running, loadModels]);
  const selected = queue.items.find((it) => it.key === selectedKey) ?? null;
  const active = queue.items.find((it) => it.key === queue.activeKey) ?? null;
  const counts = {
    waiting: queue.items.filter((it) => it.status === "waiting").length,
    running: queue.items.filter((it) => it.status === "running").length,
    done: queue.items.filter((it) => it.status === "done").length,
    error: queue.items.filter((it) => it.status === "error").length,
  };

  const onShutdown = useCallback(async () => {
    try {
      await shutdown();
      message.info("服务已停止，可以关掉这个页面了");
    } catch { /* 进程可能先关掉 */ }
  }, [message]);

  const pagePort = window.location.port || (window.location.protocol === "https:" ? "443" : "80");

  return (
    <div className="studio-root">
      <div className="shell">
        <header className="transport rise">
          <div className="transport-id">
            <span className={`rec-dot${queue.running ? " live" : ""}`} />
            <span className="wordmark nowrap" style={{ fontSize: 20 }}>funasr-subtitle</span>
            <span className="label-cap nowrap">
              <span className="cap-cn">本地 · 离线 · 转写</span>
            </span>
          </div>
          <div className="meters">
            <span className="meter">等待 <strong>{counts.waiting}</strong></span>
            <span className="meter run">转写中 <strong>{counts.running}</strong></span>
            <span className="meter">完成 <strong>{counts.done}</strong></span>
            <span className="meter bad">失败 <strong>{counts.error}</strong></span>
          </div>
          <div className="transport-meta">
            <Tooltip title="当前页面的端口。便携版里页面和后台是同一个端口；开发时前端端口和后台端口可以分开设。">
              <span className="port-chip">:{pagePort}</span>
            </Tooltip>
            <Tooltip
              title={
                compute.startsWith("GPU")
                  ? "完整 funasr 后端，正在使用 NVIDIA CUDA"
                  : backendKind === "full"
                    ? "完整 funasr 后端，但当前无可用 CUDA（驱动/torch 或已设 FUNASR_SUBTITLE_FORCE_CPU=1）→ CPU"
                    : "onnx 后端（默认开发环境），固定 CPU。要用 GPU：建 backend\\.venv-full 并设 FUNASR_SUBTITLE_BACKEND=full"
              }
            >
              <Tag color={compute.startsWith("GPU") ? "gold" : "default"} className="mono" style={{ marginRight: 0 }}>{compute}</Tag>
            </Tooltip>
            <Popconfirm
              title="要停止后台服务吗？"
              description="正在跑的任务会中断，页面可以关掉。"
              okText="停止服务"
              cancelText="取消"
              okButtonProps={{ danger: true, variant: "outlined" }}
              onConfirm={onShutdown}
            >
              <Button className="btn-exit" color="danger" variant="text" icon={<PoweroffOutlined />} size="small">
                停止服务
              </Button>
            </Popconfirm>
          </div>
        </header>

        <div className="stack">
          {modelsError && (
            <Alert
              type="error"
              showIcon
              message={modelsError}
              action={<Button size="small" icon={<ReloadOutlined />} onClick={() => void loadModels()}>重新获取模型</Button>}
            />
          )}
          {modelNotDownloaded && currentModel && (
            <ModelDownloadCard model={currentModel} onDownloaded={loadModels} />
          )}

          <div className="workspace">
            <BatchQueue
              items={queue.items}
              running={queue.running}
              selectedKey={selectedKey}
              exportFormats={exportFormats}
              modelNotDownloaded={modelNotDownloaded}
              onSelect={setSelectedKey}
              onFormats={setExportFormats}
              onFiles={queue.addFiles}
              onPathText={(text) => { void queue.addPathText(text); }}
              onApplyDirectory={(dir) => { void queue.applyDirectory(dir); }}
              onPathChange={queue.setPath}
              onPathCommit={queue.commitPath}
              onMove={queue.move}
              onRemove={(key) => { void queue.remove(key); }}
              onClear={queue.clearFinished}
              onStart={() => { void queue.start(); }}
              onCancel={(stopAfter) => { void queue.cancelCurrent(stopAfter); }}
            />
            <SettingsCard
              models={models}
              modelId={modelId}
              onModelId={setModelId}
              language={language}
              onLanguage={setLanguage}
              hotwords={hotwords}
              onHotwords={setHotwords}
              maxChars={maxChars}
              onMaxChars={setMaxChars}
              punctuation={punctuation}
              onPunctuation={setPunctuation}
              diarization={diarization}
              onDiarization={setDiarization}
              diarAvailable={diarAvailable}
              supportsHotwords={supportsHotwords}
            />
          </div>

          {active && (
            <ProgressCard
              filename={active.name}
              stage={active.stage}
              percent={active.percent}
              running={active.status === "running"}
              fetchingModel={modelNotDownloaded && active.status === "running"}
              modelSizeMb={currentModel?.size_mb}
            />
          )}

          {selected?.status === "cancelled" && (
            <Alert
              type="info"
              showIcon
              message="已取消转写"
              description="这一条还在队列里的话可以重新开始；文件不会被删。"
            />
          )}

          {selected?.status === "error" && selected.error && (
            <Alert
              type="error"
              showIcon
              message="转写没完成"
              description={
                <Flex vertical gap={6}>
                  <span>{selected.error}</span>
                  {selected.detail && (
                    <details>
                      <summary style={{ cursor: "pointer" }}>查看详情</summary>
                      <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 11.5, margin: "6px 0 0" }}>
                        {selected.detail}
                      </pre>
                    </details>
                  )}
                </Flex>
              }
              action={<Button size="small" icon={<ReloadOutlined />} onClick={() => queue.retry(selected.key)}>重新转写</Button>}
            />
          )}

          {selected?.status === "done" && selected.job && (
            <TranscriptCard job={{ ...selected.job, filename: selected.name, written_files: selected.writtenFiles, write_error: selected.writeError, output_note: selected.outputNote }} />
          )}
        </div>
      </div>
    </div>
  );
}
