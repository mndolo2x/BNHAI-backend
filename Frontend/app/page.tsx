'use client'

import { useMemo, useRef, useState } from 'react'
import { apiRequest, calculateAge, formatDateTime, getInitials, type ApiCurrentUser, type ApiLoginResponse, type ApiPatient, type ApiPatientWorkspace, type ApiFollowUpTask } from '@/lib/backend-api'

import {
  Activity, AlertCircle, Archive, ArrowRight, Bell, BookOpen, CalendarClock, Check, ChevronDown, ChevronLeft, ClipboardList, Clock3, FileCheck2, FileText, Filter, FlaskConical, HelpCircle, History, Home, LayoutDashboard, Link2, ListChecks, Menu, MessageSquareText, MoreHorizontal, PanelLeftClose, Plus, RefreshCw, Search, Settings, ShieldCheck, SlidersHorizontal, Stethoscope, UserRound, Users, Wifi, X, Zap,
} from 'lucide-react'

type PageKey = 'Dashboard' | 'Patients' | 'Encounters' | 'Laboratory Results' | 'Follow-up Queue' | 'Notifications' | 'Clinical Copilot' | 'AI Activity' | 'Audit Log' | 'Users and Roles' | 'Facilities' | 'Integrations' | 'Reports' | 'Settings'

type Patient = { id: string; name: string; age: number | null; sex: string; facility: string; last: string; status: string; initials: string }
const demoPatients: Patient[] = [
  { id: 'BW-004821', name: 'Naledi Molefe', age: 34, sex: 'Female', facility: 'Princess Marina Hospital', last: '18 Oct 2026', status: 'Active', initials: 'NM' },
  { id: 'BW-004798', name: 'Thabo Kgosidintsi', age: 58, sex: 'Male', facility: 'Nyangabwe Referral Hospital', last: '16 Oct 2026', status: 'Active', initials: 'TK' },
  { id: 'BW-004756', name: 'Boitumelo Dube', age: 27, sex: 'Female', facility: 'Molepolole General Hospital', last: '14 Oct 2026', status: 'Active', initials: 'BD' },
  { id: 'BW-004703', name: 'Kagiso Rantao', age: 46, sex: 'Male', facility: 'Princess Marina Hospital', last: '11 Oct 2026', status: 'Pending review', initials: 'KR' },
  { id: 'BW-004669', name: 'Masego Seboni', age: 71, sex: 'Female', facility: 'Nyangabwe Referral Hospital', last: '08 Oct 2026', status: 'Active', initials: 'MS' },
  { id: 'BW-004612', name: 'Otsile Gasebalwe', age: 41, sex: 'Male', facility: 'Molepolole General Hospital', last: '04 Oct 2026', status: 'Inactive', initials: 'OG' },
]
const labs = [
  { id: 'LAB-10284', patient: 'Naledi Molefe', test: 'Full blood count', value: '12.8', unit: 'g/dL', range: '12.0–16.0', date: '18 Oct 2026', status: 'Awaiting review' },
  { id: 'LAB-10279', patient: 'Thabo Kgosidintsi', test: 'Serum creatinine', value: '98', unit: 'µmol/L', range: '60–110', date: '17 Oct 2026', status: 'Reviewed' },
  { id: 'LAB-10273', patient: 'Boitumelo Dube', test: 'Malaria RDT', value: 'Negative', unit: 'qualitative', range: 'Negative', date: '16 Oct 2026', status: 'Follow-up required' },
  { id: 'LAB-10261', patient: 'Masego Seboni', test: 'HbA1c', value: '7.2', unit: '%', range: '4.0–6.5', date: '14 Oct 2026', status: 'Awaiting review' },
]
type Task = { id: string; patient: string; link: string; description: string; owner: string; due: string; status: string; outcome?: string }
function mapFollowUpTask(record: ApiFollowUpTask, patients: Patient[]): Task {
  const linkedPatient = patients.find(p => p.id === record.patient_id)

  const statusLabels: Record<string, string> = {
    open: 'Open',
    assigned: 'Assigned',
    in_progress: 'In progress',
    completed: 'Completed',
    escalated: 'Escalated',
    cancelled: 'Cancelled',
  }

  return {
    id: record.task_id,
    patient: linkedPatient?.name || record.patient_id,
    link: record.report_id || record.encounter_id || '—',
    description: record.description,
    owner: record.assigned_to || 'Unassigned',
    due: record.due_at ? formatDateTime(record.due_at) : 'Not set',
    status: statusLabels[record.status] || record.status,
    outcome: record.outcome || undefined,
  }
}
const tasks: Task[] = [
  { id: 'TASK-0087', patient: 'Boitumelo Dube', link: 'LAB-10273', description: 'Review malaria test result with patient', owner: 'Unassigned', due: '20 Oct 2026', status: 'Open' },
  { id: 'TASK-0086', patient: 'Naledi Molefe', link: 'ENC-24891', description: 'Complete clinical note review', owner: 'Dr. K. Moagi', due: '19 Oct 2026', status: 'In progress' },
  { id: 'TASK-0084', patient: 'Masego Seboni', link: 'LAB-10261', description: 'Arrange follow-up consultation', owner: 'S. Bapela', due: '15 Oct 2026', status: 'Overdue' },
]

const navGroups = [
  { label: 'WORKSPACE', items: [['Dashboard', LayoutDashboard], ['Patients', Users], ['Encounters', Stethoscope], ['Laboratory Results', FlaskConical], ['Follow-up Queue', ListChecks], ['Notifications', Bell]] },
  { label: 'INTELLIGENCE', items: [['Clinical Copilot', MessageSquareText], ['AI Activity', Activity]] },
  { label: 'ADMINISTRATION', items: [['Audit Log', History], ['Users and Roles', ShieldCheck], ['Facilities', Home], ['Integrations', Link2], ['Reports', FileText], ['Settings', Settings]] },
] as const

