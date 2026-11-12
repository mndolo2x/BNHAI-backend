'use client'

import { useEffect, useState } from 'react'
import { EncounterNoteForm } from './encounter-note-form'
import { SubmitNoteForReview } from './submit-note-for-review'
import {
  apiRequest,
  formatDateTime,
  type ApiClinicalNote,
  type ApiEncounter,
} from '@/lib/backend-api'

type ClinicalNoteDetail = ApiClinicalNote & {
  history_of_present_illness?: string | null
  relevant_history?: string | null
  medications_and_allergies?: string | null
  vitals?: string | null
  examination?: string | null
  assessment?: string | null
  plan?: string | null
  follow_up?: string | null
}

type Props = {
  token: string
  encounterId: string
  patientName: string
  canWriteNotes: boolean
  onClose: () => void
}

const noteFields = [
  { key: 'presenting_complaint', label: 'Presenting complaint' },
  { key: 'history_of_present_illness', label: 'History of present illness' },
  { key: 'relevant_history', label: 'Relevant history' },
  { key: 'medications_and_allergies', label: 'Medications and allergies' },
  { key: 'vitals', label: 'Vital signs' },
  { key: 'examination', label: 'Examination' },
  { key: 'assessment', label: 'Assessment' },
  { key: 'plan', label: 'Plan' },
  { key: 'follow_up', label: 'Follow-up' },
] as const

export function EncounterDetails({
  token,
  encounterId,
  patientName,
  canWriteNotes,
  onClose,
}: Props) {
  const [encounter, setEncounter] = useState<ApiEncounter | null>(null)
  const [notes, setNotes] = useState<ClinicalNoteDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)
  const [noteFormOpen, setNoteFormOpen] = useState(false)
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setEncounter(null)
    setNotes([])

    Promise.all([
      apiRequest<ApiEncounter>(
        `api/v1/encounters/${encodeURIComponent(encounterId)}`,
        token,
      ),
      apiRequest<ClinicalNoteDetail[]>(
        `api/v1/encounters/${encodeURIComponent(encounterId)}/notes`,
        token,
      ),
    ])
      .then(([details, versions]) => {
        if (!active) return
        setEncounter(details)
        setNotes(versions)
      })
      .catch(cause => {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : 'Could not load encounter details.'
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => { active = false }
  }, [token, encounterId, refreshCount])

  return (
    <section
      className="panel"
      aria-label="Encounter details"
      style={{ marginBottom: 20 }}
    >
      <div className="panel-head">
        <div>
          <p className="eyebrow">
            LIVE ENCOUNTER DETAILS · CLINICAL DOCUMENTATION
          </p>
          <h2>{patientName}</h2>
          <p>Synthetic clinical records loaded from FastAPI.</p>
        </div>

        <div style={{
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
        }}>
          <button
            className="button secondary"
            type="button"
            disabled={loading}
            onClick={() => setRefreshCount(count => count + 1)}
          >
            Refresh details
          </button>

          <button
            className="button secondary"
            type="button"
            onClick={onClose}
          >
            Close details
          </button>
        </div>
      </div>

      {loading ? (
        <p role="status">
          Loading encounter details and clinical notes…
        </p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : encounter ? (
        <>
          <dl style={{
            display: 'grid',
            gridTemplateColumns:
              'repeat(auto-fit, minmax(190px, 1fr))',
            gap: 12,
          }}>
            <div>
              <dt>Encounter ID</dt>
              <dd><code>{encounter.encounter_id}</code></dd>
            </div>
            <div>
              <dt>Patient ID</dt>
              <dd>{encounter.patient_id}</dd>
            </div>
            <div>
              <dt>Facility</dt>
              <dd>{encounter.facility_id}</dd>
            </div>
            <div>
              <dt>Clinician</dt>
              <dd>{encounter.clinician_name}</dd>
            </div>
            <div>
              <dt>Type</dt>
              <dd>{encounter.encounter_type}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{encounter.status.replaceAll('_', ' ')}</dd>
            </div>
            <div>
              <dt>Started</dt>
              <dd>{formatDateTime(encounter.started_at)}</dd>
            </div>
            <div>
              <dt>Last updated</dt>
              <dd>{formatDateTime(encounter.updated_at)}</dd>
            </div>
          </dl>

          <div style={{ marginTop: 24 }}>
            <p className="eyebrow">CLINICAL DOCUMENTATION</p>
            <h3>Clinical note history ({notes.length})</h3>

            {canWriteNotes && encounter.status === 'in_progress' && (
              <button
                className="button primary"
                type="button"
                onClick={() => {
                  setEditingNoteId(null)
                  setNoteFormOpen(true)
                }}
                disabled={noteFormOpen}
              >
                New clinical note
              </button>
            )}

            {!canWriteNotes && (
              <p className="api-footnote">
                Your role permits viewing clinical notes but not creating them.
              </p>
            )}

            {noteFormOpen && canWriteNotes && encounter.status === 'in_progress' && (
              <EncounterNoteForm
                key={editingNoteId ?? 'new'}
                token={token}
                initialNote={editingNoteId
                  ? notes.find(note => note.note_id === editingNoteId)
                  : undefined}
                encounterId={encounter.encounter_id}
                onCancel={() => {
                  setNoteFormOpen(false)
                  setEditingNoteId(null)
                }}
                onSaved={() => {
                  setNoteFormOpen(false)
                  setEditingNoteId(null)
                  setRefreshCount(count => count + 1)
                }}
              />
            )}

            {notes.length === 0 ? (
              <p>
                No clinical notes recorded for this encounter.
              </p>
            ) : notes.map(note => (
              <article
                key={note.note_id}
                className="panel"
                style={{ marginTop: 16, padding: 16 }}
              >
                <h4>
                  Version {note.version} ·{' '}
                  {note.status.replaceAll('_', ' ')}
                </h4>

                <p>
                  Author: {note.author_name} · Updated:{' '}
                  {formatDateTime(note.updated_at)}
                </p>

                {note.approved_by && (
                  <p>
                    Approved by: {note.approved_by} ·{' '}
                    {formatDateTime(note.approved_at)}
                  </p>
                )}

                {canWriteNotes && encounter.status === 'in_progress' && note.status === 'draft' && (
                  <button
                    className="button secondary"
                    type="button"
                    disabled={noteFormOpen}
                    onClick={() => {
                      setEditingNoteId(note.note_id)
                      setNoteFormOpen(true)
                    }}
                  >
                    Edit draft
                  </button>
                )}

                {canWriteNotes && encounter.status === 'in_progress' && note.status === 'draft' && (
                  <SubmitNoteForReview
                    token={token}
                    noteId={note.note_id}
                    disabled={noteFormOpen}
                    onSubmitted={() => setRefreshCount(count => count + 1)}
                  />
                )}

                {noteFields.map(field => {
                  const value = note[field.key]
                  if (!value?.trim()) return null

                  return (
                    <div
                      key={field.key}
                      style={{ marginTop: 12 }}
                    >
                      <strong>{field.label}</strong>
                      <p style={{
                        whiteSpace: 'pre-wrap',
                        overflowWrap: 'anywhere',
                      }}>
                        {value}
                      </p>
                    </div>
                  )
                })}
              </article>
            ))}
          </div>
        </>
      ) : (
        <p role="alert">
          Encounter details are unavailable.
        </p>
      )}
    </section>
  )
}
