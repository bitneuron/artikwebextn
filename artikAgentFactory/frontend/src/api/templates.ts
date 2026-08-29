import { api } from "./client";
import { Template } from "./types";

export const templatesApi = {
  list: () => api.get<Template[]>("/api/templates"),
  get: (id: string) => api.get<Template>(`/api/templates/${id}`),
};
