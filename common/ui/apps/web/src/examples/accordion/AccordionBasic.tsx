import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@posthog/ui-primitives'

export default function AccordionBasic(): React.ReactElement {
    return (
        <Accordion type="single" collapsible className="w-full">
            <AccordionItem value="item-1">
                <AccordionTrigger>What is Base UI?</AccordionTrigger>
                <AccordionContent>
                    A library of unstyled, accessible UI components for building high-quality web apps and design
                    systems.
                </AccordionContent>
            </AccordionItem>
            <AccordionItem value="item-2">
                <AccordionTrigger>How do I get started?</AccordionTrigger>
                <AccordionContent>Install the package and import the components you need.</AccordionContent>
            </AccordionItem>
            <AccordionItem value="item-3">
                <AccordionTrigger>Can I use it for my project?</AccordionTrigger>
                <AccordionContent>Yes! It&apos;s open source and free to use.</AccordionContent>
            </AccordionItem>
        </Accordion>
    )
}
