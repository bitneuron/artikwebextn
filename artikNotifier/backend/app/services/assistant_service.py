"""Artik Assistant — read-only insight engine over the CURRENT user's data only.

Every query is scoped to `self.user_id`, so the assistant can never reach another
user's reminders, notifications, settings, or chat. It is deterministic (no external
LLM dependency) and performs NO destructive actions — it only summarizes and suggests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.utils import ensure_aware, from_json_list
from app.models.chat import ChatMessage
from app.models.quick_note import QuickNote
from app.models.reminder import Reminder
from app.repositories.notification_repo import NotificationRepository
from app.repositories.quick_note_repo import QuickNoteRepository
from app.repositories.reminder_repo import ReminderRepository

FINANCE_CATEGORIES = {"Finance", "Payment", "Investment", "Tax", "Insurance"}
_STOPWORDS = {"show", "me", "my", "the", "a", "an", "find", "search", "list", "get",
              "notes", "note", "tagged", "tag", "with", "for", "of", "in", "any",
              "what", "which", "are", "is", "do", "i", "have", "all", "summarize",
              "summary", "this", "week", "month", "due", "overdue", "and", "related"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_overdue(r: Reminder) -> bool:
    return r.status in ("active", "snoozed") and ensure_aware(r.due_at) < _utcnow()


class AssistantService:
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user
        self.user_id = user.id
        self.reminders = ReminderRepository(db)
        self.notifs = NotificationRepository(db)
        self.notes = QuickNoteRepository(db)

    # ── data (all scoped to self.user_id) ─────────────────────────────────────
    def _active(self) -> list[Reminder]:
        return [r for r in self.reminders.query(self.user_id, limit=500)
                if r.status in ("active", "snoozed")]

    def _due_within(self, days: int) -> list[Reminder]:
        now = _utcnow(); end = now + timedelta(days=days)
        return [r for r in self._active() if now <= ensure_aware(r.due_at) <= end]

    # ── proactive insights ────────────────────────────────────────────────────
    def insights(self) -> list[str]:
        out: list[str] = []
        active = self._active()
        # finance due this week
        fin_week = [r for r in self._due_within(7) if r.category in FINANCE_CATEGORIES]
        if fin_week:
            out.append(f"You have {len(fin_week)} finance reminder(s) due this week.")
        # recurring items notifying only on the due date
        same_day = [r for r in active if r.recurrence != "one_time"
                    and from_json_list(r.schedule) == ["on_due"]]
        if same_day:
            r = same_day[0]
            out.append(f"Your {r.recurrence} reminder “{r.title}” notifies only on the same day. "
                       f"Consider adding 2 days before.")
        # unread notifications
        unread = self.notifs.unread_count(self.user_id)
        if unread:
            out.append(f"You have {unread} unread notification(s).")
        # reminders without notes
        no_notes = [r for r in active if not (r.notes or "").strip()]
        if len(no_notes) >= 3:
            out.append(f"You have {len(no_notes)} reminder(s) without notes — adding context helps.")
        # overdue (esp. finance) — pattern of late handling
        overdue_fin = [r for r in active if _is_overdue(r) and r.category in FINANCE_CATEGORIES]
        if overdue_fin:
            out.append(f"{len(overdue_fin)} finance reminder(s) are overdue — you may be handling "
                       f"finance items late.")
        # repeated obligations
        recurring = [r for r in active if r.recurrence in ("monthly", "yearly", "quarterly")]
        if len(recurring) >= 2:
            out.append(f"You have {len(recurring)} repeating obligation(s) "
                       f"({', '.join(sorted({r.recurrence for r in recurring}))}).")
        # grouping suggestion
        cats = {r.category for r in active}
        uncategorized = [r for r in active if r.category == "Personal"]
        if len(uncategorized) >= 4:
            out.append(f"{len(uncategorized)} reminders are under “Personal” — consider grouping "
                       f"them into clearer categories.")
        # Quick Notes with a due date that haven't been turned into reminders yet.
        notes = self._note_active()
        unconverted_due = [n for n in notes if n.due_date and not n.reminder_id]
        if unconverted_due:
            out.append(f"You have {len(unconverted_due)} note(s) with a due date not yet converted "
                       f"to reminders — convert them so you get notified.")
        if not out:
            out.append("Everything looks tidy — no pressing reminders or settings to improve right now.")
        return out

    # ── quick notes (all scoped to self.user_id) ──────────────────────────────
    def _note_active(self) -> list[QuickNote]:
        return [n for n in self.notes.query(self.user_id, limit=500) if n.status == "active"]

    def _note_line(self, n: QuickNote) -> str:
        label = n.title or (n.note_text[:60] + ("…" if len(n.note_text) > 60 else ""))
        due = f" — due {n.due_date:%b %d}" if n.due_date else ""
        link = " (reminder linked)" if n.reminder_id else ""
        return f"• {label} ({n.category}){due}{link}"

    def _notes_answer(self, m: str) -> str:
        notes = self._note_active()
        if not notes:
            return "You have no active quick notes yet. Capture one from the Quick Notes tab."
        today = _utcnow().date()

        if any(w in m for w in ("overdue", "late", "behind")):
            od = [n for n in notes if n.due_date and n.due_date < today]
            if not od:
                return "None of your notes are overdue. 🎉"
            return f"You have {len(od)} overdue note(s):\n" + "\n".join(self._note_line(n) for n in od[:10])

        if "due" in m or "this week" in m or "week" in m:
            wk = [n for n in notes if n.due_date and today <= n.due_date <= today + timedelta(days=7)]
            if not wk:
                return "You have no notes due in the next 7 days."
            return f"You have {len(wk)} note(s) due this week:\n" + "\n".join(self._note_line(n) for n in wk[:10])

        # category match (finance, medical, …)
        for cat in FINANCE_CATEGORIES | {"Medical", "Shopping", "Travel", "Research",
                                         "Education", "Business", "Personal", "Ideas"}:
            if cat.lower() in m:
                items = [n for n in notes if n.category == cat]
                if not items:
                    return f"You have no active {cat} notes."
                return f"You have {len(items)} {cat} note(s):\n" + "\n".join(self._note_line(n) for n in items[:10])

        # tag / keyword search across title, text, tags
        terms = [w for w in m.replace(":", " ").split() if w not in _STOPWORDS and len(w) > 2]
        if "summ" in m:
            by_cat: dict[str, int] = {}
            for n in notes:
                by_cat[n.category] = by_cat.get(n.category, 0) + 1
            breakdown = ", ".join(f"{c} ({n})" for c, n in sorted(by_cat.items(), key=lambda x: -x[1]))
            return f"You have {len(notes)} active note(s): {breakdown}."
        if terms:
            def hit(n: QuickNote) -> bool:
                hay = " ".join([n.title or "", n.note_text, n.category,
                                " ".join(t.name for t in n.tags)]).lower()
                return any(t in hay for t in terms)
            found = [n for n in notes if hit(n)]
            if found:
                return (f"Found {len(found)} note(s) matching “{' '.join(terms)}”:\n"
                        + "\n".join(self._note_line(n) for n in found[:10]))
            return f"No notes matched “{' '.join(terms)}”."

        return f"You have {len(notes)} active note(s):\n" + "\n".join(self._note_line(n) for n in notes[:10])

    # ── natural-language Q&A (intent routing) ────────────────────────────────
    def answer(self, message: str) -> str:
        m = (message or "").lower().strip()
        if not m:
            return "Ask me about your upcoming reminders, quick notes, overdue items, unread " \
                   "notifications, a category (e.g. finance), or how to improve your settings."

        # Quick Notes first — "note(s)" is an explicit signal, so route there before
        # the reminder intents (e.g. "overdue notes" must not hit the reminder branch).
        if "note" in m:
            if "convert" in m:
                return ("To convert a note into a reminder, open the note and tap "
                        "“Convert to Reminder”. I can show which notes have due dates — "
                        "just ask “show notes due this week”.")
            return self._notes_answer(m)

        # Intent checks first (so "overdue payments" → overdue, not the Payment category).
        if any(w in m for w in ("overdue", "late", "missed", "behind")):
            od = [r for r in self._active() if _is_overdue(r)]
            if "payment" in m or "finance" in m:
                od = [r for r in od if r.category in FINANCE_CATEGORIES]
            if not od:
                return "Good news — you have no overdue reminders. 🎉"
            lines = "\n".join(f"• {r.title} ({r.category}) — was due {ensure_aware(r.due_at):%b %d}"
                              for r in sorted(od, key=lambda x: x.due_at)[:10])
            return f"You have {len(od)} overdue reminder(s):\n{lines}"

        if any(w in m for w in ("unread", "notification", "bell")):
            bell = self.notifs.unread_count(self.user_id)
            recent = self.notifs.query(self.user_id, unread_only=True, limit=5)
            if not bell:
                return "You have no unread notifications."
            lines = "\n".join(f"• {n.title}" for n in recent)
            return f"You have {bell} unread notification(s):\n{lines}"

        if any(w in m for w in ("setting", "improve", "how should", "advice", "recommend", "suggest")):
            tips = self.insights()
            return "Here are some suggestions based on your reminders:\n" + \
                   "\n".join(f"• {t}" for t in tips)

        if any(w in m for w in ("calendar", "month", "summar")):
            month = self._due_within(31)
            if not month:
                return "You have no reminders scheduled in the next month."
            by_cat: dict[str, int] = {}
            for r in month:
                by_cat[r.category] = by_cat.get(r.category, 0) + 1
            breakdown = ", ".join(f"{n} {c.lower()}" for c, n in sorted(by_cat.items(), key=lambda x: -x[1]))
            return f"You have {len(month)} reminder(s) coming up this month ({breakdown})."

        # category lookup (after the specific intents above)
        for cat in FINANCE_CATEGORIES | {"Medical", "Vehicle", "Subscription", "Family",
                                         "Personal", "Business", "Education", "Shopping"}:
            if cat.lower() in m and any(w in m for w in ("show", "find", "list", "reminder", "related", cat.lower())):
                items = [r for r in self._active() if r.category == cat]
                if not items:
                    return f"You have no active {cat} reminders."
                lines = "\n".join(f"• {r.title} — due {ensure_aware(r.due_at):%b %d, %H:%M}"
                                  + (" (overdue)" if _is_overdue(r) else "") for r in items[:10])
                return f"You have {len(items)} {cat} reminder(s):\n{lines}"

        # default: upcoming this week + a nudge
        week = self._due_within(7)
        if not week:
            return "You have nothing due in the next 7 days. Ask about overdue items, " \
                   "unread notifications, a category, or settings advice."
        lines = "\n".join(f"• {r.title} ({r.category}) — {ensure_aware(r.due_at):%b %d, %H:%M}"
                          for r in sorted(week, key=lambda x: x.due_at)[:10])
        return f"You have {len(week)} reminder(s) coming up this week:\n{lines}"

    # ── chat (persisted history, scoped to user) ──────────────────────────────
    def chat(self, message: str) -> dict:
        message = (message or "").strip()[:1000]
        reply = self.answer(message)
        self.db.add(ChatMessage(user_id=self.user_id, role="user", content=message))
        self.db.add(ChatMessage(user_id=self.user_id, role="assistant", content=reply))
        self.db.commit()
        return {"reply": reply, "insights": self.insights()}

    def history(self, limit: int = 50) -> list[ChatMessage]:
        stmt = (select(ChatMessage).where(ChatMessage.user_id == self.user_id)
                .order_by(ChatMessage.created_at.desc()).limit(limit))
        rows = list(self.db.execute(stmt).scalars().all())
        rows.reverse()
        return rows

    def clear_history(self) -> None:
        for msg in self.db.execute(
                select(ChatMessage).where(ChatMessage.user_id == self.user_id)).scalars().all():
            self.db.delete(msg)
        self.db.commit()
