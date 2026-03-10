import { Input, Label } from '@posthog/ui-primitives'

export default function InputBasic(): React.ReactElement {
    return (
        <div className="grid w-full max-w-sm gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input type="email" id="email" placeholder="Enter your email" />
        </div>
    )
}
