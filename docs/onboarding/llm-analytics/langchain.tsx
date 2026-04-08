import { OnboardingComponentsContext, createInstallation } from 'scenes/onboarding/OnboardingDocsContentWrapper'

import { StepDefinition } from '../steps'

export const getLangChainSteps = (ctx: OnboardingComponentsContext): StepDefinition[] => {
    const { CodeBlock, Markdown, dedent, snippets } = ctx

    const NotableGenerationProperties = snippets?.NotableGenerationProperties

    return [
        {
            title: 'Install dependencies',
            badge: 'required',
            content: (
                <>
                    <Markdown>
                        Install the OpenTelemetry SDK, the LangChain instrumentation, and LangChain with OpenAI.
                    </Markdown>

                    <CodeBlock
                        blocks={[
                            {
                                language: 'bash',
                                file: 'Python',
                                code: dedent`
                                    pip install langchain langchain-openai opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-langchain
                                `,
                            },
                            {
                                language: 'bash',
                                file: 'Node',
                                code: dedent`
                                    npm install langchain @langchain/core @langchain/openai @posthog/ai @opentelemetry/sdk-node @opentelemetry/resources @traceloop/instrumentation-langchain
                                `,
                            },
                        ]}
                    />
                </>
            ),
        },
        {
            title: 'Set up OpenTelemetry tracing',
            badge: 'required',
            content: (
                <>
                    <Markdown>
                        Configure OpenTelemetry to auto-instrument LangChain calls and export traces to PostHog. PostHog
                        converts `gen_ai.*` spans into `$ai_generation` events automatically.
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
                                    from opentelemetry.instrumentation.langchain import LangchainInstrumentor

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

                                    LangchainInstrumentor().instrument()
                                `,
                            },
                            {
                                language: 'typescript',
                                file: 'Node',
                                code: dedent`
                                    import { NodeSDK, tracing } from '@opentelemetry/sdk-node'
                                    import { resourceFromAttributes } from '@opentelemetry/resources'
                                    import { PostHogTraceExporter } from '@posthog/ai/otel'
                                    import { LangChainInstrumentation } from '@traceloop/instrumentation-langchain'

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
                                      instrumentations: [new LangChainInstrumentation()],
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
            title: 'Call LangChain',
            badge: 'required',
            content: (
                <>
                    <Markdown>
                        Use LangChain as normal. The OpenTelemetry instrumentation automatically captures
                        `$ai_generation` events for each LLM call — no callback handlers needed.
                    </Markdown>

                    <CodeBlock
                        blocks={[
                            {
                                language: 'python',
                                file: 'Python',
                                code: dedent`
                                    from langchain_openai import ChatOpenAI
                                    from langchain_core.prompts import ChatPromptTemplate

                                    prompt = ChatPromptTemplate.from_messages([
                                        ("system", "You are a helpful assistant."),
                                        ("user", "{input}")
                                    ])

                                    model = ChatOpenAI(openai_api_key="your_openai_api_key")
                                    chain = prompt | model

                                    response = chain.invoke({"input": "Tell me a joke about programming"})

                                    print(response.content)
                                `,
                            },
                            {
                                language: 'typescript',
                                file: 'Node',
                                code: dedent`
                                    import { ChatOpenAI } from '@langchain/openai'
                                    import { ChatPromptTemplate } from '@langchain/core/prompts'

                                    const prompt = ChatPromptTemplate.fromMessages([
                                      ["system", "You are a helpful assistant."],
                                      ["user", "{input}"]
                                    ])

                                    const model = new ChatOpenAI({ apiKey: "your_openai_api_key" })
                                    const chain = prompt.pipe(model)

                                    const response = await chain.invoke({ input: "Tell me a joke about programming" })

                                    console.log(response.content)
                                `,
                            },
                        ]}
                    />

                    <Markdown>
                        PostHog automatically captures an `$ai_generation` event along with these properties:
                    </Markdown>

                    {NotableGenerationProperties && <NotableGenerationProperties />}

                    <Markdown>
                        It also automatically creates a trace hierarchy based on how LangChain components are nested.
                    </Markdown>
                </>
            ),
        },
    ]
}

export const LangChainInstallation = createInstallation(getLangChainSteps)
