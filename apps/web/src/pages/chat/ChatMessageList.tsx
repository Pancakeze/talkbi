import type { ReactNode } from "react";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: ReactNode;
};

function Avatar({ role }: { role: "user" | "assistant" }) {
  if (role === "assistant") {
    return (
      <div className="chat-avatar chat-avatar-ai" aria-hidden="true">
        ◆
      </div>
    );
  }
  return (
    <div className="chat-avatar chat-avatar-user" aria-hidden="true">
      U
    </div>
  );
}

export default function ChatMessageList({
  messages,
  isLoading
}: {
  messages: ChatMessage[];
  isLoading: boolean;
}) {
  return (
    <div className="chat-box" data-testid="chat-messages">
      {messages.map((m) => (
        <div
          key={m.id}
          className={`chat-msg ${m.role === "user" ? "chat-user" : "chat-ai"}`}
        >
          <Avatar role={m.role} />
          <div className="chat-bubble">{m.content}</div>
        </div>
      ))}
      {isLoading && (
        <div className="chat-msg chat-ai" data-testid="chat-loading">
          <Avatar role="assistant" />
          <div className="chat-bubble">
            <span className="chat-spinner">⟳</span>
            {" "}正在跨主题库构建联合查询模型…
          </div>
        </div>
      )}
    </div>
  );
}

