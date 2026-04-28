import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useAuthStore } from "../store/auth";

export default function LoginPage() {
  const token = useAuthStore((s) => s.token);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("analyst123");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (token) {
    return <Navigate to="/chat" replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username, password);
      navigate("/chat", { replace: true });
    } catch {
      setError("登录失败，请检查用户名或密码");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <form className="card" onSubmit={onSubmit} style={{ width: 360 }}>
        <h1 style={{ marginTop: 0 }}>TalkBI</h1>
        <p style={{ color: "#6b7280", fontSize: 14 }}>使用演示账号 analyst / analyst123 或 admin / admin123</p>
        {error && <p style={{ color: "#b91c1c", fontSize: 14 }}>{error}</p>}
        <label style={{ display: "block", marginBottom: 8, fontSize: 14 }}>用户名</label>
        <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        <label style={{ display: "block", margin: "12px 0 8px", fontSize: 14 }}>密码</label>
        <input
          className="input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: "100%", marginTop: 16 }}>
          {loading ? "登录中…" : "登录"}
        </button>
      </form>
    </div>
  );
}
