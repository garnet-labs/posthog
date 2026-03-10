import { Tabs, TabsContent, TabsList, TabsTrigger } from '@posthog/ui-primitives'

export default function TabsBasic(): React.ReactElement {
    return (
        <Tabs defaultValue="account" className="w-[400px]">
            <TabsList>
                <TabsTrigger value="account">Account</TabsTrigger>
                <TabsTrigger value="password">Password</TabsTrigger>
            </TabsList>
            <TabsContent value="account">
                <p className="text-sm text-muted-foreground">Make changes to your account here.</p>
            </TabsContent>
            <TabsContent value="password">
                <p className="text-sm text-muted-foreground">Change your password here.</p>
            </TabsContent>
        </Tabs>
    )
}
