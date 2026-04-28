import { FormEvent, useEffect, useMemo, useState } from "react";
import axios from "axios";

import api from "../api/client";
import { type ChartSpec } from "../components/ChartPreview";
import ChatComposer from "./chat/ChatComposer";
import ChatMessageList, { type ChatMessage } from "./chat/ChatMessageList";
import ChartPanel from "./chat/ChartPanel";
import ThemeScopeHeader from "./chat/ThemeScopeHeader";
import type { ThemeLibrary } from "../types";

type ChatResultField = {
  name: string;
  type: "dimension" | "metric" | "filter";
};

type ChatResult = {
  sql: string;
  chart_spec: ChartSpec;
  rows: Record<string, unknown>[];
  explanation: string;
  fields?: ChatResultField[];
};

export default function ChatPage() {
  const [themes, setThemes] = useState<ThemeLibrary[]>([]);
  const [selectedThemes, setSelectedThemes] = useState<number[]>([]);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChatResult | null>(null);
  const [saved, setSaved] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const selectedThemeNames = useMemo(() => {
    const m = new Map(themes.map((t) => [t.id, t.name] as const));
    return selectedThemes.map((id) => m.get(id)).filter(Boolean) as string[];
  }, [themes, selectedThemes]);

  useEffect(() => {
    api
      .get<ThemeLibrary[]>("/theme-libraries")
      .then((r) => {
        setThemes(r.data);
        if (r.data.length) {
          setSelectedThemes(r.data.slice(0, 2).map((t) => t.id));
        }
      })
      .catch(() => setThemes([]));
  }, []);

  function newId() {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function greetingContent() {
    const themeText =
      selectedThemeNames.length > 0 ? selectedThemeNames.join("、") : "（未选择主题）";
    return (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>
          你好，我是 TalkBI 分析助手
        </div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          当前已连接主题：{themeText}
        </div>
        <div style={{ fontSize: 12 }}>
          你可以这样问：
          <ul style={{ margin: "6px 0 0 18px" }}>
            <li>对比不同区域的事故数量趋势（折线）</li>
            <li>拥堵指数与事故数量是否相关（散点）</li>
            <li>按月份统计 TOP 10 高风险路段（柱状）</li>
          </ul>
        </div>
      </div>
    );
  }

  function errorGuideContent(input: { title: string; reason: string; actions: string[] }) {
    return (
      <div className="chat-error-bubble" data-testid="chat-error-guide">
        <div style={{ fontWeight: 600, marginBottom: 6, color: "var(--c-danger)" }}>
          {input.title}
        </div>
        <div style={{ fontSize: 12, marginBottom: 8 }}>
          <div className="muted" style={{ marginBottom: 4 }}>
            原因
          </div>
          <div>{input.reason}</div>
        </div>
        <div style={{ fontSize: 12 }}>
          <div className="muted" style={{ marginBottom: 4 }}>
            建议操作
          </div>
          <ul style={{ margin: "6px 0 0 18px" }}>
            {input.actions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  function mapSendError(err: unknown) {
    if (axios.isAxiosError(err)) {
      const status = err.response?.status;
      if (!err.response) {
        return {
          title: "连接失败",
          reason: "无法连接到后端服务，可能未启动或网络不可用。",
          actions: ["确认后端已启动（API 可访问）", "稍后重试", "如一直失败，请重新登录后再试"]
        };
      }
      if (status === 401) {
        return {
          title: "登录已失效",
          reason: "当前会话已过期或无权限访问。",
          actions: ["重新登录后再发送", "确认账号权限与数据源归属"]
        };
      }
      if (status === 422) {
        return {
          title: "信息不足，无法生成分析",
          reason: "请求参数校验失败，通常是意图不清晰或缺少必要范围信息。",
          actions: [
            "补充统计口径（时间范围/分组维度/指标）",
            "确认已选择至少 1 个主题库",
            "给出期望图表类型（折线/柱状/散点）"
          ]
        };
      }
      return {
        title: "请求失败",
        reason: `服务端返回错误（HTTP ${status ?? "未知"}），本次分析未完成。`,
        actions: ["稍后重试", "换一种更具体的问法", "确认主题库已配置可用字段"]
      };
    }
    return {
      title: "请求失败",
      reason: "发生未知错误，本次分析未完成。",
      actions: ["稍后重试", "换一种更具体的问法"]
    };
  }

  // 初始化/刷新 greeting：仅在还没开始对话时更新，避免打断用户上下文
  useEffect(() => {
    setMessages((prev) => {
      if (prev.length === 0) {
        return [{ id: "greeting", role: "assistant", content: greetingContent() }];
      }
      if (prev.length === 1 && prev[0]?.id === "greeting") {
        return [{ ...prev[0], content: greetingContent() }];
      }
      return prev;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedThemeNames.join("|")]);

  async function onSend(e: FormEvent) {
    e.preventDefault();
    setSaved(false);
    if (!prompt.trim()) return;
    if (selectedThemes.length === 0) {
      const guide = errorGuideContent({
        title: "请先选择分析范围",
        reason: "当前未选择任何主题库，无法进行跨主题联合分析。",
        actions: ["点击上方「选择主题」添加至少 1 个主题", "再描述你的分析需求（指标/维度/时间范围）"]
      });
      setMessages((prev) => [...prev, { id: newId(), role: "assistant", content: guide }]);
      return;
    }
    setLoading(true);
    const userText = prompt;
    setPrompt("");
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", content: userText }
    ]);
    try {
      const { data } = await api.post<ChatResult>("/chat/query", {
        prompt: userText,
        theme_ids: selectedThemes
      });
      setResult(data);
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          content: (
            <div>
              {data.fields && data.fields.length > 0 && (
                <div className="chat-field-tags">
                  {data.fields.map((f) => (
                    <span key={f.name} className={`chat-field-tag chat-field-tag-${f.type}`}>
                      {f.name}
                    </span>
                  ))}
                </div>
              )}
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                {data.explanation}
              </div>
              <pre className="code-block" data-testid="chat-sql">
                {data.sql}
              </pre>
            </div>
          )
        }
      ]);
    } catch (err: unknown) {
      const guide = errorGuideContent(mapSendError(err));
      setMessages((prev) => [...prev, { id: newId(), role: "assistant", content: guide }]);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function saveChart() {
    if (!result) return;
    await api.post("/charts", {
      title: result.chart_spec.title || "分析图表",
      chart_type: result.chart_spec.chartType,
      chart_spec: { ...result.chart_spec, rows: result.rows }
    });
    setSaved(true);
  }

  function clearChat() {
    setPrompt("");
    setLoading(false);
    setResult(null);
    setSaved(false);
    setMessages([{ id: "greeting", role: "assistant", content: greetingContent() }]);
  }

  return (
    <div data-testid="chat-page">
      <h2>聊天分析</h2>
      <ThemeScopeHeader
        themes={themes}
        selectedThemeIds={selectedThemes}
        onChangeSelectedThemeIds={setSelectedThemes}
      />
      <div className="grid-2">
        <div data-testid="chat-left">
          <ChatMessageList messages={messages} isLoading={loading} />
          <ChatComposer
            prompt={prompt}
            onChangePrompt={setPrompt}
            onSend={onSend}
            onClear={clearChat}
            isSending={loading}
          />
        </div>
        <div data-testid="chat-right">
          <ChartPanel
            title={result?.chart_spec.title || "图表预览"}
            spec={result?.chart_spec ?? null}
            rows={result?.rows ?? []}
            sql={result?.sql}
            canSave={!!result}
            onSave={saveChart}
            saved={saved}
          />
        </div>
      </div>
    </div>
  );
}
