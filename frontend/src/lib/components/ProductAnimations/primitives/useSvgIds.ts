import { createContext, useContext, useId } from 'react'

export const SvgIdContext = createContext<string>('')

export function useSvgIds(): (localId: string) => string {
    const prefix = useContext(SvgIdContext)
    return (localId: string): string => `${prefix}-${localId}`
}

export function useSvgIdPrefix(): string {
    return useId()
}
