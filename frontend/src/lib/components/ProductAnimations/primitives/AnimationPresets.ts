import type { Transition, Variants } from 'motion/react'

export const springDefault: Transition = {
    type: 'spring',
    stiffness: 300,
    damping: 20,
}

export const springBouncy: Transition = {
    type: 'spring',
    stiffness: 400,
    damping: 10,
}

export const springGentle: Transition = {
    type: 'spring',
    stiffness: 200,
    damping: 25,
}

export const breathe: Variants = {
    idle: {
        y: [0, -1.5, 0],
        transition: { duration: 3, ease: 'easeInOut', repeat: Infinity },
    },
}

export const blink: Variants = {
    idle: {
        scaleY: [1, 1, 0.1, 1, 1],
        transition: {
            duration: 4,
            times: [0, 0.48, 0.5, 0.52, 1],
            repeat: Infinity,
            repeatDelay: 2,
        },
    },
}

export const bounce: Variants = {
    initial: { y: 0 },
    animate: {
        y: [0, -8, 0],
        transition: { duration: 0.6, ease: 'easeInOut', repeat: Infinity, repeatDelay: 1.5 },
    },
}

export const float: Variants = {
    initial: { y: 0 },
    animate: {
        y: [0, -4, 0],
        transition: { duration: 2, ease: 'easeInOut', repeat: Infinity },
    },
}

export const fadeIn: Variants = {
    initial: { opacity: 0 },
    animate: { opacity: 1, transition: { duration: 0.3 } },
}
