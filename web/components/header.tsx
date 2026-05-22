import Link from "next/link";

export function Header() {
  return (
    <header className="border-b border-ink/10 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Link href="/" className="group flex items-baseline gap-3">
          <span className="mono text-[11px] uppercase tracking-[0.32em] text-ink-soft">
            Agora /
          </span>
          <span className="mono text-base font-bold tracking-tight text-ink">
            ALPHA
          </span>
        </Link>
        <nav className="flex items-center gap-7 mono text-[12px] uppercase tracking-[0.22em] text-ink-soft">
          <Link href="/" className="hover:text-ink">
            Picks
          </Link>
          <a
            href="https://agora.thecanteenapp.com/"
            target="_blank"
            rel="noopener"
            className="hover:text-ink"
          >
            Hackathon ↗
          </a>
        </nav>
      </div>
    </header>
  );
}
