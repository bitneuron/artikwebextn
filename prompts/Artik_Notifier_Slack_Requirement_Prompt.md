# Add Central Slack Notification API to Artik Notifier

Act like a senior full-stack developer, security engineer, and platform architect.

Update **Artik Notifier** so it becomes the centralized notification service for Slack messages across the Artik ecosystem.

The goal is to allow applications such as:

- ArtikNotifier
- ArtikBroker
- ArtikMedia
- Future Artik apps and websites

to call a standard API endpoint in Artik Notifier and send Slack notifications to the configured Artik Slack workspace/channel.

---

## Objective

Create a reusable Slack notification API inside Artik Notifier.

Other Artik applications should be able to make a secure API call to Artik Notifier, and Artik Notifier should send the message to Slack.

This avoids every app managing Slack webhooks separately.

---

## Slack Workspace

Slack workspace:

`https://artik-talk.slack.com`

Default Slack channel:

`#artik-notify`

Use environment variables for all Slack configuration.

Never hardcode Slack webhook URLs or Slack tokens.

---

## Environment Variables

Add the following to `.env.example`:

```env
# Slack

SLACK_ENABLED=true

SLACK_WEBHOOK_URL=<your-incoming-webhook-url>

SLACK_DEFAULT_CHANNEL=#artik-notify

# Optional (only needed for Slack Events, Slash Commands, or Interactive Apps)

SLACK_CLIENT_ID=8046130622772.11469248766577

SLACK_CLIENT_SECRET=890ecd3a3986199e5731c91d517f7a01

SLACK_SIGNING_SECRET=aebb83f35f0eaeebde68f12fa4eee4d2

# Artik Notifier API

ARTIK_NOTIFY_API_KEY=<generate-a-random-64-character-secret>
```

The real values must only be stored in local `.env`, AWS Secrets Manager, or CI/CD secrets.

---

## API Requirement

Create a secure API endpoint:

```http
POST /api/v1/notifications/slack
```

This endpoint will be called by ArtikBroker, ArtikMedia, ArtikNotifier, and future apps.

---

## Request Body

Support this JSON payload:

```json
{
  "source_app": "artikBroker",
  "event_type": "deployment_complete",
  "severity": "success",
  "title": "ArtikBroker Deployment Complete",
  "message": "Build, test, and AWS deployment completed successfully.",
  "channel": "#artik-notify",
  "metadata": {
    "environment": "production",
    "version": "1.0.0",
    "commit": "abc123",
    "application_url": "https://example.com",
    "api_url": "https://api.example.com"
  }
}
```

---

## Required Fields

- source_app
- event_type
- severity
- title
- message

---

## Optional Fields

- channel
- metadata
- correlation_id
- user_id
- environment
- tags

---

## Severity Values

Support:

- info
- success
- warning
- error
- critical

Format Slack messages differently based on severity.

Use emojis:

- info: ℹ️
- success: ✅
- warning: ⚠️
- error: ❌
- critical: 🚨

---

## Slack Message Format

Send a clean Slack message like:

```text
✅ ArtikBroker Deployment Complete

Source: artikBroker
Event: deployment_complete
Severity: success
Environment: production

Build, test, and AWS deployment completed successfully.

Version: 1.0.0
Commit: abc123
Application: https://example.com
API: https://api.example.com
```

---

## Security Requirements

The API must be protected.

Support API key authentication using:

```http
Authorization: Bearer <ARTIK_NOTIFY_API_KEY>
```

or:

```http
X-API-Key: <ARTIK_NOTIFY_API_KEY>
```

Reject unauthorized requests with HTTP 401.

Validate all input.

Rate limit the endpoint.

Prevent payload injection.

Do not log secrets.

Audit every notification request.

---

## Database Requirements

Persist every Slack notification request.

Create table:

### slack_notifications

Fields:

- id
- source_app
- event_type
- severity
- title
- message
- channel
- metadata_json
- status
- slack_response
- error_message
- correlation_id
- created_at
- sent_at
- retry_count

Status values:

- pending
- sent
- failed
- skipped

---

## Behavior

When API is called:

1. Authenticate request.
2. Validate payload.
3. Store notification request in database.
4. Send message to Slack if Slack is enabled.
5. Store Slack response.
6. Mark status as sent, failed, or skipped.
7. Return API response.

---

## API Response

Success:

```json
{
  "success": true,
  "status": "sent",
  "notification_id": "123",
  "message": "Slack notification sent successfully"
}
```

Failure:

```json
{
  "success": false,
  "status": "failed",
  "notification_id": "123",
  "message": "Slack notification failed",
  "error": "Slack webhook returned non-200 response"
}
```

---

## Retry Support

If Slack send fails:

- Store failure details.
- Increment retry_count.
- Allow retry through internal scheduler or admin action.
- Do not lose the notification.

Create optional endpoint:

```http
POST /api/v1/notifications/slack/{id}/retry
```

---

## Admin UI

Add an admin page in Artik Notifier:

**Slack Notifications**

Display:

- Source App
- Event Type
- Severity
- Title
- Channel
- Status
- Created At
- Sent At
- Retry Count

Actions:

- View details
- Retry failed notification
- Mark skipped
- Search
- Filter by source app
- Filter by severity
- Filter by status

---

## Integration Examples

Add documentation showing how other apps call the API.

### Python Example

```python
import requests

payload = {
    "source_app": "artikBroker",
    "event_type": "deployment_complete",
    "severity": "success",
    "title": "ArtikBroker Deployment Complete",
    "message": "Build, tests, GitHub push, and AWS deployment completed.",
    "channel": "#artik-notify",
    "metadata": {
        "environment": "production",
        "version": "1.0.0",
        "commit": "abc123"
    }
}

response = requests.post(
    "https://<artik-notifier-api>/api/v1/notifications/slack",
    json=payload,
    headers={
        "Authorization": "Bearer <ARTIK_NOTIFY_API_KEY>"
    },
    timeout=10
)

print(response.json())
```

### JavaScript Example

```javascript
await fetch("https://<artik-notifier-api>/api/v1/notifications/slack", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <ARTIK_NOTIFY_API_KEY>"
  },
  body: JSON.stringify({
    source_app: "artikMedia",
    event_type: "transcription_complete",
    severity: "success",
    title: "Transcript Ready",
    message: "The uploaded Zoom recording has been transcribed successfully.",
    channel: "#artik-notify",
    metadata: {
      environment: "production",
      file_name: "zoom_meeting.mp4"
    }
  })
});
```

---

## Testing Requirements

Write automated tests for:

- Valid Slack notification request
- Missing API key
- Invalid API key
- Missing required fields
- Invalid severity
- Slack disabled mode
- Slack webhook success
- Slack webhook failure
- Database persistence
- Retry logic
- Admin UI display
- Filtering/searching notifications
- API rate limiting

All tests must pass before completion.

---

## Documentation

Update README with:

- Slack setup instructions
- How to create Slack Incoming Webhook
- Required environment variables
- API payload examples
- Security model
- How ArtikBroker and other apps should call this API
- Troubleshooting Slack delivery issues

---

## Autonomous Development

Implement this feature fully without asking for step-by-step confirmation.

Complete:

1. Backend API
2. Slack service
3. Database migration
4. Admin UI
5. Retry support
6. Security
7. Tests
8. Documentation

Run all tests and fix failures.

Commit changes to Git with a meaningful message.

If deployment is configured, deploy and validate.

Only ask for review after implementation, tests, documentation, and deployment validation are complete

