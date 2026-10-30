import React from 'react';
import { motion } from 'framer-motion';
import { scalePress } from '../design/motion';
import Spinner from './Spinner';
export default function Button({
  children,
  type = 'button',
  variant = 'secondary',
  size = 'md',
  fullWidth = false,
  loading = false,
  className = '',
  ...props
}) {
  return (
    <motion.button
      type={type}
      {...scalePress}
      className={`button ${variant} size-${size} ${fullWidth ? 'full' : ''} ${className}`}
      {...props}
      disabled={loading || props.disabled}
      aria-busy={loading}
    >
      {loading ? (
        <>
          <Spinner size="sm" aria-hidden="true" /> Working…
        </>
      ) : (
        children
      )}
    </motion.button>
  );
}
