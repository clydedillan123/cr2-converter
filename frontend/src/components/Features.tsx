"use client";

import { motion } from "framer-motion";
import { ShieldCheck, Lightning, CloudArrowDown, LockKey } from "@phosphor-icons/react";

const features = [
  {
    icon: Lightning,
    title: "Blazing fast",
    desc: "Optimised LibRaw pipeline processes a 30 MB CR2 in under 6 seconds.",
  },
  {
    icon: ShieldCheck,
    title: "Colour accurate",
    desc: "Full debayering with camera-matched colour profiles. What you shot is what you get.",
  },
  {
    icon: CloudArrowDown,
    title: "No installs",
    desc: "Everything runs in the browser. No desktop software, no plugins, no setup.",
  },
  {
    icon: LockKey,
    title: "Private by design",
    desc: "Files are processed in-memory and deleted immediately. Nothing is stored or logged.",
  },
];

const container = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.1 },
  },
};

const card = {
  hidden: { opacity: 0, y: 12 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 120, damping: 18 },
  },
};

export function Features() {
  return (
    <section id="features" className="py-24 lg:py-32 px-6 border-t border-white/[0.06]">
      <div className="mx-auto max-w-8xl">
        <div className="mb-16">
          <p className="text-xs font-medium tracking-widest text-accent-400 uppercase mb-3">
            Features
          </p>
          <h2 className="text-3xl md:text-4xl tracking-tighter leading-tight font-bold text-white max-w-[20ch]">
            Built for photographers who care about quality.
          </h2>
        </div>

        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-60px" }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6"
        >
          {features.map((f) => (
            <motion.div
              key={f.title}
              variants={card}
              className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-6
                         hover:border-white/[0.12] transition-colors duration-300"
            >
              <f.icon weight="duotone" className="w-6 h-6 text-accent-400 mb-4" />
              <h3 className="text-sm font-semibold text-white mb-1.5 tracking-tight">
                {f.title}
              </h3>
              <p className="text-sm text-zinc-500 leading-relaxed">{f.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
