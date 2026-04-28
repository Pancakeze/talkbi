import { FormEvent, useEffect, useState } from "react";

import api from "../api/client";
import { toast } from "../store/toast";
import type { DataSource } from "../types";

export default function DataSourcePage() {
  const [list, setList] = useState<DataSource[]>([]);
  const [name, setName] = useState("演示 MySQL 连接");
  const [showDbForm, setShowDbForm] = useState(false);
  const [showExcelForm, setShowExcelForm] = useState(false);
  const [syncing, setSyncing] = useState<number | null>(null);

  async function refresh() {
    const { data } = await api.get<DataSource[]>("/data-sources");
    setList(data);
  }

  useEffect(() => {
    refresh().catch(() => setList([]));
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    await api.post("/data-sources", {
      name,
      source_type: "mysql",
      connection_info: { host: "10.0.0.1", port: 3306 }
    });
    toast("已创建数据源记录（演示）");
    setShowDbForm(false);
    await refresh();
  }

  async function onUpload(file: File | null) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post("/data-sources/excel/upload", fd);
      toast("Excel 已上传并解析元数据");
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Excel 上传失败，请重试";
      toast(detail, "error");
    }
    setShowExcelForm(false);
    await refresh();
  }

  async function onSync(id: number) {
    setSyncing(id);
    await new Promise((r) => setTimeout(r, 1200));
    await refresh();
    setSyncing(null);
    toast("同步完成");
  }

  const total = list.length;
  const active = list.filter((d) => d.status === "active").length;
  const excelCount = list.filter((d) => d.source_type === "excel").length;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>数据源管理</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-primary"
            onClick={() => { setShowDbForm(!showDbForm); setShowExcelForm(false); }}
          >
            + 接入数据库
          </button>
          <button
            className="btn"
            style={{ background: "#16a34a", color: "#fff" }}
            onClick={() => { setShowExcelForm(!showExcelForm); setShowDbForm(false); }}
          >
            + 接入 Excel
          </button>
        </div>
      </div>

      {showDbForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>接入数据库（演示）</h3>
          <form onSubmit={onCreate} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ fontSize: 14 }}>连接名称</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit">保存</button>
            <button className="btn btn-muted" type="button" onClick={() => setShowDbForm(false)}>取消</button>
          </form>
        </div>
      )}

      {showExcelForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>上传 Excel</h3>
          <input
            type="file"
            accept=".xlsx,.xls,.csv"
            onChange={(e) => onUpload(e.target.files?.[0] || null)}
          />
          <div style={{ marginTop: 10 }}>
            <button className="btn btn-muted" type="button" onClick={() => setShowExcelForm(false)}>取消</button>
          </div>
        </div>
      )}

      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">总数据源</div>
          <div className="kpi-value">{total}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">活跃</div>
          <div className="kpi-value">{active}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Excel 来源</div>
          <div className="kpi-value">{excelCount}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">最近同步</div>
          <div className="kpi-value" style={{ fontSize: 16, lineHeight: "1.8" }}>—</div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {list.length === 0 && (
              <tr>
                <td colSpan={4} style={{ textAlign: "center", color: "#6b7280", padding: 24 }}>
                  暂无数据源，请点击上方按钮接入
                </td>
              </tr>
            )}
            {list.map((ds) => (
              <tr key={ds.id} className={ds.source_type === "excel" ? "row-excel" : ""}>
                <td>
                  <strong>{ds.name}</strong>
                  {ds.source_type === "excel" && ds.connection_info?.staging?.tables?.length ? (
                    <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
                      {ds.connection_info.staging.tables.length} 张表（
                      {ds.connection_info.staging.tables.map((t) => t.table).join(", ")}）
                    </div>
                  ) : null}
                </td>
                <td>
                  <span>{ds.source_type === "excel" ? "📊 Excel" : ds.source_type === "mysql" ? "🗄️ MySQL" : ds.source_type}</span>
                </td>
                <td>
                  <span className={`status-pill ${ds.status === "active" ? "status-pill-active" : "status-pill-inactive"}`}>
                    {ds.status === "active" ? "活跃" : ds.status}
                  </span>
                </td>
                <td>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn btn-muted"
                      style={{ fontSize: 12, padding: "4px 10px" }}
                      onClick={() => onSync(ds.id)}
                      disabled={syncing === ds.id}
                    >
                      {syncing === ds.id ? <span className="chat-spinner">⟳</span> : "↻"} 同步
                    </button>
                    <button
                      className="btn btn-muted"
                      style={{ fontSize: 12, padding: "4px 10px", color: "#6b7280" }}
                    >
                      表管理
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
