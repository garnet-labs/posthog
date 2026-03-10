import { Separator } from '@posthog/ui-primitives'

export default function SeparatorBasic(): React.ReactElement {
    return (
        <div>
            <div className="space-y-1">
                <h4 className="text-sm font-medium leading-none">PostHog UI</h4>
                <p className="text-sm text-muted-foreground">An open-source component library.</p>
            </div>
            <Separator className="my-4" />
            <div className="flex h-5 items-center space-x-4 text-sm">
                <div>Docs</div>
                <Separator orientation="vertical" />
                <div>Source</div>
                <Separator orientation="vertical" />
                <div>Blog</div>
            </div>
        </div>
    )
}
