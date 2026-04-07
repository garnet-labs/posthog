/**
 * Reimplementation of useSize (https://github.com/jaredLunde/react-hook/tree/master/packages/size)
 * MIT License
 * Original copyright  2019 Jared Lunde.
 *
 * The original code is over 7 years old and depends on an outdated
 * version of d3, so we shipped two versions of d3 to the client.
 * This reimplementation is more modern and only depends on newer
 * versions of the d3 modules we actually use.
 */

import * as React from 'react'
import ResizeObserverPolyfill from 'resize-observer-polyfill'

if (!window.ResizeObserver) {
    window.ResizeObserver = ResizeObserverPolyfill
}

/**
 * A React hook for measuring the size of HTML elements including when they change
 *
 * @param target A React ref created by `useRef()` or an HTML element
 * @param options Configures the initial width and initial height of the hook's state
 */
const useSize = <T extends HTMLElement>(
    target: React.RefObject<T> | T | null,
    options?: UseSizeOptions
): [number, number] => {
    const [size, setSize] = React.useState<[number, number]>(() => {
        const targetEl = target && 'current' in target ? target.current : target
        return targetEl
            ? [targetEl.offsetWidth, targetEl.offsetHeight]
            : [options?.initialWidth ?? 0, options?.initialHeight ?? 0]
    })

    React.useLayoutEffect(() => {
        const targetEl = target && 'current' in target ? target.current : target
        if (!targetEl) {
            return
        }
        setSize([targetEl.offsetWidth, targetEl.offsetHeight])
    }, [target])

    // Where the magic happens
    React.useEffect(() => {
        const targetEl = target && 'current' in target ? target.current : target
        if (!targetEl) {
            return
        }
        const observer = new ResizeObserver((entries) => {
            const el = entries[0].target as HTMLElement
            setSize([el.offsetWidth, el.offsetHeight])
        })
        observer.observe(targetEl)
        return () => observer.disconnect()
    }, [target])

    return size
}

export interface UseSizeOptions {
    // The initial width to set into state.
    initialWidth: number
    // The initial height to set into state.
    initialHeight: number
}

export default useSize
