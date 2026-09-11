/**
 * lib/api.ts — Client API Hydra ETL
 * Base URL configurée via import.meta.env.VITE_API_URL (défaut: /api via proxy Vite)
 */

const BASE = import.meta.env.VITE_API_URL ?? '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

const get  = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) })
const put  = <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT',  body: JSON.stringify(body) })
const del  = <T>(path: string) => request<T>(path, { method: 'DELETE' })

// ── Types ───────────────────────────────────────────────────────────────────

export interface Project {
  id: string; name: string; description?: string; path: string; created_at: string
}
export interface Workflow {
  id: string; name: string; project_id: string; description?: string
  trigger_type: string; cron?: string; published: boolean; path: string
  layout?: Record<string, unknown>
  yaml_content?: string        // contenu workflow.yaml (GET détail — lecture seule)
}
export interface Run {
  run_id: string
  workflow_name: string
  workflow_path?: string
  status: 'pending' | 'running' | 'success' | 'failed'
  started_at: string; finished_at?: string; duration?: number
  error?: string; steps: StepResult[]
  trigger?: string            // manual | schedule | webhook — source du run
}
export interface StepResult {
  step_name: string
  success: boolean
  duration: number
  error?: string
  logs?: string[]
  skipped?: boolean
  rows_in?: number
  rows_out?: number
  output_sample?: Record<string, unknown>[]
  output_columns?: string[]
}
export interface Environment {
  id: string; name: string; project_id: string; vars: Record<string, string>
}
export interface NodeInfo {
  id: string; name: string
  category: 'source' | 'destination' | 'transformation' | 'action'
  description: string
}
export interface Template {
  id: string; name: string; description: string; category: string; yaml_content: string
}
export interface CLIResult {
  returncode: number; stdout: string; stderr: string; success: boolean
}
export interface JobScaffoldRequest {
  job_name: string; base_dir: string
  source_type: string; source_path: string
  transformations: Array<{ op: string; params: Record<string, unknown> }>
  dest_type: string; dest_path: string; dest_mode?: string
}
export interface JobScaffoldResponse { job_path: string; created: boolean }
export interface JobFilesPayload {
  name: string          // slug → dossier jobs/<name>/
  sources: string       // sources.yaml
  transformations: string
  destinations: string
  pipeline: string
}
export interface WorkflowUpdatePayload extends Partial<Workflow> {
  yaml_content?: string
  jobs?: JobFilesPayload[]   // jobs à matérialiser sur disk (symétrie CLI ↔ Studio)
}

// ── Projects ─────────────────────────────────────────────────────────────────

