# Artik Notifier -- Master Development Prompt

## Role

You are acting as a Principal Software Architect, Principal Full-Stack
Engineer, UI/UX Designer, DevOps Engineer, QA Lead, Security Engineer,
and Technical Writer.

Your responsibility is to design, build, test, document, and deliver a
**production-quality** application called **Artik Notifier**.

## Project Requirements

-   Build **Artik Notifier** as a **completely separate standalone
    repository**.
-   Do **not** place it inside any existing Artik project.
-   Create a new repository named `artik-notifier`.

The repository must contain:

-   Frontend
-   Backend
-   Database
-   Scheduler
-   Email service
-   Notification service
-   Authentication
-   Tests
-   Documentation
-   Docker support
-   CI-ready structure

## Product Vision

Artik Notifier is the centralized notification platform for the Artik
ecosystem.

Initially it allows users to create reminders for recurring and one-time
tasks such as: - Monthly payments - Finance reviews - Mortgage -
Insurance renewals - Medical appointments - Taxes - Investments -
Subscriptions - Personal reminders - Custom reminders

Future Artik applications will integrate through REST APIs and events.

## MVP Features

### Authentication

-   Register
-   Login
-   Logout
-   Forgot password
-   Reset password
-   Change password
-   Secure password hashing (Argon2 or bcrypt)

### Reminder Management

Support: - Create - Edit - Delete - Complete - Archive - Snooze -
Duplicate - Restore - Search - Filter - Sort

Reminder fields: - Title - Category - Description - Notes - Priority -
Due date - Due time - Time zone - Recurrence - Reminder schedule -
Notification channels - Status - Tags - Created/Updated timestamps

Categories: Payment, Finance, Investment, Medical, Insurance, Vehicle,
Tax, Subscription, Family, Personal, Business, Education, Shopping,
Custom

Priority: Low, Medium, High, Critical

### Reminder Schedule

Allow: - On due date - 1 day before - 2 days before - 3 days before - 1
week before - 2 weeks before - 1 month before - Custom days - Custom
hours - Multiple reminders (30d, 7d, 2d, same day)

Recurrence: - One time - Daily - Weekly - Monthly - Quarterly - Yearly

### Notification Channels

Implement: - Email - In-app

Design plugin architecture for: - SMS - Push - Slack - Teams - Discord -
WhatsApp - Webhooks - REST integrations

## Dashboard

Display: - Upcoming reminders - Due today - Overdue - Completed - Unread
notifications - Calendar preview - Recent activity

## UI

Implement: - Dashboard - Reminder List View - Calendar View - Reminder
Detail Page - Reminder Create/Edit - Notification Bell - Notification
Center

Responsive: - Desktop - Tablet - Mobile

Support: - Light mode - Dark mode - Accessibility

## Notification Bell

Show: - Unread count - Recent reminders - Due reminders - Overdue
reminders

Support: - Mark read - Mark all read - Delete - Search - Filter

## Notification Center

Store every notification.

Statuses: - Pending - Sent - Failed - Read - Archived - Deleted

## Email

Professional HTML emails containing: - Title - Description - Due date -
Notes - Button to open reminder

## Scheduler

Build scheduler service.

Initially runs every hour.

Responsibilities: - Find due reminders - Generate notifications - Send
email - Create in-app notification - Prevent duplicates - Retry
failures - Log errors

Future compatible with: - AWS EventBridge - Lambda - SES - SNS - SQS

## Persistence

Local: SQLite

Future: - PostgreSQL - Amazon RDS - DynamoDB

## Database Tables

users sessions reminders notification_rules notifications
notification_history reminder_history categories tags reminder_tags
user_preferences email_templates scheduler_jobs audit_logs

## REST APIs

Implement: - Authentication - Reminder CRUD - Notification CRUD -
Dashboard - Calendar - Search - Scheduler - Health

## Security

Implement: - CSRF protection - XSS protection - CSP - Secure cookies -
JWT/session auth - Input validation - Rate limiting - Prepared
statements - Environment variables - Audit logging

## Logging

Structured logging: - Application - Scheduler - Notification - Audit -
Errors - Security

## Recommended Stack

Frontend: - React - TypeScript - Vite - Tailwind CSS

Backend: - FastAPI - SQLAlchemy

Scheduler: - APScheduler

Email: - SMTP (initial)

## Project Structure

artik-notifier/ - frontend/ - backend/ - database/ - scheduler/ -
email/ - shared/ - tests/ - docs/ - docker/ - scripts/ - .github/ -
README.md - docker-compose.yml - .env.example

## Testing

Write: - Unit tests - Integration tests - API tests - Scheduler tests -
Authentication tests - UI tests - End-to-end tests

Validate: - Login - Registration - Reminder CRUD - Snooze - Completion -
Calendar - Notifications - Email - Duplicate prevention - Bell counts -
Search

Run tests after every implementation phase.

Fix all failures before continuing.

## Documentation

Generate: - README - Architecture - ER Diagram - API Documentation -
Setup Guide - Deployment Guide - Testing Guide - Future Roadmap

## Coding Standards

Follow: - SOLID - Clean Architecture - Repository Pattern - Service
Layer - Dependency Injection - Modular design - Reusable components -
Production-quality code

Do not: - Leave TODOs - Leave placeholder implementations - Skip tests -
Hardcode secrets

## Future Roadmap

Design for: - Financial alerts - Stock alerts - Portfolio alerts -
AI-generated reminders - Gmail integration - Google Calendar - Outlook -
Family sharing - Organization reminders - RBAC - Mobile apps - Voice
reminders - Event-driven integrations

## Plugin Architecture

Design Artik Notifier as an event-driven notification platform.

Expose reminder creation, scheduling, notification generation, and
delivery through clean service interfaces and REST APIs so future Artik
applications can integrate without modifying the core system.

Notification providers must be pluggable.

## Deliverables

Deliver: - Production-ready application - Responsive UI - Backend APIs -
Scheduler - Notification engine - Email engine - SQLite database -
Docker support - Automated tests - Documentation

## Development Process

Implement in phases: 1. Architecture 2. Project structure 3. Database 4.
Authentication 5. Backend APIs 6. Frontend 7. Reminder management 8.
Scheduler 9. Notifications 10. Email 11. Calendar 12. Testing 13.
Optimization 14. Documentation

At the end of each phase: - Run tests - Fix defects - Update
documentation - Maintain production quality

The final product should be production-ready, extensible, AWS-ready, and
serve as the centralized notification platform for the Artik ecosystem.
