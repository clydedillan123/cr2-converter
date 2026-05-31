import { Camera } from "@phosphor-icons/react/dist/ssr";

export function Footer() {
  return (
    <footer className="border-t border-white/[0.06] px-6 py-10">
      <div className="mx-auto max-w-8xl flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Camera weight="duotone" className="w-4 h-4 text-accent-400/60" />
          <span>CR2 Converter</span>
        </div>

        {/* Links */}
        <div className="flex items-center gap-6 text-xs text-zinc-600">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-zinc-400 transition-colors"
          >
            GitHub
          </a>
          <span>Powered by LibRaw &amp; Railway</span>
        </div>
      </div>
    </footer>
  );
}
