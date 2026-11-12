'use client'

import { useState } from 'react'
import { apiRequest, type ApiClinicalNote } from '@/lib/backend-api'

type Props = {
  token: string
  noteId: string
  disabled?: boolean
  onSubmitted: (note: ApiClinicalNote) => void
}

export function SubmitNoteForReview({
  token,
  noteId,
  disabled = false,
  onSubmitted,
}: Props) {
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    if (!confirming || submitting || disabled) return

    setSubmitting(true)
    setError('')

    try {
      const saved = await apiRequest<ApiClinicalNote>(
        `api/v1/notes/${encodeURIComponent(noteId)}/submit-for-review`,
        token,
        { method: 'POST' },
      )

      if (
        saved.note_id !== noteId ||
        saved.status !== 'awaiting_review'
      ) {
        throw new Error(
          'Unexpected submission response. Refresh the encounter before retrying.'
        )
      }

      setConfirming(false)
      onSubmitted(saved)
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Could not submit note for review.'
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ marginTop: 12 }}>
      {!confirming ? (
        <button
          className="button secondary"
          type="button"
          disabled={disabled || submitting}
          onClick={() => {
            setError('')
            setConfirming(true)
          }}
        >
          Submit for review
        </button>
      ) : (
        <div
          role="group"
          aria-label="Confirm clinical note submission"
        >
          <p>
            Submit this draft for review? Its status will
            change to awaiting review. Editing it later
            returns it to draft status.
          </p>

          <div style={{
            display: 'flex',
            gap: 12,
            flexWrap: 'wrap',
          }}>
            <button
              className="button primary"
              type="button"
              disabled={submitting || disabled}
              onClick={submit}
            >
              {submitting
                ? 'Submitting…'
                : 'Confirm submission'}
            </button>

            <button
              className="button secondary"
              type="button"
              disabled={submitting}
              onClick={() => {
                setConfirming(false)
                setError('')
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