export const api = {
  health: () => get<{ message: string }>('/health'),

  projects: {
    list: ()                                  => get<Project[]>('/projects'),
    get:  (id: string)                        => get<Project>(`/projects/${id}`),
    create: (body: { name: string; description?: string; project_path?: string }) => post<Project>('/projects', body),
    open:   (path: string, adopt = true)      => post<Project>('/projects/open', { path, adopt }),
    unlist: (id: string)                      => post<{ message: string }>(`/projects/${id}/unlist`, {}),
    delete: (id: string)                      => del<{ message: string }>(`/projects/${id}?remove_files=true`),
  },

  workflows: {
    list:    (projectId?: string)             => get<Workflow[]>(`/workflows${projectId ? `?project_id=${projectId}` : ''}`),
    get:     (id: string, projectId: string)  => get<Workflow>(`/workflows/${id}?project_id=${projectId}`),
    create:  (body: Partial<Workflow>)        => post<Workflow>('/workflows', body),
    update:  (id: string, projectId: string, body: WorkflowUpdatePayload) =>
                                               put<Workflow>(`/workflows/${id}?project_id=${projectId}`, body),
    publish: (id: string, projectId: string) => post<Workflow>(`/workflows/${id}/publish?project_id=${projectId}`, {}),
    delete:  (id: string, projectId: string) => del<{ message: string }>(`/workflows/${id}?project_id=${projectId}`),
  },

  runs: {
    list:    (workflowName?: string)          => get<Run[]>(`/runs${workflowName ? `?workflow_name=${workflowName}` : ''}`),
    get:     (id: string)                     => get<Run>(`/runs/${id}`),
    logs:    (id: string)                     => get<Run>(`/runs/${id}/logs`),
    start:   (body: { workflow_path: string; env?: string; step?: string }) => post<Run>('/runs', body),
    startInline: (body: { hdr_content: string; job_name?: string; work_dir?: string; env?: string; preview_up_to?: number }) =>
                  post<Run>('/runs/inline', body),
    startAction: (body: { node_type: string; command: string; working_dir?: string; timeout?: number; job_name?: string; params?: Record<string, string> }) =>
                  post<Run>('/runs/inline/action', body),
    peek: (body: { dest: Record<string, unknown>; limit: number; work_dir?: string }) =>
                  post<{ columns: string[]; rows: Record<string, unknown>[]; error: string | null }>('/runs/peek', body),
  },

  fs: {
    findJobFolder: (name: string) =>
      get<{ found: boolean; path: string | null }>(`/fs/find-job-folder?name=${encodeURIComponent(name)}`),
  },

  export: {
    save: (body: { content: string; suggested_name: string; fmt: 'csv' | 'txt' }) =>
      post<{ saved: boolean; path: string | null; cancelled: boolean }>('/export/save', body),
  },

  environments: {
    list:   (projectId: string)               => get<Environment[]>(`/environments?project_id=${projectId}`),
    create: (body: { name: string; project_id: string; vars: Record<string, string> }) =>
                                               post<Environment>('/environments', body),
    update: (name: string, projectId: string, vars: Record<string, string>) =>
                                               put<Environment>(`/environments/${name}?project_id=${projectId}`, { vars }),
    delete: (name: string, projectId: string) => del<{ message: string }>(`/environments/${name}?project_id=${projectId}`),
  },

  nodes:     { list: (category?: string)     => get<NodeInfo[]>(`/nodes${category ? `?category=${category}` : ''}`),
  },

  system: {
    info:   ()                      => get<{ platform: string; python_version: string; hydra_version: string; homedir: string; is_windows: boolean }>('/system/info'),
    browse: (type: 'file' | 'directory' | 'save_file', filter?: string) =>
      get<{ path: string | null }>(`/system/browse?type=${type}${filter ? `&filter=${encodeURIComponent(filter)}` : ''}`),
    fsRoots: () => get<{ roots: { name: string; path: string }[] }>(`/fs/roots`),
    fsList: (path: string, dirsOnly?: boolean, ext?: string) =>
      get<{ path: string; parent: string | null; sep: string; entries: { name: string; path: string; is_dir: boolean }[] }>(
        `/fs/list?path=${encodeURIComponent(path)}${dirsOnly ? '&dirs_only=true' : ''}${ext ? `&ext=${encodeURIComponent(ext)}` : ''}`),
  },

  templates: {
    list: () => get<Template[]>('/templates'),
  },

  cli: {
    run: (body: { command: string; args: string[] }) => post<CLIResult>('/jobs/run', body),
  },

  scaffold: {
    job: (body: JobScaffoldRequest) => post<JobScaffoldResponse>('/jobs/scaffold', body),
  },

  jobs: {
    files: (projectId: string, name: string) =>
      get<JobFilesPayload>(`/jobs/files?project_id=${projectId}&name=${encodeURIComponent(name)}`),
    delete: (projectId: string, name: string) =>
      post<{ ok: boolean; message: string }>('/jobs/delete', { project_id: projectId, name }),
    archive: (projectId: string, name: string) =>
      post<{ ok: boolean; message: string; archived_as?: string }>('/jobs/archive', { project_id: projectId, name }),
  },

  transform: {
    scriptPreview: (body: { inputs: string[]; outputs: Record<string, string>; code: string; mode: string; rows: Record<string, unknown>[] }) =>
      post<{ columns: string[]; rows: Record<string, unknown>[]; error: string | null }>('/transform/script/preview', body),
  },

  parameters: {
    get: (projectId: string) =>
      get<{ declarations: Record<string, Record<string, unknown>>; environments: Record<string, Record<string, unknown>> }>(`/parameters?project_id=${encodeURIComponent(projectId)}`),
    save: (body: { project_id: string; declarations: Record<string, Record<string, unknown>>; environments: Record<string, Record<string, unknown>> }) =>
      put<{ declarations: Record<string, Record<string, unknown>>; environments: Record<string, Record<string, unknown>> }>('/parameters', body),
  },

}

