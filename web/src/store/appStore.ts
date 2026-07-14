import { create } from "zustand";

type ThemeMode = "dark" | "light";

interface AppStore {
  theme: ThemeMode;
  sidebarOpen: boolean;
  botRunning: boolean;
  botMode: string;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setBotRunning: (v: boolean) => void;
  setBotMode: (v: string) => void;
}

export const useAppStore = create<AppStore>((set) => ({
  theme: (localStorage.getItem("theme") as ThemeMode) || "dark",
  sidebarOpen: true,
  botRunning: false,
  botMode: "online",
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === "dark" ? "light" : "dark";
      localStorage.setItem("theme", next);
      return { theme: next };
    }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setBotRunning: (botRunning) => set({ botRunning }),
  setBotMode: (botMode) => set({ botMode }),
}));
