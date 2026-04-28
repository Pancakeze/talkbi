import { useState } from "react";

type TicketStatus = "pending" | "in_progress" | "resolved";

type Ticket = {
  id: number;
  user: string;
  question: string;
  error: string;
  suggestion: string;
  status: TicketStatus;
};

const MOCK_TICKETS: Ticket[] = [
  {
    id: 1,
    user: "alice",
    question: "各城市2024年Q1销售额对比",
    error: "KeyError: 'city_name'\nTraceback (most recent call last):\n  File \"chat_service.py\", line 83, in run\n    df[field] for field in fields",
    suggestion: "检查主题库字段映射，确认 city_name 字段已添加到语义层。",
    status: "pending",
  },
  {
    id: 2,
    user: "bob",
    question: "本月订单量趋势",
    error: "OperationalError: no such table: orders_2024\nSQLite error at line 1",
    suggestion: "数据源同步可能失败，请重新触发 Excel 同步或检查数据库连接。",
    status: "resolved",
  },
];

const STATUS_LABELS: Record<TicketStatus, string> = {
  pending: "待处理",
  in_progress: "处理中",
  resolved: "已解决",
};

const STATUS_BG: Record<TicketStatus, string> = {
  pending: "#fef9c3",
  in_progress: "#dbeafe",
  resolved: "#dcfce7",
};

const STATUS_COLOR: Record<TicketStatus, string> = {
  pending: "#854d0e",
  in_progress: "#1d4ed8",
  resolved: "#15803d",
};

export default function AdminTicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>(MOCK_TICKETS);

  function setStatus(id: number, status: TicketStatus) {
    setTickets((prev) => prev.map((t) => (t.id === id ? { ...t, status } : t)));
  }

  return (
    <div style={{ maxWidth: 800, margin: "0 auto" }}>
      <h2 style={{ marginBottom: 4 }}>AI 异常工单</h2>
      <p style={{ color: "var(--c-muted)", fontSize: 13, marginBottom: 20 }}>
        用户遇到 AI 分析异常时自动生成的工单，由管理员跟进处理。
      </p>

      <div className="list">
        {tickets.map((ticket) => (
          <div key={ticket.id} className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 2 }}>#{ticket.id} · {ticket.user}</div>
                <div style={{ fontSize: 14 }}>{ticket.question}</div>
              </div>
              <span
                style={{
                  background: STATUS_BG[ticket.status],
                  color: STATUS_COLOR[ticket.status],
                  borderRadius: "var(--r-pill)",
                  padding: "2px 10px",
                  fontSize: 12,
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
              >
                {STATUS_LABELS[ticket.status]}
              </span>
            </div>

            <pre className="code-block" style={{ margin: 0 }}>
              {ticket.error}
            </pre>

            <div style={{ fontSize: 13, color: "var(--c-muted)", background: "#f9fafb", padding: "8px 10px", borderRadius: "var(--r-sm)" }}>
              💡 {ticket.suggestion}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-muted"
                style={{ fontSize: 12 }}
                onClick={() => setStatus(ticket.id, "in_progress")}
                disabled={ticket.status === "in_progress"}
              >
                处理中
              </button>
              <button
                className="btn btn-primary"
                style={{ fontSize: 12 }}
                onClick={() => setStatus(ticket.id, "resolved")}
                disabled={ticket.status === "resolved"}
              >
                已解决
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
