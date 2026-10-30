import React, { useId, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { motion, animate, useMotionValue } from 'framer-motion';
import { useDrag } from '@use-gesture/react';
import { X } from 'lucide-react';
import { springNormal } from '../design/motion';

export default function BottomSheet({
  open,
  onClose,
  title,
  description,
  detent = 'mid',
  children,
  container,
}) {
  const content = useRef(null),
    y = useMotionValue(0);
  const descriptionId = useId();
  const [height, setHeight] = useState(detent);
  const bind = useDrag(
    ({ movement: [, distance], last }) => {
      y.set(Math.max(0, distance));
      if (last) {
        if (distance > 80) onClose();
        animate(y, 0, springNormal);
      }
    },
    { axis: 'y', filterTaps: true },
  );
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <Dialog.Portal container={container}>
        <Dialog.Overlay className="ui-sheet-overlay" />
        <Dialog.Content
          asChild
          aria-describedby={description ? descriptionId : undefined}
          onOpenAutoFocus={(event) => {
            const first = content.current?.querySelector(
              '[data-autofocus="true"], input, textarea',
            );
            if (first) {
              event.preventDefault();
              first.focus();
            }
          }}
        >
          <motion.section
            ref={content}
            className="ui-sheet"
            data-detent={height}
            style={{ y }}
            initial={{ opacity: 0, y: '100%' }}
            animate={{ opacity: 1, y: 0 }}
            transition={springNormal}
          >
            <button
              type="button"
              className="ui-sheet-handle"
              aria-label={height === 'full' ? 'Reduce sheet' : 'Expand sheet'}
              {...bind()}
              onClick={() => setHeight(height === 'full' ? 'mid' : 'full')}
            >
              <span />
            </button>
            <Dialog.Close className="close-button" aria-label="Close sheet">
              <X size={20} />
            </Dialog.Close>
            <Dialog.Title asChild>
              <h2>{title}</h2>
            </Dialog.Title>
            {description && (
              <Dialog.Description id={descriptionId} className="muted">
                {description}
              </Dialog.Description>
            )}
            {children}
          </motion.section>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
