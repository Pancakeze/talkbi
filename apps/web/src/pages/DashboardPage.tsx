import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactGridLayout, { type Layout, type LayoutItem as RGLItem } from "react-grid-layout/legacy";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import api from "../api/client";
import ChartPreview, { type ChartSpec } from "../components/ChartPreview";
import { toast } from "../store/toast";
import type { Chart, Dashboard } from "../types";

const BANNER_KEY = "dashboard_banner_dismissed";

type LayoutItem = {
  chart_id: number;
  title: string;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
};

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [items, setItems] = useState<LayoutItem[]>([]);
  const [chartsById, setChartsById] = useState<Record<number, Chart>>({});
  const [editMode, setEditMode] = useState(false);
  const [pickChartId, setPickChartId] = useState<number | "">("");
  const [bannerDismissed, setBannerDismissed] = useState(
    () => localStorage.getItem(BANNER_KEY) === "1"
  );
  const gridWrapRef = useRef<HTMLDivElement | null>(null);
  const [gridWidth, setGridWidth] = useState<number>(0);

  const loadCharts = useCallback(async () => {
    const { data } = await api.get<Chart[]>("/charts");
    const map: Record<number, Chart> = {};
    data.forEach((c) => {
      map[c.id] = c;
    });
    setChartsById(map);
  }, []);

  const loadLayout = useCallback(
    async (dashId: number) => {
      const { data } = await api.get<{ items: LayoutItem[] }>(`/dashboards/${dashId}/layout`);
      setItems(data.items);
    },
    []
  );

  useEffect(() => {
    (async () => {
      const { data: list } = await api.get<Dashboard[]>("/dashboards");
      let dash = list[0];
      if (!dash) {
        const created = await api.post<Dashboard>("/dashboards", { name: "我的仪表盘" });
        dash = created.data;
      }
      setDashboard(dash);
      await loadCharts();
      await loadLayout(dash.id);
    })().catch(() => toast("加载失败", "error"));
  }, [loadCharts, loadLayout]);

  async function saveLayout() {
    if (!dashboard) return;
    await api.patch(`/dashboards/${dashboard.id}/layout`, {
      items: items.map((it) => ({
        chart_id: it.chart_id,
        title: it.title,
        position_x: it.position_x,
        position_y: it.position_y,
        width: it.width,
        height: it.height
      }))
    });
    toast("布局已保存", "success");
  }

  function removeItem(chartId: number) {
    setItems((prev) => prev.filter((i) => i.chart_id !== chartId));
  }

  function addPickedChart() {
    if (pickChartId === "") return;
    const chart = chartsById[pickChartId as number];
    if (!chart) return;
    if (items.some((i) => i.chart_id === chart.id)) return;
    const nextY = items.length ? Math.max(...items.map((i) => i.position_y)) + 1 : 0;
    setItems((prev) => [
      ...prev,
      {
        chart_id: chart.id,
        position_x: 0,
        position_y: nextY,
        width: 6,
        height: 4,
        title: chart.title
      }
    ]);
    setPickChartId("");
  }

  const layout = useMemo<Layout>(
    () =>
      items.map((it) => ({
        i: String(it.chart_id),
        x: it.position_x,
        y: it.position_y,
        w: it.width,
        h: it.height
      })),
    [items]
  );

  const onLayoutChange = useCallback((next: Layout) => {
    setItems((prev) =>
      prev.map((it) => {
        const l = next.find((x: RGLItem) => x.i === String(it.chart_id));
        if (!l) return it;
        return {
          ...it,
          position_x: l.x,
          position_y: l.y,
          width: l.w,
          height: l.h
        };
      })
    );
  }, []);

  useEffect(() => {
    const el = gridWrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const rect = el.getBoundingClientRect();
      setGridWidth(Math.max(0, Math.floor(rect.width)));
    });
    ro.observe(el);
    const rect = el.getBoundingClientRect();
    setGridWidth(Math.max(0, Math.floor(rect.width)));
    return () => ro.disconnect();
  }, []);

  function dismissBanner() {
    localStorage.setItem(BANNER_KEY, "1");
    setBannerDismissed(true);
  }

  return (
    <div>
      <h2>仪表盘</h2>

      {!bannerDismissed && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "#fefce8",
            border: "1px solid #fde68a",
            borderRadius: "var(--r-md)",
            padding: "10px 14px",
            fontSize: 13,
            marginBottom: 14,
          }}
        >
          <span>从图表库拖拽卡片到此处，或使用下方下拉添加</span>
          <button
            type="button"
            onClick={dismissBanner}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16, lineHeight: 1, color: "#92400e" }}
            aria-label="关闭提示"
          >
            ×
          </button>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button
          className={editMode ? "btn" : "btn btn-muted"}
          style={editMode ? { background: "#16a34a", color: "#fff" } : undefined}
          type="button"
          onClick={() => setEditMode((v) => !v)}
        >
          {editMode ? "完成编辑" : "编辑布局"}
        </button>
        <button className="btn btn-primary" type="button" onClick={saveLayout}>
          保存布局到服务器
        </button>
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <strong>从图表库添加</strong>
        <p style={{ fontSize: 13, color: "#6b7280" }}>
          通过下拉选择已保存的图表加入仪表盘；加入后可在编辑模式下拖拽/缩放布局，最后保存到服务器。
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select
            className="select"
            style={{ maxWidth: 320 }}
            value={pickChartId}
            onChange={(e) => setPickChartId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">选择图表…</option>
            {Object.values(chartsById).map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
          <button className="btn btn-primary" type="button" onClick={addPickedChart}>
            添加到仪表盘
          </button>
        </div>
      </div>

      <div ref={gridWrapRef}>
        {gridWidth > 0 && (
          <ReactGridLayout
            className="dashboard-grid"
            layout={layout}
            cols={12}
            rowHeight={80}
            width={gridWidth}
            margin={[16, 16]}
            containerPadding={[0, 0]}
            isDraggable={editMode}
            isResizable={editMode}
            draggableHandle=".dash-card-handle"
            onLayoutChange={onLayoutChange}
            compactType="vertical"
            preventCollision={false}
          >
            {items.map((it) => {
              const chart = chartsById[it.chart_id];
              const raw = (chart?.chart_spec || {}) as Record<string, unknown>;
              const rows = (Array.isArray(raw.rows) ? raw.rows : []) as Record<string, unknown>[];
              const { rows: _r, ...rest } = raw;
              const spec = Object.keys(rest).length ? (rest as ChartSpec) : null;
              return (
                <div key={String(it.chart_id)}>
                  <div className="card" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
                    <div
                      className="dash-card-handle"
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        cursor: editMode ? "move" : "default",
                        marginBottom: 8
                      }}
                    >
                      <strong>{it.title || chart?.title}</strong>
                      {editMode && (
                        <button className="btn btn-muted" type="button" onClick={() => removeItem(it.chart_id)}>
                          移除
                        </button>
                      )}
                    </div>
                    <div style={{ flex: 1, minHeight: 0 }}>
                      <ChartPreview spec={spec} rows={rows} />
                    </div>
                  </div>
                </div>
              );
            })}
          </ReactGridLayout>
        )}
      </div>
    </div>
  );
}
