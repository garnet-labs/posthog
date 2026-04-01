/**
 * Zod helpers for parsing config from environment variables.
 *
 * Each helper wraps Zod's chaining into a single-call factory that handles
 * env-var coercion (string → number, boolean, enum). Returns a real Zod type
 * so `z.infer` gives the exact TypeScript type.
 */
import { ZodRawShape, z } from 'zod'

export type Infer<T extends z.ZodType> = z.infer<T>

/** String field with a default. */
export const str = (defaultValue: string, description: string) => z.string().default(defaultValue).describe(description)

/** Number field, coerced from string env var. */
export const num = (defaultValue: number, description: string) =>
    z.coerce.number().default(defaultValue).describe(description)

/** Boolean field — parses 'true'/'false' strings, falls back to default when unset. */
export const bool = (defaultValue: boolean, description: string) =>
    z
        .enum(['true', 'false', ''])
        .default('')
        .transform((v) => (v === '' ? defaultValue : v === 'true'))
        .describe(description)

/** Enum field with a default value. */
export const oneOf = <const T extends string>(
    values: readonly [T, ...T[]],
    defaultValue: NoInfer<T>,
    description: string
) => z.enum(values).default(defaultValue).describe(description)

/**
 * Define a config schema that parses from environment variables.
 * Wrapper around `z.object` — use with `str`, `num`, `bool`, `oneOf`, `nullableOneOf` helpers.
 *
 * @example
 * ```ts
 * const schema = env({
 *     PORT: num(8080, 'HTTP server port'),
 *     DEBUG: bool(false, 'Enable debug logging'),
 * })
 * type Config = z.infer<typeof schema>
 * const config = schema.parse(process.env)
 * ```
 */
export const env = <T extends ZodRawShape>(shape: T) => z.object(shape)

/** Nullable enum — empty env var becomes null, non-empty must be one of the values. */
export const nullableOneOf = <const T extends string>(values: readonly [T, ...T[]], description: string) => {
    const enumSchema = z.enum(values)
    return z
        .string()
        .default('')
        .transform((v) => (v === '' ? null : enumSchema.parse(v)))
        .describe(description)
}
