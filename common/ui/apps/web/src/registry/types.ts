import type { ComponentType, LazyExoticComponent } from 'react'

export interface ComponentExample {
    name: string
    component: LazyExoticComponent<ComponentType>
    code: string
}

export interface ComponentProp {
    name: string
    type: string
    default?: string
    description: string
}

export interface ComponentEntry {
    slug: string
    name: string
    description: string
    category: string
    anatomy?: string
    props: ComponentProp[]
    examples: ComponentExample[]
}
