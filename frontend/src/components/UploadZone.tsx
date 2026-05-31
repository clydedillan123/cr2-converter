"use client";

import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Image, Upload, CheckCircle, XCircle, SpinnerGap } from "@phosphor-icons/react";

type Status = "idle" | "uploading" | "converting" | "done" | "error";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function UploadZone() {
  const [status, setStatus] = useState<Status>("idle");
  const [dragOver, setDragOver] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [fileName, setFileName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".cr2")) {
      setStatus("error");
      setErrorMsg("Only .CR2 RAW files are supported.");
      return;
    }

    setFileName(file.name);
    setErrorMsg("");
    setStatus("uploading");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("quality", "85");

    try {
      setStatus("converting");
      const res = await fetch(`${API_URL}/convert`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || "Conversion failed.");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name.replace(/\.cr2$/i, ".jpg");
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      setStatus("done");
    } catch (e: unknown) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "Upload or conversion failed.");
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    },
    [handleFile],
  );

  const onChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) handleFile(e.target.files[0]);
    },
    [handleFile],
  );

  const reset = () => {
    setStatus("idle");
    setErrorMsg("");
    setFileName("");
  };

  return (
    <div className="w-full max-w-lg mx-auto">
      {/* ── Drop Zone ───────────────────────────── */}
      <AnimatePresence mode="wait">
        {status === "done" ? (
          <motion.div
            key="done"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 200, damping: 20 }}
            className="glass-strong rounded-2xl p-10 text-center"
          >
            <CheckCircle
              weight="duotone"
              className="w-12 h-12 text-accent-400 mx-auto mb-4"
            />
            <p className="text-lg font-medium text-white mb-1">Conversion complete</p>
            <p className="text-sm text-zinc-400 mb-6">
              {fileName.replace(/\.cr2$/i, ".jpg")} downloaded
            </p>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={reset}
              className="px-5 py-2 rounded-lg bg-white/10 text-sm text-zinc-300
                         hover:bg-white/20 transition-colors"
            >
              Convert another
            </motion.button>
          </motion.div>
        ) : (
          <motion.div
            key="dropzone"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 160, damping: 20 }}
          >
            <div
              role="button"
              tabIndex={0}
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={`glass rounded-2xl p-12 text-center cursor-pointer
                          transition-all duration-200 outline-none
                          ${
                            dragOver
                              ? "border-accent-400/50 bg-accent-400/5 scale-[1.01]"
                              : "hover:border-white/20 hover:bg-white/[0.06]"
                          }`}
            >
              {/* Icon */}
              <motion.div
                animate={dragOver ? { y: -4 } : { y: 0 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
              >
                {status === "uploading" || status === "converting" ? (
                  <SpinnerGap
                    weight="bold"
                    className="w-12 h-12 text-accent-400 mx-auto mb-4 animate-spin"
                  />
                ) : dragOver ? (
                  <Upload
                    weight="duotone"
                    className="w-12 h-12 text-accent-400 mx-auto mb-4"
                  />
                ) : (
                  <Image
                    weight="duotone"
                    className="w-12 h-12 text-zinc-500 mx-auto mb-4"
                  />
                )}
              </motion.div>

              {/* Text */}
              <p className="text-lg font-medium text-white mb-1">
                {status === "uploading"
                  ? "Uploading..."
                  : status === "converting"
                    ? "Processing RAW data..."
                    : dragOver
                      ? "Drop your file"
                      : "Drop a .CR2 file here"}
              </p>
              <p className="text-sm text-zinc-500">
                {status === "idle"
                  ? "or click to browse — up to 60 MB"
                  : fileName}
              </p>
            </div>

            {/* Hidden file input */}
            <input
              ref={inputRef}
              type="file"
              accept=".cr2,.CR2"
              onChange={onChange}
              className="hidden"
            />

            {/* ── Progress bar (converting) ──────── */}
            {(status === "uploading" || status === "converting") && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="mt-4 h-1 rounded-full bg-zinc-800 overflow-hidden"
              >
                <motion.div
                  className="h-full bg-accent-400 rounded-full"
                  initial={{ width: "0%" }}
                  animate={{
                    width: status === "converting" ? "90%" : "40%",
                  }}
                  transition={{
                    width: { duration: status === "converting" ? 3 : 0.6, ease: "easeOut" },
                  }}
                />
              </motion.div>
            )}

            {/* ── Error ─────────────────────────── */}
            <AnimatePresence>
              {status === "error" && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="mt-4 flex items-center gap-2 text-red-400 text-sm"
                >
                  <XCircle weight="fill" className="w-4 h-4 shrink-0" />
                  <span>{errorMsg}</span>
                  <button
                    onClick={reset}
                    className="ml-auto text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    Try again
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
