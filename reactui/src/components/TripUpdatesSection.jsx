function severityLabel(value) {
  return String(value || "medium").toLowerCase() === "high" ? "Important" : "Advisory";
}

export default function TripUpdatesSection({
  updates,
  onReadUpdate,
  onReadAll,
}) {
  const unreadItems = (updates?.items || []).filter((item) => !item.read);
  if (!unreadItems.length) return null;

  return (
    <section className="trip-updates" aria-labelledby="trip-updates-title" aria-live="polite">
      <div className="trip-updates-header">
        <div>
          <span className="trip-updates-eyebrow">Since your last check</span>
          <h2 id="trip-updates-title">Trip updates</h2>
        </div>
        <span className="trip-updates-count">
          {unreadItems.length} new
        </span>
      </div>

      <div className="trip-updates-list">
        {unreadItems.slice(0, 3).map((item) => (
          <article
            className={`trip-update-card ${String(item.severity || "medium").toLowerCase()}`}
            key={item.notification_id}
          >
            <div className="trip-update-meta">
              <span>{item.day ? `Day ${item.day}` : "Trip"}</span>
              {item.location_label && <span>{item.location_label}</span>}
              <span className="trip-update-severity">{severityLabel(item.severity)}</span>
            </div>
            <h3>{item.title || "Conditions changed"}</h3>
            <p className="trip-update-message">{item.message}</p>

            {!!item.changes?.length && (
              <div className="trip-update-changes">
                {item.changes.map((change) => (
                  <span key={`${item.notification_id}-${change.signal}`}>
                    {change.summary}
                  </span>
                ))}
              </div>
            )}

            {item.recommendation?.action && (
              <div className="trip-update-recommendation">
                <strong>What to do</strong>
                <p>{item.recommendation.action}</p>
                {item.recommendation.alternative_search_recommended && (
                  <small>Nearby alternatives can be checked in Tips.</small>
                )}
              </div>
            )}

            <button type="button" onClick={() => onReadUpdate?.(item.notification_id)}>
              Got it
            </button>
          </article>
        ))}
      </div>

      {unreadItems.length > 1 && (
        <button className="trip-updates-read-all" type="button" onClick={onReadAll}>
          Mark all as read
        </button>
      )}
    </section>
  );
}
