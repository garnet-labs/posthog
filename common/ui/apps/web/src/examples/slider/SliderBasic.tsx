import { Slider } from '@posthog/ui-primitives'

export default function SliderBasic(): React.ReactElement {
    return <Slider defaultValue={[50]} max={100} step={1} className="w-[300px]" />
}
