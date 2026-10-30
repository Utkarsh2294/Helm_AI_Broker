import React from 'react';
import { motion } from 'framer-motion';
import { scalePress } from '../design/motion';
export default function Button({ children, variant = 'secondary', loading = false, ...props }) {
  return (
    <motion.button
      {...scalePress}
      className={`button ${variant}`}
      {...props}
      disabled={loading || props.disabled}
      aria-busy={loading}
    >
      {loading ? 'Working…' : children}
    </motion.button>
  );
}
