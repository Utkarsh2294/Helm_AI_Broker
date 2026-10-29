export const springFast = { type: 'spring', stiffness: 500, damping: 35 };
export const springNormal = { type: 'spring', stiffness: 350, damping: 30 };
export const springSlow = { type: 'spring', stiffness: 200, damping: 25 };
export const fadeIn = { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } };
export const slideUp = { initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0, transition: springNormal } };
export const staggerChildren = { animate: { transition: { staggerChildren: 0.06 } } };
export const scalePress = { whileTap: { scale: 0.97, transition: springFast } };