function Status({ children }: { children: string }) { return <span className="status">{children}</span> }
function Metric({ icon: Icon, label, value, detail, onClick }: { icon: typeof Activity; label: string; value: string; detail: string; onClick: () => void }) { return <button className="metric" onClick={onClick}><span className="metric-icon"><Icon /></span><span><strong>{value}</strong><small>{label}</small><em>{detail}</em></span><ArrowRight className="metric-arrow" /></button> }

export default function Page() {
  const [page, setPage] = useState<PageKey>('Dashboard')
  const [patient, setPatient] = useState<Patient>(demoPatients[0])
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [labStatus, setLabStatus] = useState('All statuses')
  const [taskState, setTaskState] = useState<Task[]>(tasks)
  const [apiFollowUps, setApiFollowUps] = useState<ApiFollowUpTask[]>([])
  const [followUpsLoading, setFollowUpsLoading] = useState(false)
  const [followUpsError, setFollowUpsError] = useState('')
  const [taskFilter, setTaskFilter] = useState('All statuses')
  const [selectedLab, setSelectedLab] = useState<(typeof labs)[number] | null>(null)
  const [encounterEditor, setEncounterEditor] = useState(false)
  const [noteText, setNoteText] = useState('')
  const [noteSaved, setNoteSaved] = useState(false)
  const [copilotOpen, setCopilotOpen] = useState(false)
  const [draft, setDraft] = useState(false)
  const [notice, setNotice] = useState('')
  const [mobileNav, setMobileNav] = useState(false)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const sessionVersion = useRef(0)
  const [currentUser, setCurrentUser] = useState<ApiCurrentUser | null>(null)
  const [loginUsername, setLoginUsername] = useState('facility_admin_demo')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [apiPatients, setApiPatients] = useState<Patient[]>([])
  const [patientsLoading, setPatientsLoading] = useState(false)
  const [patientsError, setPatientsError] = useState('')
  const [patientStatusFilter, setPatientStatusFilter] = useState('All statuses')
  const [facilityFilter, setFacilityFilter] = useState('All facilities')
  const [workspaceData, setWorkspaceData] = useState<ApiPatientWorkspace | null>(null)
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const [workspaceError, setWorkspaceError] = useState('')

  const filteredPatients = useMemo(() => apiPatients.filter(p =>
    `${p.id} ${p.name}`.toLowerCase().includes(query.toLowerCase()) &&
    (patientStatusFilter === 'All statuses' || p.status === patientStatusFilter) &&
    (facilityFilter === 'All facilities' || p.facility === facilityFilter)
  ), [query, apiPatients, patientStatusFilter, facilityFilter])
  const filteredLabs = useMemo(() => labs.filter(l => (labStatus === 'All statuses' || l.status === labStatus) && `${l.id} ${l.patient} ${l.test}`.toLowerCase().includes(query.toLowerCase())), [query, labStatus])
  const mappedFollowUpTasks = useMemo(
  () => apiFollowUps.map(record => mapFollowUpTask(record, apiPatients)),
  [apiFollowUps, apiPatients]

)
  const showNotice = (text: string) => { setNotice(text); window.setTimeout(() => setNotice(''), 2600) }
  function handleSessionExpired(error: unknown, requestSession: number): boolean {
  if (
    error instanceof Error &&
    error.message === 'BNHAI_SESSION_EXPIRED'
  ) {
    if (requestSession === sessionVersion.current) {
      handleLogout()
      setLoginError('Your session has expired. Please sign in again.')
    }
    return true
  }

  return false
}

  const activeAssignment = currentUser?.assignments[0]
  const userInitials = currentUser ? getInitials(currentUser.display_name) : 'BN'
  const userRoleLabel = currentUser?.assignments.map(a => a.role.replace(/_/g, ' ')).join(' · ') || 'No role assigned'

  async function loadPatients(token: string) {
  const requestSession = sessionVersion.current

  setPatientsLoading(true)
  setPatientsError('')

  try {
    const records = await apiRequest<ApiPatient[]>(
      'api/v1/patients',
      token
    )

    if (requestSession !== sessionVersion.current) return

    setApiPatients(records.map(record => ({
      id: record.patient_id,
      name: record.display_name,
      age: calculateAge(record.date_of_birth),
      sex: 'Not recorded',
      facility: record.facility_id,
      last: 'Not available',
      status: record.record_status === 'active' ? 'Active' : 'Inactive',
      initials: getInitials(record.display_name),
    })))

  } catch (error) {
    if (requestSession !== sessionVersion.current) return

    if (handleSessionExpired(error, requestSession)) return

    setPatientsError(
      error instanceof Error
        ? error.message
        : 'Unable to load patients.'
    )

  } finally {
    if (requestSession === sessionVersion.current) {
      setPatientsLoading(false)
    }
  }
}
  async function loadFollowUps(token: string) {
  const requestSession = sessionVersion.current

  setFollowUpsLoading(true)
  setFollowUpsError('')

  try {
    const records = await apiRequest<ApiFollowUpTask[]>(
      'api/v1/follow-ups',
      token
    )

    if (requestSession !== sessionVersion.current) return

    setApiFollowUps(records)
  } catch (error) {
  if (requestSession !== sessionVersion.current) return

  if (handleSessionExpired(error, requestSession)) return

  setFollowUpsError(
    error instanceof Error
      ? error.message
      : 'Unable to load follow-up tasks.'
    )
  } finally {
    if (requestSession === sessionVersion.current) {
      setFollowUpsLoading(false)
    }
  }
}
async function updateFollowUpStatus(taskId: string, nextStatus: string) {
  if (!accessToken) {
    showNotice('Please sign in again.')
    return
  }

  const requestSession = sessionVersion.current

  try {
    const updated = await apiRequest<ApiFollowUpTask>(
      `api/v1/follow-ups/${encodeURIComponent(taskId)}`,
      accessToken,
      {
        method: 'PATCH',
        body: JSON.stringify({ status: nextStatus }),
      }
    )

    if (requestSession !== sessionVersion.current) return

    setApiFollowUps(current =>
      current.map(task =>
        task.task_id === taskId ? updated : task
      )
    )

    showNotice('Follow-up status saved successfully.')
  } catch (error) {
    if (requestSession !== sessionVersion.current) return

    if (handleSessionExpired(error, requestSession)) return

    showNotice(
      error instanceof Error
        ? error.message
        : 'Unable to update follow-up.'
    )
  }
}
async function createFollowUpTask(description: string) {
  if (!accessToken) {
    showNotice('Please sign in again.')
    return
  }

  const requestSession = sessionVersion.current

  const selectedPatient =
    apiPatients.find(p => p.id === patient.id) ?? apiPatients[0]

  if (!selectedPatient) {
    showNotice('No backend patient is available.')
    return
  }

  try {
    const created = await apiRequest<ApiFollowUpTask>(
      'api/v1/follow-ups',
      accessToken,
      {
        method: 'POST',
        body: JSON.stringify({
          patient_id: selectedPatient.id,
          description,
        }),
      }
        )

    if (requestSession !== sessionVersion.current) return

    setApiFollowUps(current => [created, ...current])

    showNotice('Follow-up task created successfully.')
  } catch (error) {
  if (requestSession !== sessionVersion.current) return

  if (handleSessionExpired(error, requestSession)) return

  showNotice(
    error instanceof Error
      ? error.message
      : 'Unable to create follow-up task.'
  )
}
}
  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
  event.preventDefault()

  sessionVersion.current += 1
  const requestSession = sessionVersion.current

  setLoginBusy(true)
  setLoginError('')
    try {
      const login = await apiRequest<ApiLoginResponse>('api/v1/auth/login', undefined, {
        method: 'POST',
        body: JSON.stringify({ username: loginUsername.trim(), password: loginPassword }),
      })
      const user = await apiRequest<ApiCurrentUser>('api/v1/auth/me', login.access_token)
      const records = await apiRequest<ApiPatient[]>('api/v1/patients', login.access_token)
      const mappedPatients: Patient[] = records.map(record => ({
        id: record.patient_id,
        name: record.display_name,
        age: calculateAge(record.date_of_birth),
        sex: 'Not recorded',
        facility: record.facility_id,
        last: 'Not available',
        status: record.record_status === 'active' ? 'Active' : 'Inactive',
        initials: getInitials(record.display_name),
            }))

      if (requestSession !== sessionVersion.current) return

      setAccessToken(login.access_token)
      setCurrentUser(user)
      setApiPatients(mappedPatients)
      await loadFollowUps(login.access_token)

      if (requestSession !== sessionVersion.current) return

      setLoginPassword('')
      setPage('Patients')
      setWorkspaceOpen(false)
      setWorkspaceData(null)
      setPatientsError('')
      setNotice('Connected to the local FastAPI patient API')
      window.setTimeout(() => setNotice(''), 2600)
    } catch (error) {
  if (requestSession !== sessionVersion.current) return

  setLoginError(
    error instanceof Error
      ? error.message
      : 'Login failed. Check the backend server and your credentials.'
  )
} finally {
  if (requestSession === sessionVersion.current) {
    setLoginBusy(false)
  }
}
  }


  function handleLogout() {
  sessionVersion.current += 1

  setAccessToken(null)
  setCurrentUser(null)
  setApiPatients([])
  setApiFollowUps([])
  setWorkspaceData(null)
  setWorkspaceOpen(false)
  setWorkspaceLoading(false)
  setWorkspaceError('')
  setPatientsError('')
  setFollowUpsError('')
  setFollowUpsLoading(false)
  setPatient(demoPatients[0])
  setSelectedLab(null)
  setNoteText('')
  setNoteSaved(false)
  setEncounterEditor(false)
  setCopilotOpen(false)
  setDraft(false)
  setLoginPassword('')
  setLoginError('')
  setQuery('')
  setPage('Dashboard')

  showNotice('Signed out. Your session data has been cleared.')
}

  async function openPatient(p: Patient) {
    const requestSession = sessionVersion.current
    setPatient(p)
    setWorkspaceData(null)
    setWorkspaceError('')
    setWorkspaceOpen(true)
    setWorkspaceLoading(true)
    setPage('Patients')
    setQuery('')
    if (!accessToken) {
      setWorkspaceError('Your session has ended. Sign in again to load this workspace.')
      setWorkspaceLoading(false)
      return
    }
    try {
      const workspace = await apiRequest<ApiPatientWorkspace>(
  `api/v1/patients/${encodeURIComponent(p.id)}/workspace`,
  accessToken
)

if (requestSession !== sessionVersion.current) return

setWorkspaceData(workspace)
    } catch (error) {
  if (requestSession === sessionVersion.current) {
    if (handleSessionExpired(error, requestSession)) return

    setWorkspaceError(
      error instanceof Error
        ? error.message
        : 'Unable to load this patient workspace.'
    )
  }
} finally {
    if (requestSession === sessionVersion.current) {
      setWorkspaceLoading(false)
    }
  }
}

  function Dashboard() { return <>
    <PageHeader eyebrow="LOCAL DEVELOPMENT OVERVIEW" title={`Welcome, ${currentUser?.display_name || 'user'}`} subtitle="The patient directory and workspace use live local API data. Other dashboard metrics are still prototype examples." actions={<button className="button primary" onClick={() => setPage('Encounters')}><Plus /> Start encounter</button>} />
    <section className="metric-grid">
      <Metric icon={Stethoscope} label="Encounters in progress" value="4" detail="2 assigned to you" onClick={() => setPage('Encounters')} />
      <Metric icon={FileCheck2} label="Notes awaiting review" value="7" detail="3 updated today" onClick={() => setPage('Encounters')} />
      <Metric icon={FlaskConical} label="Results awaiting review" value="12" detail="4 require follow-up" onClick={() => setPage('Laboratory Results')} />
      <Metric icon={Clock3} label="Outstanding follow-ups" value="9" detail="2 overdue" onClick={() => setPage('Follow-up Queue')} />
    </section>
    <div className="dashboard-grid"><section className="panel"><div className="panel-head"><div><p className="eyebrow">ASSIGNED WORK</p><h2>My work queue</h2></div><button className="text-button" onClick={() => setPage('Follow-up Queue')}>View all <ArrowRight /></button></div><div className="work-list">{tasks.map(t => <button key={t.id} className="work-row" onClick={() => setPage('Follow-up Queue')}><span className="work-icon"><ClipboardList /></span><span className="work-copy"><strong>{t.description}</strong><small>{t.patient} · {t.id}</small></span><span className="work-date"><Status>{t.status}</Status><small>Due {t.due}</small></span><ChevronDown className="chevron" /></button>)}</div></section><section className="panel activity-panel"><div className="panel-head"><div><p className="eyebrow">RECENT ACTIVITY</p><h2>System activity</h2></div><button className="icon-button" aria-label="Refresh" onClick={() => showNotice('Activity refreshed')}><RefreshCw /></button></div><div className="activity-list">{[['Clinical note submitted', 'Naledi Molefe · ENC-24891', '08:42'], ['Result received', 'Full blood count · LAB-10284', '08:18'], ['Task assigned', 'Thabo Kgosidintsi · TASK-0086', 'Yesterday'], ['Patient record updated', 'Kagiso Rantao · BW-004703', 'Yesterday']].map(([a,b,c]) => <div className="activity-row" key={a}><span className="activity-dot" /><span><strong>{a}</strong><small>{b}</small></span><time>{c}</time></div>)}</div></section></div>
    <section className="quick-actions"><p className="eyebrow">QUICK ACTIONS</p><div>{[['Find a patient', Search, 'Patients'], ['Review laboratory results', FlaskConical, 'Laboratory Results'], ['Open follow-up tasks', ListChecks, 'Follow-up Queue'], ['View notifications', Bell, 'Notifications']].map(([label, Icon, target]) => <button key={label as string} onClick={() => setPage(target as PageKey)}><Icon /><span>{label as string}</span><ArrowRight /></button>)}</div></section>
  </> }

  function Patients() {
    const facilityOptions = Array.from(new Set(apiPatients.map(p => p.facility))).sort()
    return <>
      <PageHeader eyebrow="WORKSPACE / PATIENTS · LIVE API" title="Patient directory" subtitle="Records below are loaded from your local FastAPI backend and are limited by your assigned facility." actions={<><button className="button secondary" onClick={() => accessToken && loadPatients(accessToken)} disabled={patientsLoading}><RefreshCw /> Refresh</button><button className="button primary" onClick={() => showNotice('Patient creation is not connected in this milestone. No record was created.')}><Plus /> Add patient</button></>} />
      <div className="toolbar"><div className="searchbox"><Search /><input placeholder="Search patient name or ID" value={query} onChange={e => setQuery(e.target.value)} /></div><select value={facilityFilter} onChange={e => setFacilityFilter(e.target.value)} aria-label="Facility filter"><option>All facilities</option>{facilityOptions.map(facility => <option key={facility}>{facility}</option>)}</select><select value={patientStatusFilter} onChange={e => setPatientStatusFilter(e.target.value)} aria-label="Status filter"><option>All statuses</option><option>Active</option><option>Inactive</option></select><button className="button secondary" onClick={() => { setQuery(''); setFacilityFilter('All facilities'); setPatientStatusFilter('All statuses') }}><X /> Clear</button></div>
      {patientsLoading ? <section className="panel" role="status">Loading patient records from the local API…</section> : patientsError ? <section className="panel" role="alert"><div className="panel-head"><div><p className="eyebrow">PATIENT API ERROR</p><h2>Could not load patient records</h2></div><AlertCircle /></div><p className="ai-copy">{patientsError}</p><button className="button primary" onClick={() => accessToken && loadPatients(accessToken)}><RefreshCw /> Try again</button></section> : <DataTable headers={['Patient ID', 'Patient', 'Demographics', 'Facility ID', 'Last encounter', 'Record status', '']} rows={filteredPatients.map(p => [<code key="id">{p.id}</code>, <button key="name" className="table-link" onClick={() => void openPatient(p)}><span className="avatar">{p.initials}</span>{p.name}</button>, `${p.age === null ? 'Age not recorded' : `${p.age} years`} · ${p.sex}`, p.facility, p.last, <Status key="status">{p.status}</Status>, <button className="icon-button" aria-label={`Open ${p.name}`} onClick={() => void openPatient(p)}><ArrowRight /></button>])} empty="No patients match your search or filters." />}
      <p className="api-footnote">Connected data: patient ID, display name, date of birth when available, record status and facility ID. The current patient-directory API does not provide sex or last-encounter date.</p>
    </>
  }
  function PatientWorkspace() {
    if (workspaceLoading) return <><button className="back-link" onClick={() => { setWorkspaceOpen(false); setPage('Patients') }}><ChevronLeft /> Back to patient directory</button><section className="panel" role="status"><RefreshCw /> Loading patient workspace from FastAPI…</section></>
    if (workspaceError || !workspaceData) return <><button className="back-link" onClick={() => { setWorkspaceOpen(false); setPage('Patients') }}><ChevronLeft /> Back to patient directory</button><section className="panel" role="alert"><div className="panel-head"><div><p className="eyebrow">PATIENT WORKSPACE</p><h2>Workspace could not be loaded</h2></div><AlertCircle /></div><p className="ai-copy">{workspaceError || 'No workspace data is available.'}</p><p className="ai-copy">The backend requires a role with clinical-read access at this patient’s facility. No clinical summary has been generated.</p><div className="copilot-actions"><button className="button primary" onClick={() => void openPatient(patient)}><RefreshCw /> Retry</button><button className="button secondary" onClick={() => { setWorkspaceOpen(false); setPage('Patients') }}>Return to directory</button></div></section></>

    const record = workspaceData.patient
    const timelineEntries = [
      ...workspaceData.encounters.map(item => ({ id: item.encounter_id, when: item.started_at, title: `${item.encounter_type} encounter`, detail: `${item.encounter_id} · ${item.clinician_name}`, status: item.status.replace(/_/g, ' ') })),
      ...workspaceData.clinical_notes.map(item => ({ id: item.note_id, when: item.created_at, title: `Clinical note · version ${item.version}`, detail: `${item.author_name} · ${item.encounter_id}`, status: item.status.replace(/_/g, ' ') })),
      ...workspaceData.lab_reports.map(item => ({ id: item.report_id, when: item.received_at, title: `Laboratory report · ${item.report_id}`, detail: `${item.source_system} · ${item.observations.map(observation => observation.test_name).join(', ') || 'No observations listed'}`, status: item.status.replace(/_/g, ' ') })),
      ...workspaceData.follow_up_tasks.map(item => ({ id: item.task_id, when: item.created_at, title: item.description, detail: `${item.task_id}${item.due_at ? ` · Due ${formatDateTime(item.due_at)}` : ''}`, status: item.status.replace(/_/g, ' ') })),
    ].sort((a, b) => new Date(b.when).getTime() - new Date(a.when).getTime())
    const linkedCount = workspaceData.encounters.length + workspaceData.clinical_notes.length + workspaceData.lab_reports.length + workspaceData.follow_up_tasks.length

    return <>
      <button className="back-link" onClick={() => { setWorkspaceOpen(false); setWorkspaceData(null); setPage('Patients') }}><ChevronLeft /> Back to patient directory</button>
      <section className="patient-header"><div className="large-avatar">{getInitials(record.display_name)}</div><div><p className="eyebrow">PATIENT WORKSPACE · SYNTHETIC BACKEND RECORD</p><h1>{record.display_name}</h1><p className="patient-meta"><code>{record.patient_id}</code><span>{calculateAge(record.date_of_birth) === null ? 'Age not recorded' : `${calculateAge(record.date_of_birth)} years`}</span><span>{record.record_status}</span><span>{record.facility_id}</span></p></div><div className="patient-actions"><Status>{record.record_status}</Status><button className="button secondary" onClick={() => setCopilotOpen(true)}><MessageSquareText /> Clinical Copilot</button></div></section>
      <nav className="tabs"><button className="active">Overview</button><button onClick={() => showNotice('The live record timeline is displayed below.')}>Timeline</button><button onClick={() => showNotice(`${workspaceData.encounters.length} encounter(s) loaded from the backend.`)}>Encounters ({workspaceData.encounters.length})</button><button onClick={() => showNotice(`${workspaceData.lab_reports.length} laboratory report(s) loaded from the backend.`)}>Laboratory results ({workspaceData.lab_reports.length})</button><button onClick={() => showNotice(`${workspaceData.clinical_notes.length} clinical note version(s) loaded from the backend.`)}>Clinical notes ({workspaceData.clinical_notes.length})</button><button onClick={() => showNotice(`${workspaceData.follow_up_tasks.length} follow-up task(s) loaded from the backend.`)}>Follow-ups ({workspaceData.follow_up_tasks.length})</button></nav>
      <div className="workspace-grid"><div className="workspace-main"><section className="panel"><div className="panel-head"><div><p className="eyebrow">PATIENT OVERVIEW</p><h2>Available backend records</h2></div><small>Record status: {record.record_status}</small></div><div className="info-grid"><Info label="Encounters" value={String(workspaceData.encounters.length)} /><Info label="Clinical note versions" value={String(workspaceData.clinical_notes.length)} /><Info label="Laboratory reports" value={String(workspaceData.lab_reports.length)} /><Info label="Follow-up tasks" value={String(workspaceData.follow_up_tasks.length)} /><Info label="Problem list" value="Not represented by the current API" /><Info label="Medications and allergies" value="Not represented by the current API" /></div></section>
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">SOURCE RECORDS</p><h2>Clinical timeline</h2></div><small>{linkedCount} linked record(s)</small></div>{timelineEntries.length ? <div className="timeline">{timelineEntries.map(item => <div key={`${item.id}-${item.title}`}><time>{formatDateTime(item.when)}</time><strong>{item.title}</strong><span>{item.detail}</span><span><Status>{item.status}</Status></span></div>)}</div> : <div className="empty-state"><FileText /><h2>No linked records</h2><p>The API returned no encounters, clinical notes, laboratory reports or follow-up tasks for this patient. This does not imply anything about the patient's health.</p></div>}</section></div>
      <aside className="panel follow-panel"><div className="panel-head"><div><p className="eyebrow">FOLLOW-UP TASKS</p><h2>Open items</h2></div><ListChecks /></div>{workspaceData.follow_up_tasks.length ? workspaceData.follow_up_tasks.map(task => <div className="mini-task" key={task.task_id}><Status>{task.status.replace(/_/g, ' ')}</Status><strong>{task.description}</strong><small>{task.task_id} · {task.assigned_to || 'Unassigned'}</small><small>{task.due_at ? `Due ${formatDateTime(task.due_at)}` : 'No due date recorded'}</small></div>) : <p className="ai-copy">No follow-up tasks are linked in this workspace.</p>}<button className="button secondary full" onClick={() => showNotice('Follow-up creation and editing are not connected in this milestone. No task was changed.')}>Manage follow-ups <ArrowRight /></button></aside></div>
      {copilotOpen && <Copilot onClose={() => setCopilotOpen(false)} showNotice={showNotice} />}
    </>
  }
  function Copilot({ onClose, showNotice }: { onClose: () => void; showNotice: (s: string) => void }) {
    const sourceCount = workspaceData ? workspaceData.encounters.length + workspaceData.clinical_notes.length + workspaceData.lab_reports.length + workspaceData.follow_up_tasks.length : 0
    return <div className="copilot-overlay"><aside className="copilot"><div className="copilot-head"><div><p className="eyebrow">CLINICAL COPILOT</p><h2>Contextual assistance</h2></div><button className="icon-button" aria-label="Close clinical copilot" onClick={onClose}><X /></button></div><div className="ai-notice"><AlertCircle /> AI SERVICE NOT CONNECTED — NO CLINICAL OUTPUT</div><section><p className="eyebrow">PATIENT SUMMARY</p><p className="ai-copy">The workspace loaded {sourceCount} related record(s) from the local API. This interface is not yet connected to an AI model, so it has not generated a patient summary, diagnosis, or treatment recommendation.</p><button className="button secondary full" onClick={() => showNotice('No AI service is connected. No summary or clinical draft was generated.')}><Zap /> Check AI connection</button></section><section><p className="eyebrow">AVAILABLE SOURCE RECORDS</p><div className="source-list">{workspaceData?.encounters.map(item => <span key={item.encounter_id}><FileText /> {item.encounter_id} · Encounter</span>)}{workspaceData?.clinical_notes.map(item => <span key={item.note_id}><FileText /> {item.note_id} · Clinical note v{item.version}</span>)}{workspaceData?.lab_reports.map(item => <span key={item.report_id}><FlaskConical /> {item.report_id} · Laboratory report</span>)}{workspaceData?.follow_up_tasks.map(item => <span key={item.task_id}><ClipboardList /> {item.task_id} · Follow-up task</span>)}{sourceCount === 0 && <span><AlertCircle /> No linked source records were returned.</span>}</div></section><section><p className="eyebrow">SAFETY STATUS</p><p className="ai-copy">No AI output has been created or inserted into a clinical note. Any future generated content must remain a draft with explicit source references and human review.</p></section></aside></div>
  }
  function SparkIcon() { return <Zap /> }
  function Info({ label, value }: { label: string; value: string }) { return <div className="info"><small>{label}</small><strong>{value}</strong></div> }

  function Labs() { return <><PageHeader eyebrow="WORKSPACE / LABORATORY" title="Laboratory results" subtitle="Review supplied results and manage linked follow-up work." actions={<button className="button secondary" onClick={() => showNotice('Queue refreshed')}><RefreshCw /> Refresh queue</button>} /><div className="toolbar"><div className="searchbox"><Search /><input placeholder="Search result ID, patient or test" value={query} onChange={e => setQuery(e.target.value)} /></div><select value={labStatus} onChange={e => setLabStatus(e.target.value)} aria-label="Result status"><option>All statuses</option><option>Awaiting review</option><option>Reviewed</option><option>Follow-up required</option></select><button className="button secondary"><Filter /> More filters</button></div><DataTable headers={['Result ID', 'Patient', 'Test', 'Result', 'Reference range', 'Report date', 'Status', '']} rows={filteredLabs.map(l => [<code key="id">{l.id}</code>, <button className="table-link" key="patient" onClick={() => { setPatient(demoPatients.find(p => p.name === l.patient) || demoPatients[0]); setPage('Patients') }}>{l.patient}</button>, l.test, <strong key="value">{l.value} <small>{l.unit}</small></strong>, l.range, l.date, <Status key="status">{l.status}</Status>, <button className="icon-button" aria-label={`Open ${l.id}`} onClick={() => setSelectedLab(l)}><ArrowRight /></button>])} empty="No laboratory results match your filters." />{selectedLab && <section className="panel detail-panel"><div className="panel-head"><div><p className="eyebrow">RESULT DETAIL · SYNTHETIC</p><h2>{selectedLab.test}</h2></div><button className="icon-button" aria-label="Close result detail" onClick={() => setSelectedLab(null)}><X /></button></div><div className="info-grid"><Info label="Result ID" value={selectedLab.id} /><Info label="Patient" value={selectedLab.patient} /><Info label="Reported" value={selectedLab.date} /><Info label="Interpretation" value={`${selectedLab.value} ${selectedLab.unit} · reference ${selectedLab.range}`} /></div><div className="detail-actions"><button className="button primary" onClick={() => { setSelectedLab(null); setTaskState([...taskState, { id: `TASK-00${88 + taskState.length}`, patient: selectedLab.patient, link: selectedLab.id, description: `Follow up ${selectedLab.test} result`, owner: 'Unassigned', due: '22 Oct 2026', status: 'Open' }]); setPage('Follow-up Queue'); showNotice('Follow-up task created') }}><Plus /> Create follow-up</button><button className="button secondary" onClick={() => showNotice(`${selectedLab.id} marked for clinician review`)}><Check /> Mark reviewed</button></div></section>}</> }

 
 
