import React, { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { motion, useMotionValue, animate } from 'framer-motion';
import { useDrag } from '@use-gesture/react';
import { springNormal } from '../design/motion';
export default function SurveySheet({ children, container, ready }) {
  const [open, setOpen] = useState(false), y = useMotionValue(0);
  const bind = useDrag(({ movement: [, dy], last }) => { y.set(Math.max(0, dy)); if (last) { if (dy > 100) setOpen(false); animate(y, 0, springNormal); } }, { axis: 'y', filterTaps: true });
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Trigger asChild><button className="button primary full" disabled={!ready}>Review selections & feedback</button></Dialog.Trigger><Dialog.Portal container={container}><Dialog.Overlay className="survey-overlay"/><Dialog.Content asChild><motion.section className="survey-sheet" style={{ y }} initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="sheet-handle" {...bind()} aria-hidden="true"/><Dialog.Title>A quick sense check</Dialog.Title><Dialog.Description className="muted">Your feedback keeps the learning grounded. Each selected plan needs a response.</Dialog.Description>{children}<Dialog.Close className="button">Back to comparison</Dialog.Close></motion.section></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
