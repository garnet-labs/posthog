import { Checkbox, Label } from '@posthog/ui-primitives'

export default function CheckboxBasic(): React.ReactElement {
    return (
        <div className="flex items-center gap-2">
            <Checkbox id="terms" />
            <Label htmlFor="terms">Accept terms and conditions</Label>
        </div>
    )
}
