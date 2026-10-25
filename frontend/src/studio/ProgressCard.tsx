import { Card, Progress, Steps, Typography } from "antd";
import { STAGE_LABELS } from "../labels";
import { STUDIO } from "../theme";
import type { Stage } from "../types";
import { SectionLabel } from "./SectionLabel";

const { Text } = Typography;
const STAGE_FLOW: Stage[] = ["decoding", "vad", "asr", "punc", "assembling"];

export function ProgressCard({
  filename,
  stage,
  percent,
  running,
  fetchingModel,
  modelSizeMb,
}: {
  filename: string;
  stage: Stage | null;
  percent: number;
  running: boolean;
  fetchingModel: boolean;
  modelSizeMb?: number;
}) {
  const stageIndex = stage ? STAGE_FLOW.indexOf(stage) : -1;
  return (
    <Card className="deck-card rise" variant="outlined">
      <SectionLabel en="PROGRESS">
        {filename ? `${filename} · ` : ""}
        {stage ? STAGE_LABELS[stage] : "等待开始"}
      </SectionLabel>
      <Steps
        size="small"
        current={stageIndex}
        items={STAGE_FLOW.map((s) => ({ title: STAGE_LABELS[s] }))}
        style={{ marginBottom: 16 }}
      />
      <Progress
        percent={Math.round(percent)}
        strokeColor={{ from: STUDIO.amber, to: STUDIO.amberSoft }}
        status={running ? "active" : "normal"}
      />
      {fetchingModel && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          第一次用这个模型，正在先下载（约 {modelSizeMb?.toFixed(0) ?? "若干"} MB），
          进度可能长时间停在「读音频」。
        </Text>
      )}
    </Card>
  );
}
