import { OnboardingComponentsContext, createInstallation } from 'scenes/onboarding/OnboardingDocsContentWrapper'

import { StepDefinition } from '../steps'

export const getLlamaIndexSteps = (ctx: OnboardingComponentsContext): StepDefinition[] => {
    const { CodeBlock, Markdown, dedent, snippets } = ctx

    const NotableGenerationProperties = snippets?.NotableGenerationProperties

    return [
        {
            title: 'Install dependencies',
            badge: 'required',
            content: (
                <>
                    <Markdown>
                        Install LlamaIndex, OpenAI, and the OpenTelemetry SDK with the LlamaIndex instrumentation.
                    </Markdown>

                    <CodeBlock
                        language="bash"
                        code={dedent`
                            pip install llama-index llama-index-llms-openai opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-llamaindex
                        `}
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
                        Configure OpenTelemetry to auto-instrument LlamaIndex calls and export traces to PostHog.
                        PostHog converts `gen_ai.*` spans into `$ai_generation` events automatically.
                    </Markdown>

                    <CodeBlock
                        language="python"
                        code={dedent`
                            from opentelemetry import trace
                            from opentelemetry.sdk.trace import TracerProvider
                            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
                            from opentelemetry.sdk.resources import Resource, SERVICE_NAME
                            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                            from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor

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

                            LlamaIndexInstrumentor().instrument()
                        `}
                    />
                </>
            ),
        },
        {
            title: 'Query with LlamaIndex',
            badge: 'required',
            content: (
                <>
                    <Markdown>
                        Use LlamaIndex as normal. The OpenTelemetry instrumentation automatically captures
                        `$ai_generation` events for each LLM call.
                    </Markdown>

                    <CodeBlock
                        language="python"
                        code={dedent`
                            from llama_index.llms.openai import OpenAI
                            from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

                            llm = OpenAI(model="gpt-4o-mini", api_key="your_openai_api_key")

                            # Load your documents
                            documents = SimpleDirectoryReader("data").load_data()

                            # Create an index
                            index = VectorStoreIndex.from_documents(documents, llm=llm)

                            # Query the index
                            query_engine = index.as_query_engine(llm=llm)
                            response = query_engine.query("What is this document about?")

                            print(response)
                        `}
                    />

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

export const LlamaIndexInstallation = createInstallation(getLlamaIndexSteps)
