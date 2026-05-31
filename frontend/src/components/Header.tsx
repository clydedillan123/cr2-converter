import Link from "next/link";
import { Camera } from "@phosphor-icons/react/dist/ssr";

export function Header() {
  return (
    <header className="fixed top-0 inset-x-0 z-50">
      <nav className="mx-auto max-w-8xl px-6 py-4 flex items-center justify-between">
        {/* Logo */}
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-medium text-zinc-300
                     hover:text-white transition-colors"
        >
          <Camera weight="duotone" className="w-5 h-5 text-accent-400" />
          <span className="tracking-tight">CR2 Converter</span>
        </Link>

        {/* Nav links */}
        <div className="hidden sm:flex items-center gap-6 text-sm text-zinc-500">
          <a href="#how" className="hover:text-zinc-300 transition-colors">
            How it works
          </a>
          <a href="#features" className="hover:text-zinc-300 transition-colors">
            Features
          </a>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-zinc-300 transition-colors"
          >
            GitHub
          </a>
        </div>
      </nav>
    </header>
  );
}
