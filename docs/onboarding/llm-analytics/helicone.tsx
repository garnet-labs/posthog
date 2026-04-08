import { OnboardingComponentsContext, createInstallation } from 'scenes/onboarding/OnboardingDocsContentWrapper'

import { StepDefinition } from '../steps'

export const getHeliconeSteps = (ctx: OnboardingComponentsContext): StepDefinition[] => {
    const { CodeBlock, CalloutBox, Markdown, Blockquote, dedent, snippets } = ctx

    const NotableGenerationProperties = snippets?.NotableGenerationProperties

    return [
        {
            title: 'Install dependencies',
            badge: 'required',
            content: (
                <>
                    <CalloutBox type="fyi" icon="IconInfo" title="About Helicone">
                        <Markdown>
                            Helicone is an open-source AI gateway that provides access to 100+ LLM providers through an
                            OpenAI-compatible interface. The Helicone API key handles authentication and routing to your
                            chosen model provider.
                        </Markdown>
                    </CalloutBox>

                    <Markdown>Install the OpenTelemetry SDK, the OpenAI instrumentation, and the OpenAI SDK.</Markdown>

                    <CodeBlock
                        blocks={[
                            {
                                language: 'bash',
                                file: 'Python',
                                code: dedent`
                                    pip install openai opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-openai-v2
                                `,
                            },
                            {
                                language: 'bash',
                                file: 'Node',
                                code: dedent`
                                    npm install openai @posthog/ai @opentelemetry/sdk-node @opentelemetry/resources @opentelemetry/instrumentation-openai
                                `,
                            },
                        ]}
                    />

                    <CalloutBox type="fyi" icon="IconInfo" title="No proxy">
                        <Markdown>
                            These SDKs **do not** proxy your calls. They only send analytics data to PostHog in the
                            background.
                        </Markdown>
                    </CalloutBox>
                </>
            ),
        },
        {
            title: 'Set up OpenTelemetry tracing',
            badge: 'required',
            content: (
                <>
                    <Markdown>
                        Configure OpenTelemetry to auto-instrument OpenAI SDK calls and export traces to PostHog.
                        PostHog converts `gen_ai.*` spans into `$ai_generation` events automatically.
                    </Markdown>

                    <CodeBlock
                        blocks={[
                            {
                                language: 'python',
                                file: 'Python',
                                code: dedent`
                                    from opentelemetry import trace
                                    from opentelemetry.sdk.trace import TracerProvider
                                    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
                                    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
                                    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                                    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

                                    resource = Resource(attributes={
                                        SERVICE_NAME: "my-app",
                                        "user.id": "user_123", # optional: identifies the user in PostHog
                                    })

                                    exporter = OTLPSpanExporter(
                                        endpoint="<ph_client_api_host>/i/v0/ai/otel",
                                        headers={"Authorization": "Bearer <ph_project_token>"},
                                    )

                                    provider = TracerProvider(resource=resource)
                                    provider.add_span_processor(SimpleSpanProcessor(exporter))
                                    trace.set_tracer_provider(provider)

                                    OpenAIInstrumentor().instrument()
                                `,
                            },
                            {
                                language: 'typescript',
                                file: 'Node',
                                code: dedent`
                                    import { NodeSDK, tracing } from '@opentelemetry/sdk-node'
                                    import { resourceFromAttributes } from '@opentelemetry/resources'
                                    import { PostHogTraceExporter } from '@posthog/ai/otel'
                                    import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai'

                                    const sdk = new NodeSDK({
                                      resource: resourceFromAttributes({
                                        'service.name': 'my-app',
                                        'user.id': 'user_123', // optional: identifies the user in PostHog
                                      }),
                                      spanProcessors: [
                                        new tracing.SimpleSpanProcessor(
                                          new PostHogTraceExporter({
                                            apiKey: '<ph_project_token>',
                                            host: '<ph_client_api_host>',
                                          })
                                        ),
                                      ],
                                      instrumentations: [new OpenAIInstrumentation()],
                                    })
                                    sdk.start()
                                `,
                            },
                        ]}
                    />
                </>
            ),
        },
        {
            title: 'Call Helicone',
            badge: 'required',
            content: (
                <>
                    <Markdown>
                        Now, when you call Helicone with the OpenAI SDK, PostHog automatically captures `$ai_generation`
                        events via the OpenTelemetry instrumentation.
                    </Markdown>

                    <CodeBlock
                        blocks={[
                            {
                                language: 'python',
                                file: 'Python',
                                code: dedent`
                                    import openai

                                    client = openai.OpenAI(
                                        base_url="https://ai-gateway.helicone.ai/",
                                        api_key="<helicone_api_key>",
                                    )

                                    response = client.chat.completions.create(
                                        model="gpt-5-mini",
                                        messages=[
                                            {"role": "user", "content": "Tell me a fun fact about hedgehogs"}
                                        ],
                                    )

                                    print(response.choices[0].message.content)
                                `,
                            },
                            {
                                language: 'typescript',
                                file: 'Node',
                                code: dedent`
                                    import OpenAI from 'openai'

                                    const client = new OpenAI({
                                      baseURL: 'https://ai-gateway.helicone.ai/',
                                      apiKey: '<helicone_api_key>',
                                    })

                                    const response = await client.chat.completions.create({
                                      model: 'gpt-5-mini',
                                      messages: [{ role: 'user', content: 'Tell me a fun fact about hedgehogs' }],
                                    })

                                    console.log(response.choices[0].message.content)
                                `,
                            },
                        ]}
                    />

                    <Blockquote>
                        <Markdown>
                            **Note:** If you want to capture LLM events anonymously, omit the `user.id` resource
                            attribute. See our docs on [anonymous vs identified
                            events](https://posthog.com/docs/data/anonymous-vs-identified-events) to learn more.
                        </Markdown>
                    </Blockquote>

                    <Markdown>
                        {dedent`
                            You can expect captured \`$ai_generation\` events to have the following properties:
                        `}
                    </Markdown>

                    {NotableGenerationProperties && <NotableGenerationProperties />}
                </>
            ),
        },
    ]
}

export const HeliconeInstallation = createInstallation(getHeliconeSteps)
