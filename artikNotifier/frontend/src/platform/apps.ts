// ── Artik Platform — app registry (single source of truth) ───────────────────
// Adding a new Artik product to the platform = append ONE entry here. The landing
// page, the in-app "switch product" menu, and URL aliases are all derived from it.
// Nothing else needs to change to register an app: logo, name, aliases, url, and
// metadata live only here.

export type ArtikApp = {
  id: string;
  name: string;          // display name, e.g. "ArtikNotifier"
  short: string;         // brand suffix, e.g. "Notifier"
  icon: string;          // emoji/logo glyph
  accent: string;        // tailwind/text color for cards
  tagline: string;
  description: string;
  /** Lowercase URL aliases that should resolve to this app (path segments). */
  aliases: string[];
  /** Absolute deployment URL (env-overridable). "self" = this very app. */
  url: string;
  /** True for the app this build *is* (drives in-app nav vs. external link). */
  current?: boolean;
};

const env = import.meta.env as Record<string, string | undefined>;

export const PLATFORM_NAME = "Artik Platform";

/** Deploy URLs are env-overridable so the same build works in any environment. */
const BROKER_URL = env.VITE_BROKER_URL || "https://hpzkeypha3.us-west-2.awsapprunner.com";
const NOTIFIER_URL = env.VITE_NOTIFIER_URL || "/"; // self

export const APPS: ArtikApp[] = [
  {
    id: "broker",
    name: "ArtikBroker",
    short: "Broker",
    icon: "📈",
    accent: "text-emerald-500",
    tagline: "Score, screen & analyze equities",
    description:
      "Peer-relative stock scoring, S&P 500 / DOW screeners, AI search, and a research copilot.",
    aliases: ["artikbroker", "artik-broker", "broker"],
    url: BROKER_URL,
  },
  {
    id: "notifier",
    name: "ArtikNotifier",
    short: "Notifier",
    icon: "🔔",
    accent: "text-brand",
    tagline: "Never miss a payment or deadline",
    description:
      "Recurring & one-time reminders with multi-stage notifications, a calendar, and an AI assistant.",
    aliases: ["artiknotifier", "artik-notifier", "notifier"],
    url: NOTIFIER_URL,
    current: true,
  },
];

export const CURRENT_APP = APPS.find((a) => a.current)!;
export const OTHER_APPS = APPS.filter((a) => !a.current);

export const APP_VERSION = env.VITE_APP_VERSION || "1.0.0";
export const APP_ENV = env.VITE_APP_ENV || (env.PROD ? "production" : "development");

/** Resolve a URL alias (case-insensitive path segment) to a registered app. */
export function appForAlias(segment: string): ArtikApp | undefined {
  const s = segment.replace(/^\/+/, "").toLowerCase();
  return APPS.find((a) => a.id === s || a.aliases.includes(s));
}
