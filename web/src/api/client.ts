import axios from "axios";

let _token: string | null = localStorage.getItem("token");

export function setToken(t: string | null) {
  _token = t;
  if (t) localStorage.setItem("token", t);
  else localStorage.removeItem("token");
}
export function getToken() { return _token; }

const api = axios.create({ baseURL: "/", timeout: 15000, headers: { "Content-Type": "application/json" } });

api.interceptors.request.use((c) => {
  if (_token) c.headers.Authorization = `Bearer ${_token}`;
  return c;
});

api.interceptors.response.use((r) => r, (err) => {
  if (err.response?.status === 401) { setToken(null); window.location.href = "/login"; }
  return Promise.reject(err);
});

export default api;

export async function fetchJSON<T>(url: string): Promise<T> {
  const { data } = await api.get<T>(url);
  return data;
}

export async function postJSON<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.post<T>(url, body ?? {});
  return data;
}

export async function putJSON<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.put<T>(url, body ?? {});
  return data;
}

export async function login(username: string, password: string): Promise<boolean> {
  try {
    const { data } = await api.post("/api/auth/login", { username, password });
    setToken(data.token);
    return true;
  } catch { return false; }
}
