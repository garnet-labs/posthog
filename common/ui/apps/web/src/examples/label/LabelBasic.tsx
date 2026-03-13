import { Input, Label } from '@posthog/ui-primitives'

export default function LabelBasic(): React.ReactElement {
    return (
        <div className="flex flex-col gap-2">
            <Label htmlFor="email2">Email</Label>
            <Input id="email2" type="email" placeholder="you@example.com" />
        </div>
    )
}
