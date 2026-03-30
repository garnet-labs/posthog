import { LemonButton } from 'lib/lemon-ui/LemonButton'
import { SceneExport } from 'scenes/sceneTypes'

export const scene: SceneExport = {
    component: InboxScene,
}

export function InboxScene(): JSX.Element {
    return (
        <div className="flex flex-col items-center justify-center h-full gap-4">
            <h2>The PostHog Inbox has moved to the PostHog Code desktop app.</h2>
            <LemonButton
                type="primary"
                targetBlank
                to="https://posthog.com/code?utm_source=in-product&utm_medium=inbox-redirect"
            >
                Download here
            </LemonButton>
        </div>
    )
}
