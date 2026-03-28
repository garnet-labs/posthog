import { type VariantProps } from 'class-variance-authority'
import { XIcon } from 'lucide-react'
import * as React from 'react'

import { Button, type buttonVariants } from './button'
import { ButtonGroup, type buttonGroupVariants } from './button-group'
import { cn } from './lib/utils'

type ChipProps = React.ComponentProps<typeof Button> &
    VariantProps<typeof buttonVariants> & {
        onRemove?: () => void
    }

const Chip = React.forwardRef<HTMLButtonElement, ChipProps>(
    ({ className, size = 'sm', variant = 'outline', onRemove, children, ...props }, ref) => {
        return (
            <Button
                ref={ref}
                data-slot="chip"
                size={size}
                variant={variant}
                className={cn('gap-1 has-data-[slot=chip-remove]:pe-0 rounded-sm', className)}
                {...props}
            >
                {children}
                {onRemove && (
                    <Button
                        data-slot="chip-remove"
                        variant="ghost"
                        size="icon-xs"
                        className="opacity-50 hover:opacity-100"
                        onClick={(e) => {
                            e.stopPropagation()
                            onRemove()
                        }}
                    >
                        <XIcon />
                    </Button>
                )}
            </Button>
        )
    }
)
Chip.displayName = 'Chip'

function ChipGroup({
    className,
    ...props
}: React.ComponentProps<typeof ButtonGroup> & VariantProps<typeof buttonGroupVariants>): React.ReactElement {
    return <ButtonGroup data-slot="chip-group" className={cn('flex-wrap gap-1', className)} {...props} />
}

export { Chip, ChipGroup }
