import type { ReactNode } from "react";
import { Card, Flex, Input, InputNumber, Segmented, Select, Switch, Tooltip, Typography } from "antd";
import { LANGUAGE_OPTIONS } from "../labels";
import type { Language, ModelInfo } from "../types";
import { SectionLabel } from "./SectionLabel";

const { Text } = Typography;

function FieldLabel({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <Flex vertical gap={2}>
      <Text type="secondary" style={{ fontSize: 12 }}>{children}</Text>
      {hint ? <Text type="secondary" style={{ fontSize: 11.5, opacity: 0.85 }}>{hint}</Text> : null}
    </Flex>
  );
}

export function SettingsCard({
  models,
  modelId,
  onModelId,
  language,
  onLanguage,
  hotwords,
  onHotwords,
  maxChars,
  onMaxChars,
  punctuation,
  onPunctuation,
  diarization,
  onDiarization,
  diarAvailable,
  supportsHotwords,
}: {
  models: ModelInfo[];
  modelId: string;
  onModelId: (id: string) => void;
  language: Language;
  onLanguage: (lang: Language) => void;
  hotwords: string;
  onHotwords: (value: string) => void;
  maxChars: number;
  onMaxChars: (value: number) => void;
  punctuation: "auto" | "on" | "off";
  onPunctuation: (value: "auto" | "on" | "off") => void;
  diarization: boolean;
  onDiarization: (value: boolean) => void;
  diarAvailable: boolean;
  supportsHotwords: boolean;
}) {
  return (
    <Card className="deck-card rise d2" variant="outlined">
      <SectionLabel en="SETTINGS">这一批共用</SectionLabel>
      <Flex vertical gap={18}>
        <Flex vertical gap={8}>
          <Text type="secondary" style={{ fontSize: 12 }}>语言</Text>
          <div className="seg-scroll">
            <Segmented
              value={language}
              onChange={(v) => onLanguage(v as Language)}
              options={LANGUAGE_OPTIONS.map((o) => ({ label: o.label, value: o.value }))}
            />
          </div>
        </Flex>
        <Flex vertical gap={8}>
          <Text type="secondary" style={{ fontSize: 12 }}>模型</Text>
          <Select
            value={modelId || undefined}
            onChange={onModelId}
            loading={models.length === 0}
            options={models.map((m) => ({
              value: m.id,
              label: m.downloaded ? m.name : `${m.name}（未下载）`,
            }))}
          />
        </Flex>
        <Flex vertical gap={8}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            热词{supportsHotwords ? "" : "（只有「热词版」模型认）"}
          </Text>
          <Input
            value={hotwords}
            onChange={(e) => onHotwords(e.target.value)}
            placeholder="输入关键词，用空格分开（可不填）"
            disabled={!supportsHotwords}
          />
        </Flex>
        <Flex vertical gap={8}>
          <Tooltip title="一行显示多少个字符。中文按字算，英文两个字母算一个。填 0 就只按句子断，不控长度。">
            <FieldLabel hint="0 = 不按长度断句">每行最多几个字</FieldLabel>
          </Tooltip>
          <InputNumber
            min={0}
            max={100}
            value={maxChars}
            onChange={(v) => { if (v != null) onMaxChars(v); }}
            style={{ width: "100%" }}
          />
        </Flex>
        <Flex vertical gap={8}>
          <Tooltip title="自动：中文加标点，英文按停顿断句（英文标点容易加错）。加标点：不管什么语言都加。不加标点：只按停顿和行宽断。">
            <FieldLabel>标点</FieldLabel>
          </Tooltip>
          <Segmented
            value={punctuation}
            onChange={(v) => onPunctuation(v as "auto" | "on" | "off")}
            options={[
              { label: "自动", value: "auto" },
              { label: "加标点", value: "on" },
              { label: "不加标点", value: "off" },
            ]}
          />
        </Flex>
        <Tooltip title={diarAvailable
          ? "给每句字幕标上是谁说的，导出的字幕里会带 [spk0]、[spk1] 这样的记号"
          : "只有「完整版」程序配 Paraformer 模型能区分说话人。轻量版（onnx）和 SenseVoice 做不到。"}>
          <Flex align="center" gap={10}>
            <span className="switch-hit">
              <Switch checked={diarization && diarAvailable} disabled={!diarAvailable} onChange={onDiarization} />
            </span>
            <Text type={diarAvailable ? undefined : "secondary"}>
              区分说话人{diarAvailable ? "" : "（需完整版 + Paraformer）"}
            </Text>
          </Flex>
        </Tooltip>
      </Flex>
    </Card>
  );
}
