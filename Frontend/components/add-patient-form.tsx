'use client'

import { useState, type ChangeEvent, type FormEvent } from 'react'
import { apiRequest, type ApiPatient } from '@/lib/backend-api'

type Props = {
  token: string
  facilities: string[]
  onCancel: () => void
  onCreated: () => Promise<void>
}

export function AddPatientForm({
  token, facilities, onCancel, onCreated,
}: Props) {
  const [patientId, setPatientId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [facilityId, setFacilityId] = useState('')
  const [recordStatus, setRecordStatus] =
    useState<'active' | 'inactive'>('active')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const selectedFacility = facilities.includes(facilityId)
    ? facilityId
    : (facilities[0] ?? '')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedFacility || busy) return

    setBusy(true)
    setError('')

    try {
      await apiRequest<ApiPatient>('api/v1/patients', token, {
        method: 'POST',
        body: JSON.stringify({
          patient_id: patientId.trim(),
          display_name: displayName.trim(),
          date_of_birth: birthDate || null,
          facility_id: selectedFacility,
          record_status: recordStatus,
        }),
      })
      await onCreated()
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Could not create patient.'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section
      className="panel"
      aria-label="Add synthetic patient"
      style={{ marginBottom: 20 }}
    >
      <div className="panel-head">
        <div>
          <p className="eyebrow">
            LOCAL DEVELOPMENT · SYNTHETIC DATA ONLY
          </p>
          <h2>Add patient record</h2>
        </div>
      </div>

      <form onSubmit={submit} autoComplete="off">
        <div className="info-grid" style={{ marginBottom: 16 }}>
          <label>
            Patient ID
            <input
              className="auth-input"
              autoFocus
              required
              maxLength={40}
              placeholder="DEMO-0001"
              value={patientId}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setPatientId(event.target.value)}
            />
          </label>

          <label>
            Full name (synthetic)
            <input
              className="auth-input"
              required
              maxLength={200}
              placeholder="Demo Patient A"
              value={displayName}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setDisplayName(event.target.value)}
            />
          </label>

          <label>
            Date of birth (optional)
            <input
              className="auth-input"
              type="date"
              value={birthDate}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setBirthDate(event.target.value)}
            />
          </label>

          <label>
            Facility
            <select
              className="auth-input"
              required
              value={selectedFacility}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setFacilityId(event.target.value)}
            >
              {facilities.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
          </label>

          <label>
            Record status
            <select
              className="auth-input"
              value={recordStatus}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setRecordStatus(
                  event.target.value as 'active' | 'inactive'
                )}
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
        </div>

        {error && (
          <p role="alert" className="auth-error">{error}</p>
        )}

        <div style={{
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
        }}>
          <button
            className="button primary"
            type="submit"
            disabled={busy || !selectedFacility}
          >
            {busy ? 'Saving…' : 'Save patient'}
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
