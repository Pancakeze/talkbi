import type { FormEvent } from "react";

export default function ChatComposer({
  prompt,
  onChangePrompt,
  onSend,
  onClear,
  isSending
}: {
  prompt: string;
  onChangePrompt: (next: string) => void;
  onSend: (e: FormEvent) => void;
  onClear: () => void;
  isSending: boolean;
}) {
  const canSend = !!prompt.trim() && !isSending;
  return (
    <div className="chat-composer-bar">
      <form onSubmit={onSend} data-testid="chat-composer">
        <textarea
          className="textarea chat-composer-textarea"
          rows={3}
          placeholder="输入分析需求，例如：各区拥堵指数与事故数量相关性（散点）"
          value={prompt}
          onChange={(e) => onChangePrompt(e.target.value)}
          disabled={isSending}
          data-testid="chat-input"
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <button
            className="btn btn-primary"
            type="submit"
            disabled={!canSend}
            data-testid="chat-send"
          >
            ➤ 发送
          </button>
          <button
            className="btn btn-muted"
            type="button"
            onClick={onClear}
            data-testid="chat-clear"
            disabled={isSending}
          >
            清空对话
          </button>
        </div>
      </form>
    </div>
  );
}

