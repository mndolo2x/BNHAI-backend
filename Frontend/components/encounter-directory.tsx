'use client'

import { useEffect, useState } from 'react'
import { EncounterCreateForm } from './encounter-create-form'
import {
  apiRequest,
  formatDateTime,
  type ApiEncounter,
} from '@/lib/backend-api'

type PatientName = { id: string; name: string; facility: string; status: string }

type Props = {
  token: string
  patients: PatientName[]
  writableFacilities: string[]
}

export function EncounterDirectory({ token, patients, writableFacilities }: Props) {
  const [encounters, setEncounters] = useState<ApiEncounter[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)
  const [formOpen, setFormOpen] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')

    apiRequest<ApiEncounter[]>('api/v1/encounters', token)
      .then(records => {
        if (active) setEncounters(records)
      })
      .catch(cause => {
        if (active) {
          setEncounters([])
          setError(
            cause instanceof Error
              ? cause.message
              : 'Could not load encounters.'
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => { active = false }
  }, [token, refreshCount])

  const names = new Map(
    patients.map(patient => [patient.id, patient.name])
  )

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">
            WORKSPACE / ENCOUNTERS · LIVE API
          </p>
          <h1>Clinical encounters</h1>
          <p>
            Facility-scoped records from FastAPI.
            Synthetic data only.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {writableFacilities.length > 0 && (
            <button
              className="button primary"
              type="button"
              onClick={() => setFormOpen(true)}
            >
              Start encounter
            </button>
          )}
        <button
          className="button secondary"
          onClick={() => setRefreshCount(count => count + 1)}
          disabled={loading}
          type="button"
        >
          Refresh encounters
        </button>
        </div>
      </header>

      {writableFacilities.length === 0 && (
        <p className="api-footnote">
          Your role permits viewing encounters but not creating them.
        </p>
      )}

      {formOpen && (
        <EncounterCreateForm
          token={token}
          patients={patients}
          writableFacilities={writableFacilities}
          onCancel={() => setFormOpen(false)}
          onCreated={() => {
            setFormOpen(false)
            setRefreshCount(count => count + 1)
          }}
        />
      )}

      {loading ? (
        <section className="panel" role="status">
          Loading encounters…
        </section>
      ) : error ? (
        <section className="panel" role="alert">
          {error}
        </section>
      ) : (
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">
                LIVE ENCOUNTER DIRECTORY
              </p>
              <h2>{encounters.length} encounter(s)</h2>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Encounter ID</th>
                  <th>Patient</th>
                  <th>Started</th>
                  <th>Type</th>
                  <th>Clinician</th>
                  <th>Facility</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                {encounters.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="table-empty">
                      No encounters recorded for your
                      assigned facilities.
                    </td>
                  </tr>
                ) : encounters.map(item => (
                  <tr key={item.encounter_id}>
                    <td>
                      <code>{item.encounter_id}</code>
                    </td>
                    <td>
                      {names.get(item.patient_id) ??
                        item.patient_id}
                    </td>
                    <td>
                      {formatDateTime(item.started_at)}
                    </td>
                    <td>{item.encounter_type}</td>
                    <td>{item.clinician_name}</td>
                    <td>{item.facility_id}</td>
                    <td>
                      <span className="status">
                        {item.status.replaceAll('_', ' ')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
