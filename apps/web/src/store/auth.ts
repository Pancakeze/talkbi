import { create } from "zustand";

import api from "../api/client";
import type { LoginResponse, User } from "../types";

type AuthState = {
  token: string | null;
  currentUser: User | null;
  login: (username: string, password: string) => Promise<void>;
  loadMe: () => Promise<void>;
  logout: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem("talkbi_token"),
  currentUser: null,
  login: async (username, password) => {
    const { data } = await api.post<LoginResponse>("/auth/login", { username, password });
    localStorage.setItem("talkbi_token", data.access_token);
    set({ token: data.access_token });
    const me = await api.get<User>("/me");
    set({ currentUser: me.data });
  },
  loadMe: async () => {
    const token = localStorage.getItem("talkbi_token");
    if (!token) return;
    const { data } = await api.get<User>("/me");
    set({ token, currentUser: data });
  },
  logout: () => {
    localStorage.removeItem("talkbi_token");
    set({ token: null, currentUser: null });
  }
}));
