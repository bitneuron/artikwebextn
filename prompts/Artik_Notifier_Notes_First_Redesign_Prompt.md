# Artik Notifier — Notes-First (Evernote-Style) Redesign Prompt

> Submitted 2026-07-06. The master spec that reframed Artik Notifier from a reminder-first app
> into a notes-first productivity platform. Iteration 1 (Notebooks + notes-first data model +
> migration + Notebooks UI + Evernote 2-pane Notes page) was implemented and deployed; larger
> pieces (rich-text/WYSIWYG, attachments/S3, AI Insights, real-time sync, semantic search) are
> tracked as fast-follows. See memory `artiknotifier-notes-first`.

---

## Redesign Artik Notifier into an Evernote-Style Productivity Platform

Act as a Principal Product Manager, UX Designer, Principal Software Architect, Senior Frontend
Engineer, Senior Backend Engineer, AI Engineer, QA Lead, and DevOps Engineer.

Redesign Artik Notifier from a reminder-centric application into a notes-first productivity
platform, similar to Evernote. The current application treats reminders and scheduling as the
primary feature and notes as a secondary feature. The new vision is the opposite.

### Product Vision
Transform Artik Notifier into an AI-powered personal productivity platform. The primary experience
should feel similar to Evernote, focused on: Notes, Notebooks, Organization, Search, AI Assistant.
Scheduling and reminders become integrated capabilities inside notes instead of the primary
navigation. Think: **Evernote + Apple Reminders + AI Copilot + Knowledge Base.**

### UX Inspiration
Use the attached Evernote screenshots as UX inspiration (do NOT copy pixel-for-pixel). Design goals:
Clean · Minimal · Fast · AI-first · Mobile-friendly · Keyboard friendly.

### New Navigation
🏠 Home · 📝 Notes · 📚 Notebooks · 🏷 Tags · 📅 Calendar · ⏰ Reminders · 🔔 Notifications ·
🤖 AI Copilot · ⚙ Settings.
Future: 👥 Shared Notebooks · 📄 Documents · 🎙 ArtikMedia · 💼 ArtikBroker · 📊 Dashboard.

### Primary Home Screen
Resemble Evernote Home: Recent Notes · Favorite Notes · Recent Notebooks · Upcoming Reminders ·
Calendar Preview · Recently Edited · AI Suggestions · Recently Uploaded Files. Widgets configurable.

### Notes Become Primary
Every feature revolves around notes. Each note supports: Rich Text · Markdown · Images ·
Attachments · Links · Tables · Code Blocks · Checklists · AI Summary · Reminder · Due Date · Tags ·
Notebook · Created/Updated dates.

### Notebook Support
Full notebook management: Create · Rename · Delete · Archive · Favorite · Share (future). Every
note belongs to a notebook. Examples: Finance, Medical, Projects, Personal, School, Research,
Travel, Passwords, Ideas, Meetings, Recipes.

### Left Navigation (Evernote-inspired)
Search · + New Note · Home · Notes · Tasks · Files · Calendar · Notebooks · Tags · Shared ·
Spaces (future) · Settings.

### Notes List
Center pane displays notes inside the selected notebook. Card View + Compact List View. Each
row/card: Title · Preview · Updated Date · Reminder indicator · Tags · Attachment icon.

### Note Editor
Right pane = editor. Rich Text · Markdown · Images · Checklists · Tables · Files · Hyperlinks ·
Syntax highlighting · Drag & Drop · Paste images. Auto-save continuously. No Save button.

### Integrated Reminder
Every note may optionally contain: Reminder · Due Date · Due Time · Repeat Schedule (e.g. Renew
Passport → July 1, 9:00 AM, Repeat Yearly). When a reminder exists: show reminder icon · add to
Calendar · add to Reminder Queue · generate notification.

### Reminder Menu
A dedicated Reminders page that automatically lists every note containing a reminder. Columns:
Note · Notebook · Due Date · Status · Repeat. Clicking opens the original note. Do NOT duplicate
reminder content — notes remain the source of truth.

### Calendar
Shows notes with reminders, completed reminders, upcoming reminders. Clicking an entry opens the note.

### Search
Global search across Notes · Notebooks · Attachments · OCR · AI summaries · Tags · Reminder text.
Full-text · Semantic search (future) · AI search.

### AI Copilot
Understands the entire notebook system. Examples: "Summarize my Finance notebook." · "Show notes
about mortgage." · "What reminders are due this week?" · "Find everything related to Visa." ·
"Summarize today's meeting." · "What notes mention AWS?" · "What tasks are overdue?" Searches Notes,
Notebooks, Reminders, Attachments.

### Attachments
Images · PDF · Word · Excel · PowerPoint · Videos · Audio · ZIP. Store locally + Amazon S3.

### Tags
Unlimited tags: autocomplete · filtering · search · AI tag suggestions.

### Favorites
Favorite Notes + Notebooks. Display favorites on Home.

### Home Widgets
Recent Notes · Pinned Notes · Recent Notebooks · Upcoming Reminders · Today's Tasks · Calendar ·
Recently Uploaded Files · AI Suggestions. Each widget hidden or reordered.

### Mobile Experience
Resemble Evernote. Bottom navigation: Home · Notes · + · Reminders · AI. FAB: + New Note ·
New Reminder · Upload File · Voice Note.

### Real-Time Synchronization
On create/update/delete/archive/move → immediately update Desktop/Tablet/Mobile without refresh.
Optimistic updates.

### Persistence
Dev: SQLite. Prod: Amazon RDS PostgreSQL. Attachments: local (dev) / Amazon S3 (prod).

### Security
Encrypt Notes, Attachments, Credentials. Private S3 · HTTPS · Authentication · Authorization ·
Audit Logs.

### APIs
Notebook · Note · Reminder · Search · Calendar · AI · Tag · Attachment · Notification.

### Migration
Existing Quick Notes become Notes. Existing Reminder records migrated + linked to Notes whenever
possible. Backward compatible. No existing data lost.

### Testing
Automated tests: Notebook CRUD · Note CRUD · Reminder integration · Notebook switching · Search ·
Tag filtering · Calendar · Reminder creation/notification · Rich text editor · Attachments ·
Auto-save · Mobile/Desktop/Tablet layout · AI search · Migration · Real-time sync. All tests pass.

### Autonomous Development
Implement autonomously (UX redesign → DB migration → Notebooks → Notes redesign → Reminder
integration → AI → APIs → Frontend → Mobile → Tests → Docs → Git commit → GitHub push → AWS deploy
→ Deployment validation). Do not ask for confirmation after each phase. Only stop on a genuine blocker.

### Definition of Done
Artik Notifier feels like a modern Evernote-style app; notes are the primary workflow; notebooks
fully organize notes; reminders integrated into notes; Home resembles a productivity dashboard;
mobile optimized; search across all content; AI Copilot understands notes/notebooks/reminders/
attachments; existing reminder functionality still works; data migrated safely; all tests pass;
docs updated; code committed + pushed; app deployed + validated.
