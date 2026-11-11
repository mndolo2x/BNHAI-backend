'use client'

import { useState, type ChangeEvent, type FormEvent } from 'react'
import { apiRequest, type ApiEncounter } from '@/lib/backend-api'

type PatientChoice = {
  id: string
  name: string
  facility: string
  status: string
}

type Props = {
  token: string
  patients: PatientChoice[]
  writableFacilities: string[]
  onCancel: () => void
  onCreated: (encounter: ApiEncounter) => void
}

export function EncounterCreateForm({
  token,
  patients,
  writableFacilities,
  onCancel,
  onCreated,
}: Props) {
  const [patientId, setPatientId] = useState('')
  const [clinicianName, setClinicianName] = useState('')
  const [encounterType, setEncounterType] = useState('consultation')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const eligiblePatients = patients.filter(
    patient =>
      patient.status === 'Active' &&
      writableFacilities.includes(patient.facility)
  )

  const selectedPatient = eligiblePatients.find(
    patient => patient.id === patientId
  )

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (busy) return

    if (!selectedPatient || !clinicianName.trim() || !encounterType.trim()) {
      setError('Choose an active patient and complete all required fields.')
      return
    }

    setBusy(true)
    setError('')

    try {
      const created = await apiRequest<ApiEncounter>(
        'api/v1/encounters',
        token,
        {
          method: 'POST',
          body: JSON.stringify({
            patient_id: selectedPatient.id,
            facility_id: selectedPatient.facility,
            clinician_name: clinicianName.trim(),
            encounter_type: encounterType.trim(),
          }),
        }
      )

      onCreated(created)
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Could not create encounter.'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section
      className="panel"
      aria-label="Start synthetic encounter"
      style={{ marginBottom: 20 }}
    >
      <div className="panel-head">
        <div>
          <p className="eyebrow">
            LOCAL DEVELOPMENT · SYNTHETIC DATA ONLY
          </p>
          <h2>Start clinical encounter</h2>
        </div>
      </div>

      {eligiblePatients.length === 0 ? (
        <p role="status">
          No active patients are available in your authorized facilities.
          Add a synthetic patient first.
        </p>
      ) : (
        <form onSubmit={submit} autoComplete="off">
          <div className="info-grid" style={{ marginBottom: 16 }}>
            <label>
              Active patient
              <select
                className="auth-input"
                required
                value={patientId}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setPatientId(event.target.value)
                }
              >
                <option value="">Choose a patient</option>
                {eligiblePatients.map(patient => (
                  <option key={patient.id} value={patient.id}>
                    {patient.name} ({patient.id}) · {patient.facility}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Responsible clinician name
              <input
                className="auth-input"
                placeholder="Demo clinician name"
                value={clinicianName}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setClinicianName(event.target.value)
                }
                required
                maxLength={200}
              />
            </label>

            <label>
              Encounter type
              <select
                className="auth-input"
                value={encounterType}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setEncounterType(event.target.value)
                }
                required
              >
                <option value="consultation">Consultation</option>
                <option value="follow-up">Follow-up</option>
                <option value="emergency">Emergency</option>
                <option value="review">Review</option>
              </select>
            </label>
          </div>

          {error && (
            <p className="auth-error" role="alert">{error}</p>
          )}

          <div style={{
            display: 'flex',
            gap: 12,
            flexWrap: 'wrap',
          }}>
            <button
              className="button primary"
              type="submit"
              disabled={busy || !patientId}
            >
              {busy ? 'Creating…' : 'Create encounter'}
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
      )}
    </section>
  )
}
