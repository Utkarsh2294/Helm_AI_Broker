import React from 'react';
import { motion } from 'framer-motion';

export default function Card({ elevated = false, onClick, children, className = '', ...props }) {
  const Element = onClick ? motion.button : motion.section;
  return (
    <Element
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      whileHover={onClick ? { y: -2 } : undefined}
      className={`surface ui-card ${elevated ? 'elevated' : ''} ${className}`}
      {...props}
    >
      {children}
    </Element>
  );
}
