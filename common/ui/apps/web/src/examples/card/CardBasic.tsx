import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@posthog/ui-primitives'

export default function CardBasic(): React.ReactElement {
    return (
        <Card className="w-[350px]">
            <CardHeader>
                <CardTitle>Card title</CardTitle>
                <CardDescription>Card description goes here.</CardDescription>
            </CardHeader>
            <CardContent>
                <p>Card content</p>
            </CardContent>
        </Card>
    )
}
