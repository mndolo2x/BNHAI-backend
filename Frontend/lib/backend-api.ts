export interface ApiPatient {
  patient_id: string
  display_name: string
  date_of_birth: string | null
  record_status: 'active' | 'inactive'
  facility_id: string
}

export interface ApiLoginResponse {
  access_token: string
  token_type: 'bearer' | string
  expires_in: number
}

export interface ApiRoleAssignment {
  facility_id: string
  role: string
}

export interface ApiCurrentUser {
  user_id: string
  username: string
  display_name: string
  is_active: boolean
  assignments: ApiRoleAssignment[]
}

export interface ApiEncounter {
  encounter_id: string
  patient_id: string
  facility_id: string
  clinician_name: string
  encounter_type: string
  status: 'in_progress' | 'completed' | 'cancelled' | string
  started_at: string
  updated_at: string
}

export interface ApiClinicalNote {
  note_id: string
  encounter_id: string
  version: number
  author_name: string
  presenting_complaint: string | null
  status: 'draft' | 'awaiting_review' | 'approved' | string
  created_at: string
  updated_at: string
  submitted_at: string | null
  approved_at: string | null
  approved_by: string | null
}

export interface ApiLabObservation {
  observation_id: string
  report_id: string
  test_code: string
  test_name: string
  value_numeric: number | null
  value_text: string | null
  unit: string | null
  reference_range: string | null
  interpretation: string | null
}

export interface ApiLabReport {
  report_id: string
  patient_id: string
  encounter_id: string | null
  source_system: string
  status: string
  issued_at: string | null
  received_at: string
  updated_at: string
  observations: ApiLabObservation[]
}

export interface ApiFollowUpTask {
  task_id: string
  patient_id: string
  report_id: string | null
  encounter_id: string | null
  description: string
  assigned_to: string | null
  status: string
  due_at: string | null
  outcome: string | null
  created_at: string
  updated_at: string
  closed_at: string | null
}

export interface ApiPatientWorkspace {
  patient: ApiPatient
  encounters: ApiEncounter[]
  clinical_notes: ApiClinicalNote[]
  lab_reports: ApiLabReport[]
  follow_up_tasks: ApiFollowUpTask[]
}

function responseMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    if (detail !== undefined) return JSON.stringify(detail)
  }
  return `API request failed (${status}).`
}

/** Calls the same-origin Next.js proxy; bearer tokens are held in page memory only. */
export async function apiRequest<T>(
  path: string,
  token?: string,
  init: RequestInit = {},
): Promise<T> {
  const safePath = path.replace(/^\/+/, '')
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`/api/backend/${safePath}`, {
      ...init,
      headers,
      cache: 'no-store',
    })
  } catch {
    throw new Error(
      'Could not reach the Next.js API proxy. Check that the frontend and FastAPI backend are running.',
    )
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : await response.text().catch(() => '')

  if (!response.ok) {
  if (response.status === 401 && token) {
    throw new Error('BNHAI_SESSION_EXPIRED')
  }

  throw new Error(responseMessage(payload, response.status))
}

return payload as T
}

export function calculateAge(dateOfBirth: string | null): number | null {
  if (!dateOfBirth) return null
  const birthDate = new Date(`${dateOfBirth}T00:00:00`)
  if (Number.isNaN(birthDate.getTime())) return null
  const now = new Date()
  let age = now.getFullYear() - birthDate.getFullYear()
  const beforeBirthday =
    now.getMonth() < birthDate.getMonth() ||
    (now.getMonth() === birthDate.getMonth() && now.getDate() < birthDate.getDate())
  if (beforeBirthday) age -= 1
  return age >= 0 ? age : null
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Date not recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Date not recorded'
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function getInitials(value: string): string {
  const initials = value
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
  return initials || 'NA'
}
