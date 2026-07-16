# Condition update contract

The backend keeps itinerary generation and condition monitoring separate. Refreshing
intelligence updates weather, crowd, road, and timing signals, but never replaces a
route, attraction, flight, or accommodation.

## Refresh flow

1. A client or external scheduler calls
   `POST /sessions/{session_id}/refresh-intelligence`.
2. The planner rebuilds the session's condition signals and daily briefings.
3. The previous and refreshed daily briefings are compared.
4. Only meaningful deterioration is stored in `condition_notifications` in MongoDB.
5. The dashboard exposes unread updates under `condition_updates`.

A future twice-daily scheduler should call the same endpoint for active trips. It
must use an authenticated or service-protected request before it is enabled in
production; no scheduler is enabled by this module itself.

## Notification behavior

An update is created when rain crosses 70%, crowd pressure crosses 60/100, a risk
level worsens to medium or high, or relevant RoadLK alerts increase. Changes for the
same day are consolidated into one notification and deduplicated before storage.

Each record includes a `push` object with a title, body, and navigation data. A
future Expo notification worker can deliver that object without changing the event
schema. Marking an update as read only changes notification state; it never changes
the trip package.
