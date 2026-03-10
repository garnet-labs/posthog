import { Label, Switch } from '@posthog/ui-primitives'

export default function SwitchBasic(): React.ReactElement {
    return (
        <div className="flex items-center gap-2">
            <Switch id="airplane-mode" />
            <Label htmlFor="airplane-mode">Airplane mode</Label>
        </div>
    )
}
