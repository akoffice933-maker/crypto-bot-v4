import axios from "axios";

const api = axios.create({
  baseURL: "/",
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export default api;

export async function fetchJSON<T>(url: string): Promise<T> {
  const { data } = await api.get<T>(url);
  return data;
}

export async function putJSON<T>(url: string, body: unknown): Promise<T> {
  const { data } = await api.put<T>(url, body);
  return data;
}

export async function postJSON<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.post<T>(url, body ?? {});
  return data;
}
