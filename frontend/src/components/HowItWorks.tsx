"use client";

import { motion } from "framer-motion";
import { UploadSimple, Gear, DownloadSimple } from "@phosphor-icons/react";

const steps = [
  {
    icon: UploadSimple,
    title: "Upload your CR2",
    desc: "Drag and drop any Canon RAW file. We handle files up to 60 MB with zero quality loss.",
  },
  {
    icon: Gear,
    title: "Automatic processing",
    desc: "LibRaw decodes the sensor data with full debayering, white balance correction, and colour profiling.",
  },
  {
    icon: DownloadSimple,
    title: "Download JPEG",
    desc: "Get a high-quality JPEG at 85% compression. Optimised for web, print, and sharing — instantly.",
  },
];

const container = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.15 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 100, damping: 18 },
  },
};

export function HowItWorks() {
  return (
    <section id="how" className="py-24 lg:py-32 px-6">
      <div className="mx-auto max-w-8xl">
        {/* Section heading */}
        <div className="mb-16">
          <p className="text-xs font-medium tracking-widest text-accent-400 uppercase mb-3">
            How it works
          </p>
          <h2 className="text-3xl md:text-4xl tracking-tighter leading-tight font-bold text-white max-w-[20ch]">
            Three steps from RAW to ready.
          </h2>
        </div>

        {/* Steps grid */}
        <motion.div
          variants={container}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-80px" }}
          className="grid grid-cols-1 md:grid-cols-3 gap-8"
        >
          {steps.map((step, i) => (
            <motion.div
              key={step.title}
              variants={item}
              className="group relative rounded-2xl border border-white/[0.08]
                         bg-white/[0.03] p-8 hover:bg-white/[0.05]
                         transition-colors duration-300"
            >
              {/* Step number */}
              <span className="absolute top-6 right-6 text-6xl font-bold text-white/[0.03]
                               select-none pointer-events-none tabular-nums">
                {i + 1}
              </span>

              {/* Icon */}
              <div className="w-10 h-10 rounded-lg bg-accent-400/10 border border-accent-400/20
                              flex items-center justify-center mb-5">
                <step.icon weight="duotone" className="w-5 h-5 text-accent-400" />
              </div>

              {/* Content */}
              <h3 className="text-lg font-semibold text-white mb-2 tracking-tight">
                {step.title}
              </h3>
              <p className="text-sm text-zinc-500 leading-relaxed max-w-[40ch]">
                {step.desc}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
