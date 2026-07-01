import type { RunEvent } from '../api/types'

export function EventLog({ events }: { events: RunEvent[] }) {
  return (
    <div className="event-log">
      {events.slice().reverse().map((event, index) => (
        <div key={`${event.timestamp}-${index}`} className="event-row">
          <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
          <strong>{event.type}</strong>
          <code>{event.evaluator || event.task_id || event.report_id || ''}</code>
        </div>
      ))}
    </div>
  )
}
