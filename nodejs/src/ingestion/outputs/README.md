# Ingestion Outputs

Ingestion pipelines need to produce messages to Kafka — events, heatmaps, ingestion warnings, etc. Each of these destinations is an **output**. An output has a topic and a producer, both configurable at deploy time without code changes.

## Why

Previously, pipelines received raw `KafkaProducerWrapper` instances and hardcoded topic names. This made it impossible to route outputs to different Kafka clusters (e.g. events to MSK, heatmaps to WarpStream) without code changes. It also meant the producer was accessible everywhere, with no control over what gets produced where.

## What this module provides

**A named output abstraction.** Pipeline steps produce messages to an output by name (e.g. `'events'`). The output resolves to a topic and producer at startup. Steps never see the producer directly.

**Configurable producer routing.** Each output has a default producer, overridable via the config object (backed by env vars). Producers are defined with their own config key → rdkafka config mapping, validated with zod at startup.

**Configurable topics.** Each output has a default topic, also overridable via the config object.

**Compile-time config validation.** Both the producer registry builder and the outputs builder enforce at compile time that the server config contains all required keys. Missing keys are caught by the type checker, not at runtime.

**Health checks.** `IngestionOutputs` can verify broker connectivity and topic existence at startup, and provide ongoing health status for Kubernetes readiness probes.

## Concepts

A **producer** is a Kafka connection configured via the server config object. Each producer has a name (e.g. `'DEFAULT'`) and a mapping from config key names to rdkafka config keys. `KafkaProducerRegistryBuilder` creates all producers at startup, returning a typed `KafkaProducerRegistry<P>` where `P` is the union of registered producer names.

An **output** is a named destination (e.g. `'events'`, `'heatmaps'`). Each output points to a producer and a topic, both resolved from the config object. `IngestionOutputsBuilder` registers outputs with their config key pairs, then `build(registry, config)` resolves them — verifying at compile time that all config keys exist and producer values match the registry's type.

`IngestionOutputs` is the interface pipeline steps use to produce messages. It maps each output name to its resolved producer and topic, exposing `produce()` and `queueMessages()` methods that route messages to the right Kafka cluster and topic without the caller needing to know the details.

## Conventions

Pipeline steps receive `IngestionOutputs<O>` as a dependency and produce messages through it using `outputs.produce(output, message)` or `outputs.queueMessages(output, messages)`. Steps should never access Kafka producers directly.

Each pipeline defines its output and producer config in its own directory (e.g. `analytics/config/`). Shared output constants that appear in multiple pipelines go in `common/outputs.ts`. The server builds the outputs at startup and passes them down.

## How to extend

To add a new output:

1. Add the output name constant to the appropriate `outputs.ts` file (`common/` if shared, or the pipeline's own)
2. Add topic and producer config keys to the pipeline's config type (e.g. `IngestionOutputsConfig`)
3. Add defaults in the `getDefault*Config()` function
4. Add a `.register()` call in the pipeline's `register*Outputs()` function

To add a new producer:

1. Add the name constant and config map to the pipeline's `producers.ts`
2. Add the config keys to `KafkaProducerEnvConfig` with defaults
3. Add a `.register()` call on the `KafkaProducerRegistryBuilder` in the server

## File layout

```text
ingestion/outputs/              — generic infrastructure (pipeline-agnostic)
ingestion/common/outputs.ts     — shared output constants (e.g. EVENTS_OUTPUT)
ingestion/common/producers.ts   — shared producer constants and config maps
ingestion/analytics/outputs.ts  — analytics-specific output constants
ingestion/analytics/config/     — analytics pipeline config (output types, defaults, registration)
```
