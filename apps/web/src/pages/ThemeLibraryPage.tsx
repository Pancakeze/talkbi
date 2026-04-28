import { FormEvent, useEffect, useState } from "react";

import api from "../api/client";
import { toast } from "../store/toast";
import type { DataSource, ThemeLibrary } from "../types";

type FieldRow = {
  id: number;
  table_name: string;
  field_name: string;
  alias_zh: string;
  visible: boolean;
};

export default function ThemeLibraryPage() {
  const [themes, setThemes] = useState<ThemeLibrary[]>([]);
  const [name, setName] = useState("交通流量主题库");
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [dataSourceId, setDataSourceId] = useState<number | "">("");
  const [activeId, setActiveId] = useState<number | null>(null);
  const [fields, setFields] = useState<FieldRow[]>([]);
  const [stagingTableOptions, setStagingTableOptions] = useState<string[]>([]);
  const [tableName, setTableName] = useState("traffic_flow_monthly");
  const [fieldName, setFieldName] = useState("congestion_index");
  const [aliasZh, setAliasZh] = useState("拥堵指数");
  const [showCreateForm, setShowCreateForm] = useState(false);

  async function refreshThemes() {
    const { data } = await api.get<ThemeLibrary[]>("/theme-libraries");
    setThemes(data);
    if (data.length && !activeId) {
      setActiveId(data[0].id);
    }
  }

  async function refreshDataSources() {
    const { data } = await api.get<DataSource[]>("/data-sources");
    setDataSources(data.filter((d) => d.source_type === "excel" && d.status === "active"));
  }

  useEffect(() => {
    refreshThemes().catch(() => setThemes([]));
    refreshDataSources().catch(() => setDataSources([]));
  }, []);

  useEffect(() => {
    if (!activeId) {
      setFields([]);
      return;
    }
    api
      .get<FieldRow[]>(`/theme-libraries/${activeId}/fields`)
      .then((r) => setFields(r.data))
      .catch(() => setFields([]));
  }, [activeId]);

  useEffect(() => {
    const t = themes.find((x) => x.id === activeId);
    if (!t?.data_source_id) {
      setStagingTableOptions([]);
      return;
    }
    api
      .get<DataSource>(`/data-sources/${t.data_source_id}`)
      .then((r) => {
        const tables = r.data.connection_info?.staging?.tables?.map((x) => x.table) ?? [];
        setStagingTableOptions(tables);
        if (tables.length) {
          setTableName((prev) => (tables.includes(prev) ? prev : tables[0]));
        }
      })
      .catch(() => setStagingTableOptions([]));
  }, [activeId, themes]);

  async function createTheme(e: FormEvent) {
    e.preventDefault();
    await api.post("/theme-libraries", {
      name,
      description: "语义层演示",
      data_source_id: dataSourceId === "" ? null : dataSourceId
    });
    toast("主题库已创建");
    setShowCreateForm(false);
    await refreshThemes();
  }

  async function addField(e: FormEvent) {
    e.preventDefault();
    if (!activeId) return;
    await api.post(`/theme-libraries/${activeId}/fields`, {
      table_name: tableName,
      field_name: fieldName,
      alias_zh: aliasZh,
      visible: true
    });
    toast("字段已添加");
    const { data } = await api.get<FieldRow[]>(`/theme-libraries/${activeId}/fields`);
    setFields(data);
  }

  const activeTheme = themes.find((t) => t.id === activeId);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>主题库管理</h2>
        <button className="btn btn-primary" onClick={() => setShowCreateForm(!showCreateForm)}>
          + 新建主题库
        </button>
      </div>

      <div className="info-callout">
        <strong>什么是主题库？</strong> 主题库是连接数据源与 AI 分析的语义层——通过为物理字段配置中文别名和可见性，让 AI 能用业务语言理解数据结构，从而生成更精准的分析 SQL。
      </div>

      {showCreateForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>新建主题库</h3>
          <form onSubmit={createTheme} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <label style={{ fontSize: 14 }}>名称</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div style={{ minWidth: 200 }}>
              <label style={{ fontSize: 14 }}>绑定 Excel 数据源</label>
              <select
                className="input"
                value={dataSourceId}
                onChange={(e) => setDataSourceId(e.target.value === "" ? "" : Number(e.target.value))}
              >
                <option value="">不绑定</option>
                {dataSources.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} (#{d.id})
                  </option>
                ))}
              </select>
            </div>
            <button className="btn btn-primary" type="submit">创建</button>
            <button className="btn btn-muted" type="button" onClick={() => setShowCreateForm(false)}>取消</button>
          </form>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: 20 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 44 }}></th>
              <th>名称</th>
              <th>关联数据源</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {themes.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: "center", color: "#6b7280", padding: 24 }}>
                  暂无主题库，请点击上方按钮创建
                </td>
              </tr>
            )}
            {themes.map((t) => (
              <tr key={t.id} style={{ cursor: "pointer" }} onClick={() => setActiveId(t.id)}>
                <td>
                  <div
                    style={{
                      width: 30,
                      height: 30,
                      borderRadius: "50%",
                      background: t.id === activeId ? "#2563eb" : "#dbeafe",
                      color: t.id === activeId ? "#fff" : "#1d4ed8",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 700,
                      fontSize: 13,
                      flexShrink: 0,
                    }}
                  >
                    {t.name.charAt(0)}
                  </div>
                </td>
                <td>
                  <strong style={{ color: t.id === activeId ? "var(--c-primary)" : undefined }}>
                    {t.name}
                  </strong>
                </td>
                <td style={{ color: "#6b7280", fontSize: 13 }}>
                  {t.data_source_id != null ? `DS #${t.data_source_id}` : "—"}
                </td>
                <td>
                  <span className={`status-pill ${t.status === "active" ? "status-pill-active" : "status-pill-inactive"}`}>
                    {t.status === "active" ? "已发布" : t.status || "草稿"}
                  </span>
                </td>
                <td>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      className="btn btn-primary"
                      style={{ fontSize: 12, padding: "4px 10px" }}
                      onClick={(e) => { e.stopPropagation(); setActiveId(t.id); }}
                    >
                      配置
                    </button>
                    <button
                      className="btn btn-muted"
                      style={{ fontSize: 12, padding: "4px 10px", color: "#6b7280" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      下线
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {activeId && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>
            配置字段
            {activeTheme && (
              <span style={{ fontWeight: 400, color: "#6b7280", marginLeft: 6 }}>— {activeTheme.name}</span>
            )}
          </h3>
          <form onSubmit={addField} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16 }}>
            <div style={{ minWidth: 180 }}>
              <label style={{ fontSize: 14, display: "block", marginBottom: 4 }}>物理表名</label>
              <input
                className="input"
                list="staging-tables"
                value={tableName}
                onChange={(e) => setTableName(e.target.value)}
              />
              <datalist id="staging-tables">
                {stagingTableOptions.map((tn) => (
                  <option key={tn} value={tn} />
                ))}
              </datalist>
            </div>
            <div style={{ minWidth: 160 }}>
              <label style={{ fontSize: 14, display: "block", marginBottom: 4 }}>字段名</label>
              <input className="input" value={fieldName} onChange={(e) => setFieldName(e.target.value)} />
            </div>
            <div style={{ minWidth: 140 }}>
              <label style={{ fontSize: 14, display: "block", marginBottom: 4 }}>中文别名</label>
              <input className="input" value={aliasZh} onChange={(e) => setAliasZh(e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit">添加字段</button>
          </form>

          {fields.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#6b7280", marginBottom: 8 }}>已配置字段</div>
              <div style={{ border: "1px solid var(--c-border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>物理表名</th>
                      <th>字段名</th>
                      <th>中文别名</th>
                      <th>可见性</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fields.map((f) => (
                      <tr key={f.id}>
                        <td style={{ fontFamily: "monospace", fontSize: 12 }}>{f.table_name}</td>
                        <td style={{ fontFamily: "monospace", fontSize: 12 }}>{f.field_name}</td>
                        <td>{f.alias_zh}</td>
                        <td>
                          <span className={`status-pill ${f.visible ? "status-pill-active" : "status-pill-inactive"}`}>
                            {f.visible ? "可见" : "隐藏"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {fields.length === 0 && (
            <p style={{ color: "#6b7280", fontSize: 13 }}>尚未配置字段，请使用上方表单添加。</p>
          )}
        </div>
      )}
    </div>
  );
}
