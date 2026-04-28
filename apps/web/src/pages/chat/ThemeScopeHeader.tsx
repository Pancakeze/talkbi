import { useMemo, useState } from "react";

import type { ThemeLibrary } from "../../types";

export default function ThemeScopeHeader({
  themes,
  selectedThemeIds,
  onChangeSelectedThemeIds
}: {
  themes: ThemeLibrary[];
  selectedThemeIds: number[];
  onChangeSelectedThemeIds: (next: number[]) => void;
}) {
  const [query, setQuery] = useState("");
  const selectedIdSet = useMemo(() => new Set(selectedThemeIds), [selectedThemeIds]);
  const selected = useMemo(
    () => themes.filter((t) => selectedThemeIds.includes(t.id)),
    [themes, selectedThemeIds]
  );
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? themes.filter((t) => t.name.toLowerCase().includes(q)) : themes;
    return [...list].sort((a, b) => {
      const aSel = selectedIdSet.has(a.id) ? 1 : 0;
      const bSel = selectedIdSet.has(b.id) ? 1 : 0;
      if (aSel !== bSel) return bSel - aSel; // selected first
      return a.name.localeCompare(b.name, "zh-Hans-CN");
    });
  }, [themes, query, selectedIdSet]);

  function remove(id: number) {
    onChangeSelectedThemeIds(selectedThemeIds.filter((x) => x !== id));
  }

  function toggle(id: number) {
    onChangeSelectedThemeIds(
      selectedThemeIds.includes(id)
        ? selectedThemeIds.filter((x) => x !== id)
        : [...selectedThemeIds, id]
    );
  }

  return (
    <div className="card" data-testid="theme-scope">
      <div className="scope-header">
        <div>
          <div className="scope-title">当前分析范围</div>
          <div className="scope-tags" aria-label="已选主题" data-testid="theme-scope-tags">
            {selected.length === 0 ? (
              <span className="muted">未选择主题</span>
            ) : (
              selected.map((t) => (
                <span key={t.id} className="tag" data-testid="theme-scope-tag">
                  {t.name}
                  <button
                    type="button"
                    className="tag-x"
                    aria-label={`移除 ${t.name}`}
                    onClick={() => remove(t.id)}
                    data-testid="theme-scope-tag-remove"
                  >
                    ×
                  </button>
                </span>
              ))
            )}
          </div>
        </div>

        <details className="scope-dropdown">
          <summary className="btn btn-muted" data-testid="theme-scope-trigger">
            选择主题
          </summary>
          <div className="scope-popover">
            <input
              className="input"
              placeholder="搜索主题…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="搜索主题"
              data-testid="theme-scope-search"
            />
            <div className="scope-list" role="listbox" aria-label="主题列表">
              {themes.length === 0 && (
                <div className="muted" style={{ padding: 8 }}>
                  暂无主题库，请先在「主题库管理」中创建
                </div>
              )}
              {themes.length > 0 && filtered.length === 0 && (
                <div className="muted" style={{ padding: 8 }}>
                  无匹配主题
                </div>
              )}
              {filtered.map((t) => (
                <label
                  key={t.id}
                  className="scope-item"
                  data-testid={`theme-scope-item-${t.id}`}
                >
                  <input
                    type="checkbox"
                    checked={selectedThemeIds.includes(t.id)}
                    onChange={() => toggle(t.id)}
                  />
                  <span>{t.name}</span>
                </label>
              ))}
            </div>
            <div className="scope-foot muted" data-testid="theme-scope-foot">
              支持跨主题联合分析 / 已选 {selectedThemeIds.length} 个主题
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}

