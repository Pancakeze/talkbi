import { useEffect, useState } from "react";

import api from "../api/client";
import type { Chart } from "../types";

export default function ChartLibraryPage() {
  const [charts, setCharts] = useState<Chart[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.get<Chart[]>("/charts").then((r) => setCharts(r.data)).catch(() => setCharts([]));
  }, []);

  const filtered = query
    ? charts.filter(
        (c) =>
          c.title.toLowerCase().includes(query.toLowerCase()) ||
          c.chart_type.toLowerCase().includes(query.toLowerCase())
      )
    : charts;

  function onDragStart(e: React.DragEvent, chart: Chart) {
    e.dataTransfer.setData("application/json", JSON.stringify({ chartId: chart.id, title: chart.title }));
    e.dataTransfer.effectAllowed = "copy";
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>个人图表库</h2>
        <span className="badge">{charts.length}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <p style={{ color: "#6b7280", fontSize: 14, margin: 0, flex: 1 }}>
          将卡片拖到「仪表盘」页中的放置区即可加入大屏（需在仪表盘页完成保存布局）。
        </p>
        <input
          className="input"
          placeholder="搜索图表..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ width: 200 }}
        />
      </div>

      <div className="grid-3">
        {filtered.map((c) => (
          <div
            key={c.id}
            className="card chart-library-card drag-item"
            draggable
            onDragStart={(e) => onDragStart(e, c)}
          >
            <div
              className="chart-placeholder-bg"
              style={{ height: 80, borderRadius: 6, marginBottom: 10 }}
            />
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
              <strong style={{ fontSize: 14 }}>{c.title}</strong>
              <span
                className="badge"
                style={{ background: "#e0e7ff", color: "#4338ca", flexShrink: 0, fontSize: 11 }}
              >
                可拖拽
              </span>
            </div>
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 6 }}>类型：{c.chart_type}</div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && charts.length > 0 && (
        <p style={{ color: "#6b7280" }}>没有匹配「{query}」的图表。</p>
      )}
      {charts.length === 0 && (
        <p style={{ color: "#6b7280" }}>暂无图表，请先在聊天分析中生成并保存。</p>
      )}
    </div>
  );
}
