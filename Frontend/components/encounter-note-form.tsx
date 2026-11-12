'use client'

import { useState, type ChangeEvent, type FormEvent } from 'react'
import { apiRequest, type ApiClinicalNote } from '@/lib/backend-api'

const sections = [
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

type SectionKey = (typeof sections)[number]['key']

const emptySections: Record<SectionKey, string> = {
  presenting_complaint: '',
  history_of_present_illness: '',
  relevant_history: '',
  medications_and_allergies: '',
  vitals: '',
  examination: '',
  assessment: '',
  plan: '',
  follow_up: '',
}

type EditableDraft = ApiClinicalNote & Partial<Record<SectionKey, string | null>>

type Props = {
  token: string
  encounterId: string
  initialNote?: EditableDraft
  onCancel: () => void
  onSaved: (note: ApiClinicalNote) => void
}

export function EncounterNoteForm({
  token,
  encounterId,
  initialNote,
  onCancel,
  onSaved,
}: Props) {
  const [authorName, setAuthorName] = useState(initialNote?.author_name ?? '')
  const [values, setValues] = useState<Record<SectionKey, string>>(() => {
    const seeded = { ...emptySections }
    if (initialNote) {
      for (const item of sections) {
        seeded[item.key] = initialNote[item.key] ?? ''
      }
    }
    return seeded
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return

    if (initialNote && initialNote.status !== 'draft') {
      setError('Only draft notes can be edited.')
      return
    }

    if (!authorName.trim() || !sections.some(item => values[item.key].trim())) {
      setError('Enter an author name and at least one clinical note section.')
      return
    }

    setSaving(true)
    setError('')

    try {
      const saved = await apiRequest<ApiClinicalNote>(
        initialNote
          ? `api/v1/notes/${encodeURIComponent(initialNote.note_id)}`
          : `api/v1/encounters/${encodeURIComponent(encounterId)}/notes`,
        token,
        {
          method: initialNote ? 'PATCH' : 'POST',
          body: JSON.stringify({
            author_name: authorName.trim(),
            ...Object.fromEntries(
              sections.map(item => [item.key, values[item.key].trim() || null])
            ),
          }),
        }
      )

      onSaved(saved)
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Could not save note draft.'
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <section
      className="panel"
      aria-label="New clinical note draft"
      style={{ marginTop: 16 }}
    >
      <div className="panel-head">
        <div>
          <p className="eyebrow">
            SYNTHETIC DATA ONLY · DRAFT
          </p>
          <h3>{initialNote ? 'Edit clinical note draft' : 'New clinical note'}</h3>
          <p>
            {initialNote
              ? 'Saving updates this draft in place. Previous field values are not retained as a new version.'
              : 'Saving creates a draft. It does not submit or approve the note.'}
          </p>
        </div>
      </div>

      <form onSubmit={submit} autoComplete="off">
        <label style={{ display: 'block', marginBottom: 16 }}>
          Author name (development only)
          <input
            className="auth-input"
            type="text"
            required
            maxLength={200}
            value={authorName}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              setAuthorName(event.target.value)
            }
            placeholder="Demo Clinician A"
          />
        </label>

        {sections.map(item => (
          <label
            key={item.key}
            style={{ display: 'block', marginBottom: 16 }}
          >
            {item.label}
            <textarea
              className="auth-input"
              rows={3}
              maxLength={10000}
              value={values[item.key]}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                setValues(current => ({
                  ...current,
                  [item.key]: event.target.value,
                }))
              }
              style={{
                display: 'block',
                width: '100%',
                resize: 'vertical',
              }}
            />
          </label>
        ))}

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <div style={{
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
        }}>
          <button
            className="button primary"
            type="submit"
            disabled={saving}
          >
            {saving ? 'Saving…' : initialNote ? 'Save changes' : 'Save draft'}
          </button>

          <button
            className="button secondary"
            type="button"
            disabled={saving}
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
