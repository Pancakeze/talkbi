import { useState } from "react";
import ChartPreview, { type ChartSpec } from "../../components/ChartPreview";

export default function ChartPanel({
  title,
  spec,
  rows,
  sql,
  canSave,
  onSave,
  saved
}: {
  title: string;
  spec: ChartSpec | null;
  rows: Record<string, unknown>[];
  sql?: string;
  canSave: boolean;
  onSave: () => void;
  saved: boolean;
}) {
  const [showSql, setShowSql] = useState(false);

  return (
    <div data-testid="chart-panel">
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="chart-panel-toolbar">
          <div style={{ fontSize: 14, fontWeight: 600, flex: 1, minWidth: 0 }}>
            {title}
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            {sql && (
              <button
                className="btn btn-muted chart-panel-sql-btn"
                type="button"
                onClick={() => setShowSql((v) => !v)}
              >
                SQL 代码 {showSql ? "▲" : "▼"}
              </button>
            )}
            <button
              className="btn btn-primary"
              type="button"
              disabled={!canSave || saved}
              onClick={onSave}
              data-testid="chat-save"
            >
              {saved ? "已保存" : "保存到图表库"}
            </button>
          </div>
        </div>
        {showSql && sql && (
          <pre className="code-block" style={{ marginTop: 12 }}>
            {sql}
          </pre>
        )}
      </div>
      <ChartPreview spec={spec} rows={rows} />
    </div>
  );
}

