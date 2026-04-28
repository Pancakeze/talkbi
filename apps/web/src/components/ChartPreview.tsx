import ReactECharts from "echarts-for-react";

export type ChartSpec = {
  chartType: string;
  title?: string;
  xField: string;
  yField: string;
  rows?: Record<string, unknown>[];
};

function buildOption(spec: ChartSpec, rows: Record<string, unknown>[]) {
  const xf = spec.xField;
  const yf = spec.yField;
  if (spec.chartType === "scatter") {
    const data = rows.map((r) => [Number(r[xf]), Number(r[yf])]);
    return {
      title: { text: spec.title || "图表", left: "center" },
      tooltip: { trigger: "item" },
      xAxis: { type: "value", name: xf, scale: true },
      yAxis: { type: "value", name: yf, scale: true },
      series: [{ type: "scatter", data, symbolSize: 10 }]
    };
  }
  return {
    title: { text: spec.title || "图表", left: "center" },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: rows.map((r) => String(r[xf])) },
    yAxis: { type: "value", name: yf },
    series: [{ type: "bar", data: rows.map((r) => Number(r[yf])) }]
  };
}

export default function ChartPreview({
  spec,
  rows
}: {
  spec: ChartSpec | null;
  rows: Record<string, unknown>[];
}) {
  if (!spec || !rows.length) {
    return (
      <div
        className="card chart-placeholder-bg"
        data-testid="chart-empty"
        style={{
          minHeight: 320,
          display: "grid",
          placeItems: "center",
          color: "var(--c-muted)"
        }}
      >
        发送问题后将在此预览图表
      </div>
    );
  }
  const option = buildOption(spec, rows);
  return <ReactECharts option={option} style={{ height: 360 }} data-testid="chart-render" />;
}
