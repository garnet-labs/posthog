/**
 * jscodeshift codemod: Convert TypeScript parameter properties to explicit
 * field declarations + constructor assignments.
 *
 * Before:
 *   class Foo {
 *     constructor(private x: number, public y: string, name: string) {}
 *   }
 *
 * After:
 *   class Foo {
 *     private x: number
 *     public y: string
 *     constructor(x: number, y: string, name: string) {
 *       this.x = x
 *       this.y = y
 *     }
 *   }
 *
 * Usage:
 *   npx jscodeshift --parser tsx -t codemods/erasable-syntax/parameter-properties.js \
 *     'nodejs/src/**\/*.{ts,tsx}' 'frontend/src/**\/*.{ts,tsx}' 'services/**\/*.{ts,tsx}'
 */

module.exports = function transform(file, api) {
    const j = api.jscodeshift
    const root = j(file.source)
    let hasChanges = false

    root.find(j.ClassBody).forEach((classBodyPath) => {
        // Find constructor method
        const constructorPath = classBodyPath
            .get('body')
            .filter(
                (memberPath) =>
                    memberPath.node.type === 'ClassMethod' &&
                    memberPath.node.kind === 'constructor'
            )

        if (constructorPath.length === 0) {
            return
        }

        const ctorNode = constructorPath[0].node
        const params = ctorNode.params

        // Find parameter properties (params with accessibility or readonly modifier)
        const paramProperties = []
        const newParams = []

        for (const param of params) {
            const isParamProp =
                param.type === 'TSParameterProperty' ||
                param.accessibility ||
                param.readonly

            if (isParamProp) {
                // TSParameterProperty wraps the actual parameter
                const innerParam = param.parameter || param
                const accessibility = param.accessibility || null
                const isReadonly = param.readonly || false

                paramProperties.push({
                    innerParam,
                    accessibility,
                    isReadonly,
                    name: innerParam.type === 'AssignmentPattern'
                        ? innerParam.left.name
                        : innerParam.name,
                    typeAnnotation: innerParam.type === 'AssignmentPattern'
                        ? innerParam.left.typeAnnotation
                        : innerParam.typeAnnotation,
                    defaultValue: innerParam.type === 'AssignmentPattern'
                        ? innerParam.right
                        : null,
                })

                // Strip the parameter property to a plain parameter
                if (innerParam.type === 'AssignmentPattern') {
                    const plainParam = j.assignmentPattern(
                        j.identifier(innerParam.left.name),
                        innerParam.right
                    )
                    if (innerParam.left.typeAnnotation) {
                        plainParam.left.typeAnnotation = innerParam.left.typeAnnotation
                    }
                    newParams.push(plainParam)
                } else {
                    const plainParam = j.identifier(innerParam.name)
                    if (innerParam.typeAnnotation) {
                        plainParam.typeAnnotation = innerParam.typeAnnotation
                    }
                    newParams.push(plainParam)
                }
            } else {
                newParams.push(param)
            }
        }

        if (paramProperties.length === 0) {
            return
        }

        // Create class property declarations
        const classProperties = paramProperties.map(({ name, accessibility, isReadonly, typeAnnotation }) => {
            const prop = j.classProperty(j.identifier(name), null)
            if (accessibility) {
                prop.accessibility = accessibility
            }
            if (isReadonly) {
                // Use definite assignment since we assign in constructor
                prop.readonly = true
            }
            if (typeAnnotation) {
                prop.typeAnnotation = typeAnnotation
            }
            return prop
        })

        // Create assignment statements: this.x = x
        const assignments = paramProperties.map(({ name }) =>
            j.expressionStatement(
                j.assignmentExpression(
                    '=',
                    j.memberExpression(j.thisExpression(), j.identifier(name)),
                    j.identifier(name)
                )
            )
        )

        // Update constructor params
        ctorNode.params = newParams

        // Prepend assignments to constructor body
        ctorNode.body.body = [...assignments, ...ctorNode.body.body]

        // Insert class properties before the constructor
        const ctorIndex = classBodyPath.node.body.indexOf(ctorNode)
        classBodyPath.node.body.splice(ctorIndex, 0, ...classProperties)

        hasChanges = true
    })

    return hasChanges ? root.toSource({ quote: 'single' }) : undefined
}
