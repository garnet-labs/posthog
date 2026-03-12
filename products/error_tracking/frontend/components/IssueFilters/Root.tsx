import { PropsWithChildren } from 'react'

import { cn } from 'lib/utils/css-classes'

export const ErrorFiltersRoot = ({ children, className }: PropsWithChildren<{ className?: string }>): JSX.Element => {
    return <div className={cn('space-y-2.5', className)}>{children}</div>
}
