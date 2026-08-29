export default function ConfirmDialog({
  open, title, body, confirmLabel = "Confirm", danger = true, onConfirm, onCancel,
}: {
  open: boolean; title: string; body: string; confirmLabel?: string; danger?: boolean;
  onConfirm: () => void; onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog" aria-modal="true" aria-labelledby="confirm-title"
      onKeyDown={(e) => e.key === "Escape" && onCancel()}
    >
      <div className="card w-full max-w-sm animate-rise-in p-5">
        <h2 id="confirm-title" className="font-display text-base font-bold text-ink">{title}</h2>
        <p className="mt-2 text-sm text-ink-dim">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-ghost btn-sm" onClick={onCancel} autoFocus>Cancel</button>
          <button className={danger ? "btn-danger btn-sm" : "btn-primary btn-sm"} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
