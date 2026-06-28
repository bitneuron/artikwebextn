export interface User {
  id: number;
  email: string;
  full_name: string | null;
  role: string;
  timezone: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface Reminder {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  notes: string | null;
  category: string;
  priority: string;
  status: string;
  due_at: string;
  timezone: string;
  recurrence: string;
  schedule: string[];
  channels: string[];
  tags: string[];
  completed_at: string | null;
  snoozed_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: number;
  reminder_id: number | null;
  channel: string;
  title: string;
  body: string | null;
  status: string;
  is_read: boolean;
  created_at: string;
  sent_at: string | null;
  read_at: string | null;
}

export interface Bell {
  unread_count: number;
  due_count: number;
  overdue_count: number;
  recent: Notification[];
}

export interface Dashboard {
  counts: Record<string, number>;
  due_today: Reminder[];
  overdue: Reminder[];
  upcoming: Reminder[];
  recent_activity: Notification[];
}

export interface CalendarMonth {
  month: number;
  year: number;
  days: { date: string; reminders: Reminder[] }[];
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatResponse {
  reply: string;
  insights: string[];
}

export interface Options {
  categories: string[];
  priorities: string[];
  recurrences: string[];
  channels: string[];
  all_channels: string[];
  schedule_offsets: string[];
}
