import { NavLink, Outlet, useNavigate } from "react-router-dom";

import ToastContainer from "../components/Toast";
import { useAuthStore } from "../store/auth";

const BUSINESS_MENU = [
  { to: "/dashboard", label: "仪表盘", icon: "📊" },
  { to: "/library", label: "个人图表库", icon: "🖼️" },
] as const;

const ADMIN_MENU = [
  { to: "/admin/sources", label: "数据源管理", icon: "📦" },
  { to: "/admin/themes", label: "主题库管理", icon: "🔖" },
  { to: "/admin/tickets", label: "AI 异常工单", icon: "🎫" },
] as const;

function RolePill({ role }: { role: string }) {
  const isAdmin = role === "admin";
  return (
    <span className={isAdmin ? "role-pill role-pill-admin" : "role-pill role-pill-analyst"}>
      {isAdmin ? "管理员" : "分析师"}
    </span>
  );
}

export default function AppLayout() {
  const user = useAuthStore((s) => s.currentUser);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const isAdmin = user?.role === "admin";

  return (
    <div className="layout">
      <aside className="sidebar">
        {/* Logo */}
        <div className="sidebar-logo">TalkBI</div>

        {/* User card */}
        <div className="sidebar-user-card">
          <div className="sidebar-avatar">
            {user?.full_name?.charAt(0)?.toUpperCase() ?? "U"}
          </div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{user?.full_name}</div>
            {user?.role && <RolePill role={user.role} />}
          </div>
        </div>

        {/* New analysis CTA */}
        <button
          className="btn btn-primary sidebar-cta"
          onClick={() => navigate("/chat")}
        >
          + 新建分析
        </button>

        {/* Business menu */}
        <nav className="menu">
          <div className="menu-section-label">我的资产</div>
          {BUSINESS_MENU.map(({ to, label, icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : undefined)}>
              <span className="menu-icon">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Admin menu */}
        <nav className="menu">
          <div className="menu-section-label">管理员</div>
          {ADMIN_MENU.filter(({ to }) => isAdmin || to !== "/admin/tickets").map(({ to, label, icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : undefined)}>
              <span className="menu-icon">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="btn btn-muted" onClick={logout} style={{ width: "100%" }}>
            退出登录
          </button>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>

      <ToastContainer />
    </div>
  );
}
