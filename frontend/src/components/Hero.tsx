"use client";

import { motion } from "framer-motion";
import { UploadZone } from "./UploadZone";

const stagger = {
  animate: {
    transition: { staggerChildren: 0.12 },
  },
};

const fadeUp = {
  initial: { opacity: 0, y: 16 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 120, damping: 18 },
  },
};

export function Hero() {
  return (
    <section className="relative min-h-[100dvh] flex items-center">
      {/* ── Subtle bg grain texture via CSS (pointer-events-none per Taste §5) ── */}
      <div className="fixed inset-0 z-0 pointer-events-none opacity-[0.03]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
      />

      <div className="relative z-10 mx-auto max-w-8xl w-full px-6 py-32 lg:py-40">
        {/* ── Split Screen: Left content / Right upload ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left ── */}
          <motion.div
            variants={stagger}
            initial="initial"
            animate="animate"
          >
            <motion.div
              variants={fadeUp}
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full
                         bg-accent-400/10 border border-accent-400/20 text-accent-400
                         text-xs font-medium tracking-wide mb-6"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-accent-400 animate-pulse" />
              Free &amp; Open Source
            </motion.div>

            <motion.h1
              variants={fadeUp}
              className="text-4xl md:text-6xl tracking-tighter leading-none font-bold
                         text-white mb-6"
            >
              RAW photos,
              <br />
              <span className="text-accent-400">ready in seconds.</span>
            </motion.h1>

            <motion.p
              variants={fadeUp}
              className="text-base text-zinc-400 leading-relaxed max-w-[55ch] mb-8"
            >
              Convert Canon CR2 RAW files to high-quality JPEG — no installs,
              no watermarks, no upload limits. Just drag, drop, and download.
              Powered by LibRaw for pixel-perfect colour reproduction.
            </motion.p>

            <motion.div variants={fadeUp} className="flex flex-wrap gap-3">
              <a
                href="#how"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg
                           bg-white text-zinc-900 text-sm font-medium
                           hover:bg-zinc-200 transition-colors
                           active:scale-[0.98]"
              >
                See how it works
              </a>
              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg
                           bg-white/5 border border-white/10 text-zinc-300 text-sm font-medium
                           hover:bg-white/10 transition-colors
                           active:scale-[0.98]"
              >
                View on GitHub
              </a>
            </motion.div>
          </motion.div>

          {/* Right — Upload Zone */}
          <motion.div
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ type: "spring", stiffness: 100, damping: 20, delay: 0.3 }}
          >
            <UploadZone />
          </motion.div>
        </div>
      </div>
    </section>
  );
}
