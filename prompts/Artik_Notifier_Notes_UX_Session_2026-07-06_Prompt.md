# Artik Notifier — Notes UX Iteration Prompts (Session 2026-07-06)

> The follow-up prompts submitted after the master notes-first redesign (see
> `Artik_Notifier_Notes_First_Redesign_Prompt.md`). Each was implemented on the Evernote-style
> Notes page (`frontend/src/pages/Notes.tsx`) and deployed to AWS App Runner
> (https://c9frk5u4hf.us-west-2.awsapprunner.com). Verbatim/paraphrased with the outcome.

---

## 1. Evernote 2-pane Notes layout (with attached Evernote screenshots)
> "when i click notes, i want to look like this [Evernote screenshot] with search on top, add
> reminder and notes, ability to add tags [Tags filter screenshot]"

**Built:** Redesigned `/notes` into a master-detail 2-pane layout — LIST pane (top Search box,
"Notes N" header, **Notes / Reminders** tabs, 🖉 new-note, ⚑ filter-by-tag popover, cards showing
title + 2-line preview + updated date + indicators) and EDITOR pane (breadcrumb, large inline
Title, tag chips with inline "+ add tag", integrated reminder, full-height body with continuous
debounced **autosave** — no Save button). New `Notes.tsx` replaced the old `QuickNotes` route.

## 2. Reminder behind an icon, opens on the right
> "can you move the reminder to right side, when you click that icon, reminder shows up
> [reminder panel screenshot]"

**Built:** Removed the always-visible reminder bar. Added a **⏰ button** in the editor's top-right
actions → opens a right-aligned popover (date · time · repeat · move-to-notebook, stacked) with a
click-away backdrop + Clear. ⏰ is accented when a reminder is set.

## 3. Fix dark date-picker color + richer right pane
> "can you give a different color to calendar pop up, it is visible now with black background.
> also see whether you change the design bit more for right side [rich editor reference]"

**Built:** (a) Native date/time pickers no longer render black-on-black — forced
`color-scheme: dark` on those inputs in dark mode + inverted the calendar/clock indicator icon;
lightened the reminder popover (`#1c2333` + brand ring + field labels). (b) Editor pane redesign
toward the reference: breadcrumb (📓 notebook › title); "Edited <date> • **Auto saved ✓**" status;
larger title; **colored tag chips** (hashed palette) + "🔔 Add tag"; body in a rounded card; and a
proper **Reminder card** (📅 date · 🕐 12h time · 🔁 Repeat · 🔔 Enabled + Edit Reminder) when set.
(Rich-text toolbar / Attachments / AI Insights / Activity History from the reference left as
explicitly-flagged fast-follows, not faked.)

## 4. Mobile-friendly
> "make the UI mobile friendly"

**Built:** On phones the 2-pane collapses to one pane — full-width notes list; tapping a note (or
+New) slides in the full-screen editor with a "‹ Notes" back button; deleting returns to the list.
Desktop keeps both panes (md: breakpoints). Responsive title/padding; reminder popover capped to
viewport width. (App shell sidebar was already a mobile drawer.)

## 5. Show reminder details on each note card
> "show the reminder details in each titles [notes list screenshot]"

**Built:** Notes with a reminder show a prominent amber "⏰ <date>, <12h time> · 🔁 <repeat>" line on
their list card (between preview and updated-date); favorite ★ inline by the title.

## 6. Reminders tab as an agenda (accepted suggestion)
> "ok" — to: sort the Reminders tab by due date, soonest first.

**Built:** Reminders tab orders notes by `due_date` ascending (backend `_SORTS` supports it); Notes
tab keeps updated-at desc.

---

### Backend foundation these UX prompts build on (deployed, 62 tests pass)
Notebook model + `/api/notebooks` CRUD; `QuickNote` gained `notebook_id/is_favorite/pinned/repeat`;
notes list filters by `notebook_id/is_favorite/has_reminder`; idempotent startup migration
(`app/core/migrations.py`) adds columns, seeds a default notebook per user, backfills notes, and
migrates existing Reminders → linked Notes. See `Artik_Notifier_Notes_First_Redesign_Prompt.md`.