function FollowUps() {
  const now = Date.now()
  const weekFromNow = now + 7 * 24 * 60 * 60 * 1000

  const isActiveTask = (status: string) =>
    status !== 'completed' && status !== 'cancelled'

  const openCount = apiFollowUps.filter(
    task => task.status === 'open'
  ).length

  const assignedCount = apiFollowUps.filter(
    task => Boolean(task.assigned_to) && isActiveTask(task.status)
  ).length

  const overdueCount = apiFollowUps.filter(task =>
    task.due_at !== null &&
    new Date(task.due_at).getTime() < now &&
    isActiveTask(task.status)
  ).length

  const dueThisWeekCount = apiFollowUps.filter(task => {
    if (!task.due_at || !isActiveTask(task.status)) return false

    const dueTime = new Date(task.due_at).getTime()
    return dueTime >= now && dueTime <= weekFromNow
  }).length

  const filteredTasks = mappedFollowUpTasks.filter(task => {
    const source = apiFollowUps.find(
      item => item.task_id === task.id
    )

    const dueTime = source?.due_at
      ? new Date(source.due_at).getTime()
      : null

    const isOverdue =
      dueTime !== null &&
      dueTime < now &&
      source !== undefined &&
      isActiveTask(source.status)

    const matchesStatus =
      taskFilter === 'All statuses' ||
      (taskFilter === 'Overdue'
        ? isOverdue
        : task.status === taskFilter)

    const matchesSearch =
      `${task.id} ${task.patient} ${task.description} ${task.owner}`
        .toLowerCase()
        .includes(query.toLowerCase())

    return matchesStatus && matchesSearch
  })

  return <>
    <PageHeader
      eyebrow="WORKSPACE / FOLLOW-UP"
      title="Follow-up queue"
      subtitle="Coordinate outstanding actions across connected clinical records."
      actions={
        <>
          <button
            className="button secondary"
            onClick={() => {
              if (accessToken) void loadFollowUps(accessToken)
            }}
            disabled={followUpsLoading}
          >
            <RefreshCw /> Refresh
          </button>

          <button
            className="button primary"
            onClick={() => {
              const description = window.prompt('Task description')

              if (!description?.trim()) return

              void createFollowUpTask(description.trim())
            }}
          >
            <Plus /> Create task
          </button>
        </>
      }
    />

    <div className="queue-stats">
      <div>
        <strong>{openCount}</strong>
        <span>Open tasks</span>
      </div>
      <div>
        <strong>{assignedCount}</strong>
        <span>Assigned tasks</span>
      </div>
      <div>
        <strong>{overdueCount}</strong>
        <span>Overdue</span>
      </div>
      <div>
        <strong>{dueThisWeekCount}</strong>
        <span>Due this week</span>
      </div>
    </div>

    {followUpsLoading && (
      <section className="panel" role="status">
        Loading follow-up records from FastAPI...
      </section>
    )}

    {followUpsError && (
      <section className="panel" role="alert">
        <div className="panel-head">
          <h2>Unable to load follow-up tasks</h2>
          <AlertCircle />
        </div>
        <p className="ai-copy">{followUpsError}</p>
        <button
          className="button primary"
          onClick={() => {
            if (accessToken) void loadFollowUps(accessToken)
          }}
        >
          <RefreshCw /> Try again
        </button>
      </section>
    )}

    <div className="toolbar">
      <div className="searchbox">
        <Search />
        <input
          placeholder="Search task or patient"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
      </div>

      <select
        aria-label="Task status"
        value={taskFilter}
        onChange={e => setTaskFilter(e.target.value)}
      >
        <option>All statuses</option>
        <option>Open</option>
        <option>Assigned</option>
        <option>In progress</option>
        <option>Completed</option>
        <option>Escalated</option>
        <option>Cancelled</option>
        <option>Overdue</option>
      </select>

      <button
        className="button secondary"
        onClick={() => setTaskFilter('In progress')}
      >
        <SlidersHorizontal /> My tasks
      </button>
    </div>

    <DataTable
      headers={[
        'Task ID',
        'Patient',
        'Origin',
        'Task description',
        'Owner',
        'Due date',
        'Status',
        '',
      ]}
      rows={filteredTasks.map(task => [
        <code key="id">{task.id}</code>,
        task.patient,
        <code key="link">{task.link}</code>,
        task.description,
        task.owner,
        task.due,
        <Status key="status">{task.status}</Status>,
        <button
          className="icon-button"
          key="update"
          aria-label={`Update ${task.id}`}
          disabled={
            task.status === 'Completed' ||
            task.status === 'Cancelled'
          }
          onClick={() => {
            const nextStatus =
              task.status === 'In progress'
                ? 'completed'
                : 'in_progress'

            void updateFollowUpStatus(task.id, nextStatus)
          }}
        >
          <Check />
        </button>,
      ])}
      empty="No follow-up tasks match your search."
    />
  </>
}



  function Encounters() { return <><PageHeader eyebrow="WORKSPACE / ENCOUNTERS" title="Clinical encounters" subtitle="Open, resume and review structured clinical documentation." actions={<button className="button primary" onClick={() => showNotice('New encounter started')}><Plus /> Start encounter</button>} /><div className="encounter-feature"><div><p className="eyebrow">ACTIVE ENCOUNTER</p><h2>Naledi Molefe <code>ENC-24891</code></h2><p>Outpatient consultation · Princess Marina Hospital · 18 Oct 2026, 08:42</p><Status>Draft in progress</Status></div><button className="button primary" onClick={() => { setPatient(demoPatients[0]); setDraft(false); setCopilotOpen(true); showNotice('Encounter editor opened') }}>Open encounter <ArrowRight /></button></div><section className="panel"><div className="panel-head"><div><p className="eyebrow">RECENT ENCOUNTERS</p><h2>All encounters</h2></div><div className="searchbox compact"><Search /><input placeholder="Search encounters" /></div></div><DataTable headers={['Encounter ID', 'Patient', 'Date and time', 'Clinician', 'Facility', 'Status', '']} rows={demoPatients.slice(0,4).map((p,i) => [<code key="id">ENC-2489{i}</code>, p.name, `${18-i} Oct 2026 · 0${8+i}:42`, 'Dr. K. Moagi', p.facility, <Status key="s">{i === 0 ? 'Draft' : 'Completed'}</Status>, <button className="icon-button" key="a" onClick={() => openPatient(p)}><ArrowRight /></button>])} /></section></> }
  function SimplePage({ title, eyebrow, icon: Icon, description }: { title: PageKey; eyebrow: string; icon: typeof Activity; description: string }) { return <><PageHeader eyebrow={eyebrow} title={title} subtitle={description} /><div className="empty-state"><Icon /><h2>{title} workspace</h2><p>This prototype area is ready for connection to the FastAPI service layer. Administrative actions are simulated and do not enforce real access control.</p><button className="button secondary" onClick={() => showNotice('Prototype action completed')}>Simulate action <ArrowRight /></button></div></> }
  function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow: string; title: string; subtitle: string; actions?: React.ReactNode }) { return <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{subtitle}</p></div>{actions}</header> }
  function DataTable({ headers, rows, empty }: { headers: string[]; rows: (React.ReactNode[])[]; empty?: string }) { return <div className="table-wrap"><table><thead><tr>{headers.map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.length ? rows.map((row,i) => <tr key={i}>{row.map((cell,j) => <td key={j}>{cell}</td>)}</tr>) : <tr><td className="table-empty" colSpan={headers.length}>{empty || 'No records found.'}</td></tr>}</tbody></table></div> }

  const content = page === 'Dashboard' ? <Dashboard /> : page === 'Patients' && workspaceOpen ? <PatientWorkspace /> : page === 'Encounters' ? <Encounters /> : page === 'Laboratory Results' ? <Labs /> : page === 'Follow-up Queue' ? <FollowUps /> : page === 'Patients' ? <Patients /> : page === 'Notifications' ? <SimplePage title="Notifications" eyebrow="WORKSPACE / NOTIFICATIONS" icon={Bell} description="Review assignments, result alerts, approaching due dates and simulated integration events." /> : page === 'Clinical Copilot' ? <SimplePage title="Clinical Copilot" eyebrow="INTELLIGENCE / COPILOT" icon={MessageSquareText} description="Generate contextual drafts from synthetic source records with clinician review required." /> : <SimplePage title={page} eyebrow={`ADMINISTRATION / ${page.toUpperCase()}`} icon={Settings} description="This prototype area demonstrates the intended workflow and remains disconnected from clinical systems." />

  if (!accessToken || !currentUser) {
    return <main className="auth-screen"><form className="auth-card" onSubmit={handleLogin}><div className="brand auth-brand"><div className="brand-mark">BN</div><div><strong>BNH<span>AI</span></strong><small>National Healthcare AI</small></div></div><p className="eyebrow">LOCAL DEVELOPMENT · SYNTHETIC DATA ONLY</p><h1>Sign in to BNH AI</h1><p className="auth-description">Use one of the demo accounts created by the backend seed command. The patient directory is loaded only after authentication succeeds.</p><label htmlFor="login-username">Username</label><input id="login-username" className="auth-input" value={loginUsername} onChange={event => setLoginUsername(event.target.value)} autoComplete="username" required /><label htmlFor="login-password">Password</label><input id="login-password" className="auth-input" type="password" value={loginPassword} onChange={event => setLoginPassword(event.target.value)} autoComplete="current-password" required /><button className="button primary full auth-submit" type="submit" disabled={loginBusy}>{loginBusy ? 'Connecting…' : 'Sign in and connect'}</button>{loginError && <p className="auth-error" role="alert">{loginError}</p>}<p className="auth-footnote">Passwords are not stored in the browser. The short-lived access token stays in page memory and is cleared when you sign out or refresh the page. Never use real patient data in this prototype.</p></form></main>
  }

  return <div className="app-shell"><aside className={`sidebar ${mobileNav ? 'mobile-open' : ''}`} ><div className="brand"><div className="brand-mark">BN</div><div><strong>BNH<span>AI</span></strong><small>National Healthcare AI</small></div><button className="icon-button mobile-close" onClick={() => setMobileNav(false)}><X /></button></div><div className="facility"><small>ACTIVE FACILITY</small><strong>{activeAssignment?.facility_id || 'No facility assigned'}</strong><ChevronDown /></div><nav>{navGroups.map(group => <div className="nav-group" key={group.label}><p>{group.label}</p>{group.items.map(item => { const label = item[0]; const Icon = item[1]; return <button key={label} className={page === label ? 'active' : ''} onClick={() => { setPage(label as PageKey); if (label === 'Patients') setWorkspaceOpen(false); setMobileNav(false) }}><Icon />{label}{label === 'Notifications' && <span className="nav-count">3</span>}</button> })}</div>)}</nav><div className="sidebar-footer"><div className="connection"><Wifi /><span><strong>Patient API connected</strong><small>Other screens remain prototype-only</small></span></div><button className="user-small" onClick={handleLogout} title="Sign out"><span className="avatar">{userInitials}</span><span><strong>{currentUser.display_name}</strong><small>{userRoleLabel} · Sign out</small></span><MoreHorizontal /></button></div></aside><main className="main"><header className="topbar"><button className="icon-button menu-trigger" onClick={() => setMobileNav(true)}><Menu /></button><div className="topbar-title"><strong>Botswana National Healthcare AI Platform</strong><span>LOCAL API CONNECTED · SYNTHETIC DATA ONLY · NO NATIONAL SYSTEM LINK</span></div><div className="topbar-actions"><div className="global-search"><Search /><input placeholder="Search records" onChange={e => { setQuery(e.target.value); if (e.target.value) setPage('Patients') }} /></div><button className="icon-button notification" aria-label="Notifications" onClick={() => setPage('Notifications')}><Bell /><span>3</span></button><button className="top-user" onClick={handleLogout} title="Sign out"><span className="avatar">{userInitials}</span><span><strong>{currentUser.display_name}</strong><small>{userRoleLabel} · Sign out</small></span><ChevronDown /></button></div></header><div className="content">{content}</div></main>{notice && <div className="toast"><Check /> {notice}</div>}</div>
}
