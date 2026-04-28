import { Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./layouts/AppLayout";
import AdminTicketsPage from "./pages/AdminTicketsPage";
import DashboardPage from "./pages/DashboardPage";
import DataSourcePage from "./pages/DataSourcePage";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";
import ThemeLibraryPage from "./pages/ThemeLibraryPage";
import ChartLibraryPage from "./pages/ChartLibraryPage";
import { useAuthStore } from "./store/auth";

function PrivateRouter() {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <AppLayout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<PrivateRouter />}>
        <Route index element={<ChatPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="library" element={<ChartLibraryPage />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="admin/sources" element={<DataSourcePage />} />
        <Route path="admin/themes" element={<ThemeLibraryPage />} />
        <Route path="admin/tickets" element={<AdminTicketsPage />} />
      </Route>
    </Routes>
  );
}
