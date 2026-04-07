/**
 * jscodeshift codemod: Convert TypeScript enums to `as const` objects + type aliases,
 * and update type-position references from `Foo.Member` to `typeof Foo.Member`.
 *
 * Usage:
 *   # Generate the list of all enum names in the repo
 *   npx jscodeshift --parser tsx -t codemods/erasable-syntax/enum-to-const-object.js \
 *     --dry --enumNamesOut=codemods/erasable-syntax/enum-names.json \
 *     'frontend/src/**\/*.{ts,tsx}' 'products/**\/*.{ts,tsx}' 'common/**\/*.{ts,tsx}' \
 *     'nodejs/src/**\/*.{ts,tsx}' 'services/**\/*.{ts,tsx}'
 *
 *   # Run the actual transform (reads enum-names.json for cross-file type ref fixups)
 *   npx jscodeshift --parser tsx -t codemods/erasable-syntax/enum-to-const-object.js \
 *     --enumNames=codemods/erasable-syntax/enum-names.json \
 *     'frontend/src/**\/*.{ts,tsx}' 'products/**\/*.{ts,tsx}' 'common/**\/*.{ts,tsx}' \
 *     'nodejs/src/**\/*.{ts,tsx}' 'services/**\/*.{ts,tsx}'
 */

const fs = require('fs')

// Global set to collect enum names across files (for --dry --enumNamesOut mode)
const collectedEnumNames = new Set()

module.exports = function transform(file, api, options) {
    const j = api.jscodeshift
    const root = j(file.source)
    let hasChanges = false

    // --- Collect enum names defined in this file ---
    const localEnumNames = new Set()
    root.find(j.TSEnumDeclaration).forEach((path) => {
        localEnumNames.add(path.node.id.name)
    })

    // If --enumNamesOut is set, we're just collecting names
    if (options.enumNamesOut) {
        localEnumNames.forEach((name) => collectedEnumNames.add(name))
        return undefined
    }

    // --- Load known enum names (local + cross-file) ---
    const allEnumNames = new Set(localEnumNames)
    if (options.enumNames) {
        try {
            const names = JSON.parse(fs.readFileSync(options.enumNames, 'utf8'))
            names.forEach((name) => allEnumNames.add(name))
        } catch {
            // If file doesn't exist, just use local names
        }
    }

    // --- Helper: compute auto-increment values for numeric enum members ---
    function computeMembers(members) {
        let currentValue = 0
        let isNumericAutoIncrement = true

        return members.map((member) => {
            if (member.initializer) {
                if (member.initializer.type === 'NumericLiteral') {
                    currentValue = member.initializer.value + 1
                } else {
                    // String literal or expression — no auto-increment after this
                    isNumericAutoIncrement = false
                }
                return { id: member.id, value: member.initializer, comments: member.leadingComments }
            }

            if (!isNumericAutoIncrement) {
                // This would be a TS error in the original code, but handle gracefully
                return { id: member.id, value: j.numericLiteral(0), comments: member.leadingComments }
            }

            const value = j.numericLiteral(currentValue)
            currentValue++
            return { id: member.id, value, comments: member.leadingComments }
        })
    }

    // --- Convert enum declarations ---
    root.find(j.TSEnumDeclaration).forEach((path) => {
        const enumNode = path.node
        const enumName = enumNode.id.name

        // Skip `declare enum` (ambient only, no runtime)
        if (enumNode.declare) {
            return
        }

        const computed = computeMembers(enumNode.members)

        // Build object properties
        const properties = computed.map(({ id, value, comments }) => {
            const key = id.type === 'Identifier' ? j.identifier(id.name) : j.stringLiteral(id.value)
            const prop = j.objectProperty(key, value)
            if (comments) {
                prop.comments = comments.map((c) => ({ ...c, leading: true }))
            }
            return prop
        })

        // { A: 'a', B: 'b' } as const
        const objectExpr = j.objectExpression(properties)
        const asConst = j.tsAsExpression(objectExpr, j.tsTypeReference(j.identifier('const')))

        // const Foo = { ... } as const
        const constDecl = j.variableDeclaration('const', [j.variableDeclarator(j.identifier(enumName), asConst)])

        // type Foo = (typeof Foo)[keyof typeof Foo]
        const typeofRef1 = j.tsTypeQuery(j.identifier(enumName))
        const keyofTypeof = {
            type: 'TSTypeOperator',
            operator: 'keyof',
            typeAnnotation: j.tsTypeQuery(j.identifier(enumName)),
        }
        const indexedAccess = j.tsIndexedAccessType(typeofRef1, keyofTypeof)
        const typeAlias = j.tsTypeAliasDeclaration(j.identifier(enumName), indexedAccess)

        // Handle export
        const parent = path.parent.node
        if (parent.type === 'ExportNamedDeclaration') {
            const exportConst = j.exportNamedDeclaration(constDecl)
            const exportType = j.exportNamedDeclaration(typeAlias)

            // Preserve leading comments from the original export
            if (parent.leadingComments) {
                exportConst.comments = parent.leadingComments.map((c) => ({ ...c, leading: true }))
            } else if (enumNode.leadingComments) {
                exportConst.comments = enumNode.leadingComments.map((c) => ({ ...c, leading: true }))
            }

            j(path.parent).replaceWith([exportConst, exportType])
        } else {
            // Preserve leading comments
            if (enumNode.leadingComments) {
                constDecl.comments = enumNode.leadingComments.map((c) => ({ ...c, leading: true }))
            }
            j(path).replaceWith([constDecl, typeAlias])
        }

        hasChanges = true
    })

    // --- Convert type-position references: Foo.Member → typeof Foo.Member ---
    root.find(j.TSTypeReference).forEach((path) => {
        const typeName = path.node.typeName
        if (!typeName || typeName.type !== 'TSQualifiedName') {
            return
        }

        const left = typeName.left
        if (left.type !== 'Identifier' || !allEnumNames.has(left.name)) {
            return
        }

        // Foo.Member in type position → typeof Foo.Member
        const qualifiedName = j.tsQualifiedName(j.identifier(left.name), j.identifier(typeName.right.name))
        const typeQuery = j.tsTypeQuery(qualifiedName)

        j(path).replaceWith(typeQuery)
        hasChanges = true
    })

    return hasChanges ? root.toSource({ quote: 'single' }) : undefined
}

// Hook into jscodeshift's post-processing to write collected enum names
module.exports.postProcess = function (_, options) {
    if (options.enumNamesOut && collectedEnumNames.size > 0) {
        fs.writeFileSync(options.enumNamesOut, JSON.stringify([...collectedEnumNames].sort(), null, 2))
        console.log(`Wrote ${collectedEnumNames.size} enum names to ${options.enumNamesOut}`)
    }
}
